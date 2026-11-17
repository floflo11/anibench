"""Grader v3 rule changes, on tiny synthetic tasks (no Chrome).

G1: the allowed region grows by ceil(0.075 x the target's larger extent) px (room for +-15% squash/stretch).
G2: faint pieces (median contrast against white < 80) are not counted.
"""
import numpy as np
from conftest import write_task

from graders import G1_GROW, G2_MIN_CONTRAST, g1_region, grade

N = 96
WHITE = (255, 255, 255)
DARK = (60, 40, 30)
ARM = (150, 150, 150)


def box(y0, y1, x0, x1, n=N):
    m = np.zeros((n, n), bool)
    m[y0:y1, x0:x1] = True
    return m


def canvas(*layers, n=N):
    img = np.full((n, n, 3), 255, np.uint8)
    for m, c in layers:
        img[m] = c
    return img


# ---------------------------------------------------------------- G1: squash/stretch room

def test_g1_region_grows_by_share_of_target_extent():
    target = box(20, 60, 40, 50)          # 40 px tall, 10 wide
    allowed = box(18, 62, 38, 52)
    r = int(np.ceil(G1_GROW * 40))        # 3 px
    grown = g1_region(allowed, target)
    assert grown[18 - r, 45] and not grown[18 - r - 1, 45]
    assert grown[45, 52 + r - 1] and not grown[45, 52 + r]


def test_g1_stretch_within_grown_region_passes_but_far_change_fails(tmp_path):
    target = box(20, 60, 40, 50)
    allowed = box(20, 60, 40, 50)          # tight: no slack at all
    img = canvas((target, DARK))
    d = write_task(tmp_path, img, target, allowed, graders=("G1",))
    stretched = canvas((box(17, 60, 40, 50), DARK))   # 3 px longer at the top (7.5% of 40)
    res = grade(np.stack([img, stretched, img]), d)
    assert res["G1"]["ok"], res
    too_far = canvas((box(12, 60, 40, 50), DARK))     # 8 px longer: outside even the grown region
    res = grade(np.stack([img, too_far, img]), d)
    assert not res["G1"]["ok"], res


# ---------------------------------------------------------------- G2: faint pieces do not count

def _g2_task(tmp_path):
    part = box(30, 60, 40, 52)
    img = canvas((part, DARK))
    allowed = box(10, 80, 20, 80)
    return part, img, write_task(tmp_path, img, part, allowed, graders=("G2",))


def test_g2_faint_strip_left_behind_is_not_a_new_piece(tmp_path):
    part, img, d = _g2_task(tmp_path)
    halo = box(30, 60, 60, 63)                      # 90 px, light grey: contrast 55 < 80
    f = canvas((box(30, 60, 30, 42), DARK), (halo, (200, 200, 200)))
    assert 255 - 200 < G2_MIN_CONTRAST
    res = grade(np.stack([img, f, img]), d)
    assert res["G2"]["ok"], res


def test_g2_dark_piece_left_behind_still_counts(tmp_path):
    part, img, d = _g2_task(tmp_path)
    piece = box(30, 40, 60, 68)                     # 80 px, dark
    f = canvas((box(30, 60, 30, 42), DARK), (piece, DARK))
    res = grade(np.stack([img, f, img]), d)
    assert not res["G2"]["ok"], res
    assert res["G2"]["value"] == 2 and res["G2"]["base"] == 1


# ---------------------------------------------------------------- G2c rigid-motion residual

from conftest import RotScene, write_rot_task  # noqa: E402


def _tip(sc, r=7):
    """The hand's far end (a disc around its top-most pixel), the piece a 'missed thumb' leaves behind."""
    ys, xs = np.nonzero(sc.hand)
    i = np.argmin(ys)
    yy, xx = np.mgrid[:sc.N, :sc.N]
    return sc.hand & ((xx - xs[i]) ** 2 + (yy - ys[i]) ** 2 <= r * r)


def test_g2c_rigid_rotation_passes(tmp_path, rot_scene):
    d = write_rot_task(tmp_path, rot_scene, ("G2b", "G2c"))
    res = grade(rot_scene.swing(), d)
    assert res["G2c"]["ok"], res
    assert res["G2c"]["value"] == 0


