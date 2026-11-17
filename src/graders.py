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
G1_GROW = 0.075    # v3: G1 tolerates changes this share of the target's larger extent beyond the allowed region
                   # (room for +-15% squash/stretch; results/alt_refs/whatif.json: clears T13/T14/T16 squash)
G2_MIN_CONTRAST = 80  # v3: G2 ignores pieces whose median contrast against white is below this (faint halos,
                      # pale stripes: T15/T17 false fails in results/alt_refs)
G4_MIN = 0.20      # fraction of target pixels that must change at peak
G5_MAX = 0.20      # max fraction of the part's pixels at the joint that may change
G5_R = 10
G6_LOOP = 0.001
G6_ORIG = 0.005
SKULL_KEEP = 0.85
G2B_MIN = 20       # px: a piece of the part at least this big counts as a piece
G2B_EMBED = 0.75   # a footprint-free piece whose border is >= this fraction unchanged scenery is ignored
                   # (islands seen on references: 0.81-1.0 enclosed; 0.9 failed T12's lace sleeve)
G2B_CORE = 4       # px: a piece must keep this many pixels after a 3x3 erosion (lines are not pieces)
G2B_BG = 8         # original pixels within this distance of white are blank background, not scenery
EIGHT = np.ones((3, 3), bool)


def raw_changed(a, b):
    return np.abs(a.astype(np.int16) - b.astype(np.int16)).max(-1) > CHANGE_T


def changed(a, b):
    return ndimage.binary_opening(raw_changed(a, b), structure=np.ones((3, 3)))


def foreground(img):
    return (255 - img.astype(int)).max(-1) > FG_T


def blobs(fg, img=None, min_contrast=None):
    """Number of 4-connected pieces of fg with >= MIN_BLOB px; with img and min_contrast, only pieces whose
    median contrast against white (max over channels of 255 - value) is at least min_contrast."""
    lab, n = ndimage.label(fg)
    if n == 0:
        return 0
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    keep = sizes >= MIN_BLOB
    if min_contrast is not None and keep.any():
        con = (255 - img.astype(np.int16)).max(-1)
        med = np.asarray(ndimage.median(con, lab, range(1, n + 1)))
        keep &= med >= min_contrast
    return int(keep.sum())


def g1_region(allowed, target):
    """G1's allowed region: allowed.png grown by ceil(G1_GROW x the target's larger bounding-box extent) px."""
    ys, xs = np.nonzero(target)
    if not len(xs):
        return allowed
    r = int(np.ceil(G1_GROW * max(np.ptp(xs) + 1, np.ptp(ys) + 1)))
    return ndimage.binary_dilation(allowed, iterations=r) if r > 0 else allowed


def pieces(mask, min_px):
    """Number of 8-connected components of mask with at least min_px pixels."""
    lab, n = ndimage.label(mask, structure=EIGHT)
    if n == 0:
        return 0
    sizes = np.bincount(lab.ravel())[1:]
    return int((sizes >= min_px).sum())


