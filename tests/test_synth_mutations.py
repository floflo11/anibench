"""Broken copies of the synthetic reference (src/synth/mutations.py), checked in numpy (no Chrome)."""
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from synth import mutations as M
from synth.check_reference import simulate

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / "tasks_synth/sample/S001/spec.json").read_text())


def composite(base, layers, t):
    c = Image.fromarray(base).convert("RGBA")
    for im, L in layers:
        c.alpha_composite(Image.fromarray(M._place(im, L, t)))
    return np.array(c.convert("RGB"))


@pytest.fixture(scope="module")
def scene():
    return M.scene_for(SPEC)


def test_ref_plan_matches_the_reference_simulation(scene):
    base, layers, _ = M.plan(SPEC, "ref", scene)
    sim = simulate(scene)
    for i in (0, 6, 12, 18, 24):
        diff = np.abs(composite(base, layers, i * 2 / 24).astype(int) - sim[i]).max(-1) > 24
        assert diff.sum() <= 3, i  # pivots are rounded to 0.01 px on the page


def test_every_variant_is_listed_and_builds(tmp_path, scene):
    assert M.variants_for(SPEC) == ["ref", "whole", "missed_thumb", "hole", "frozen", "center_pivot", "no_loop",
                                    "wrong_part", "detach_small", "detach_tip", "gap_seam"]
    for v in ("ref", "missed_thumb", "wrong_part"):
        d = M.build_variant(SPEC, v, tmp_path / v)
        assert (d / "index.html").exists() and (d / "base.png").exists()
        cfg = json.loads((d / "index.html").read_text().split("const CFG = ")[1].split(";\n")[0])
        assert len(cfg["layers"]) == len(list(d.glob("layer*.png")))


def test_missed_thumb_leaves_a_static_piece_of_the_part(scene):
    base, layers, is_part = M.plan(SPEC, "missed_thumb", scene)
    static_part = [im for (im, L), p in zip(layers, is_part) if p and L["kind"] == "static"]
    assert static_part and sum(int((im[..., 3] > 0).sum()) for im in static_part) >= 20
    _, ref_layers, _ = M.plan(SPEC, "ref", scene)
    # same pixels overall: the piece was moved from the sprite into a static layer, nothing else changed
    a0 = sum(int((im[..., 3] > 0).sum()) for im, _ in ref_layers)
    a1 = sum(int((im[..., 3] > 0).sum()) for im, _ in layers)
    assert a0 == a1


def test_hole_page_hides_only_moving_layers():
    assert "L.kind !== 'static'" in M.PAGE


def test_frozen_and_whole_have_no_layers(scene):
    for v in ("frozen", "whole"):
        base, layers, _ = M.plan(SPEC, v, scene)
        assert layers == [] and np.array_equal(base, scene.composite())


def test_wrong_part_moves_a_non_target_part(scene):
    mv = M._decoy(scene)
    assert mv[0]["parts"][0] not in scene.task["targets"]


def test_oracle_split_on_detach_tip_and_ref():
    assert M.oracle_split(SPEC, "ref")["split"] is False
    o = M.oracle_split(SPEC, "detach_tip")
    assert o["worst"] >= o["base"]
