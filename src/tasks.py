"""Task definitions T01-T24 and the grading masks each task needs.

Writes tasks/<ID>/{spec.json, prompt.md, image.png, allowed.png, target.png, extra.png?}
"""
import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
PARTS = json.loads((ROOT / "annotations/parts.json").read_text())
SIZES = {"lineup": (1200, 600), "toddlers": (1024, 683)}
SUFFIX = "Nothing else in the image may move or change. Make it a seamless 2-second loop."

# kind: rotate (about pivots) | translate_up (lift) | jump | body (squat/bounce) | flutter | human
TASKS = [
    # id, tier, image, instruction, target parts, kind, amplitude (deg or px)
    ("T01", 1, "lineup", "Make the boy on the far left wave his raised hand, bending at the wrist.", ["A1_hand"], "rotate", 25),
    ("T02", 1, "lineup", "Make the girl with pigtails wave her raised forearm from the elbow.", ["A2_forearm"], "rotate", 20),
    ("T03", 1, "lineup", "Make the small boy in the striped shirt wave his raised hand from the wrist.", ["A3_hand"], "rotate", 25),
    ("T04", 1, "lineup", "Make the girl in the white dress (far right) wave her raised forearm from the elbow.", ["A4_forearm"], "rotate", 20),
    ("T05", 1, "toddlers", "Make the toddler in the red jacket wave her raised hand from the wrist.", ["B1_hand"], "rotate", 25),
    ("T06", 1, "toddlers", "Make the toddler in the navy jacket swing his whole raised arm from the shoulder.", ["B2_arm"], "rotate", 15),
    ("T07", 1, "lineup", "Make the red earrings of the girl in the white dress (far right) swing gently, as if in a breeze.", ["A4_earringL", "A4_earringR"], "rotate", 25),
    ("T08", 1, "lineup", "Make the pigtails of the girl with pigtails swing side to side.", ["A2_pigtailL", "A2_pigtailR"], "rotate", 12),
    ("T09", 1, "lineup", "Make the boy on the far left nod his head.", ["A1_head"], "rotate", 8),
    ("T10", 1, "toddlers", "Make the toddler in the navy jacket nod his head; his hat stays on his head.", ["B2_head"], "rotate", 8),
    ("T11", 1, "lineup", "Make the small boy in the striped shirt tilt his head side to side.", ["A3_head"], "rotate", 10),
    ("T12", 1, "lineup", "Make all four children wave their raised hands at the same time.", ["A1_hand", "A2_forearm", "A3_hand", "A4_forearm"], "rotate", 22),
    ("T13", 2, "toddlers", "Make the toddler in the red jacket lift her hat off her head and settle it back down.", ["B1_hat"], "translate_up", 70),
    ("T14", 2, "toddlers", "Make the toddler in the navy jacket tilt his hat up and back in greeting, pivoting on the left end of the brim (viewer's left).", ["B2_hat"], "rotate_hat", 15),
    ("T15", 2, "lineup", "Make the small boy in the striped shirt jump once; the other three children stay perfectly still.", ["A3_body"], "jump", 80),
    ("T16", 2, "toddlers", "Make the toddler in the red jacket jump; the other toddler stays perfectly still.", ["B1_body"], "jump", 80),
    ("T17", 2, "lineup", "Make the girl with pigtails squat down and stand back up.", ["A2_body"], "body", 60),
    ("T18", 2, "toddlers", "Make the toddler in the navy jacket bounce at the knees.", ["B2_body"], "body", 40),
    ("T19", 2, "lineup", "Make the lace veil of the girl in the white dress (far right) flutter in the wind.", ["A4_veil"], "flutter", 35),
    ("T20", 2, "lineup", "Make the boy on the far left wave with his left hand.", ["A1_hand"], "rotate", 25),
    ("T21", 2, "toddlers", "Make the toddler in the red jacket wave with her right hand.", ["B1_hand"], "rotate", 25),
    ("T22", 3, "toddlers", "Make the toddler in the navy jacket give a thumbs up with his raised hand.", ["B2_arm"], "human", 0),
    ("T23", 3, "lineup", "Make the small boy in the striped shirt walk in place.", ["A3_body"], "human", 0),
    ("T24", 3, "toddlers", "Make the toddler in the red jacket clap her hands.", ["B1_body"], "human", 0),
]

HAT_PIVOT_T14 = (560, 160)

PROMPT = """You are given an image, `image.png`, {W}x{H} pixels, with a white background.

**Task:** {instruction} {suffix}

Write ONE self-contained HTML file that animates the image with three.js and follows this contract exactly:

1. Load three.js as an ES module from `./vendor/three.module.js`, e.g. `<script type="module">import * as THREE from './vendor/three.module.js';</script>`. No other libraries and no network requests.
2. Load `./image.png` and draw it on a canvas of exactly {W}x{H} CSS pixels at the top-left of the page (body margin 0), at device pixel ratio 1 (`renderer.setPixelRatio(1)`). Use an orthographic camera so one image pixel maps to one canvas pixel. Use `texture.colorSpace = THREE.SRGBColorSpace` and no tone mapping, so that frame 0 matches the original image. Keep the white background.
3. Expose `window.setTime(t)`, which synchronously renders the frame at time `t` seconds (0 <= t <= 2). The animation must repeat every 2 seconds: `setTime(0)` and `setTime(2)` must render identical frames, and `setTime(0)` must show the original image unchanged.
4. Set `window.ANIM_READY = true` only after the texture has loaded and `setTime` works. Correctness must not depend on `requestAnimationFrame` timing (you may also run a rAF loop for live playback).
5. Deterministic: no unseeded randomness and no wall-clock time inside `setTime`.

How you isolate and move the part is up to you (for example: cut it out with a polygon or alpha mask into its own mesh, and fill what it reveals). Pixel coordinates refer to the image with (0,0) at the top-left.

Return only the complete HTML file in a single ```html code block."""


