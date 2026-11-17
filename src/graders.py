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
G5_MAX = 0.30      # max fraction of the part's pixels at the joint that may change (v2: 0.20; v3: 0.30, the
                   # smallest center-pivot value caught was 0.35, results/alt_refs/whatif.json)
G5_DISP = 4.0      # v3: px the fitted joint may move; a joint that stays put passes even if its texture shimmers
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


G2C_DMIN = 4.0     # px: footprint pixels the fitted motion moves at least this far must have moved
G2C_STILL = 3      # max per-channel difference for a pixel to count as untouched (left exactly as it was)
G2C_TOL = 2        # px of slack around the fitted part (fit and resampling error)
G3_MIN_AREA = 400  # px: G3 normalises by max(part area, this): tiny parts are not over-sensitive, and T07's
                   # earrings (449 px) still lose more than half their area in the hole copy (1000 hid it: 0.42)

# ---- rigid motion of the part --------------------------------------------------------------------
FIT_TOL = 24        # per-channel difference within which a part pixel "matches" its moved original
FIT_MIN = 0.5       # a frame's fit is trusted (G2c, G5) when at least this share of the part's pixels match
FIT_SEEN = 0.25     # ... and, for G3's occlusion credit, when this share match and
FIT_EXPLAINED = 0.7 # this share match or sit behind unchanged scenery
FIT_HIDDEN_W = 0.25 # score weight of a pixel that may be hidden behind scenery (a match scores 1)
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


def _edges(img):
    """Pixels whose colour differs by more than CHANGE_T (some channel) from one of their 8 neighbours:
    outlines, texture and the part's border. Only these pin the fit down: inside a flat-coloured area
    every small shift matches equally well."""
    a = img.astype(np.int16)
    e = np.zeros(a.shape[:2], bool)
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        d = np.abs(a - np.roll(a, (dy, dx), (0, 1))).max(-1) > CHANGE_T
        e |= d | np.roll(d, (-dy, -dx), (0, 1))
    return e


class _Level:
    """The part's sampled pixels at one resolution (s x s pooling)."""

    def __init__(self, orig, P, allowed, scenery, s, n, seed):
        self.s = s
        pool = (lambda m, q: m) if s == 1 else (lambda m, q: _pool(m.astype(np.uint8) * 100, s) >= q)
        Ps = pool(P, 100)
        self.ok = int(Ps.sum()) >= 12
        self.allowed = pool(allowed, 50)
        self.scenery = pool(scenery, 50)
        o = _pool(orig, s)
        self.orig = o.reshape(-1, 3)
        # match on informative pixels: the part's own pixels on an edge (or touching its border)
        inner = ndimage.binary_erosion(Ps, structure=EIGHT)
        info = Ps & (_edges(o) | ~inner)
        if info.sum() >= 40:
            Ps = info
        ys, xs = np.nonzero(Ps)
        if len(xs) > n:
            i = np.sort(np.random.default_rng(seed).choice(len(xs), n, replace=False))
            ys, xs = ys[i], xs[i]
        self.xs, self.ys = xs.astype(np.float64), ys.astype(np.float64)
        self.ref = o[ys, xs]

    def scores(self, flat, still, H, W, c, th, txs, tys, tol):
        """(matched, hidden) sampled pixels for each translation (txs[i], tys[i]) at rotation th (rad).
        matched: the frame shows the part's colour where the pixel lands. hidden: it lands on non-target scenery
        that is unchanged in the frame, which may be in front of the part. A pixel mapped outside the allowed
        region is neither: a fit must stay where the part may go."""
        ct, st = np.cos(th), np.sin(th)
        rx = ct * (self.xs - c[0]) - st * (self.ys - c[1]) + c[0]
        ry = st * (self.xs - c[0]) + ct * (self.ys - c[1]) + c[1]
        X = np.rint(rx[None, :] + txs[:, None]).astype(np.int64)
        Y = np.rint(ry[None, :] + tys[:, None]).astype(np.int64)
        inside = (X >= 0) & (X < W) & (Y >= 0) & (Y < H)
        X, Y = np.clip(X, 0, W - 1), np.clip(Y, 0, H - 1)
        ok = inside & self.allowed[Y, X]
        i = Y * W + X
        match = (np.abs(flat[i] - self.ref[None]).max(-1) <= tol) & ok
        hid = ~match & ok & still[i] & self.scenery[Y, X]
        return match.sum(1), hid.sum(1)


