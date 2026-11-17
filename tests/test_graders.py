"""Unit tests for the pixel graders on tiny synthetic tasks (run in seconds, no Chrome)."""
import numpy as np
from conftest import HAND, Scene, paint, rect, shifted, sway, write_task

from graders import G2B_MIN, candidate_checks, grade


def offsets(dxs, n_pieces, still=()):
    """Per-frame offsets: every piece sways by dx except the indices in `still`."""
    return [[(0, 0) if i in still else (0, dx) for i in range(n_pieces)] for dx in dxs]


# ---------------------------------------------------------------- G2b Connectivity

def test_rigid_part_passes(tmp_path, one_piece_hand):
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    res = grade(fr, d)
    assert res["G2b"]["ok"], res
    assert res["G2b"]["base"] == 1
    assert res["pass"] is True


def test_thumb_left_behind_fails(tmp_path, one_piece_hand):
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    assert sc.pieces[1].sum() >= 20  # the detached piece is at least 20 px
    fr = sc.frames(offsets(sway(), 2, still={1}))
    res = grade(fr, d)
    assert not res["G2b"]["ok"], res
    assert res["G2b"]["value"] == 2 and res["G2b"]["base"] == 1
    assert res["pass"] is False


def test_split_mid_animation_only(tmp_path, one_piece_hand):
    """Frames 0 and last are whole; only the middle frames split. Still a failure."""
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    offs = offsets(sway(), 2)
    offs[2] = [(0, 6), (-5, 6)]  # thumb lifted 5 px away from the palm in one frame
    res = grade(sc.frames(offs), d)
    assert not res["G2b"]["ok"], res
    assert res["G2b"]["frame"] == 2


def test_detached_thumb_touching_parent_is_caught_only_by_g2b(tmp_path, thumb_on_arm):
    """The headline failure: the thumb stays behind but still touches the forearm, so the
    whole moving region is one blob (G2 passes). G2b must still see the split."""
    sc = thumb_on_arm
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed, graders=("G2", "G2b"))
    fr = sc.frames(offsets(sway(), 2, still={1}))
    res = grade(fr, d)
    assert res["G2"]["ok"], res  # documents why G2 alone is not enough
    assert not res["G2b"]["ok"], res
    rigid = grade(sc.frames(offsets(sway(), 2)), d)
    assert rigid["G2b"]["ok"] and rigid["G2"]["ok"], rigid


def test_two_piece_part_that_stays_two_pieces_passes(tmp_path, two_piece_part):
    sc = two_piece_part
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    # the two earrings swing in opposite directions but each stays whole
    offs = [[(0, dx), (0, -dx)] for dx in sway(amp=4)]
    res = grade(sc.frames(offs), d)
    assert res["G2b"]["ok"], res
    assert res["G2b"]["base"] == 2


def test_two_piece_part_that_splits_further_fails(tmp_path):
    a_top, a_bot = rect(10, 14, 14, 20), rect(14, 18, 14, 20)  # 24 px each, one earring
    b = rect(10, 16, 40, 46)
    sc = Scene([a_top, a_bot, b])
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    offs = [[(0, dx), (0, 0), (0, dx)] for dx in sway(amp=8)]  # bottom of earring A stays
    res = grade(sc.frames(offs), d)
    assert res["G2b"]["base"] == 2
    assert not res["G2b"]["ok"] and res["G2b"]["value"] == 3, res


def test_tiny_fragment_below_min_size_is_ignored(tmp_path):
    palm = rect(26, 40, 28, 36)
    nub = rect(23, 26, 28, 31)  # 9 px, below the floor
    assert nub.sum() < G2B_MIN
    sc = Scene([palm, nub])
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    res = grade(sc.frames(offsets(sway(), 2, still={1})), d)
    assert res["G2b"]["ok"], res


def test_thin_seam_line_is_not_a_piece(tmp_path, one_piece_hand):
    """A 1-px line left along a polygon cut (a seam artifact) is not a piece of the part: a piece
    must have an interior, i.e. survive a 3x3 erosion."""
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    fr[3][8, 10:50] = (150, 150, 150)  # a 40 px grey line over the background
    assert grade(fr, d)["G2b"]["ok"]
    fr[3][8:13, 10:15] = HAND  # a 5x5 blob is a piece
    assert not grade(fr, d)["G2b"]["ok"]


def test_pieces_merging_is_not_a_split(tmp_path, two_piece_part):
    sc = two_piece_part
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    offs = [[(0, dx), (0, -dx)] for dx in [0, 4, 8, 10, 8, 4, 0]]  # they touch at dx=10
    res = grade(sc.frames(offs), d)
    assert res["G2b"]["ok"], res


