"""Render every reference/broken variant and grade it. Writes validation/results.json + table."""
import json, sys, multiprocessing as mp
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

EXPECT = {"whole": ["G1"], "missed_thumb": ["G2"], "hole": ["G3"], "frozen": ["G4"],
          "center_pivot": ["G5"], "no_loop": ["G6"], "wrong_part": ["G1", "G4"]}


def worker(jobs, q):
    from render import Renderer, prepare, save_gif
    from graders import grade
    R = Renderer()
    for tid, v in jobs:
        d = ROOT / "validation" / tid / v
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        prepare(d, ROOT / "tasks" / tid)
        fr, err, logs = R.render(d, spec["width"], spec["height"])
        if fr is None:
            q.put((tid, v, {"error": err, "logs": logs[-5:]}))
            continue
        g = grade(fr, ROOT / "tasks" / tid)
        if v in ("ref", "missed_thumb", "center_pivot"):
            save_gif(fr, d / "anim.gif", 0.4)
        q.put((tid, v, g))
    R.close()


def main(n=2, only=None):
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    from reference import VARIANTS
    jobs = [(s["id"], v) for s in idx if s["graders"] for v in VARIANTS if (only is None or s["id"] in only)]
    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(jobs[i::n], q)) for i in range(n)]
    for p in ps: p.start()
    res = {}
    for _ in jobs:
        tid, v, g = q.get()
        res.setdefault(tid, {})[v] = g
        print(tid, v, "ERR" if "error" in g else ("PASS" if g["pass"] else "fail " + ",".join(k for k, x in g.items() if k != "pass" and not x["ok"])), flush=True)
    for p in ps: p.join()
    (ROOT / "validation/results.json").write_text(json.dumps(res, indent=1))
    return res

if __name__ == "__main__":
    only = sys.argv[1].split(",") if len(sys.argv) > 1 else None
    main(only=only)
