"""Shared inputs for the alternate animators: what a skilled human solving the task would have.

Allowed inputs (the same ones src/reference.py uses, standing in for a human who cuts the part out by hand):
  * tasks/<id>/image.png, the image a model is given;
  * the instruction, paraphrased as (kind, parts) in annotations/tasks_pilot.json, plus the pivot the
    instruction names (T14: "the left end of the brim");
  * the hand-drawn part masks and joint pivots, and the keep (skull) mask that says where the head is
    under a hat, from annotations/*.json.

Never read: tasks/<id>/{spec.json, allowed.png, target.png, skull.png}, the task's `amp`, or any grader
constant. Every amplitude below is the animator's own choice, picked per action from what reads as a
plausible version of that action (see docs/alt_refs.md), not from the grader-side `amp`.
"""
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402

TASK_FILE = ROOT / "annotations" / "tasks_pilot.json"

# Plausible range per action: (low, typical, high). Units: degrees for swings, px for lifts and jumps,
# fraction of the character's height for squats and bounces, px of tip travel for the veil flutter.
RANGES = {
    "wave_hand": (15, 25, 40),
    "wave_forearm": (12, 20, 32),
    "swing_arm": (8, 15, 25),
    "earring": (10, 22, 35),
    "pigtail": (6, 12, 20),
    "head": (5, 8, 14),
    "hat_tilt": (8, 15, 25),
    "flutter": (15, 30, 50),
    "hat_lift": (30, 60, 110),
    "jump": (35, 70, 120),
    "squat": (0.06, 0.12, 0.20),
    "bounce": (0.03, 0.06, 0.10),
}
MODE = {a: "rot" for a in ("wave_hand", "wave_forearm", "swing_arm", "earring", "pigtail", "head", "hat_tilt", "flutter")}
MODE.update(hat_lift="lift", jump="lift", squat="squash", bounce="squash")
LEVEL = {"lo": 0, "typ": 1, "hi": 2}


def task_defs():
    """{id: task definition}. Only id, image, instruction, parts, kind and a named pivot are used."""
    return {t["id"]: t for t in json.loads(TASK_FILE.read_text())["tasks"]}


def action_for(part, kind, instruction):
    if kind == "jump":
        return "jump"
    if kind == "body":
        return "squat" if "squat" in instruction.lower() else "bounce"
    if kind == "translate_up":
        return "hat_lift"
    if kind == "rotate_hat":
        return "hat_tilt"
    if kind == "flutter":
        return "flutter"
    name = part.split("_", 1)[1]
    for key, act in (("hand", "wave_hand"), ("forearm", "wave_forearm"), ("arm", "swing_arm"),
                     ("earring", "earring"), ("pigtail", "pigtail"), ("head", "head")):
        if name.startswith(key):
            return act
    raise ValueError(f"no action for part {part!r} ({kind})")


@dataclass
class Part:
    name: str
    mask: np.ndarray        # bool (H, W)
    pivot: tuple            # (x, y) image px; for lifts/squashes the ground/brim anchor
    action: str
    mode: str               # rot | lift | squash
    axis: tuple             # unit vector pivot -> mask centroid (image coords, y down)
    length: float           # max distance from pivot to a mask pixel
    bbox: tuple             # x0, y0, x1, y1 (exclusive), padded and clipped to the image

    def amount(self, level):
        v = RANGES[self.action][LEVEL[level] if isinstance(level, str) else level]
        if self.action == "flutter":  # tip travel in px -> swing angle
            v = float(np.degrees(np.arctan2(v, self.length)))
        return float(v)


def _anchor(mask, action):
    """Squash/lift anchor: the feet (centre of the lowest rows) for a body, the bottom centre for a hat."""
    ys, xs = np.nonzero(mask)
    y1 = int(ys.max())
    if action == "hat_lift":
        return (float(np.round(xs.mean())), float(y1))
    low = ys >= y1 - max(3, int(0.03 * (y1 - ys.min())))
    return (float(np.round((xs[low].min() + xs[low].max()) / 2)), float(y1))


def _bbox(mask, pad, W, H):
    ys, xs = np.nonzero(mask)
    return (int(max(0, xs.min() - pad)), int(max(0, ys.min() - pad)), int(min(W, xs.max() + 1 + pad)),
            int(min(H, ys.max() + 1 + pad)))


