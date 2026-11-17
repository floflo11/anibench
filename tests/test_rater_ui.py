"""Headless test of tools/rater.html: load a study folder, rate every clip with the keyboard, export, resume.

Needs Playwright (python) and Chrome at /usr/bin/google-chrome; skipped otherwise.
"""
import csv
import io
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from study import make_clips as M  # noqa: E402
from study.common import DEFECT_CODES, RATING_SCHEMA  # noqa: E402

CHROME = "/usr/bin/google-chrome"
TOOL = ROOT / "tools/rater.html"
pw = pytest.importorskip("playwright.sync_api")
if not Path(CHROME).exists():
    pytest.skip("no Chrome at /usr/bin/google-chrome", allow_module_level=True)


def synth(w, h, n=25):
    base = np.full((h, w, 3), 255, np.uint8)
    base[h // 4: 3 * h // 4, w // 8: w // 4] = (200, 60, 60)
    fr = np.repeat(base[None], n, axis=0).copy()
    for i in range(n):
        dx = int(30 * np.sin(2 * np.pi * i / (n - 1)))
        fr[i, 150:230, 200 + dx: 260 + dx] = (30, 30, 200)
    return fr


@pytest.fixture(scope="module")
def study(tmp_path_factory):
    out = tmp_path_factory.mktemp("study")
    runs = []
    for i, t in enumerate(("T01", "T02")):
        spec = M.task_spec(t)
        runs.append(dict(run=f"m{i}/{t}/1", model=f"m{i}", task=t, try_="1", stage="first", setting="chat",
                         status="FAIL", checks={"G1": False}, passed=False, width=spec["width"],
                         height=spec["height"], instruction=spec["instruction"], attention=False))
    man, key = M.build_study(runs, out, n=None, seed=0, salt="ui", panel_w=240,
                             frames_fn=lambda it: synth(it["width"], it["height"]),
                             fmt="mp4" if M.have_ffmpeg() else "webp")
    return out / "rater", man


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        yield b
        b.close()


@pytest.fixture
def ctx(browser):
    c = browser.new_context(viewport={"width": 1400, "height": 950}, accept_downloads=True)
    yield c
    c.close()


def open_tool(ctx, query="?minwatch=0", init=None):
    pg = ctx.new_page()
    requests, errors = [], []
    pg.on("request", lambda r: requests.append(r.url))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    if init:
        pg.add_init_script(init)
    pg.goto(TOOL.as_uri() + query)
    pg.wait_for_function("window.rater !== undefined")
    pg._log = (requests, errors)
    return pg


def check_clean(pg):
    requests, errors = pg._log
    assert not errors, errors
    remote = [u for u in requests if not u.startswith(("file:", "data:", "blob:"))]
    assert not remote, f"rater page made network requests: {remote}"


def load(pg, folder, rater="r1"):
    pg.fill("#raterId", rater)
    pg.set_input_files("#pickDir", str(folder))
    pg.wait_for_selector("#rate:not([hidden])")
    wait_media(pg)


def wait_media(pg):
    pg.wait_for_function("window.rater.mediaReady()", timeout=10000)


def pos(pg):
    return pg.evaluate("window.rater.state.pos")


def answer(pg, i):
    """Clip i: even -> pass, confidence 3; odd -> fail with 'outside moved' + 'other' (text), confidence 2."""
    wait_media(pg)
    if i % 2 == 0:
        pg.keyboard.press("y")
        pg.keyboard.press("3")
    else:
        pg.keyboard.press("n")
        pg.keyboard.press("o")
        pg.keyboard.press("x")
        pg.click("#otherText")
        pg.keyboard.type(f"weird flicker {i}")
        pg.keyboard.press("Escape")
        pg.keyboard.press("2")
    pg.keyboard.press("Enter")


def download(pg, sel):
    with pg.expect_download() as d:
        pg.click(sel)
    return Path(d.value.path()).read_text(), d.value.suggested_filename


def test_full_session_and_export(ctx, study):
    folder, man = study
    pg = open_tool(ctx)
    assert pg.evaluate("window.rater.DEFECTS.map(d => d.code)") == DEFECT_CODES
    load(pg, folder)
    n = len(man["clips"])
    assert pg.inner_text("#progressText").startswith(f"0 / {n}")
    # the clip is shown and playing
    if man["clips"][0]["video"].endswith(".mp4"):
        t0 = pg.evaluate("document.querySelector('#media video').currentTime")
        pg.wait_for_timeout(600)
        assert pg.evaluate("document.querySelector('#media video').currentTime") != t0
        pg.keyboard.press(".")                                     # frame step pauses
        assert pg.evaluate("document.querySelector('#media video').paused")
        pg.keyboard.press(" ")
        assert not pg.evaluate("document.querySelector('#media video').paused")
    assert pg.inner_text("#instruction") in {c["instruction"] for c in man["clips"]}
    order = pg.evaluate("window.rater.state.order")
    assert sorted(order) == sorted(c["clip_id"] for c in man["clips"])
    for i in range(n):
        assert pos(pg) == i
        answer(pg, i)
    pg.wait_for_selector("#done:not([hidden])")
    assert pg.inner_text("#progressText").startswith(f"{n} / {n}")

    text, name = download(pg, "#exportJson")
    assert name.endswith(".json") and "r1" in name
    data = json.loads(text)
    assert data["schema"] == RATING_SCHEMA and data["rater_id"] == "r1" and data["study_id"] == man["study_id"]
    rs = {r["clip_id"]: r for r in data["ratings"]}
    assert set(rs) == set(order) and len(data["ratings"]) == n
    for i, cid in enumerate(order):
        r = rs[cid]
        assert r["position"] == i
        if i % 2 == 0:
            assert r["pass"] is True and r["defects"] == [] and r["confidence"] == 3
        else:
            assert r["pass"] is False and r["defects"] == ["outside_moved", "other"] and r["confidence"] == 2
            assert r["other_text"] == f"weird flicker {i}"
        assert r["answered_at"] >= r["first_shown_at"] and r["time_ms"] >= 0

    text, name = download(pg, "#exportCsv")
    assert name.endswith(".csv")
    rows = list(csv.DictReader(io.StringIO(text)))
    assert len(rows) == n
    assert {"rater_id", "study_id", "clip_id", "pass", "defects", "confidence", "other_text", "first_shown_at",
            "answered_at", "time_ms"} <= set(rows[0])
    assert all(f"d_{c}" in rows[0] for c in DEFECT_CODES)
    byid = {r["clip_id"]: r for r in rows}
    odd = byid[order[1]]
    assert odd["pass"] == "0" and odd["d_outside_moved"] == "1" and odd["d_size_shape"] == "0"
    assert odd["defects"] == "outside_moved;other" and odd["other_text"] == "weird flicker 1"
    check_clean(pg)


def test_validation_rules_and_min_watch(ctx, study):
    folder, _ = study
    pg = open_tool(ctx, "?minwatch=1500")
    load(pg, folder)
    pg.keyboard.press("y")
    pg.keyboard.press("o")                                         # defects are only for a "No"
    assert pg.evaluate("window.rater.current().defects") == []
    pg.keyboard.press("3")
    pg.keyboard.press("Enter")                                     # too early: must watch at least 1.5 s
    assert pos(pg) == 0 and "watch" in pg.inner_text("#msg").lower()
    pg.keyboard.press("n")
    pg.wait_for_timeout(1600)
    pg.keyboard.press("Enter")                                     # "No" without a defect
    assert pos(pg) == 0 and "defect" in pg.inner_text("#msg").lower()
    pg.keyboard.press("x")
    pg.keyboard.press("Enter")                                     # "Other" without text
    assert pos(pg) == 0 and "describe" in pg.inner_text("#msg").lower()
    pg.keyboard.press("x")
    pg.keyboard.press("t")
    pg.keyboard.press("Enter")
    assert pos(pg) == 1
    check_clean(pg)


def test_autosave_and_resume(ctx, study):
    folder, man = study
    pg = open_tool(ctx)
    load(pg, folder, rater="r2")
    answer(pg, 0)
    answer(pg, 1)
    assert pos(pg) == 2
    first = pg.evaluate("window.rater.state.order[0]")
    pg.reload()
    pg.wait_for_function("window.rater !== undefined")
    load(pg, folder, rater="r2")
    assert pos(pg) == 2 and pg.evaluate("Object.keys(window.rater.state.answers).length") == 2
    pg.keyboard.press("[")                                         # back to the previous clip, answer kept
    assert pos(pg) == 1
    assert pg.evaluate("window.rater.current().pass") is False
    pg.keyboard.press("[")
    assert pg.evaluate("window.rater.current().clip_id") == first
    # a different rater starts fresh, in a different order (seeded by rater id)
    pg.reload()
    pg.wait_for_function("window.rater !== undefined")
    load(pg, folder, rater="someone-else")
    assert pos(pg) == 0 and pg.evaluate("Object.keys(window.rater.state.answers).length") == 0
    check_clean(pg)


def test_works_without_localstorage(ctx, study):
    folder, _ = study
    init = "Object.defineProperty(window, 'localStorage', {get() { throw new Error('denied'); }});"
    pg = open_tool(ctx, init=init)
    load(pg, folder)
    assert pg.is_visible("#storageWarn")
    answer(pg, 0)
    assert pos(pg) == 1
    text, _ = download(pg, "#exportJson")
    assert len(json.loads(text)["ratings"]) == 1
    check_clean(pg)


def test_warns_about_key_file(ctx, study, tmp_path):
    folder, _ = study
    bad = tmp_path / "bundle"
    shutil.copytree(folder, bad)
    shutil.copy(folder.parent / "key.json", bad / "key.json")
    pg = open_tool(ctx)
    load(pg, bad)
    assert "key.json" in pg.inner_text("#loadWarn")
    assert pg.evaluate("window.rater.keyFileSeen") is True
