"""Tests for the alternate valid animators (src/alt_refs/).

- Registry: at least the four required styles, each with one or more variants.
- No leakage: a page builds from a task folder that holds only image.png (what a model gets), and the
  grader-side amplitude in the task definitions does not change the page.
- Contract (needs Chrome): every variant's page loads, exposes setTime and ANIM_READY, and moves.
- Fidelity (needs Chrome): frame 0 equals the original within the G6 tolerance on a few tasks, and the
  loop closes (t=0 and t=2 render the same frame).
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import alt_refs  # noqa: E402
from alt_refs import common  # noqa: E402

REQUIRED_STYLES = {"easing", "squash_stretch", "follow_through", "alt_impl"}
ALL = sorted(alt_refs.VARIANTS)
FIDELITY_TASKS = ["T01", "T13", "T17", "T19"]
OUT = ROOT / "out" / "test_alt_refs"


def test_registry_has_required_styles():
    styles = {alt_refs.VARIANTS[v]["style"] for v in ALL}
    assert REQUIRED_STYLES <= styles
    for s in REQUIRED_STYLES:
        assert sum(alt_refs.VARIANTS[v]["style"] == s for v in ALL) >= 1


def test_every_admitted_task_has_most_variants():
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    admitted = [s["id"] for s in idx if s["graders"]]
    assert len(admitted) == 21
    for tid in admitted:
        n = sum(alt_refs.applicable(tid, v) for v in ALL)
        assert n >= len(ALL) - 2, (tid, n)


@pytest.mark.parametrize("variant", ALL)
def test_builds_from_model_inputs_only(variant, tmp_path):
    """The page builds when the task folder holds only image.png (no spec, allowed, target or skull masks)."""
    tid = "T01" if alt_refs.applicable("T01", variant) else "T13"
    fake = tmp_path / "tasks" / tid
    fake.mkdir(parents=True)
    shutil.copy(ROOT / "tasks" / tid / "image.png", fake / "image.png")
    out = tmp_path / "page"
    alt_refs.build(tid, variant, out, task_dir=fake)
    html = (out / "index.html").read_text()
    assert "window.setTime" in html and "ANIM_READY" in html
    assert "./vendor/three.module.js" in html
    for bad in ("allowed.png", "target.png", "skull.png", "spec.json"):
        assert bad not in html


def test_grader_amplitude_is_not_used(tmp_path, monkeypatch):
    """Amplitudes are each style's own choice: changing the task definition's amp changes nothing."""
    a, b = tmp_path / "a", tmp_path / "b"
    v = "easing-sine_small"
    alt_refs.build("T01", v, a)
    real = common.task_defs()
    fake = {k: dict(d, amp=999) for k, d in real.items()}
    monkeypatch.setattr(common, "task_defs", lambda: fake)
    alt_refs.build("T01", v, b)
    assert (a / "index.html").read_text() == (b / "index.html").read_text()


# ---- browser tests -------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def renderer():
    import render
    if not Path(render.CHROME).exists():
        pytest.skip("Chrome not available")
    R = render.Renderer()
    yield R
    R.close()


def _render(renderer, tid, variant, n=3):
    import render
    d = OUT / variant / tid
    if d.exists():
        shutil.rmtree(d)
    alt_refs.build(tid, variant, d)
    render.prepare(d, ROOT / "tasks" / tid)
    old = render.N_FRAMES
    render.N_FRAMES = n  # t = 0, 1, 2 (or finer); the contract only needs a few frames
    try:
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        fr, err, logs = renderer.render(d, spec["width"], spec["height"])
    finally:
        render.N_FRAMES = old
    assert fr is not None, f"{variant} {tid}: {err} {logs[-3:]}"
    return fr


@pytest.mark.parametrize("variant", ALL)
def test_page_exposes_contract_and_moves(renderer, variant):
    tid = "T01" if alt_refs.applicable("T01", variant) else "T13"
    fr = _render(renderer, tid, variant, n=5)
    from graders import changed
    assert max(changed(f, fr[0]).sum() for f in fr[1:-1]) > 200, "nothing moved"


@pytest.mark.parametrize("variant", ALL)
@pytest.mark.parametrize("tid", FIDELITY_TASKS)
def test_frame0_matches_original_and_loops(renderer, variant, tid):
    if not alt_refs.applicable(tid, variant):
        pytest.skip("variant does not apply to this task")
    from graders import G6_LOOP, G6_ORIG, changed
    fr = _render(renderer, tid, variant, n=3)
    orig = np.array(Image.open(ROOT / "tasks" / tid / "image.png").convert("RGB"))
    assert changed(fr[0], orig).mean() <= G6_ORIG
    assert changed(fr[0], fr[-1]).mean() <= G6_LOOP