class RigidTrack:
    """Fits, in every frame, the rigid motion of one part: T(q) = Rot(theta) (q - c) + c + (tx, ty), c = the
    centroid of the part's visible pixels P in the original.

    Score of a pose: the part's sampled pixels whose colour in the frame at T(q) matches orig[q] (within FIT_TOL
    per channel), plus FIT_HIDDEN_W for each that lands on unchanged non-target scenery (the part may be behind
    it: occlusion). Matching is robust, so a few pixels left behind, hidden or recoloured do not pull the fit
    off. Only pixels on edges or texture are sampled, since inside a flat colour any small shift matches.
    Coarse search on pooled images over rotation and translation, then a fine search at full resolution; each
    frame starts from the previous frame's pose and falls back to a global search when that matches poorly.
    Each pose comes with the shares of sampled pixels matched and hidden. Only numpy: deterministic, ~1-3 s for
    25 frames."""

    def __init__(self, orig, P, allowed, scenery, th_max, reach):
        ys, xs = np.nonzero(P)
        self.c = np.array([xs.mean(), ys.mean()])
        self.n = len(xs)
        self.orig = orig
        s = 8 if self.n > 30000 else 4 if self.n > 6000 else 2 if self.n > 1500 else 1
        self.coarse = _Level(orig, P, allowed, scenery, s, FIT_N[0], 0)
        if not self.coarse.ok:
            self.coarse = _Level(orig, P, allowed, scenery, 1, FIT_N[0], 0)
        self.fine = _Level(orig, P, allowed, scenery, 1, FIT_N[1], 1)
        self.th_max, self.reach = th_max, reach

    def _search(self, lev, flat, still, H, W, thetas, cx, cy, r, tol, prior, step=1):
        s = lev.s
        cs = (self.c + 0.5) / s - 0.5
        k = int(np.ceil(r / s))
        g = np.arange(-k, k + 1, step, dtype=np.float64)
        TX, TY = np.meshgrid(g + round(cx / s), g + round(cy / s))
        TX, TY = TX.ravel(), TY.ravel()
        best = None
        for th in thetas:
            m, h = lev.scores(flat, still, H, W, cs, np.deg2rad(th), TX, TY, tol)
            sc = m + FIT_HIDDEN_W * h
            # ties go to the candidate nearest the prior
            sc = sc - 1e-3 * (np.abs(TX * s - prior[1]) + np.abs(TY * s - prior[2]) + abs(th - prior[0]))
            i = int(np.argmax(sc))
            if best is None or sc[i] > best[0]:
                best = (sc[i], float(th), float(TX[i] * s), float(TY[i] * s), int(m[i]), int(h[i]))
        return best

    def fit(self, frame, prev):
        H, W = frame.shape[:2]
        s = self.coarse.s
        fs = _pool(frame, s)
        hs, ws = fs.shape[:2]
        flat_s, flat = fs.reshape(-1, 3), frame.astype(np.int16).reshape(-1, 3)
        still_s = np.abs(flat_s - self.coarse.orig).max(-1) <= FIT_TOL
        still = np.abs(flat - self.fine.orig).max(-1) <= FIT_TOL
        n = len(self.fine.xs)

        def refine(b):
            return self._search(self.fine, flat, still, H, W, np.arange(b[1] - 1.5, b[1] + 1.51, 0.5), b[2], b[3],
                                s + 1, FIT_TOL, b[1:4])
        th0, tx0, ty0 = prev
        best = refine(self._search(self.coarse, flat_s, still_s, hs, ws, np.arange(th0 - 12, th0 + 12.01, 2.0),
                                   tx0, ty0, 16, FIT_TOL * 1.5, prev))
        if best[4] < (FIT_MIN + 0.15) * n:  # lost track: search everywhere the part may go
            step = max(1, int(np.ceil(self.reach / s / 20)))  # at most ~41 x 41 coarse translations
            b = self._search(self.coarse, flat_s, still_s, hs, ws, np.arange(-self.th_max, self.th_max + 0.01, 3.0),
                             0, 0, self.reach, FIT_TOL * 1.5, (0.0, 0.0, 0.0), step)
            b = self._search(self.coarse, flat_s, still_s, hs, ws, np.arange(b[1] - 3, b[1] + 3.01, 1.0), b[2], b[3],
                             step * s, FIT_TOL * 1.5, b[1:4])
            f = refine(b)
            if f[0] > best[0]:
                best = f
        return (best[1], best[2], best[3], best[4] / max(1, n), best[5] / max(1, n))

    def track(self, frames):
        """[(theta, tx, ty, matched share, hidden share)] per frame."""
        out, prev = [], (0.0, 0.0, 0.0)
        for f in frames:
            T = self.fit(f, prev)
            out.append(T)
            if T[3] >= FIT_SEEN:
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
    target = np.any(groups, axis=0)
    scenery = ((255 - orig.astype(np.int16)).max(-1) > G2B_BG) & ~target
    out = []
    for g in groups:
        P = fg0 & region & g
        if skull is not None:
            P &= ~skull
        if P.sum() < FIT_MIN_PX:
            out.append((P, None, None))
            continue
        tr = RigidTrack(orig, P, region, scenery, th, reach)
        out.append((P, tr, tr.track(frames)))
    return out


