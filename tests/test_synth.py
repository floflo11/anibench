"""Tests for the synthetic layered-character generator (src/synth)."""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from synth.draw import Layer  # noqa: E402
from synth.scene import MOTIONS, Scene, PartInfo, build_scene  # noqa: E402
from synth.factors import compute_factors  # noqa: E402
from synth.make_tasks import write_task  # noqa: E402

CHAIN = {"wave": 3, "wiggle_fingers": 4, "nod": 1, "tip_hat": 2, "swing_earring": 2,
         "wag_tail": 1, "raise_arm": 1, "bend_elbow": 2}


@pytest.fixture(scope="module")
def scenes():
    return {m: build_scene(seed=100 + i, motion=m) for i, m in enumerate(MOTIONS)}


def test_motions_cover_spec():
    assert set(MOTIONS) == set(CHAIN)


def test_visible_masks_disjoint_and_cover_foreground(scenes):
    for m, sc in scenes.items():
        vis = np.stack([sc.visible_mask(L.name) for L in sc.layers])
        assert vis.sum(0).max() <= 1, m  # every pixel belongs to at most one part
        fg_union = np.any([sc.full_mask(L.name) for L in sc.layers], axis=0)
        assert np.array_equal(vis.any(0), fg_union), m


def test_composite_equals_union_of_layers(scenes):
    for m, sc in scenes.items():
        comp = sc.composite()
        assert comp.shape == (sc.height, sc.width, 3)
        union = np.any([sc.full_mask(L.name) for L in sc.layers], axis=0)
        assert (comp[~union] == 255).all(), m  # outside every layer: pure white background
        # where the top-most covering layer is opaque, the composite shows exactly that layer
        top = np.full((sc.height, sc.width), -1)
        for i, L in enumerate(sc.layers):
            top[sc.full_mask(L.name)] = i
        checked = 0
        for i, L in enumerate(sc.layers):
            a = sc.alpha(L.name)
            sel = (top == i) & (a == 255)
            if sel.any():
                assert np.array_equal(comp[sel], sc.rgb(L.name)[sel]), (m, L.name)
                checked += sel.sum()
        assert checked > 0.8 * union.sum()
        # and the image is the over-composite of the layers, in order, on white
        canvas = Image.new("RGBA", (sc.width, sc.height), (255, 255, 255, 255))
        for L in sc.layers:
            canvas.alpha_composite(Image.fromarray(L.rgba), dest=(L.x0, L.y0))
        assert np.array_equal(np.array(canvas.convert("RGB")), comp)


def test_pivots_on_joint(scenes):
    for m, sc in scenes.items():
        for mv in sc.task["movers"]:
            px, py = mv["pivot"]
            full = np.any([sc.full_mask(p) for p in mv["parts"]], axis=0)
            assert ndimage.binary_dilation(full, iterations=2)[int(round(py)), int(round(px))], (m, "pivot off part")
            # near the part boundary: within the joint radius of a background/other pixel of the moving set
            dist = ndimage.distance_transform_edt(full)
            assert dist[int(round(py)), int(round(px))] <= mv["joint_r"] + 2, (m, "pivot deep inside part")
            root = sc.parts[mv["root"]]
            if root.parent is not None and m != "tip_hat":
                par = sc.full_mask(root.parent)
                assert ndimage.binary_dilation(par, iterations=2)[int(round(py)), int(round(px))], (m, "pivot not in parent")


def test_chain_length(scenes):
    for m, sc in scenes.items():
        f = compute_factors(sc)
        assert f["chain_length"] == CHAIN[m], m


def test_deterministic():
    a = build_scene(seed=7, motion="wave")
    b = build_scene(seed=7, motion="wave")
    c = build_scene(seed=8, motion="wave")
    assert np.array_equal(a.composite(), b.composite())
    assert compute_factors(a) == compute_factors(b)
    assert not np.array_equal(a.composite(), c.composite())