def test_unchanged_neighbours_are_not_counted(tmp_path, one_piece_hand):
    """Non-target pixels that stay as in the original (the forearm, other children inside the
    allowed band) are not part pixels, even when they are separate blobs."""
    sc = one_piece_hand
    img = paint(sc.image, rect(8, 14, 50, 56), (0, 0, 200))  # a static blue blob in the region
    sc.image = img
    sc.erased = paint(img, sc.hand, (255, 255, 255))
    d = write_task(tmp_path, img, sc.hand, sc.allowed)
    res = grade(sc.frames(offsets(sway(), 2)), d)
    assert res["G2b"]["ok"] and res["G2b"]["base"] == 1, res


def test_new_stray_blob_outside_footprint_counts(tmp_path, one_piece_hand):
    """A piece of the part dragged somewhere new (changed pixels outside the original
    footprint) counts as a part piece."""
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    fr[3][50:56, 46:52] = HAND  # a 36 px chunk of hand colour appears on its own
    res = grade(fr, d)
    assert not res["G2b"]["ok"], res


def test_island_inside_unchanged_scenery_is_ignored(tmp_path, one_piece_hand):
    """When the part passes over a neighbour of nearly the same colour, most of it looks
    unchanged and only a textured stripe registers as changed: an island fully surrounded by
    unchanged non-target foreground. That is a recolouring of the scenery, not a piece of the
    part coming apart, so it does not count."""
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    fr[3][46:52, 29:34] = HAND  # 30 px inside the static forearm (rows 40-60, cols 26-38)
    res = grade(fr, d)
    assert res["G2b"]["ok"], res


def test_island_inside_light_scenery_is_ignored(tmp_path, one_piece_hand):
    """Same, over near-white lace: the lace is too light to be foreground, but it is still
    scenery (not blank background), so it encloses the island."""
    sc = one_piece_hand
    lace = rect(44, 60, 40, 56)
    img = paint(sc.image, lace, (235, 232, 228))
    sc.image, sc.erased = img, paint(img, sc.hand, (255, 255, 255))
    d = write_task(tmp_path, img, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    fr[3][48:54, 45:50] = HAND
    res = grade(fr, d)
    assert res["G2b"]["ok"], res


def test_island_partly_on_background_still_counts(tmp_path, one_piece_hand):
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    fr = sc.frames(offsets(sway(), 2))
    fr[3][46:52, 36:41] = HAND  # straddles the forearm's right edge: half its border is white
    res = grade(fr, d)
    assert not res["G2b"]["ok"], res


def test_skull_fill_is_not_counted(tmp_path):
    """Hat tasks: the reveal under the hat (skull.png) is repainted with hair colour; that fill
    stays behind when the hat lifts and must not count as a detached piece."""
    hat = rect(10, 30, 20, 44)
    skull = rect(24, 30, 24, 40)
    sc = Scene([hat])
    d = write_task(tmp_path, sc.image, hat, sc.allowed, skull=skull, kind="translate_up")
    base = paint(sc.erased, skull, (40, 30, 25))
    frames = []
    for dy in [0, 4, 8, 12, 8, 4, 0]:
        f = base.copy()
        f[shifted(hat, -dy, 0)] = HAND
        frames.append(f)
    res = grade(np.stack(frames), d)
    assert res["G2b"]["ok"], res


def test_g2b_folds_into_pass_and_has_own_key(tmp_path, one_piece_hand):
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed, graders=("G2", "G4"))
    fr = sc.frames(offsets(sway(), 2, still={1}))
    assert "G2b" not in grade(fr, d)  # only runs when listed
    res = grade(fr, d, checks=["G2", "G2b", "G4"])
    assert set(res) == {"G2", "G2b", "G4", "pass"}
    assert res["G4"]["ok"] and not res["G2b"]["ok"] and res["pass"] is False


def test_candidate_checks_adds_g2b():
    assert candidate_checks({"graders": ["G1", "G2", "G3"]}) == ["G1", "G2", "G2b", "G3"]
    assert candidate_checks({"graders": ["G1", "G3", "G4", "G6"]}) == ["G1", "G2b", "G3", "G4", "G6"]
    assert candidate_checks({"graders": ["G1"], "graders_all": ["G1", "G2", "G4"]}) == ["G1", "G2", "G2b", "G4"]
    assert candidate_checks({"graders": ["G1", "G2b"], "graders_all": ["G1", "G2b"]}) == ["G1", "G2b"]
    assert candidate_checks({"graders": []}) == []


# ---------------------------------------------------------------- existing checks still behave

def test_existing_checks_on_rigid_motion(tmp_path, one_piece_hand):
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed, graders=("G1", "G2", "G3", "G6"))
    res = grade(sc.frames(offsets(sway(), 2)), d)
    assert all(res[k]["ok"] for k in ("G1", "G2", "G3", "G6")), res


def test_frozen_frames_pass_g2b(tmp_path, one_piece_hand):
    """No motion at all is G4's problem, not a connectivity failure."""
    sc = one_piece_hand
    d = write_task(tmp_path, sc.image, sc.hand, sc.allowed)
    res = grade(np.stack([sc.image] * 5), d)
    assert res["G2b"]["ok"], res