def _moved(tr, T, P):
    """Original footprint pixels (xs, ys) of P and where the fitted motion T puts them (X, Y)."""
    ys, xs = np.nonzero(P)
    X, Y = tr.apply(T, xs.astype(np.float64), ys.astype(np.float64))
    return xs, ys, X, Y


def _cover(shape, X, Y, tol):
    """Pixels the moved part covers (forward-mapped, holes closed), grown by tol px."""
    H, W = shape
    Xi, Yi = np.rint(X).astype(np.int64), np.rint(Y).astype(np.int64)
    ok = (Xi >= 0) & (Xi < W) & (Yi >= 0) & (Yi < H)
    cov = np.zeros(shape, bool)
    cov[Yi[ok], Xi[ok]] = True
    cov = ndimage.binary_closing(cov, structure=EIGHT)
    return ndimage.binary_dilation(cov, iterations=tol) if tol else cov


def remnant(P, tr, T, untouched, mask=False):
    """Size of the largest piece left behind: footprint pixels that the fitted motion moves >= G2C_DMIN px away,
    that the moved part does not cover (G2C_TOL px slack), but that are untouched in the frame. Pieces need
    G2B_MIN px and a body (G2B_CORE px after a 3x3 erosion). mask=True: (size, mask of every such piece)."""
    xs, ys, X, Y = _moved(tr, T, P)
    disp = np.zeros(P.shape)
    disp[ys, xs] = np.hypot(X - xs, Y - ys)
    cand = P & ~_cover(P.shape, X, Y, G2C_TOL) & (disp >= G2C_DMIN) & untouched
    lab, n = ndimage.label(cand, structure=EIGHT)
    best = 0
    out = np.zeros_like(P) if mask else None
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        pc = lab[sl] == i
        if pc.sum() >= G2B_MIN and ndimage.binary_erosion(pc, structure=EIGHT).sum() >= G2B_CORE:
            best = max(best, int(pc.sum()))
            if mask:
                out[sl] |= pc
    return (best, out) if mask else best