def test_g2c_tip_left_behind_while_touching_fails(tmp_path, rot_scene):
    """The tip stays put while the hand swings 15 deg: the moving hand slides past it and still touches it,
    so the part never comes apart (G2b passes) but a piece of the original stays behind (G2c fails)."""
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G2b", "G2c"), amp=15)
    fr = sc.swing(amp=15, keep=_tip(sc, r=8))
    res = grade(fr, d)
    assert res["G2b"]["ok"], res
    assert not res["G2c"]["ok"], res
    assert res["G2c"]["value"] >= 20


def test_g2c_frozen_and_hidden_part_pass(tmp_path, rot_scene):
    """No motion is G4's problem and a vanished part is G3's: neither leaves a piece behind a moving part."""
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G2c",))
    assert grade(np.stack([sc.image] * 5), d)["G2c"]["ok"]
    hidden = np.stack([sc.image] + [sc.frame(0, hide=True)] * 3 + [sc.image])
    assert grade(hidden, d)["G2c"]["ok"]


def test_g2c_ghost_copy_fails(tmp_path, rot_scene):
    """The part is drawn twice: the original stays and a rotated copy swings over it (ghosting)."""
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G2c",))
    res = grade(sc.swing(amp=25, erase=False), d)
    assert not res["G2c"]["ok"], res


# ---------------------------------------------------------------- G5: joint displacement

def test_g5_textured_joint_correct_pivot_passes(tmp_path):
    """Hair-like strands at the joint: a correct rotation changes most joint pixels (the fraction test fails),
    but the joint itself does not move."""
    sc = RotScene(texture="strands")
    d = write_rot_task(tmp_path, sc, ("G5",))
    res = grade(sc.swing(amp=20), d)
    assert res["G5"]["frac"] > 0.30, res        # the v2 measure alone would fail it
    assert res["G5"]["ok"], res
    assert res["G5"]["disp"] < 2, res


def test_g5_center_pivot_fails(tmp_path, rot_scene):
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G5",))
    ys, xs = np.nonzero(sc.hand)
    res = grade(sc.swing(amp=20, pivot=(int(xs.mean()), int(ys.mean()))), d)
    assert not res["G5"]["ok"], res
    assert res["G5"]["disp"] > 5, res


# ---------------------------------------------------------------- G3: occlusion-aware area

def _occluded_scene():
    """The hand swings right, behind a static block (a sleeve, another character) drawn in front of it."""
    n = RotScene.N
    yy, xx = np.mgrid[:n, :n]
    block = (xx >= 70) & (xx < 110) & (yy >= 5) & (yy < 60)
    sc = RotScene()
    rgb = np.zeros((n, n, 3), np.uint8)
    rgb[...] = (40, 120, 60)
    sc.image[block] = rgb[block]
    sc.hand_full = sc.hand.copy()
    sc.hand = sc.hand & ~block          # the visible footprint is the target
    sc.allowed = sc.allowed | block
    return sc, (block, rgb)


def test_g3_part_swinging_behind_a_part_in_front_passes(tmp_path):
    sc, occ = _occluded_scene()
    d = write_rot_task(tmp_path, sc, ("G3",), amp=35)
    fr = sc.swing(amp=35, occluder=occ)
    # what v2 measured: the net foreground of the region drops as the hand slides behind the block
    fg0 = (255 - sc.image.astype(int)).max(-1) > 30
    net = min(((255 - f.astype(int)).max(-1) > 30).sum() - fg0.sum() for f in fr)
    assert -net / sc.hand.sum() > 0.5
    res = grade(fr, d)
    assert res["G3"]["ok"], res


def test_g3_part_that_vanishes_fails(tmp_path, rot_scene):
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G3",))
    fr = np.stack([sc.image] + [sc.frame(5, hide=True)] * 3 + [sc.image])
    res = grade(fr, d)
    assert not res["G3"]["ok"], res
    assert res["G3"]["loss"] > 0.9


def test_g3_part_drawn_twice_fails(tmp_path, rot_scene):
    sc = rot_scene
    d = write_rot_task(tmp_path, sc, ("G3",))
    two = sc.image.copy()
    yy, xx = np.mgrid[:sc.N, :sc.N]
    copy = np.zeros_like(sc.hand)
    copy[:, 30:] = sc.hand[:, :-30]      # a second hand 30 px to the right, the original stays
    two[copy] = sc.image[:, :-30][copy[:, 30:]]
    res = grade(np.stack([sc.image, two, sc.image]), d)
    assert not res["G3"]["ok"], res
    assert res["G3"]["gain"] > 0.5
