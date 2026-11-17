"""Task generation: annotations/*.json (parts) + annotations/tasks_*.json (task definitions) -> tasks/.

Writes tasks/<ID>/{spec.json, prompt.md, image.png, target.png, allowed.png?, skull.png?} and
tasks/index.json. Task definitions (id, tier, image, instruction, parts, kind, amp, optional pivot
override) live in annotations/tasks_pilot.json; part masks and pivots come from the schema-v1
annotation files via src/annotations.py.

    python src/tasks.py [--tasks annotations/tasks_pilot.json] [--out tasks]
"""
from graders import candidate_checks  # noqa: E402
import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402

TASK_FILE = ROOT / "annotations/tasks_pilot.json"
SUFFIX = "Nothing else in the image may move or change. Make it a seamless 2-second loop."
KINDS = ("rotate", "rotate_hat", "translate_up", "jump", "body", "flutter", "human")
# kind: rotate (about pivots) | rotate_hat (about the task's pivot) | translate_up (lift) | jump
#       | body (squat/bounce) | flutter | human (no automatic graders)


def load_task_defs(path=TASK_FILE):
    doc = json.loads(Path(path).read_text())
    if doc.get("schema_version") != 1 or not isinstance(doc.get("tasks"), list):
        raise ValueError(f"{path}: expected {{'schema_version': 1, 'tasks': [...]}}")
    seen = set()
    for t in doc["tasks"]:
        for k in ("id", "tier", "image", "instruction", "parts", "kind", "amp"):
            if k not in t:
                raise ValueError(f"{path}: task {t.get('id')!r} is missing {k!r}")
        if t["kind"] not in KINDS:
            raise ValueError(f"{path}: task {t['id']}: unknown kind {t['kind']!r}")
        if t["id"] in seen:
            raise ValueError(f"{path}: duplicate task id {t['id']}")
        seen.add(t["id"])
    return doc["tasks"]


# Legacy module-level API (used by src/reference.py): part pivots/areas and masks by name.
_ANNS, _LIB = A.library()
PARTS = {n: dict(image=v["image"], pivot=list(v["pivot"]) if v["pivot"] else None, area=int(v["mask"].sum()))
         for n, v in _LIB.items()}
HAT_PIVOT_T14 = tuple(next(t["pivot"] for t in load_task_defs() if t["id"] == "T14"))

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
    return _LIB[pid]["mask"].copy()


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


def allowed_region(spec, targets, pivots):
    """Union of every pose the target parts may take, grown by 10 px. pivots: one per target part."""
    kind, amp = spec["kind"], spec["amp"]
    acc = np.zeros_like(targets[0])
    for piv, m in zip(pivots, targets):
        if kind in ("rotate", "rotate_hat"):
            for a in range(-int(amp * 2), int(amp * 2) + 1, 3):
                acc |= rotate_mask(m, piv, a)
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


def build(out=None, task_file=None, ann_dir=None):
    """Generate every task in `task_file` into `out` (default tasks/). Returns the index."""
    out = Path(out) if out else ROOT / "tasks"
    defs = load_task_defs(task_file or TASK_FILE)
    anns, lib = A.library(ann_dir or A.ANN_DIR)
    out.mkdir(parents=True, exist_ok=True)
    index = []
    for t in defs:
        tid, tier, img, instr, parts, kind, amp = (t[k] for k in ("id", "tier", "image", "instruction", "parts", "kind", "amp"))
        if img not in anns:
            raise ValueError(f"task {tid}: no annotation file for image {img!r}")
        ann = anns[img]
        for p in parts:
            if p not in lib or lib[p]["image"] != img:
                raise ValueError(f"task {tid}: part {p!r} is not annotated in image {img!r}")
        W, H = ann["image"]["width"], ann["image"]["height"]
        d = out / tid
        d.mkdir(exist_ok=True)
        shutil.copy(A.image_path(ann), d / "image.png")
        targets = [lib[p]["mask"] for p in parts]
        target = np.any(targets, axis=0)
        graders = ["G1", "G2", "G3", "G4", "G5", "G6"]
        if kind in ("translate_up", "jump", "body"):
            graders.remove("G5")
        if kind in ("translate_up", "rotate_hat"):
            graders.remove("G2")  # a lifted hat is meant to come apart from the head
        if kind == "human":
            graders = []
        graders = candidate_checks({"graders": graders})  # adds G2b connectivity to every scored task
        # pivot per target part: the task's override (e.g. T14's brim end) or the part's own pivot
        part_pivots = [tuple(t["pivot"]) if t.get("pivot") else lib[p]["pivot"] for p in parts]
        if kind in ("rotate", "rotate_hat") and graders and None in part_pivots:
            raise ValueError(f"task {tid}: kind {kind} needs a pivot for every part")
        pivots = []
        if "G5" in graders:
            pivots = [part_pivots[0]] if t.get("pivot") else part_pivots
            pivots = [list(p) for p in pivots]
        spec = dict(id=tid, tier=tier, image=img, width=W, height=H, instruction=instr, parts=parts,
                    kind=kind, amp=amp, graders=graders, pivots=pivots,
                    area_tol=0.5,
                    blob_allow=3 if kind in ("translate_up", "rotate_hat") else 0)
        Image.fromarray((target * 255).astype("uint8")).save(d / "target.png")
        if graders:
            allowed = allowed_region(spec, targets, part_pivots)
            Image.fromarray((allowed * 255).astype("uint8")).save(d / "allowed.png")
        keep = [A.keep_mask_name(ann, p) for p in parts]
        keep = [k for k in keep if k]
        if keep:
            skull = np.any([lib[k]["mask"] for k in keep], axis=0)
            Image.fromarray((skull * 255).astype("uint8")).save(d / "skull.png")
            spec["skull"] = True
        (d / "spec.json").write_text(json.dumps(spec, indent=1))
        (d / "prompt.md").write_text(PROMPT.format(W=W, H=H, instruction=instr, suffix=SUFFIX))
        index.append(spec)
    (out / "index.json").write_text(json.dumps(index, indent=1))
    return index


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", default=None, help="task definition file (default annotations/tasks_pilot.json)")
    ap.add_argument("--out", default=None, help="output directory (default tasks/)")
    a = ap.parse_args()
    idx = build(out=a.out, task_file=a.tasks)
    for s in idx:
        print(s["id"], s["kind"], s["graders"], s["pivots"])