def presence(P, tr, T, frame, orig, still, scenery, trusted):
    """(matched, hidden, lost) footprint pixels at the fitted pose T: matched = the frame shows the part's own
    colour there; hidden = the frame shows unchanged non-target scenery there, which may be in front of the part
    (occlusion; only counted when the fit is trusted); lost = everything else."""
    xs, ys, X, Y = _moved(tr, T, P)
    H, W = P.shape
    Xi, Yi = np.rint(X).astype(np.int64), np.rint(Y).astype(np.int64)
    ok = (Xi >= 0) & (Xi < W) & (Yi >= 0) & (Yi < H)
    Xc, Yc = np.clip(Xi, 0, W - 1), np.clip(Yi, 0, H - 1)
    d = np.abs(frame[Yc, Xc].astype(np.int16) - orig[ys, xs].astype(np.int16)).max(-1)
    match = ok & (d <= FIT_TOL)
    hidden = ok & ~match & still[Yc, Xc] & scenery[Yc, Xc] if trusted else np.zeros_like(match)
    return int(match.sum()), int(hidden.sum()), int((~match & ~hidden).sum())


def candidate_checks(spec):
    """Every check that could apply to a task, before admission: the task's original list plus
    G2b (which applies to every scored task, hats included: a lifted hat must stay one piece)."""
    ks = list(spec.get("graders_all", spec["graders"]))
    for new, after in (("G2b", "G2"), ("G2c", "G2b")):
        if ks and new not in ks:
            i = ks.index(after) + 1 if after in ks else next((j for j, k in enumerate(ks) if k > new), len(ks))
            ks.insert(i, new)
    return ks


def disc(shape, x, y, r):
    yy, xx = np.ogrid[:shape[0], :shape[1]]
    return (xx - x) ** 2 + (yy - y) ** 2 <= r * r


def load_mask(task_dir, name):
    p = Path(task_dir) / name
    return (np.array(Image.open(p)) > 127) if p.exists() else None


def g2c(frames, orig, tracks):
    """G2c Residual: no piece of the part may stay behind while the part moves on.

    G2b sees a piece left behind only once the moving part has come apart from it. A tip that stays put while
    the rest swings past it can touch the moving part in every frame (the missed-thumb copies on T03, T05, T21,
    the earring on T07, the heads on T09-T11), so the part never splits. G2c fits the part's rigid motion in
    every frame (RigidTrack) and looks for a left-behind piece directly: original footprint pixels that the
    fitted motion carries >= G2C_DMIN px away, that the moved part does not cover (G2C_TOL px slack), but that
    are still untouched in the frame (every channel within G2C_STILL of the original). A piece of >= G2B_MIN px
    with a body fails the check.
      - Only frames whose fit is trusted (>= FIT_MIN of the part's sampled pixels matched) are looked at, so a
        part that vanishes (G3's job) or never moves (G4's) passes here.
      - A ghost (the part drawn twice, the original left in place under the moving copy) fails: its original
        stays untouched where the fit says the part has left.
    Known blind spots and false alarms: the fit is rigid, so a strongly stretched part is only roughly followed;
    content revealed behind the part that has exactly the part's colours (layer-exact synthetic references:
    a dark head under a dark hat) looks untouched and counts as left behind; the reference fails G2c there and
    admission drops it for that task. Parts with fewer than FIT_MIN_PX visible pixels are not fitted."""
    worst, at = 0, 0
    for t, f in enumerate(frames):
        untouched = np.abs(f.astype(np.int16) - orig.astype(np.int16)).max(-1) <= G2C_STILL
        for P, tr, Ts in tracks:
            if tr is None or Ts[t][3] < FIT_MIN:
                continue
            r = remnant(P, tr, Ts[t], untouched)
            if r > worst:
                worst, at = r, t
    return dict(ok=bool(worst == 0), value=int(worst), frame=int(at))


