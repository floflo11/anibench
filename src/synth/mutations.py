"""Broken copies of the synthetic reference animation (the same 10 mutation types as src/reference.py).

The synthetic reference is layer-exact (check_reference.py): the scene's layers are grouped into runs that share
one motion, the first static run is the base and every other run is an RGBA sprite. A broken copy edits those
runs, so everything it does not break stays exact:

  whole         the whole picture sways (root rotation), nothing is cut out
  missed_thumb  a 9 px disc at the far end of each mover (from its pivot) stays put as a static layer
  hole          the moving sprites disappear for part of the loop (static layers in front stay)
  frozen        nothing moves
  center_pivot  every mover rotates about the centroid of its own pixels instead of its joint
  no_loop       the motion runs one way and does not return
  wrong_part    a different, non-target part of the same character rotates instead
  detach_small  a 20-60 px piece at the far end of each mover stays put
  detach_tip    the far end (>= 80% of the reach) of each mover drifts 6 px away from it
  gap_seam      each mover is cut at its pivot: the parent-side stub stays put, the rest drifts 2 px out

A piece that stays put is drawn as a static layer just below its mover's run, like the raster copies, where
the piece stays in the base. oracle_split draws the part alone (its moving runs + the pieces left behind),
frame by frame, and counts its pieces: the ground truth of whether a detachment copy really comes apart.

    python3 src/validate.py all 2 --tasks-dir tasks_synth/sample --out validation/synth
"""
import json
import math
from pathlib import Path

import numpy as np
from PIL import Image

from graders import G2B_MIN, foreground, part_pieces
from reference import SEAM_PX, TIP_DRIFT, VARIANTS, away, far_end, seam_split, small_tip, tip_disc
from synth.check_reference import PAGE as REF_PAGE, phase
from synth.scene import build_scene

# hole: only the moving sprites vanish; a static layer in front of them (an arm across the body) stays
_HOLE = "if (CFG.hole && ph > 0.3) mesh.visible = false;"
assert _HOLE in REF_PAGE
PAGE = REF_PAGE.replace(_HOLE, "if (CFG.hole && ph > 0.3 && L.kind !== 'static') mesh.visible = false;")
DECOY_AMP = 20.0
N_FRAMES = 25


def variants_for(spec):
    return list(VARIANTS)  # every synthetic task rotates about a joint, so gap_seam applies too


def scene_for(spec):
    s = spec["synth"]
    return build_scene(s["scene_seed"], s["motion"])


def _runs(sc, movers):
    """[(mover index or None, RGBA full-canvas array)] in draw order, for the given movers."""
    mover_of = {p: i for i, mv in enumerate(movers) for p in mv["parts"]}
    runs = []
    for L in sc.layers:
        k = mover_of.get(L.name)
        if not runs or runs[-1][0] != k:
            runs.append([k, Image.new("RGBA", (sc.width, sc.height), (0, 0, 0, 0))])
        runs[-1][1].alpha_composite(Image.fromarray(L.rgba), dest=(L.x0, L.y0))
    return [(k, np.array(im)) for k, im in runs]


def _decoy(sc):
    """A non-target part of the same character to rotate instead (wrong_part): the largest visible part that
    is not a target, not attached to one and not the torso/legs, with its joint (or its top centre) as pivot."""
    t = sc.task
    pre = f"c{t['char']}_"
    skip = set(t["targets"]) | set(t.get("attach", []))
    best = None
    for L in sc.layers:
        n = L.name
        if not n.startswith(pre) or n in skip or any(w in n for w in ("torso", "leg", "shoe", "neck")):
            continue
        a = int(sc.visible_mask(n).sum())
        if a >= 300 and (best is None or a > best[0]):
            best = (a, n)
    if best is None:
        raise ValueError("no decoy part")
    n = best[1]
    j = sc.parts[n].joint if n in sc.parts else None
    if j is None:
        ys, xs = np.nonzero(sc.full_mask(n))
        j = (float(xs.mean()), float(ys.min()))
    return [dict(parts=[n], pivot=tuple(float(v) for v in j), amp=DECOY_AMP, phase="sym")]


