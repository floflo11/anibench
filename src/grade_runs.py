"""Render + grade every model output under runs/<model>/<task>/<try>/.

Writes grade_<stage>.json next to each output, a GIF, and runs/repair_jobs.json for outputs
that failed to run (one repair turn per run, same for every model).

python3 src/grade_runs.py [workers]
python3 src/grade_runs.py [workers] --regrade   # re-render (frame cache) and re-grade every output that has HTML with
                                                 # the current graders and admitted checks; writes results/regrade.json
                                                 # (status flips and the checks behind them). Runs imported from
                                                 # Valkyrie have no HTML here and keep their recorded grades.
"""
import json
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jobs import MODELS  # noqa: E402

BEFORE = "a898e10"  # commit of the last official grading (grader v1 grades in runs/; v2 never re-graded them)

REPAIR_MSG = ("Your HTML file did not run correctly in the grading harness. Error: {err}\n"
              "Last browser console lines:\n{logs}\n\n"
              "Fix it and return the complete corrected HTML file in a single ```html code block. "
              "Keep following the same contract.")


def todo(regrade=False):
    out = []
    for d in sorted((ROOT / "runs").glob("*/T*/*")):
        if not d.is_dir():
            continue
        for stage in ("first", "repair"):
            if not (d / f"meta_{stage}.json").exists():
                continue
            if not (d / f"grade_{stage}.json").exists() or (regrade and (d / f"index_{stage}.html").exists()):
                out.append((str(d), stage))
    return out


def worker(items, q):
    from framecache import CachedRenderer
    from graders import grade
    from render import save_gif
    R = CachedRenderer()
    for d, stage in items:
        d = Path(d)
        tid = d.parent.name
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        meta = json.loads((d / f"meta_{stage}.json").read_text())
        res = dict(stage=stage, task=tid, model=d.parent.parent.name, try_=d.name, tier=spec["tier"],
                   usage=meta.get("usage"), latency_s=meta.get("latency_s"))
        if meta.get("error"):
            res.update(status="API_ERROR", error=meta["error"])
        elif not (d / f"index_{stage}.html").exists():
            res.update(status="NO_HTML", finish=meta.get("finish"))
        else:
            page = d / f"page_{stage}"
            page.mkdir(exist_ok=True)
            (page / "index.html").write_text((d / f"index_{stage}.html").read_text())
            fr, err, logs = R.render(page, ROOT / "tasks" / tid, spec["width"], spec["height"])
            if fr is None:
                res.update(status="RUNTIME", error=err, logs=logs[-8:])
            else:
                save_gif(fr, d / f"anim_{stage}.gif", 0.5)
                if spec["graders"]:
                    g = grade(fr, ROOT / "tasks" / tid)
                    res.update(status="PASS" if g["pass"] else "FAIL", grades=g)
                else:
                    res.update(status="HUMAN")
        gp = d / f"grade_{stage}.json"
        prev = json.loads(gp.read_text()) if gp.exists() else None
        gp.write_text(json.dumps(res, indent=1))
        q.put((str(d), stage, res["status"], prev and dict(status=prev.get("status"), failed=sorted(
            k for k, v in (prev.get("grades") or {}).items() if k != "pass" and not v["ok"])),
            sorted(k for k, v in (res.get("grades") or {}).items() if k != "pass" and not v["ok"])))
    R.close()


def repair_jobs():
    """Second turn for runs whose first output failed to run or had no HTML."""
    jobs = []
    for g in sorted((ROOT / "runs").glob("*/T*/*/grade_first.json")):
        r = json.loads(g.read_text())
        d = g.parent
        if r["status"] not in ("RUNTIME", "NO_HTML") or (d / "meta_repair.json").exists():
            continue
        tid = r["task"]
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        prompt = (ROOT / "tasks" / tid / "prompt.md").read_text()
        prev = (d / "response_first.txt").read_text()
        err = r.get("error") or "The response did not contain a complete HTML file."
        logs = "\n".join(r.get("logs") or [])[-1500:]
        jobs.append(dict(id=f"{r['model']}__{tid}__{r['try_']}", stage="repair", model=MODELS[r["model"]], task=tid,
                         image=spec["image"], prompt=prompt, prev=prev[-60000:],
                         repair=REPAIR_MSG.format(err=err, logs=logs or "(none)")))
    (ROOT / "runs/repair_jobs.json").write_text(json.dumps(jobs))
    return jobs


def main(n=2, regrade=False):
    items = todo(regrade)
    flips = []
    if items:
        q = mp.Queue()
        ps = [mp.Process(target=worker, args=(items[i::n], q)) for i in range(n)]
        for p in ps:
            p.start()
        for _ in items:
            d, stage, st, prev, failed = q.get()
            rel = str(Path(d).relative_to(ROOT))
            print(rel, stage, st, "" if not prev else f"(was {prev['status']} {','.join(prev['failed'])})", flush=True)
            if prev:
                flips.append(dict(run=rel, stage=stage, before=prev, after=dict(status=st, failed=failed)))
        for p in ps:
            p.join()
    if regrade:
        # "before" = the grade committed at BEFORE (the last official grading), so an interrupted re-grade can be
        # resumed without losing what the runs scored before
        import subprocess
        for f in flips:
            path = f"{f['run']}/grade_{f['stage']}.json"
            try:
                prev = json.loads(subprocess.check_output(["git", "-C", str(ROOT), "show", f"{BEFORE}:{path}"],
                                                          stderr=subprocess.DEVNULL))
                f["before"] = dict(status=prev.get("status"), failed=sorted(
                    k for k, v in (prev.get("grades") or {}).items() if k != "pass" and not v["ok"]))
            except subprocess.CalledProcessError:
                pass
        flips.sort(key=lambda f: (f["run"], f["stage"]))
        changed = [f for f in flips if f["before"]["status"] != f["after"]["status"]]
        (ROOT / "results/regrade.json").write_text(json.dumps(dict(regraded=len(flips), status_flips=changed,
                                                                   all=flips), indent=1))
        print(f"re-graded {len(flips)}; status flips {len(changed)}")
    js = repair_jobs()
    print("repair jobs:", len(js))


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(int(args[0]) if args else 2, regrade="--regrade" in sys.argv)
