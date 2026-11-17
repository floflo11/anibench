"""Geometry of the broken copies used to validate the graders (no Chrome)."""
import numpy as np
from conftest import rect

from reference import VARIANTS, VARIANT_KINDS, far_end, place, seam_split, small_tip, variants_for


def arm():
    # an 11 px wide, 60 px long vertical limb; pivot on its axis, 6 px inside the top end
    m = rect(10, 70, 20, 31)
    return m, (25, 16)


def test_small_tip_is_20_to_60_px_at_far_end():
    m, piv = arm()
    fg = m.copy()
    piece = small_tip(m, fg, piv)
    assert piece is not None
    n = int((piece & fg).sum())
    assert 20 <= n <= 60
    ys, _ = np.nonzero(piece)
    assert ys.min() > 55  # at the end far from the pivot
    assert not (piece & ~m).any()


def test_small_tip_none_when_part_too_small():
    m = rect(10, 13, 10, 14)  # 12 px
    assert small_tip(m, m.copy(), (11, 10)) is None


def test_far_end_is_outer_part():
    m, piv = arm()
    tip = far_end(m, piv)
    assert tip.any() and not (tip & ~m).any()
    ys, _ = np.nonzero(tip)
    assert ys.min() >= 50 and tip.sum() < m.sum() / 2


def test_seam_split_partitions_at_pivot():
    m, piv = arm()
    stub, rest, axis = seam_split(m, piv)
    assert not (stub & rest).any() and ((stub | rest) == m).all()
    assert stub.sum() == 6 * 11  # rows 10-15 lie on the parent side of the pivot line
    assert axis[1] > 0.99  # pivot -> part points down the limb


def test_variant_list_and_applicability():
    for v in ("detach_small", "detach_tip", "gap_seam"):
        assert v in VARIANTS
    assert "gap_seam" in variants_for({"kind": "rotate"})
    assert "gap_seam" not in variants_for({"kind": "jump"})  # no joint to open a seam at
    assert set(variants_for({"kind": "body"})) <= set(VARIANTS)
    assert set(VARIANT_KINDS) <= set(VARIANTS)


def test_place_matches_page_motion():
    m = rect(20, 30, 20, 26)
    L = dict(kind="rotate", amp=25, px=23, py=30, off=[0.0, -6.0])
    assert (place(m, L, 0.0) == m).all()           # t = 0: untouched
    assert (place(m, L, 2.0) == m).all()           # t = 2: loops back
    up = np.zeros_like(m); up[14:24, 20:26] = True
    assert (place(m, L, 1.0) == up).all()          # t = 1: no rotation, full 6 px drift
    lift = dict(kind="lift", amp=10, px=23, py=30)
    assert place(m, lift, 1.0)[10:20, 20:26].all() and not place(m, lift, 1.0)[20:30].any()
    turned = place(m, dict(kind="rotate", amp=25, px=23, py=30), 0.5)
    assert abs(int(turned.sum()) - int(m.sum())) <= 6 and not (turned == m).all()