def load_part(pid):
    return np.array(Image.open(ROOT / f"annotations/parts/{pid}.png")) > 127


def rotate_mask(m, pivot, deg):
    """Rotate boolean mask about pivot by deg (image coords, y down)."""
    h, w = m.shape
    ys, xs = np.nonzero(m)
    th = np.deg2rad(deg)
    px, py = pivot
    xr = px + (xs - px) * np.cos(th) - (ys - py) * np.sin(th)
    yr = py + (xs - px) * np.sin(th) + (ys - py) * np.cos(th)
    out = np.zeros_like(m)
    xi, yi = np.round(xr).astype(int), np.round(yr).astype(int)
    ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
    out[yi[ok], xi[ok]] = True
    return ndimage.binary_closing(out, iterations=1)


def shift_mask(m, dy=0, dx=0):
    return ndimage.shift(m.astype(np.uint8), (dy, dx), order=0) > 0


def allowed_region(spec, targets):
    kind, amp = spec["kind"], spec["amp"]
    acc = np.zeros_like(targets[0])
    for pid, m in zip(spec["parts"], targets):
        piv = PARTS[pid]["pivot"]
        if kind == "rotate":
            for a in range(-int(amp * 2), int(amp * 2) + 1, 3):
                acc |= rotate_mask(m, piv, a)
            acc |= m
        elif kind == "rotate_hat":
            for a in range(-int(amp * 2), int(amp * 2) + 1, 3):
                acc |= rotate_mask(m, HAT_PIVOT_T14, a)
            acc |= m
        elif kind == "translate_up":
            for d in range(0, int(amp * 2) + 1, 4):
                acc |= shift_mask(m, dy=-d)
        elif kind == "jump":
            for d in range(-12, int(amp * 2) + 1, 4):
                acc |= shift_mask(m, dy=-d)
            acc = ndimage.binary_dilation(acc, iterations=12)
        elif kind == "body":
            ys, xs = np.nonzero(m)
            acc[max(0, ys.min() - 10):ys.max() + 1, max(0, xs.min() - 45):xs.max() + 46] = True
        elif kind == "flutter":
            acc |= ndimage.binary_dilation(m, iterations=int(amp))
        else:
            acc |= ndimage.binary_dilation(m, iterations=40)
    return ndimage.binary_dilation(acc, iterations=10)


def build():
    out = ROOT / "tasks"
    out.mkdir(exist_ok=True)
    index = []
    for tid, tier, img, instr, parts, kind, amp in TASKS:
        W, H = SIZES[img]
        d = out / tid
        d.mkdir(exist_ok=True)
        shutil.copy(ROOT / f"images/{img}_task.png", d / "image.png")
        targets = [load_part(p) for p in parts]
        target = np.any(targets, axis=0)
        graders = ["G1", "G2", "G3", "G4", "G5", "G6"]
        if kind in ("translate_up", "jump", "body"):
            graders.remove("G5")
        if kind in ("translate_up", "rotate_hat"):
            graders.remove("G2")  # a lifted hat is meant to come apart from the head
        if kind == "human":
            graders = []
        pivots = []
        if "G5" in graders:
            pivots = [HAT_PIVOT_T14] if kind == "rotate_hat" else [PARTS[p]["pivot"] for p in parts]
        spec = dict(id=tid, tier=tier, image=img, width=W, height=H, instruction=instr, parts=parts,
                    kind=kind, amp=amp, graders=graders, pivots=pivots,
                    area_tol=0.35 if kind in ("translate_up", "rotate_hat") else (0.12 if kind in ("jump", "body", "flutter") else 0.08),
                    blob_allow=3 if kind in ("translate_up", "rotate_hat") else 0)
        Image.fromarray((target * 255).astype("uint8")).save(d / "target.png")
        if graders:
            allowed = allowed_region(spec, targets)
            Image.fromarray((allowed * 255).astype("uint8")).save(d / "allowed.png")
        if kind in ("translate_up", "rotate_hat"):
            skull = load_part(parts[0].replace("_hat", "_skull"))
            Image.fromarray((skull * 255).astype("uint8")).save(d / "skull.png")
            spec["skull"] = True
        (d / "spec.json").write_text(json.dumps(spec, indent=1))
        (d / "prompt.md").write_text(PROMPT.format(W=W, H=H, instruction=instr, suffix=SUFFIX))
        index.append(spec)
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return index


if __name__ == "__main__":
    idx = build()
    for s in idx:
        print(s["id"], s["kind"], s["graders"], s["pivots"])