def plan(spec, variant, sc=None):
    """(base RGB, [(RGBA layer, page params)], part_layer_flags) for a variant. part_layer_flags[i] is True for
    layers that belong to the moving part (its sprites and the pieces it leaves behind), for oracle_split."""
    sc = sc or scene_for(spec)
    movers = sc.task["movers"]
    if variant == "wrong_part":
        movers = _decoy(sc)
    runs = _runs(sc, movers)
    base = np.full((sc.height, sc.width, 4), 255, np.uint8)
    if runs and runs[0][0] is None:
        b = Image.fromarray(base)
        b.alpha_composite(Image.fromarray(runs.pop(0)[1]))
        base = np.array(b)
    if variant in ("whole", "frozen"):
        return sc.composite(), [], []
    fg = foreground(sc.composite())
    full = {}
    for k, _ in runs:
        if k is not None and k not in full:
            full[k] = np.any([sc.full_mask(p) for p in movers[k]["parts"]], axis=0)
    layers, is_part = [], []
    for k, im in runs:
        if k is None:
            layers.append((im, dict(kind="static", amp=0, px=0, py=0)))
            is_part.append(False)
            continue
        mv = movers[k]
        piv = tuple(mv["pivot"])
        m = full[k]
        if variant == "center_pivot":
            ys, xs = np.nonzero(m)
            piv = (float(xs.mean()), float(ys.mean()))
        L = dict(kind="rotate", amp=mv["amp"], one=mv["phase"] == "one", px=round(piv[0], 2), py=round(piv[1], 2))
        stay = drift = None
        if variant == "missed_thumb":
            stay = tip_disc(m, piv) & m
        elif variant == "detach_small":
            stay = small_tip(m, fg, piv)
            if stay is None:
                raise ValueError(f"{spec['id']}: no 20-60 px tip piece")
        elif variant == "detach_tip":
            tip = far_end(m, piv)
            drift = (tip, away(tip, piv) * TIP_DRIFT)
        elif variant == "gap_seam":
            stub, rest, a = seam_split(m, piv)
            stay, drift = stub, (rest, a * SEAM_PX)
        moving = im.copy()
        if stay is not None:
            piece = np.zeros_like(im)
            piece[stay] = im[stay]
            moving[stay] = 0
            layers.append((piece, dict(kind="static", amp=0, px=0, py=0)))
            is_part.append(True)
        if drift is not None:
            dm, off = drift
            dl = np.zeros_like(im)
            dl[dm] = moving[dm]
            moving[dm] = 0
            if moving[..., 3].any():
                layers.append((moving, L))
                is_part.append(True)
            layers.append((dl, dict(L, off=[round(float(c), 3) for c in off])))
            is_part.append(True)
        else:
            layers.append((moving, L))
            is_part.append(True)
    return base[..., :3], layers, is_part


def build_variant(spec, variant, out, task_dir=None):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    base, layers, _ = plan(spec, variant)
    Image.fromarray(base).save(out / "base.png")
    params = []
    for i, (im, L) in enumerate(layers):
        Image.fromarray(im).save(out / f"layer{i}.png")
        params.append(dict(L, url=f"./layer{i}.png"))
    cfg = dict(W=spec["width"], H=spec["height"], base="./base.png", layers=params, whole=variant == "whole",
               frozen=variant == "frozen", hole=variant == "hole", noLoop=variant == "no_loop")
    (out / "index.html").write_text(PAGE % {"cfg": json.dumps(cfg)})
    return out


def _place(im, L, t):
    """Where the page puts an RGBA layer at time t (PIL nearest rotation about the pivot, then the drift)."""
    if L["kind"] == "static":
        return im
    ph = phase(dict(phase="one" if L.get("one") else "sym"), t)
    off = L.get("off", (0.0, 0.0))
    ph2 = 0.5 - 0.5 * math.cos(math.pi * t)
    return np.array(Image.fromarray(im).rotate(-L["amp"] * ph, resample=Image.NEAREST, center=(L["px"], L["py"]),
                                               translate=(off[0] * ph2, off[1] * ph2)))


def oracle_split(spec, variant, n_frames=N_FRAMES):
    """dict(split, base, worst): does the part, drawn alone, come apart in this copy? (see reference.oracle_split)"""
    _, layers, is_part = plan(spec, variant)
    H, W = spec["height"], spec["width"]
    none = np.zeros((H, W), bool)
    every = np.ones((H, W), bool)

    def pieces_at(t):
        canvas = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        for (im, L), p in zip(layers, is_part):
            if p:
                canvas.alpha_composite(Image.fromarray(_place(im, L, t)))
        return part_pieces(foreground(np.array(canvas.convert("RGB"))), none, every, G2B_MIN)

    n0 = pieces_at(0.0)
    worst = max(pieces_at(i * 2 / (n_frames - 1)) for i in range(n_frames))
    return dict(split=bool(worst > n0), base=int(n0), worst=int(worst))
