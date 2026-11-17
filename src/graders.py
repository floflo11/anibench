"""Image-math graders over rendered frames.

frames: uint8 array (N, H, W, 3), N = render.N_FRAMES frames for t = i * 2/(N-1).
orig:   uint8 array (H, W, 3), the task image.

Checks: G1 isolation, G2 integrity (new blobs in the moving region), G2b connectivity (the part
itself does not come apart), G3 area, G4 motion, G5 pivot, G6 loop/fidelity.
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
G5_MAX = 0.20      # max fraction of the part's pixels at the joint that may change
G5_R = 10
G6_LOOP = 0.001
G6_ORIG = 0.005
SKULL_KEEP = 0.85
G2B_MIN = 20       # px: a piece of the part at least this big counts as a piece
G2B_EMBED = 0.75   # a footprint-free piece whose border is >= this fraction unchanged scenery is ignored
                   # (islands seen on references: 0.81-1.0 enclosed; 0.9 failed T12's lace sleeve)
G2B_BG = 8         # original pixels within this distance of white are blank background, not scenery
EIGHT = np.ones((3, 3), bool)


def raw_changed(a, b):
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(-1) > CHANGE_T


def changed(a, b):
    return ndimage.binary_opening(raw_changed(a, b), structure=np.ones((3, 3)))


def foreground(img):
    return (255 - img.astype(int)).max(-1) > FG_T


def blobs(fg):
    lab, n = ndimage.label(fg)
    if n == 0:
        return 0
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    return int((sizes >= MIN_BLOB).sum())


def pieces(mask, min_px):
    """Number of 8-connected components of mask with at least min_px pixels."""
    lab, n = ndimage.label(mask, structure=EIGHT)
    if n == 0:
        return 0
    sizes = np.bincount(lab.ravel())[1:]
    return int((sizes >= min_px).sum())


def part_pieces(mask, static, target, min_px):
    """Count 8-connected pieces of mask with >= min_px pixels, skipping embedded islands: pieces
    with no pixel in the part's original footprint whose 1-px border is >= G2B_EMBED static
    scenery (unchanged, outside the footprint, not blank background in the original). See g2b."""
    lab, n = ndimage.label(mask, structure=EIGHT)
    if n == 0:
        return 0
    sizes = np.bincount(lab.ravel())
    count = 0
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        if sizes[i] < min_px:
            continue
        sl = tuple(slice(max(0, a.start - 1), a.stop + 1) for a in sl)
        piece = lab[sl] == i
        if not (piece & target[sl]).any():
            ring = ndimage.binary_dilation(piece, structure=EIGHT) & ~piece
            if (ring & static[sl]).sum() >= G2B_EMBED * ring.sum():
                continue
        count += 1
    return count


def part_pixels(fg, diff, region, target, skull=None):
    """The target part's pixels in one frame (see g2b for the reasoning)."""
    m = fg & region & (target | diff)
    if skull is not None:
        m &= ~skull
    return m


def g2b(fgs, raw, fg0, region, target, skull=None, scenery0=None):
    """G2b Connectivity: the moving part must not come apart.

    Isolating the part in a later frame. The part moves, so its pixels cannot be found by a
    fixed mask, and the frames have no layer information. Inside the allowed region a
    foreground pixel in frame t is taken to belong to the part if
      (a) it lies in the part's original footprint (target.png), or
      (b) it differs from the original image by more than CHANGE_T in some channel. This is the
          raw difference, not the 3x3-opened `changed` map G1/G4 use against speckle: where the
          part crosses a neighbour of similar colour only thin slivers register as changed, and
          the opening would erase them and cut the part apart (it did on T05 and T19).
    Everything else in the region is foreground that is still exactly as in the original and
    lies outside the footprint: the parent limb, the body, neighbouring children. Those pixels
    are excluded, so the part cannot be "glued back together" through them. This is what G2
    misses: a thumb left behind usually still touches the forearm, so the whole region stays
    one blob, but here the forearm is removed and the thumb shows up as its own piece.
      - A piece left behind keeps its original pixels inside the footprint: rule (a) keeps it.
      - A piece dragged to a new place is changed: rule (b) keeps it.
      - Background white is never foreground, so the reveal a correct animation leaves (filled
        with white) adds nothing.
      - skull.png (hat tasks) marks the reveal the task expects to be repainted with hair; it is
        excluded in every frame, otherwise the repainted skull would stay behind as a "piece"
        when the hat lifts.
    Embedded islands. When the part passes over a neighbour of nearly the same colour (a hand
    over a cheek, a navy sleeve over a navy jacket, a cream hat brim over a forehead), most of
    it looks unchanged there and is excluded, and the few textured pixels that do register as
    changed form islands surrounded on all sides by unchanged scenery. Such an island is
    attached to the part through pixels that merely look the same, so a piece that has no pixel
    in the original footprint and whose 1-px border is >= G2B_EMBED unchanged non-target
    scenery is not counted. Scenery means: outside the footprint, unchanged, and not blank
    background in the original (more than G2B_BG from white). It need not be foreground: near-white
    lace (T04's sleeve) is too light for FG_T but still encloses an island. A piece left behind is
    in the footprint and always counts; a piece dragged loose over the background has blank white
    on its border and counts.
    Known blind spots: a piece that drifts entirely onto a neighbour of the same colour is
    ignored, and a model that repaints the reveal with a non-white colour that touches only the
    parent can add a piece (false alarm).

    Counting. Baseline = 8-connected pieces of the original part (fg0 & footprint, skull removed)
    with at least G2B_MIN px; frame t = the same count over part_pixels. A frame fails if it has
    more pieces than the baseline. Fewer pieces is not a failure: pieces merging (two earrings
    touching) is not a split, and parts that vanish are G3's and G4's job. (A lower floor for the
    baseline was tried as hysteresis against resampling; it gave free slack wherever the original
    has 10-19 px crumbs, hiding T11's detach_tip and every split on T19, so it was dropped.)
    """
    base_mask = fg0 & region & target
    if skull is not None:
        base_mask &= ~skull
    base = pieces(base_mask, G2B_MIN)
    if scenery0 is None:
        scenery0 = fg0
    counts = [part_pieces(part_pixels(f, c, region, target, skull), scenery0 & ~target & ~c, target, G2B_MIN)
              for f, c in zip(fgs, raw)]
    worst = int(np.argmax(counts))
    return dict(ok=bool(counts[worst] <= base), value=int(counts[worst]), base=int(base), frame=worst)