def g3_area(frames, orig, fg0, fgs, raw, region, target, skull, scenery0, tracks, spec):
    """G3 Area (v3): (loss, gain), each a share of max(part area, G3_MIN_AREA).

    v2 counted any change in the region's net foreground as damage, so a part that legitimately swung in front
    of or behind another part failed (47 synthetic seeds were rejected, mostly occluded parts), and tiny parts
    (T07's earrings, 345 px) failed on a few dozen pixels. v3 measures the part itself:
      loss: in each frame, the smaller of two counts of the part's missing pixels:
        - fitted: at the part's fitted pose (RigidTrack), footprint pixels that are neither the part's own colour
          (matched) nor unchanged non-target scenery that may be in front of it (hidden: occlusion, credited only
          when the fit is trusted: >= FIT_SEEN matched and >= FIT_EXPLAINED matched or hidden). A part with no fit
          (fewer than FIT_MIN_PX pixels) counts its footprint pixels that turned into blank background.
        - visible: the drop in the part's pixel count (part_pixels: footprint or changed foreground in the region).
        The fitted count is blind to deformation (a stretched part no longer matches a rigid pose), the visible
        count to occlusion; a part that is really gone (the hole copy) is missing in both.
      gain: net new foreground in the region beyond what the part may reveal of itself: spec["hidden_px"], the
        part's pixels hidden behind other parts in the image (synthetic tasks know it exactly; 0 for raster
        images), so an arm swinging out from behind the torso may grow by what was hidden. Drawing the part
        twice or bigger is gain.
    Normalising by max(area, G3_MIN_AREA) keeps parts of a few hundred pixels (synthetic fingers) from failing on a
    small wobble; v2's net-foreground measure needed max(area, 1000) for T07's earrings, but the fitted loss does
    not (T07 reference 0.23 of its own 449 px, hole copy 0.93)."""
    loss = 0.0
    P_all = 0
    lost_t = np.zeros(len(frames))
    for g, (P, tr, Ts) in enumerate(tracks):
        P_all += int(P.sum())
        if tr is None:  # no fit: the footprint pixels that turned into blank background are lost
            for t, f in enumerate(fgs):
                lost_t[t] += int((P & ~f).sum())
            continue
        for t, f in enumerate(frames):
            T = Ts[t]
            trusted = T[3] >= FIT_SEEN and T[3] + T[4] >= FIT_EXPLAINED
            _, _, lost = presence(P, tr, T, f, orig, ~raw[t], scenery0 & ~target, trusted)
            lost_t[t] += lost
    # the same loss seen without the fit: the part's pixels (footprint or changed foreground, as G2b isolates the
    # part) that are gone. A deformed (squashed, stretched) part is all there but no longer matches a rigid pose;
    # an occluded part matches but its hidden pixels are not visible. Count a loss only when both views see it.
    A0 = int((fg0 & region & target & (~skull if skull is not None else True)).sum())
    pix_t = np.array([max(0, A0 - int(part_pixels(f, c, region, target, skull).sum())) for f, c in zip(fgs, raw)])
    loss = float(np.minimum(lost_t, pix_t).max()) / max(P_all, G3_MIN_AREA) if len(frames) else 0.0
    area0 = int((fg0 & region).sum())
    tarea = int((fg0 & target).sum())
    net = max(int((f & region).sum()) - area0 for f in fgs)
    gain = max(0, net - int(spec.get("hidden_px", 0))) / max(tarea, G3_MIN_AREA)
    return loss, gain


