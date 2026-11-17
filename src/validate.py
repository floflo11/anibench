"""Render every reference/broken variant and grade it. Writes a results JSON (default validation/results.json).

Raster tasks (tasks/): build the variant pages first with `python3 src/reference.py`, then
`python3 src/validate.py [T01,T02,...|all] [workers]`, then `python3 src/admission.py`.
Synthetic tasks: `python3 src/validate.py all 2 --tasks-dir tasks_synth --out validation/synth
--results validation/results_synth.json [--sample 40]`; their pages (src/synth/mutations.py) are built here.
Every variant is graded with all candidate checks (graders.candidate_checks), not the admitted list in
spec.json, so that admission is decided afresh on each run. A run limited to some tasks merges into the
existing results file. Frames come from the frame cache (src/framecache.py) when the page is unchanged.
"""
import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# the checks each broken copy is meant to trip (a copy is caught if any of those that apply fails)
EXPECT = {"whole": ["G1"], "missed_thumb": ["G2", "G2b", "G2c"], "hole": ["G3"], "frozen": ["G4"],
          "center_pivot": ["G5"], "no_loop": ["G6"], "wrong_part": ["G1", "G4"],
          "detach_small": ["G2", "G2b", "G2c"], "detach_tip": ["G2", "G2b", "G2c"], "gap_seam": ["G2", "G2b", "G2c"]}
GIF_VARIANTS = ("ref", "missed_thumb", "center_pivot", "hole")
# copies whose part may or may not really come apart; reference.oracle_split says which
SPLIT_VARIANTS = ("missed_thumb", "detach_small", "detach_tip", "gap_seam")


def is_synth(spec):
    return "synth" in spec


def variants(spec):
    if is_synth(spec):
        from synth.mutations import variants_for
    else:
        from reference import variants_for
    return variants_for(spec)


def worker(jobs, tasks_dir, out_dir, gifs, q):
    from framecache import CachedRenderer
    from graders import candidate_checks, grade
    from render import save_gif
    R = CachedRenderer()
    for tid, v in jobs:
        td = tasks_dir / tid
        d = out_dir / tid / v
        spec = json.loads((td / "spec.json").read_text())
        try:
            if is_synth(spec):
                from synth.mutations import build_variant, oracle_split
                build_variant(spec, v, d)
            else:
                from reference import oracle_split
            fr, err, logs = R.render(d, td, spec["width"], spec["height"])
        except ValueError as e:  # a copy that cannot be made for this task (e.g. no 20-60 px tip)
            q.put((tid, v, {"error": f"BUILD: {e}", "logs": []}))
            continue
        if fr is None:
            q.put((tid, v, {"error": err, "logs": logs[-5:]}))
            continue
        g = grade(fr, td, checks=candidate_checks(spec))
        if v in SPLIT_VARIANTS:
            g["oracle"] = oracle_split(spec, v)
        if gifs and v in GIF_VARIANTS:
            save_gif(fr, d / "anim.gif", 0.4)
        q.put((tid, v, g))
    R.close()


def main(n=2, only=None, tasks_dir=ROOT / "tasks", out_dir=ROOT / "validation", results=None, sample=None, gifs=True,
         shard=None, resume=False):
    tasks_dir, out_dir = Path(tasks_dir), Path(out_dir)
    results = Path(results) if results else out_dir / "results.json"
    idx = json.loads((tasks_dir / "index.json").read_text())
    ids = [s["id"] for s in idx if s["graders"] and (tasks_dir / s["id"] / "spec.json").exists()]
    if sample:
        byspec = {s["id"]: s for s in idx}
        groups = {}
        for i in ids:  # stratify synthetic tasks by motion (a plain stride hits only 2 of the 8 motions)
            groups.setdefault(byspec[i].get("synth", {}).get("motion"), []).append(i)
        per = max(1, sample // len(groups))
        ids = sorted(i for g in groups.values() for i in g[:: max(1, len(g) // per)][:per])
    if only is not None:
        ids = [i for i in ids if i in only]
    if shard:
        k, m = shard
        ids = ids[k::m]
    specs = {i: json.loads((tasks_dir / i / "spec.json").read_text()) for i in ids}
    prev = json.loads(results.read_text()) if (resume and results.exists()) else {}
    jobs = [(i, v) for i in ids for v in variants(specs[i]) if v not in prev.get(i, {})]
    q = mp.Queue()
    ps = [mp.Process(target=worker, args=(jobs[i::n], tasks_dir, out_dir, gifs, q)) for i in range(n)]
    for p in ps:
        p.start()
    res = json.loads(results.read_text()) if ((only is not None or resume) and results.exists()) else {}
    for tid in ids:
        res[tid] = res.get(tid, {}) if resume else {}
    results.parent.mkdir(parents=True, exist_ok=True)
    for j in range(len(jobs)):
        tid, v, g = q.get()
        res.setdefault(tid, {})[v] = g
        if resume and j % 10 == 9:  # long runs: keep partial results, so a restart resumes with --resume
            results.write_text(json.dumps(dict(sorted(res.items())), indent=1))
        print(tid, v, "ERR " + g["error"] if "error" in g else ("PASS" if g["pass"] else "fail " + ",".join(
            k for k, x in g.items() if k not in ("pass", "oracle") and not x["ok"])), flush=True)
    for p in ps:
        p.join()
    results.parent.mkdir(parents=True, exist_ok=True)
    results.write_text(json.dumps(dict(sorted(res.items())), indent=1))
    return res


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("only", nargs="?", default="all", help="comma-separated task ids, or all")
    ap.add_argument("workers", nargs="?", type=int, default=2)
    ap.add_argument("--tasks-dir", default=str(ROOT / "tasks"))
    ap.add_argument("--out", default=str(ROOT / "validation"), help="where variant pages live / are built")
    ap.add_argument("--results", default=None, help="results JSON (default <out>/results.json)")
    ap.add_argument("--sample", type=int, default=None, help="validate an evenly spaced sample of this many tasks")
    ap.add_argument("--no-gifs", action="store_true")
    ap.add_argument("--shard", default=None, help="k/m: validate only every m-th task starting at k")
    ap.add_argument("--resume", action="store_true", help="keep results already in the results file; save as you go")
    a = ap.parse_args()
    main(n=a.workers, only=None if a.only == "all" else a.only.split(","), tasks_dir=a.tasks_dir, out_dir=a.out,
         results=a.results, sample=a.sample, gifs=not a.no_gifs,
         shard=tuple(int(x) for x in a.shard.split("/")) if a.shard else None, resume=a.resume)