def candidate_checks(spec):
    """Every check that could apply to a task, before admission: the task's original list plus
    G2b (which applies to every scored task, hats included: a lifted hat must stay one piece)."""
    ks = list(spec.get("graders_all", spec["graders"]))
    if ks and "G2b" not in ks:
        i = ks.index("G2") + 1 if "G2" in ks else next((j for j, k in enumerate(ks) if k > "G2b"), len(ks))
        ks.insert(i, "G2b")
    return ks


def disc(shape, x, y, r):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - x) ** 2 + (yy - y) ** 2 <= r * r


def load_mask(task_dir, name):
    p = Path(task_dir) / name
    return (np.array(Image.open(p)) > 127) if p.exists() else None


def grade(frames, task_dir, checks=None):
    """Grade frames against a task. checks: which checks to run (default: spec["graders"],
    i.e. the admitted list); validation passes candidate_checks(spec) to re-test all of them."""
    task_dir = Path(task_dir)
    spec = json.loads((task_dir / "spec.json").read_text())
    checks = list(spec["graders"] if checks is None else checks)
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

    if "G1" in checks:
        outside = ~allowed
        worst = max((c & outside).sum() for c in ch) / outside.sum()
        res["G1"] = dict(ok=bool(worst <= G1_MAX), value=round(float(worst), 5))
    if "G2" in checks:
        # count pieces inside the moving region only; baseline = original (or frame 0 if renderer noise adds pieces)
        base = max(blobs(fg0 & region), blobs(fgs[0] & region))
        worst = max(blobs(f & region) for f in fgs)
        res["G2"] = dict(ok=bool(worst <= base + spec.get("blob_allow", 0)), value=int(worst), base=int(base))
    if "G2b" in checks:
        scenery0 = (255 - orig.astype(int)).max(-1) > G2B_BG
        res["G2b"] = g2b(fgs, [raw_changed(f, orig) for f in frames], fg0, region, target, skull, scenery0)
    if "G3" in checks:
        # net foreground lost or gained in the moving region, relative to the moving part's own area
        tarea = max(1, (fg0 & target).sum())
        dev = max(abs(int((f & region).sum()) - int(area0)) / tarea for f in fgs)
        ok = dev <= spec["area_tol"]
        extra = {}
        if skull is not None:
            keep = min((f & skull).sum() / max(1, (fg0 & skull).sum()) for f in fgs)
            extra["skull_keep"] = round(float(keep), 3)
            ok = ok and keep >= SKULL_KEEP
        res["G3"] = dict(ok=bool(ok), value=round(float(dev), 4), **extra)
    if "G4" in checks:
        peak = max((c & target).sum() for c in ch) / max(1, target.sum())
        res["G4"] = dict(ok=bool(peak >= G4_MIN), value=round(float(peak), 3))
    if "G5" in checks:
        # the moving part's own pixels right at the joint should stay put (they barely move when rotating about the joint)
        worst = 0.0
        for (x, y) in spec["pivots"]:
            dm = disc(orig.shape, x, y, G5_R) & target
            if dm.sum() < 30:
                continue
            frac = max((c & dm).sum() for c in ch) / dm.sum()
            worst = max(worst, frac)
        res["G5"] = dict(ok=bool(worst <= G5_MAX), value=round(float(worst), 3))
    if "G6" in checks:
        loop = changed(frames[0], frames[-1]).mean()
        o = ch[0].mean()
        res["G6"] = dict(ok=bool(loop <= G6_LOOP and o <= G6_ORIG), loop=round(float(loop), 5), first_vs_orig=round(float(o), 5))
    res["pass"] = bool(all(v["ok"] for v in res.values())) if res else None
    return res
