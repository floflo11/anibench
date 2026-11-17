"""Headless test of tools/annotator.html: draw parts with real mouse/keyboard input, export, re-import.

Needs Playwright (python) and Chrome at /usr/bin/google-chrome; skipped otherwise.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402

CHROME = "/usr/bin/google-chrome"
TOOL = ROOT / "tools/annotator.html"
pw = pytest.importorskip("playwright.sync_api")
if not Path(CHROME).exists():
    pytest.skip("no Chrome at /usr/bin/google-chrome", allow_module_level=True)


@pytest.fixture(scope="module")
def browser():
    with pw.sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME, headless=True)
        yield b
        b.close()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1400, "height": 900}, accept_downloads=True)
    pg = ctx.new_page()
    requests, errors = [], []
    pg.on("request", lambda r: requests.append(r.url))
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(TOOL.as_uri())
    pg.wait_for_function("window.annotator !== undefined")
    yield pg
    assert not errors, errors
    remote = [u for u in requests if not u.startswith(("file:", "data:", "blob:"))]
    assert not remote, f"annotator made network requests: {remote}"
    ctx.close()


@pytest.fixture
def test_image(tmp_path):
    im = Image.new("RGB", (200, 150), "white")
    d = ImageDraw.Draw(im)
    d.rectangle([60, 40, 140, 140], fill=(200, 60, 60), outline=(0, 0, 0), width=2)    # body
    d.ellipse([135, 15, 175, 55], fill=(240, 190, 150), outline=(0, 0, 0), width=2)    # hand
    d.rectangle([70, 10, 130, 40], fill=(40, 40, 120))                                   # hat
    path = tmp_path / "test_img.png"
    im.save(path)
    return path


def click(pg, x, y, shift=False):
    cx, cy = pg.evaluate(f"annotator.toClient({x}, {y})")
    if shift:
        pg.keyboard.down("Shift")
    pg.mouse.click(cx, cy)
    if shift:
        pg.keyboard.up("Shift")


def new_part(pg, name):
    pg.focus("#cv")
    pg.keyboard.press("n")
    assert pg.evaluate("document.activeElement.id") == "p_name"
    pg.keyboard.press("Control+A")
    pg.keyboard.type(name)
    pg.keyboard.press("Enter")
    assert pg.evaluate("document.activeElement.id") == "cv"


def export(pg, tmp_path, name):
    with pg.expect_download() as dl:
        pg.keyboard.press("Control+s")
    out = tmp_path / name
    dl.value.save_as(out)
    return dl.value.suggested_filename, out


def close_to(a, b, tol=0.6):
    return len(a) == len(b) and all(abs(p[0] - q[0]) <= tol and abs(p[1] - q[1]) <= tol for p, q in zip(a, b))


def test_draw_export_and_reimport(page, test_image, tmp_path):
    pg = page
    pg.set_input_files("#fileImg", str(test_image))
    pg.wait_for_function("annotator.state.width === 200")
    assert pg.evaluate("annotator.state.height") == 150
    assert pg.input_value("#imageId") == "test_img"
    assert pg.input_value("#imagePath") == "images/test_img.png"
    # shortcuts are listed on screen
    keys = pg.inner_text("#keys")
    for k in ("Enter", "Backspace", "Esc", "Shift+click", "Ctrl+S"):
        assert k in keys

    # whole character
    new_part(pg, "C1_body")
    body = [[55, 35], [145, 35], [145, 145], [55, 145]]
    for x, y in body:
        click(pg, x, y)
    pg.keyboard.press("Enter")

    # hand: 4 clicks, Backspace drops the last, Enter closes; pivot with P + click
    new_part(pg, "C1_hand")
    hand = [[133, 12], [178, 12], [178, 58]]
    for x, y in hand + [[133, 58]]:
        click(pg, x, y)
    pg.keyboard.press("Backspace")
    pg.keyboard.press("Enter")
    pg.keyboard.press("p")
    click(pg, 140, 50)

    # hat: pivot with Shift+click, close by clicking the first point; then a keep (skull) mask
    new_part(pg, "C1_hat")
    click(pg, 100, 40, shift=True)
    hat = [[68, 8], [132, 8], [132, 42], [68, 42]]
    for x, y in hat:
        click(pg, x, y)
    click(pg, *hat[0])
    pg.keyboard.press("k")
    skull = [[80, 35], [120, 35], [100, 45]]
    for x, y in skull:
        click(pg, x, y)
    pg.keyboard.press("Enter")

    # select the hand (key 2), exclude the hat, check the default parent
    pg.keyboard.press("2")
    assert pg.input_value("#p_name") == "C1_hand"
    assert pg.input_value("#p_parent") == "C1_body"
    pg.check('#excl input[data-part="C1_hat"]')
    pg.select_option("#p_parent", "C1_body")
    pg.fill("#p_desc", "raised hand; pivot at the wrist")
    pg.press("#p_desc", "Enter")

    pg.fill("#m_style", "flat cartoon")
    pg.fill("#m_subject", "test figure")
    pg.fill("#m_source", "unit test")
    pg.fill("#m_license", "CC0")
    pg.press("#m_license", "Enter")

    fname, path = export(pg, tmp_path, "a.json")
    assert fname == "test_img.json"
    text = path.read_text()
    doc = json.loads(text)
    A.validate(doc)  # the Python validator accepts the export
    assert doc["image"] == {"path": "images/test_img.png", "width": 200, "height": 150}
    assert doc["metadata"]["license"] == "CC0" and doc["metadata"]["style"] == "flat cartoon"
    P = {p["name"]: p for p in doc["parts"]}
    assert list(P) == ["C1_body", "C1_hand", "C1_hat"]
    assert P["C1_body"]["parent"] is None and P["C1_body"]["pivot"] is None
    assert P["C1_body"]["outline_px"] == 0   # a *_body part is a whole character
    assert close_to(P["C1_body"]["polygons"][0], body)
    assert close_to(P["C1_hand"]["polygons"][0], hand)  # Backspace removed the 4th point
    assert close_to([P["C1_hand"]["pivot"]], [[140, 50]])
    assert P["C1_hand"]["parent"] == "C1_body"
    assert P["C1_hand"]["exclude"] == ["C1_hat"]
    assert P["C1_hand"]["description"] == "raised hand; pivot at the wrist"
    assert close_to(P["C1_hat"]["polygons"][0], hat) and len(P["C1_hat"]["polygons"]) == 1
    assert close_to([P["C1_hat"]["pivot"]], [[100, 40]])
    assert doc["masks"][0]["name"] == "C1_skull" and doc["masks"][0]["role"] == "keep"
    assert doc["masks"][0]["part"] == "C1_hat" and close_to(doc["masks"][0]["polygons"][0], skull)

    # the exported file produces sensible masks
    rgb = np.array(Image.open(test_image).convert("RGB"))
    fg = rgb.min(2) < 245
    ms = A.masks(doc, fg=fg)
    hat_zone = A.dilate(A.fill(P["C1_hat"]["polygons"], fg.shape), 4)
    assert ms["C1_hand"].sum() > 500 and not (ms["C1_hand"] & hat_zone).any()
    assert ms["C1_body"].sum() > 5000 and not (ms["C1_body"] & ~fg).any()

    # re-import into a fresh page and export again: identical file
    pg.reload()
    pg.wait_for_function("window.annotator !== undefined")
    pg.set_input_files("#fileImg", str(test_image))
    pg.wait_for_function("annotator.state.width === 200")
    pg.set_input_files("#fileJson", str(path))
    pg.wait_for_function("annotator.state.parts.length === 3")
    pg.focus("#cv")
    _, path2 = export(pg, tmp_path, "b.json")
    assert path2.read_text() == text


def test_errors_block_export(page, test_image):
    pg = page
    pg.set_input_files("#fileImg", str(test_image))
    pg.wait_for_function("annotator.state.width === 200")
    new_part(pg, "C1_hand")
    click(pg, 10, 10)
    click(pg, 30, 10)
    pg.keyboard.press("Enter")  # only 2 points: refused
    assert pg.evaluate("annotator.state.parts[0].polygons.length") == 0
    assert "at least 3" in pg.inner_text("#msg")
    pg.keyboard.press("Control+s")
    assert "cannot export" in pg.inner_text("#msg")
    assert pg.input_value("#out") == ""
    # undo/redo
    click(pg, 30, 30)
    pg.keyboard.press("Enter")
    assert pg.evaluate("annotator.state.parts[0].polygons.length") == 1
    pg.keyboard.press("Control+z")
    assert pg.evaluate("annotator.state.parts[0].polygons.length") == 0
    pg.keyboard.press("Control+y")
    assert pg.evaluate("annotator.state.parts[0].polygons.length") == 1


def test_import_migrated_file_round_trip(page, tmp_path):
    """Importing a migrated annotation (no image loaded) and exporting keeps every field."""
    pg = page
    src = ROOT / "annotations/toddlers.json"
    pg.set_input_files("#fileJson", str(src))
    pg.wait_for_function("annotator.state.parts.length === 7")
    pg.focus("#cv")
    _, out = export(pg, tmp_path, "t.json")
    assert json.loads(out.read_text()) == json.loads(src.read_text())