def task_info(tid, task_dir=None):
    d = task_defs()[tid]
    task_dir = Path(task_dir) if task_dir else ROOT / "tasks" / tid
    img = np.array(Image.open(task_dir / "image.png").convert("RGB"))
    H, W = img.shape[:2]
    anns, lib = A.library()
    ann = anns[d["image"]]
    parts, skull = [], np.zeros((H, W), bool)
    for p in d["parts"]:
        m = lib[p]["mask"].copy()
        act = action_for(p, d["kind"], d["instruction"])
        mode = MODE[act]
        if d.get("pivot"):
            piv = tuple(float(v) for v in d["pivot"])
        elif mode == "rot":
            piv = tuple(float(v) for v in lib[p]["pivot"])
        else:
            piv = _anchor(m, act)
        ys, xs = np.nonzero(m)
        c = np.array([xs.mean() - piv[0], ys.mean() - piv[1]])
        axis = tuple((c / (np.linalg.norm(c) + 1e-9)).tolist())
        length = float(np.sqrt(((xs - piv[0]) ** 2 + (ys - piv[1]) ** 2).max()))
        parts.append(Part(p, m, piv, act, mode, axis, length, _bbox(m, 2, W, H)))
        k = A.keep_mask_name(ann, p)
        if k:
            skull |= lib[k]["mask"]
    return dict(id=tid, W=W, H=H, img=img, kind=d["kind"], instruction=d["instruction"], parts=parts,
                skull=skull if skull.any() else None)


# ---- hole filling (what the moved part uncovers) -------------------------------------------------

def nearest_fill(img, hole):
    """Each hole pixel takes the colour of the nearest solid pixel outside the hole (a simple content-aware
    fill). Faint anti-aliased halo pixels around the removed part are treated as background first, so the
    fill continues real neighbours (a sleeve, the face) and is white where the part bordered the sky."""
    fg = ((255 - img.astype(int)).max(-1) > 30) & ~hole
    solid = ndimage.binary_opening(fg, structure=np.ones((5, 5)))
    src = img.copy()
    src[~solid] = 255
    idx = ndimage.distance_transform_edt(hole, return_distances=False, return_indices=True)
    out = img.copy()
    out[hole] = src[idx[0], idx[1]][hole]
    return out


def base_image(info, how):
    """Background with every moving part removed. how: 'white' (white, with the skull painted in a flat
    sampled hair colour) or 'nearest' (nearest-colour fill). For a hat, 'nearest' fills the skull and a
    thin seam where the brim met the face, and leaves the rest of the hat footprint white (sky)."""
    img = info["img"]
    hole = np.any([p.mask for p in info["parts"]], axis=0)
    if how == "nearest":
        out = nearest_fill(img, hole)
        if info["skull"] is not None:
            fg = ((255 - img.astype(int)).max(-1) > 30) & ~hole
            solid = ndimage.binary_opening(fg, structure=np.ones((5, 5)))
            # the head continues under the hat: in every column the skull spans, everything below the
            # skull's top edge is head (filled); above it is sky (white)
            sk = info["skull"]
            cols = np.nonzero(sk.any(0))[0]
            top = np.full(sk.shape[1], sk.shape[0])
            top[cols] = np.argmax(sk[:, cols], axis=0)
            head = np.arange(sk.shape[0])[:, None] >= top[None, :]
            keep = (sk | head | ndimage.binary_dilation(solid, iterations=6)) & hole
            out[hole & ~keep] = 255
        return out
    out = img.copy()
    out[hole] = 255
    if info["skull"] is not None:
        sk = info["skull"]
        below = ndimage.binary_dilation(sk, iterations=12) & ~hole & ~sk
        below &= (255 - img.astype(int)).max(-1) > 60          # foreground (hair/skin), not background
        col = np.median(img[below], axis=0) if below.any() else np.array([40, 30, 25])
        out[sk & hole] = col.astype(np.uint8)
    return out


def rgba(img, mask, box=None):
    a = np.zeros((*mask.shape, 4), np.uint8)
    a[..., :3] = img
    a[..., 3] = mask.astype(np.uint8) * 255
    if box:
        x0, y0, x1, y1 = box
        a = a[y0:y1, x0:x1]
    return Image.fromarray(a)


def save_png(arr_or_im, path):
    im = arr_or_im if isinstance(arr_or_im, Image.Image) else Image.fromarray(arr_or_im)
    im.save(path)


def js(obj):
    return json.dumps(obj, separators=(",", ":"))
