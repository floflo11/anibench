"""What-if: would the recommended grader changes clear the too-strict failures and still catch the broken copies?

Re-implements three candidate variants of the checks (src/graders.py is untouched) and evaluates them on
(1) every alternate run that failed that check and (2) the reference and its targeted broken copy on the
same tasks (ref + center_pivot for G5, ref + missed_thumb for G2, ref + whole + wrong_part for G1):

  G1s  allowed region grown by ceil(0.075 * the target's larger extent) px (room for +-15% squash/stretch)
  G2o  blob count after a 3x3 binary opening of the foreground (thin halos and slivers no longer count)
  G2c  blob count ignoring pieces whose median contrast to white is < 80 (faint halos)
  G5b  change detection on images blurred with sigma 1.5 (texture shimmer is not displacement)
  G5t  the current G5 with G5_MAX = 0.30

    python3 src/alt_refs/whatif.py      # writes results/alt_refs/whatif.json
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import graders as G  # noqa: E402

RES = ROOT / "results" / "alt_refs"


def _blobs(fg, img=None, min_contrast=None):
    lab, n = ndimage.label(fg)
    if n == 0:
        return 0
    sizes = ndimage.sum(fg, lab, range(1, n + 1))
    keep = sizes >= G.MIN_BLOB
    if min_contrast is not None:
        con = (255 - img.astype(int)).max(-1)
        med = ndimage.median(con, lab, range(1, n + 1))
        keep &= med >= min_contrast
    return int(keep.sum())


def checks(frames, task_dir):
    task_dir = Path(task_dir)
    spec = json.loads((task_dir / "spec.json").read_text())
    orig = np.array(Image.open(task_dir / "image.png").convert("RGB"))
    allowed = G.load_mask(task_dir, "allowed.png")
    target = G.load_mask(task_dir, "target.png")
    out = {}
    ch = [G.changed(f, orig) for f in frames]
    ys, xs = np.nonzero(target)
    r = int(np.ceil(0.075 * max(np.ptp(xs) + 1, np.ptp(ys) + 1)))
    grown = ndimage.binary_dilation(allowed, iterations=r)
    out["G1s"] = dict(value=round(max((c & ~grown).sum() for c in ch) / (~allowed).sum(), 5), grow_px=r)
    out["G1s"]["ok"] = out["G1s"]["value"] <= G.G1_MAX
    op = np.ones((3, 3))
    fg0 = G.foreground(orig) & allowed
    fgs = [G.foreground(f) & allowed for f in frames]
    base = max(_blobs(ndimage.binary_opening(fg0, op)), _blobs(ndimage.binary_opening(fgs[0], op)))
    worst = max(_blobs(ndimage.binary_opening(f, op)) for f in fgs)
    out["G2o"] = dict(ok=worst <= base + spec.get("blob_allow", 0), value=worst, base=base)
    base = max(_blobs(fg0, orig, 80), _blobs(fgs[0], frames[0], 80))
    worst = max(_blobs(f, fr, 80) for f, fr in zip(fgs, frames))
    out["G2c"] = dict(ok=worst <= base + spec.get("blob_allow", 0), value=worst, base=base)
    blur = lambda a: ndimage.gaussian_filter(a.astype(float), (1.5, 1.5, 0))  # noqa: E731
    ob = blur(orig)
    chb = [ndimage.binary_opening(np.abs(blur(f) - ob).max(-1) > G.CHANGE_T, structure=np.ones((3, 3))) for f in frames]
    for name, cc, thr in (("G5b", chb, G.G5_MAX), ("G5t", ch, 0.30)):
        worst = 0.0
        for (x, y) in spec.get("pivots", []):
            dm = G.disc(orig.shape, x, y, G.G5_R) & target
            if dm.sum() < 30:
                continue
            worst = max(worst, max((c & dm).sum() for c in cc) / dm.sum())
        out[name] = dict(ok=worst <= thr, value=round(float(worst), 3))
    return out


def main():
    from alt_refs import build
    from reference import build_variant
    from render import Renderer, prepare
    raw = [json.loads(p.read_text()) for p in sorted((RES / "raw").glob("*/*.json"))]
    jobs = []
    for r in raw:
        for k in r.get("failed", []):
            jobs.append(("alt", r["variant"], r["task"], k))
    adm = json.loads((ROOT / "validation/admission.json").read_text())["tasks"]
    alt_tasks = {k: sorted({j[2] for j in jobs if j[3] == k}) for k in ("G1", "G2", "G5")}
    mut = {"G1": ["ref", "whole", "wrong_part"], "G2": ["ref", "missed_thumb"], "G5": ["ref", "center_pivot"]}
    for k, vs in mut.items():
        tasks = sorted(t for t in adm if k in adm[t]["kept"]) if k != "G1" else alt_tasks["G1"]
        for t in tasks:
            for v in vs:
                jobs.append(("ref", v, t, k))
    R = Renderer()
    res = []
    try:
        for kind, v, t, k in jobs:
            spec = json.loads((ROOT / "tasks" / t / "spec.json").read_text())
            d = ROOT / "out" / "whatif" / kind / v / t
            if kind == "alt":
                build(t, v, d)
            else:
                build_variant(spec, v, d)
            prepare(d, ROOT / "tasks" / t)
            fr, err, _ = R.render(d, spec["width"], spec["height"])
            if fr is None:
                print("ERR", kind, v, t, err)
                continue
            now = G.grade(fr, ROOT / "tasks" / t)
            w = checks(fr, ROOT / "tasks" / t)
            alts = {"G1": ["G1s"], "G2": ["G2o", "G2c"], "G5": ["G5b", "G5t"]}.get(k, [])
            rec = dict(kind=kind, variant=v, task=t, check=k, current=now.get(k), whatif={a: w[a] for a in alts})
            res.append(rec)
            print(kind, v, t, k, "now", now.get(k, {}).get("ok"), {a: (w[a]["ok"], w[a]["value"]) for a in alts}, flush=True)
    finally:
        R.close()
    (RES / "whatif.json").write_text(json.dumps(res, indent=1, default=lambda o: bool(o) if isinstance(o, np.bool_) else int(o)))


if __name__ == "__main__":
    main()
