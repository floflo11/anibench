"""Six image-math graders over rendered frames.

frames: uint8 array (N, H, W, 3), N = 49 frames for t = i * 2/48.
orig:   uint8 array (H, W, 3), the task image.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

CHANGE_T = 24      # per-channel difference that counts as "changed"
FG_T = 30          # distance from white that counts as foreground
MIN_BLOB = 60      # px
G1_MAX = 0.002     # fraction of outside pixels allowed to change
G4_MIN = 0.20      # fraction of target pixels that must change at peak
G5_KEEP = 0.85     # fraction of original foreground that must stay in the pivot disc
G5_R = 7
G6_LOOP = 0.001
G6_ORIG = 0.005
SKULL_KEEP = 0.85


def changed(a, b):
    d = np.abs(a.astype(int) - b.astype(int)).max(-1) > CHANGE_T
    return ndimage.binary_opening(d, structure=np.ones((3, 3)))


def foreground(img):
    return (255 - img.astype(int)).max(-1) > FG_T


def blobs(fg):
    lab, n = ndimage.label(fg)
    if n == 0:
        return 0
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    return int((sizes >= MIN_BLOB).sum())


def disc(shape, x, y, r):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - x) ** 2 + (yy - y) ** 2 <= r * r


def load_mask(task_dir, name):
    p = Path(task_dir) / name
    return (np.array(Image.open(p)) > 127) if p.exists() else None


def grade(frames, task_dir):
    task_dir = Path(task_dir)
    spec = json.loads((task_dir / "spec.json").read_text())
    orig = np.array(Image.open(task_dir / "image.png").convert("RGB"))
    allowed = load_mask(task_dir, "allowed.png")
    target = load_mask(task_dir, "target.png")
    skull = load_mask(task_dir, "skull.png")
    res = {}
    fg0 = foreground(orig)
    region = allowed if allowed is not None else np.ones(fg0.shape, bool)
    area0 = max(1, (fg0 & region).sum())
    blobs0 = blobs(fg0)
    ch = [changed(f, orig) for f in frames]
    fgs = [foreground(f) for f in frames]

    if "G1" in spec["graders"]:
        outside = ~allowed
        worst = max((c & outside).sum() for c in ch) / outside.sum()
        res["G1"] = dict(ok=bool(worst <= G1_MAX), value=round(float(worst), 5))
    if "G2" in spec["graders"]:
        # count pieces inside the moving region only; baseline = original (or frame 0 if renderer noise adds pieces)
        base = max(blobs(fg0 & region), blobs(fgs[0] & region))
        worst = max(blobs(f & region) for f in fgs)
        res["G2"] = dict(ok=bool(worst <= base + spec.get("blob_allow", 0)), value=int(worst), base=int(base))
    if "G3" in spec["graders"]:
        dev = max(abs((f & region).sum() - area0) / area0 for f in fgs)
        ok = dev <= spec["area_tol"]
        extra = {}
        if skull is not None:
            keep = min((f & skull).sum() / max(1, (fg0 & skull).sum()) for f in fgs)
            extra["skull_keep"] = round(float(keep), 3)
            ok = ok and keep >= SKULL_KEEP
        res["G3"] = dict(ok=bool(ok), value=round(float(dev), 4), **extra)
    if "G4" in spec["graders"]:
        peak = max((c & target).sum() for c in ch) / max(1, target.sum())
        res["G4"] = dict(ok=bool(peak >= G4_MIN), value=round(float(peak), 3))
    if "G5" in spec["graders"]:
        worst = 1.0
        for (x, y) in spec["pivots"]:
            dm = disc(orig.shape, x, y, G5_R)
            base = (fg0 & dm).sum()
            if base < 0.5 * dm.sum():
                continue
            keep = min((f & dm).sum() / base for f in fgs)
            worst = min(worst, keep)
        res["G5"] = dict(ok=bool(worst >= G5_KEEP), value=round(float(worst), 3))
    if "G6" in spec["graders"]:
        loop = changed(frames[0], frames[-1]).mean()
        o = ch[0].mean()
        res["G6"] = dict(ok=bool(loop <= G6_LOOP and o <= G6_ORIG), loop=round(float(loop), 5), first_vs_orig=round(float(o), 5))
    res["pass"] = bool(all(v["ok"] for v in res.values())) if res else None
    return res