def part_pieces(mask, static, target, min_px):
    """Count 8-connected pieces of mask with >= min_px pixels and a body (>= G2B_CORE pixels left
    after a 3x3 erosion, so 1-2 px lines do not count), skipping embedded islands: pieces
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
        if ndimage.binary_erosion(piece, structure=EIGHT).sum() < G2B_CORE:
            continue
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

    Thin lines. Models that cut the part out with a polygon often leave a faint 1-px seam along
    the cut (qwen T01/T03); 20-30 px stretches of it are not pieces of the part. A piece must keep
    G2B_CORE pixels after a 3x3 erosion; every real detached piece seen (fingertips, tips left
    behind, the mutation pieces) has a body.

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
    base = part_pieces(base_mask, np.zeros_like(base_mask), target, G2B_MIN)
    if scenery0 is None:
        scenery0 = fg0
    counts = [part_pieces(part_pixels(f, c, region, target, skull), scenery0 & ~target & ~c, target, G2B_MIN)
              for f, c in zip(fgs, raw)]
    worst = int(np.argmax(counts))
    return dict(ok=bool(counts[worst] <= base), value=int(counts[worst]), base=int(base), frame=worst)


# ---- rigid motion of the part --------------------------------------------------------------------
FIT_TOL = 24        # per-channel difference within which a part pixel "matches" its moved original
FIT_MIN = 0.5       # a frame's fit is trusted when at least this share of the part's pixels match
FIT_MIN_PX = 150    # parts (or groups) with fewer visible pixels are not fitted
FIT_N = (250, 700)  # sampled part pixels for the coarse and the fine search (fixed seeds: deterministic)


def _pool(img, s):
    """s x s average pooling (int16), so a coarse search can cover large motions cheaply."""
    if s == 1:
        return img.astype(np.int16)
    h, w = img.shape[0] // s, img.shape[1] // s
    a = img[:h * s, :w * s].astype(np.float32)
    a = a.reshape(h, s, w, s, *a.shape[2:]).mean((1, 3))
    return np.rint(a).astype(np.int16)


class _Level:
    def __init__(self, orig, P, allowed, s, n, seed):
        self.s = s
        Ps = P if s == 1 else _pool(P.astype(np.uint8) * 100, s) >= 100
        self.ok = int(Ps.sum()) >= 12
        self.allowed = allowed if s == 1 else _pool(allowed.astype(np.uint8) * 100, s) >= 50
        ys, xs = np.nonzero(Ps)
        if len(xs) > n:
            i = np.sort(np.random.default_rng(seed).choice(len(xs), n, replace=False))
            ys, xs = ys[i], xs[i]
        self.xs, self.ys = xs.astype(np.float64), ys.astype(np.float64)
        self.ref = _pool(orig, s)[ys, xs]

    def scores(self, flat, H, W, c, th, txs, tys, tol):
        """Matching sampled pixels for each translation (txs[i], tys[i]) at rotation th (rad).
        A pixel mapped outside the allowed region never matches: a fit must stay where the part may go."""
        ct, st = np.cos(th), np.sin(th)
        rx = ct * (self.xs - c[0]) - st * (self.ys - c[1]) + c[0]
        ry = st * (self.xs - c[0]) + ct * (self.ys - c[1]) + c[1]
        X = np.rint(rx[None, :] + txs[:, None]).astype(np.int64)
        Y = np.rint(ry[None, :] + tys[:, None]).astype(np.int64)
        inside = (X >= 0) & (X < W) & (Y >= 0) & (Y < H)
        X, Y = np.clip(X, 0, W - 1), np.clip(Y, 0, H - 1)
        d = np.abs(flat[Y * W + X] - self.ref[None]).max(-1)
        return ((d <= tol) & inside & self.allowed[Y, X]).sum(1)


class RigidTrack:
    """Fits, in every frame, the rigid motion of one part: T(q) = Rot(theta) (q - c) + c + (tx, ty), c = the
    centroid of the part's visible pixels P in the original. The fit maximises the number of part pixels
    whose colour in the frame at T(q) matches orig[q] (within FIT_TOL per channel), so a few pixels left
    behind, hidden or recoloured do not pull it off. Coarse search on pooled images over rotation and
    translation, then a fine search at full resolution; each frame starts from the previous frame's fit and
    falls back to a global search when that matches poorly. Only numpy: deterministic and fast enough
    (about 1-3 s for 25 frames)."""

    def __init__(self, orig, P, allowed, th_max, reach):
        ys, xs = np.nonzero(P)
        self.c = np.array([xs.mean(), ys.mean()])
        self.n = len(xs)
        s = 8 if self.n > 30000 else 4 if self.n > 6000 else 2 if self.n > 1500 else 1
        self.coarse = _Level(orig, P, allowed, s, FIT_N[0], 0)
        if not self.coarse.ok:
            self.coarse = _Level(orig, P, allowed, 1, FIT_N[0], 0)
        self.fine = _Level(orig, P, allowed, 1, FIT_N[1], 1)
        self.th_max, self.reach = th_max, reach

    def _search(self, lev, flat, H, W, thetas, cx, cy, r, tol, prior):
        s = lev.s
        cs = (self.c + 0.5) / s - 0.5
        g = np.arange(-int(np.ceil(r / s)), int(np.ceil(r / s)) + 1, dtype=np.float64)
        TX, TY = np.meshgrid(g + round(cx / s), g + round(cy / s))
        TX, TY = TX.ravel(), TY.ravel()
        best = None
        for th in thetas:
            sc = lev.scores(flat, H, W, cs, np.deg2rad(th), TX, TY, tol).astype(np.float64)
            # ties go to the candidate nearest the prior
            sc -= 1e-3 * (np.abs(TX * s - prior[1]) + np.abs(TY * s - prior[2]) + abs(th - prior[0]))
            i = int(np.argmax(sc))
            if best is None or sc[i] > best[0]:
                best = (sc[i], float(th), float(TX[i] * s), float(TY[i] * s))
        return best

    def fit(self, frame, prev):
        H, W = frame.shape[:2]
        s = self.coarse.s
        fs = _pool(frame, s)
        flat_s, flat = fs.reshape(-1, 3), frame.astype(np.int16).reshape(-1, 3)
        cand = []
        th0, tx0, ty0 = prev
        b = self._search(self.coarse, flat_s, fs.shape[0], fs.shape[1], np.arange(th0 - 12, th0 + 12.01, 2.0),
                         tx0, ty0, 16, FIT_TOL * 1.5, prev)
        cand.append(b)
        fine = []
        for b in cand:
            f = self._search(self.fine, flat, H, W, np.arange(b[1] - 1.5, b[1] + 1.51, 0.5), b[2], b[3], s + 1,
                             FIT_TOL, b[1:])
            fine.append(f)
        best = max(fine, key=lambda f: f[0])
        if best[0] < 0.8 * len(self.fine.xs):  # lost track: search everywhere the part may go
            ths = np.arange(-self.th_max, self.th_max + 0.01, 2.0)
            b = self._search(self.coarse, flat_s, fs.shape[0], fs.shape[1], ths, 0, 0, self.reach, FIT_TOL * 1.5,
                             (0.0, 0.0, 0.0))
            f = self._search(self.fine, flat, H, W, np.arange(b[1] - 1.5, b[1] + 1.51, 0.5), b[2], b[3], s + 1,
                             FIT_TOL, b[1:])
            if f[0] > best[0]:
                best = f
        return (best[1], best[2], best[3], max(0.0, best[0]) / max(1, len(self.fine.xs)))

    def track(self, frames):
        out, prev = [], (0.0, 0.0, 0.0)
        for f in frames:
            T = self.fit(f, prev)
            out.append(T)
            if T[3] >= FIT_MIN:
                prev = T[:3]
        return out

    def apply(self, T, x, y):
        t = np.deg2rad(T[0])
        c = self.c
        return (np.cos(t) * (x - c[0]) - np.sin(t) * (y - c[1]) + c[0] + T[1],
                np.sin(t) * (x - c[0]) + np.cos(t) * (y - c[1]) + c[1] + T[2])


def part_groups(task_dir, target):
    """The independently moving pieces of the target: parts.png labels (1..n, one per part or mover, in the
    order of spec["parts"] / spec["pivots"]) if the task has it, else the whole target as one group."""
    p = Path(task_dir) / "parts.png"
    if p.exists():
        lab = np.array(Image.open(p))
        return [(lab == k) & target for k in range(1, int(lab.max()) + 1)]
    return [target]


def fit_limits(spec, region):
    """(max rotation in degrees, max translation in px) searched for a task's part."""
    kind, amp = spec.get("kind"), float(spec.get("amp", 0))
    th = 2 * amp + 10 if kind in ("rotate", "rotate_hat", "flutter") else 10.0
    ys, xs = np.nonzero(region)
    reach = max(xs.max() - xs.min(), ys.max() - ys.min()) / 2 if len(xs) else 50
    return min(th, 90.0), float(min(reach, 250))


def track_groups(frames, orig, fg0, region, groups, skull, spec):
    """[(group footprint P, RigidTrack or None, [T per frame] or None)] for every group."""
    th, reach = fit_limits(spec, region)
    out = []
    for g in groups:
        P = fg0 & region & g
        if skull is not None:
            P &= ~skull
        if P.sum() < FIT_MIN_PX:
            out.append((P, None, None))
            continue
        tr = RigidTrack(orig, P, region, th, reach)
        out.append((P, tr, tr.track(frames)))
    return out


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
        # changes outside the grown region, as a share of the pixels outside the allowed region
        outside = ~g1_region(allowed, target)
        worst = max((c & outside).sum() for c in ch) / (~allowed).sum()
        res["G1"] = dict(ok=bool(worst <= G1_MAX), value=round(float(worst), 5))
    if "G2" in checks:
        # count pieces inside the moving region only; baseline = original (or frame 0 if renderer noise adds pieces)
        mc = G2_MIN_CONTRAST
        base = max(blobs(fg0 & region, orig, mc), blobs(fgs[0] & region, frames[0], mc))
        worst = max(blobs(f & region, fr, mc) for f, fr in zip(fgs, frames))
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
