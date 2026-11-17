"""Tests for src/study/make_clips.py: run discovery, stratified sampling, clip composition, anonymized manifest.

None of these need Chrome: frames are synthetic and passed in through `frames_fn`.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from study import make_clips as M  # noqa: E402
from study.common import MANIFEST_SCHEMA, KEY_SCHEMA  # noqa: E402

MODELS = ["alpha-model", "beta-model", "gamma-model"]


def write_run(root, model, task, try_, status, failed=(), stage="first", html=True, extra=None):
    d = root / model / task / str(try_)
    d.mkdir(parents=True, exist_ok=True)
    g = dict(stage=stage, task=task, model=model, try_=str(try_), tier=1, status=status)
    if status in ("PASS", "FAIL"):
        grades = {k: dict(ok=k not in failed, value=0.0) for k in ("G1", "G2", "G3", "G4", "G5", "G6")}
        grades["pass"] = not failed
        g["grades"] = grades
    g.update(extra or {})
    (d / f"grade_{stage}.json").write_text(json.dumps(g))
    if html:
        (d / f"index_{stage}.html").write_text("<html></html>")
    return d


def test_checks_of():
    g = {"grades": {"G1": {"ok": True}, "G2": {"ok": False}, "G5": {"ok": None}, "pass": False}}
    assert M.checks_of(g) == {"G1": True, "G2": False, "G5": None}
    assert M.checks_of({"status": "RUNTIME"}) is None


def test_discover_runs(tmp_path):
    write_run(tmp_path, "alpha-model", "T01", 1, "PASS")
    write_run(tmp_path, "alpha-model", "T02", 1, "FAIL", failed=("G1",))
    write_run(tmp_path, "alpha-model", "T03", 1, "NO_HTML", html=False)          # nothing to show
    write_run(tmp_path, "alpha-model", "T04", 1, "RUNTIME")                      # page does not run
    write_run(tmp_path, "beta-model", "T01", 1, "FAIL", failed=("G4",), html=False,
              extra=dict(source="valkyrie"))                                      # graded remotely, no HTML here
    d = write_run(tmp_path, "beta-model", "T02", 1, "RUNTIME")
    write_run(tmp_path, "beta-model", "T02", 1, "PASS", stage="repair")          # repair turn wins
    write_run(tmp_path, "gamma-model", "T22", 1, "HUMAN")                        # no graders
    runs = {r["run"]: r for r in M.discover_runs(tmp_path)}
    assert set(runs) == {"alpha-model/T01/1", "alpha-model/T02/1", "beta-model/T02/1"}
    assert runs["beta-model/T02/1"]["stage"] == "repair" and runs["beta-model/T02/1"]["passed"]
    assert runs["alpha-model/T02/1"]["checks"]["G1"] is False
    assert runs["alpha-model/T01/1"]["setting"] == "chat"
    assert runs["alpha-model/T01/1"]["html"] == str(tmp_path / "alpha-model/T01/1/index_first.html")
    assert d.exists()
    with_human = {r["run"] for r in M.discover_runs(tmp_path, include_ungraded=True)}
    assert "gamma-model/T22/1" in with_human


def cands(n_models=3, n_tasks=4, k=3, fail_share=None):
    out, i = [], 0
    for m in MODELS[:n_models]:
        for t in range(n_tasks):
            for j in range(k):
                failed = ["G1"] if (i % 3) else []
                if fail_share is not None:
                    failed = ["G4"] if i % 10 < fail_share * 10 else []
                checks = {c: c not in failed for c in ("G1", "G2", "G3", "G4", "G5", "G6")}
                out.append(dict(run=f"{m}/T{t:02d}/{j}", model=m, task=f"T{t:02d}", checks=checks,
                                passed=not failed))
                i += 1
    return out


def test_stratified_sample_balanced_and_deterministic():
    c = cands()
    s = M.stratified_sample(c, 12, seed=0)
    assert len(s) == 12 and len({r["run"] for r in s}) == 12
    assert set(Counter(r["model"] for r in s).values()) == {4}
    assert set(Counter(r["task"] for r in s).values()) == {3}
    assert [r["run"] for r in M.stratified_sample(c, 12, seed=0)] == [r["run"] for r in s]
    assert [r["run"] for r in M.stratified_sample(c, 12, seed=1)] != [r["run"] for r in s]
    assert len(M.stratified_sample(c, 999, seed=0)) == len(c)


def test_stratified_sample_oversamples_rare_outcomes():
    c = cands(k=10, fail_share=0.9)                # 90% of runs fail G4
    n_pass = sum(r["passed"] for r in c)
    s = M.stratified_sample(c, 2 * n_pass, seed=0)
    got = sum(r["passed"] for r in s)
    assert got >= n_pass - 1, (got, n_pass)        # close to half pass, far above the 10% base rate
    fails = Counter(r["checks"]["G4"] for r in s)
    assert abs(fails[True] - fails[False]) <= 2


def test_zoom_box_matches_zoom_gifs():
    import zoom_gifs
    allowed = np.array(Image.open(ROOT / "tasks/T01/allowed.png")) > 127
    assert M.zoom_box(allowed) == zoom_gifs.zbox("T01")


def synth_frames(w=1200, h=600, n=25, box=(200, 150, 260, 230)):
    base = np.full((h, w, 3), 255, np.uint8)
    base[100:400, 100:300] = (200, 60, 60)
    fr = np.repeat(base[None], n, axis=0).copy()
    for i in range(n):
        dx = int(20 * np.sin(2 * np.pi * i / (n - 1)))
        x0, y0, x1, y1 = box
        fr[i, y0:y1, x0 + dx:x1 + dx] = (30, 30, 200)
    return base, fr


def test_compose_panels():
    base, fr = synth_frames()
    box = (150, 100, 470, 280)
    comp = M.compose(fr, base, box, panel_w=600)
    assert len(comp) == len(fr) - 1                # frame 24 (t=2) repeats frame 0 when looping
    W, H = comp[0].size
    assert W % 2 == 0 and H % 2 == 0
    a = [np.asarray(c) for c in comp]
    left = [x[:, : W // 2 - 8] for x in a]          # original still and its zoom: static
    right = [x[:, W // 2 + 8:] for x in a]          # animation and its zoom: moving
    assert all(np.array_equal(left[0], l) for l in left)
    assert not np.array_equal(right[0], right[6])


def test_write_clip_formats(tmp_path):
    base, fr = synth_frames(w=320, h=160, box=(40, 40, 80, 80))
    comp = M.compose(fr, base, (0, 0, 320, 160), panel_w=200)
    p = M.write_clip(comp, tmp_path / "c", fmt="webp")
    assert p.suffix == ".webp"
    im = Image.open(p)
    assert im.n_frames == len(comp)
    if M.have_ffmpeg():
        p = M.write_clip(comp, tmp_path / "c", fmt="mp4")
        assert p.suffix == ".mp4" and p.stat().st_size > 1000


def test_build_study_is_anonymized(tmp_path):
    runs_dir = tmp_path / "runs"
    for m in MODELS:
        for t in ("T01", "T02", "T03"):
            write_run(runs_dir, m, t, 1, "FAIL" if t != "T01" else "PASS", failed=() if t == "T01" else ("G1",))
    runs = M.discover_runs(runs_dir)
    def frames_fn(item):
        return synth_frames(w=item["width"], h=item["height"])[1]
    out = tmp_path / "study"
    man, key = M.build_study(runs, out, n=4, seed=0, salt="test", frames_fn=frames_fn, fmt="webp", panel_w=200)
    manifest = json.loads((out / "manifest.json").read_text())
    keyf = json.loads((out / "key.json").read_text())
    assert manifest["schema"] == MANIFEST_SCHEMA and keyf["schema"] == KEY_SCHEMA
    clips = manifest["clips"]
    assert len(clips) == 4 + len(M.ATTENTION)
    ids = [c["clip_id"] for c in clips]
    assert len(set(ids)) == len(ids)
    text = (out / "manifest.json").read_text()
    names = [p.name for p in (out / "clips").iterdir()]
    for m in MODELS + ["alpha", "beta", "gamma", "frozen", "wrong_part", "attention", "validation", "variant"]:
        assert m not in text, m
    ids_re = "|".join(ids)
    assert all(re.fullmatch(rf"({ids_re})(_[a-z]+)?\.(mp4|webp|gif|png)", n) for n in names), names
    for c in clips:
        assert set(c) >= {"clip_id", "task", "instruction", "video", "still"}
        assert "model" not in c and "setting" not in c and "attention" not in c
        for k in ("video", "still", "sheet_full", "sheet_zoom"):
            assert (out / c[k]).exists(), c[k]
        info = keyf["clips"][c["clip_id"]]
        assert info["task"] == c["task"]
    att = [k for k, v in keyf["clips"].items() if v["attention"]]
    assert len(att) == len(M.ATTENTION) == 5
    assert all(keyf["clips"][k]["expected"]["pass"] in (True, False) for k in att)
    assert {v["model"] for v in keyf["clips"].values() if not v["attention"]} <= set(MODELS)
    assert all("checks" in v and "passed" in v for v in keyf["clips"].values())
    # same seed and salt -> same study
    man2, _ = M.build_study(runs, tmp_path / "study2", n=4, seed=0, salt="test", frames_fn=frames_fn, fmt="webp", panel_w=200)
    assert [c["clip_id"] for c in man2["clips"]] == ids
