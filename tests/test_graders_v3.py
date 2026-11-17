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