def _rect_layer(name, W, H, x0, y0, x1, y1, col):
    rgba = np.zeros((H, W, 4), np.uint8)
    rgba[y0:y1, x0:x1] = (*col, 255)
    return Layer(name=name, rgba=rgba, x0=0, y0=0)


def test_factors_hand_checked():
    W, H = 100, 60
    # back to front: parent (torso) -> target (hand) -> occluder in front -> a far part
    layers = [
        _rect_layer("torso", W, H, 0, 20, 10, 40, (10, 10, 200)),
        _rect_layer("hand", W, H, 10, 20, 30, 30, (200, 10, 10)),    # 20x10 = 200 px
        _rect_layer("cover", W, H, 25, 20, 35, 30, (10, 200, 10)),   # hides x 25..29 of the hand: 50 px
        _rect_layer("far", W, H, 50, 20, 60, 30, (100, 100, 100)),
    ]
    parts = {"torso": PartInfo("torso", None, None, 0),
             "hand": PartInfo("hand", "torso", (12, 25), 0),
             "cover": PartInfo("cover", "torso", None, 0),
             "far": PartInfo("far", "torso", None, 0)}
    sc = Scene(W, H, layers, parts, chars=[dict(style="chibi")],
               task=dict(motion="wave", char=0, targets=["hand"], attach=["torso"],
                         movers=[dict(parts=["hand"], root="hand", pivot=(12, 25), amp=20, phase="sym", joint_r=5)]),
               seed=0)
    f = compute_factors(sc)
    assert f["target_area_px"] == 150
    assert f["target_full_area_px"] == 200
    assert f["occlusion_pct"] == pytest.approx(25.0)
    assert f["chain_length"] == 1
    # the occluder touches the hand (gap 0); without it the nearest non-target part is "far" (x=50 vs hand x=29: gap 20)
    assert f["min_dist_px"] == 0
    sc.layers = [L for L in layers if L.name != "cover"]
    del sc.parts["cover"]
    sc._cache.clear()
    f = compute_factors(sc)
    assert f["occlusion_pct"] == 0
    assert f["min_dist_px"] == pytest.approx(20)


def test_write_task_format(tmp_path):
    spec = write_task("S999", seed=5, motion="wave", out_root=tmp_path)
    d = tmp_path / "S999"
    for f in ("spec.json", "prompt.md", "image.png", "allowed.png", "target.png"):
        assert (d / f).exists(), f
    ref = json.loads((ROOT / "tasks/T01/spec.json").read_text())
    on_disk = json.loads((d / "spec.json").read_text())
    assert set(ref) <= set(on_disk)
    assert on_disk == spec
    for k in ("target_area_px", "occlusion_pct", "chain_length", "min_dist_px", "style", "seed"):
        assert k in spec["factors"], k
    img = Image.open(d / "image.png")
    assert img.size == (spec["width"], spec["height"]) and img.mode == "RGB"
    tgt = np.array(Image.open(d / "target.png")) > 127
    alw = np.array(Image.open(d / "allowed.png")) > 127
    assert tgt.sum() == spec["factors"]["target_area_px"]
    assert (tgt & ~alw).sum() == 0
    assert "image.png" in (d / "prompt.md").read_text()


def test_tip_hat_has_skull(tmp_path):
    spec = write_task("S998", seed=9, motion="tip_hat", out_root=tmp_path)
    assert spec["kind"] == "rotate_hat" and spec["skull"] is True
    assert "G2" not in spec["graders"]
    assert (tmp_path / "S998/skull.png").exists()


def test_styles_differ():
    from synth.scene import STYLES
    assert len(STYLES) >= 3
    ims = [build_scene(seed=3, motion="wave", style=s, n_chars=1).composite() for s in STYLES]
    for i in range(len(ims)):
        for j in range(i + 1, len(ims)):
            assert np.abs(ims[i].astype(int) - ims[j].astype(int)).mean() > 5
