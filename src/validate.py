"""Render every reference/broken variant and grade it. Writes validation/results.json + table.

Build the variant pages first with `python3 src/reference.py`, then
`python3 src/validate.py [T01,T02,...] [workers]`, then `python3 src/admission.py`.
Every variant is graded with all candidate checks (graders.candidate_checks), not the admitted
list in spec.json, so that admission is decided afresh on each run. A run limited to some tasks
merges into the existing results.json.
"""
import json, sys, multiprocessing as mp
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# the checks each broken copy is meant to trip (a copy is caught if any of those that apply fails)
EXPECT = {"whole": ["G1"], "missed_thumb": ["G2", "G2b"], "hole": ["G3"], "frozen": ["G4"],
          "center_pivot": ["G5"], "no_loop": ["G6"], "wrong_part": ["G1", "G4"],
          "detach_small": ["G2", "G2b"], "detach_tip": ["G2", "G2b"], "gap_seam": ["G2", "G2b"]}
GIF_VARIANTS = ("ref", "missed_thumb", "center_pivot", "hole")
# copies whose part may or may not really come apart; reference.oracle_split says which
SPLIT_VARIANTS = ("missed_thumb", "detach_small", "detach_tip", "gap_seam")


def worker(jobs, q):
    from render import save_gif
    from framecache import CachedRenderer
    from graders import candidate_checks, grade
    from reference import oracle_split
    R = CachedRenderer()
    for tid, v in jobs:
        d = ROOT / "validation" / tid / v
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        fr, err, logs = R.render(d, ROOT / "tasks" / tid, spec["width"], spec["height"])
        if fr is None:
            q.put((tid, v, {"error": err, "logs": logs[-5:]}))
            continue
        g = grade(fr, ROOT / "tasks" / tid, checks=candidate_checks(spec))
        if v in SPLIT_VARIANTS:
            g["oracle"] = oracle_split(spec, v)
        if v in GIF_VARIANTS:
            save_gif(fr, d / "anim.gif", 0.4)
        q.put((tid, v, g))
    R.close()


def main(n=2, only=None):
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    from reference import variants_for
    jobs = [(s["id"], v) for s in idx if s["graders"] for v in variants_for(s) if (only is None or s["id"] in only)]
    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(jobs[i::n], q)) for i in range(n)]
    for p in ps: p.start()
    out = ROOT / "validation/results.json"
    res = json.loads(out.read_text()) if (only is not None and out.exists()) else {}
    for tid in (only or []):
        res[tid] = {}
    for _ in jobs:
        tid, v, g = q.get()
        res.setdefault(tid, {})[v] = g
        print(tid, v, "ERR" if "error" in g else ("PASS" if g["pass"] else "fail " + ",".join(k for k, x in g.items() if k not in ("pass", "oracle") and not x["ok"])), flush=True)
    for p in ps: p.join()
    out.write_text(json.dumps(dict(sorted(res.items())), indent=1))
    return res

if __name__ == "__main__":
    only = sys.argv[1].split(",") if len(sys.argv) > 1 and sys.argv[1] != "all" else None
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    main(n=n, only=only)
