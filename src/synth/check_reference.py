"""Reference animator for synthetic tasks + driver that renders it in Chrome and grades it.

The synthetic reference is layer-exact: the scene's layers (back to front) are grouped into runs of consecutive
layers that share one motion (static, or a rotation about one pivot). The first static run is flattened onto
white as the base; every other run is an RGBA sprite. Unlike src/reference.py (which must cut a part out of a
flat image and white-fill the hole), occluded and occluding parts are restored exactly, so a correct animation
exists for every generated task. The page uses the same three.js template as src/reference.py.

Usage: python src/synth/check_reference.py [tasks_dir] [max_tasks] [workers] [start]
(results of successive chunks are merged into results/synth_reference.json)
Writes out/synth_ref/<id>/ (pages; gitignored) and results/synth_reference.json.
"""
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from graders import grade  # noqa: E402
from reference import PAGE as BASE_PAGE  # noqa: E402
from synth.scene import build_scene  # noqa: E402

assert "(L.one ? ph2 : ph)" in BASE_PAGE  # one-sided rotations (L.one) are part of the shared template
PAGE = BASE_PAGE
N_FRAMES = 25


def build_runs(sc):
    """[(mover index or None, RGBA full canvas uint8)] in draw order."""
    mover_of = {}
    for i, mv in enumerate(sc.task["movers"]):
        for p in mv["parts"]:
            mover_of[p] = i
    runs = []
    for L in sc.layers:
        k = mover_of.get(L.name)
        if not runs or runs[-1][0] != k:
            runs.append([k, Image.new("RGBA", (sc.width, sc.height), (0, 0, 0, 0))])
        runs[-1][1].alpha_composite(Image.fromarray(L.rgba), dest=(L.x0, L.y0))
    return [(k, im) for k, im in runs]


def split_base(sc):
    runs = build_runs(sc)
    base = Image.new("RGBA", (sc.width, sc.height), (255, 255, 255, 255))
    if runs and runs[0][0] is None:
        base.alpha_composite(runs.pop(0)[1])
    return base, runs


def write_page(sc, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    base, runs = split_base(sc)
    base.convert("RGB").save(out / "base.png")
    layers = []
    for i, (k, im) in enumerate(runs):
        im.save(out / f"layer{i}.png")
        if k is None:
            layers.append(dict(kind="static", amp=0, px=0, py=0, url=f"./layer{i}.png"))
        else:
            mv = sc.task["movers"][k]
            # pivot in continuous image coords; the template places the group at (px, -py)
            layers.append(dict(kind="rotate", amp=mv["amp"], one=mv["phase"] == "one", url=f"./layer{i}.png",
                               px=round(mv["pivot"][0], 2), py=round(mv["pivot"][1], 2)))
    cfg = dict(W=sc.width, H=sc.height, base="./base.png", layers=layers, whole=False, frozen=False, hole=False,
               noLoop=False)
    (out / "index.html").write_text(PAGE % {"cfg": json.dumps(cfg)})
    return out


def phase(mv, t):
    if mv["phase"] == "one":
        return 0.5 - 0.5 * np.cos(2 * np.pi * t / 2)
    return np.sin(2 * np.pi * t / 2)


def simulate(sc, n=N_FRAMES):
    """numpy/PIL stand-in for the browser render (nearest-neighbour rotation, same timing)."""
    base, runs = split_base(sc)
    frames = []
    for i in range(n):
        t = i * 2 / (n - 1)
        im = base.copy()
        for k, lay in runs:
            if k is not None:
                mv = sc.task["movers"][k]
                deg = mv["amp"] * phase(mv, t)
                if abs(deg) > 1e-9:
                    lay = lay.rotate(-deg, resample=Image.NEAREST, center=tuple(mv["pivot"]))
            im.alpha_composite(lay)
        frames.append(np.array(im.convert("RGB")))
    return np.stack(frames)


def simulate_grade(sc, task_dir):
    return grade(simulate(sc), task_dir)


def scene_for(spec):
    s = spec["synth"]
    return build_scene(s["scene_seed"], s["motion"])


def _worker(jobs, tasks_dir, q):
    from framecache import CachedRenderer
    from render import save_gif
    R = CachedRenderer()
    for tid in jobs:
        td = Path(tasks_dir) / tid
        spec = json.loads((td / "spec.json").read_text())
        sc = scene_for(spec)
        assert np.array_equal(sc.composite(), np.array(Image.open(td / "image.png").convert("RGB"))), tid
        d = write_page(sc, ROOT / "out/synth_ref" / tid)
        fr, err, logs = R.render(d, td, spec["width"], spec["height"])
        if fr is None:
            q.put((tid, {"error": err, "logs": logs[-5:]}))
            continue
        g = grade(fr, td)
        save_gif(fr, d / "anim.gif", 0.4)
        q.put((tid, g))
    R.close()


def main(tasks_dir=ROOT / "tasks_synth", max_tasks=None, workers=2, start=0):
    tasks_dir = Path(tasks_dir)
    ids = sorted(p.name for p in tasks_dir.iterdir() if (p / "spec.json").exists())
    ids = ids[start:start + max_tasks] if max_tasks else ids[start:]
    q = mp.Queue()
    ps = [mp.Process(target=_worker, args=(ids[i::workers], tasks_dir, q)) for i in range(workers)]
    for p in ps:
        p.start()
    res = {}
    for _ in ids:
        tid, g = q.get()
        res[tid] = g
        bad = "ERR " + g["error"] if "error" in g else ("PASS" if g["pass"] else
                                                        "FAIL " + ",".join(k for k, v in g.items() if k != "pass" and not v["ok"]))
        print(tid, bad, flush=True)
    for p in ps:
        p.join()
    out = ROOT / "results/synth_reference.json"
    tdir = str(tasks_dir.relative_to(ROOT)) if tasks_dir.is_relative_to(ROOT) else str(tasks_dir)
    if out.exists():  # merge with earlier chunks for the same task dir
        old = json.loads(out.read_text())
        if old.get("tasks_dir") == tdir:
            res = {**old["results"], **res}
    n_pass = sum(1 for g in res.values() if g.get("pass"))
    summary = dict(tasks_dir=tdir, checked=len(res), passed=n_pass, results=dict(sorted(res.items())))
    out.write_text(json.dumps(summary, indent=1))
    print(f"reference passed {n_pass}/{len(res)}")
    return summary


if __name__ == "__main__":
    a = sys.argv[1:]
    main(Path(a[0]) if a else ROOT / "tasks_synth", int(a[1]) if len(a) > 1 else None, int(a[2]) if len(a) > 2 else 2,
         int(a[3]) if len(a) > 3 else 0)