def g5_pivot(ch, orig, target, pivots, tracks):
    """G5 Pivot (v3): the part must turn about its joint.

    frac: the share of the part's pixels within G5_R px of the pivot that change (v2's measure), now allowed up
    to G5_MAX = 0.30. On textured joints (T08's hair, T04's lace) a correct rotation moves those pixels only
    2-4 px, but high-frequency texture turns that into 26-50% changed pixels, as much as a center pivot gives
    elsewhere. So in the frames where frac > G5_MAX, the pivot point is carried along by the part's fitted motion
    (RigidTrack): disp = the largest distance it moves there. The displacement only ever rescues: a pivot fails
    when frac > G5_MAX unless the fit is trusted in each of those frames and keeps the joint within G5_DISP px.
    A rigid fit can lock onto a look-alike neighbour (synthetic fingers), so letting it fail a joint on its own
    would add false fails. value = frac (as in v2); disp (px, over the frames that needed it) alongside."""
    worst_frac, worst_disp, ok = 0.0, None, True
    for i, (x, y) in enumerate(pivots):
        dm = disc(orig.shape, x, y, G5_R) & target
        if dm.sum() < 30:
            continue
        fr_t = [(c & dm).sum() / dm.sum() for c in ch]
        frac = max(fr_t)
        worst_frac = max(worst_frac, frac)
        if frac <= G5_MAX:
            continue
        # the joint's pixels changed too much: a fail, unless the fit is trusted in every such frame and shows
        # the joint itself staying within G5_DISP px there
        k = i if len(tracks or []) == len(pivots) else 0
        P, tr, Ts = tracks[k] if tracks else (None, None, None)
        bad = [t for t, f in enumerate(fr_t) if f > G5_MAX]
        disp = None
        if tr is not None and all(Ts[t][3] >= FIT_MIN for t in bad):
            disp = max(float(np.hypot(*(np.array(tr.apply(Ts[t], x, y)) - (x, y)))) for t in bad)
            worst_disp = disp if worst_disp is None else max(worst_disp, disp)
        ok &= disp is not None and disp <= G5_DISP
    return dict(ok=bool(ok), value=round(float(worst_frac), 3), frac=round(float(worst_frac), 3),
                disp=None if worst_disp is None else round(float(worst_disp), 2))


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
    raw = [raw_changed(f, orig) for f in frames] if {"G2b", "G2c", "G3"} & set(checks) else None
    scenery0 = (255 - orig.astype(np.int16)).max(-1) > G2B_BG
    tracks = None
    if {"G2c", "G3", "G5"} & set(checks):
        tracks = track_groups(frames, orig, fg0, region, part_groups(task_dir, target), skull, spec)
    if "G2b" in checks:
        res["G2b"] = g2b(fgs, raw, fg0, region, target, skull, scenery0)
    if "G2c" in checks:
        res["G2c"] = g2c(frames, orig, tracks)
    if "G3" in checks:
        loss, gain = g3_area(frames, orig, fg0, fgs, raw, region, target, skull, scenery0, tracks, spec)
        dev = max(loss, gain)
        ok = dev <= spec["area_tol"]
        extra = dict(loss=round(float(loss), 4), gain=round(float(gain), 4))
        if skull is not None:
            keep = min((f & skull).sum() / max(1, (fg0 & skull).sum()) for f in fgs)
            extra["skull_keep"] = round(float(keep), 3)
            ok = ok and keep >= SKULL_KEEP
        res["G3"] = dict(ok=bool(ok), value=round(float(dev), 4), **extra)
    if "G4" in checks:
        peak = max((c & target).sum() for c in ch) / max(1, target.sum())
        res["G4"] = dict(ok=bool(peak >= G4_MIN), value=round(float(peak), 3))
    if "G5" in checks:
        res["G5"] = g5_pivot(ch, orig, target, spec["pivots"], tracks)
    if "G6" in checks:
        loop = changed(frames[0], frames[-1]).mean()
        o = ch[0].mean()
        res["G6"] = dict(ok=bool(loop <= G6_LOOP and o <= G6_ORIG), loop=round(float(loop), 5), first_vs_orig=round(float(o), 5))
    res["pass"] = bool(all(v["ok"] for v in res.values())) if res else None
    return res
