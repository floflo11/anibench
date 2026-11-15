"""Render + grade every model output under runs/<model>/<task>/<try>/.

Writes grade_<stage>.json next to each output, a GIF, and runs/repair_jobs.json for outputs
that failed to run (one repair turn per run, same for every model).

python3 src/grade_runs.py [workers]
"""
import json
import multiprocessing as mp
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from jobs import MODELS  # noqa: E402

REPAIR_MSG = ("Your HTML file did not run correctly in the grading harness. Error: {err}\n"
              "Last browser console lines:\n{logs}\n\n"
              "Fix it and return the complete corrected HTML file in a single ```html code block. "
              "Keep following the same contract.")


def todo():
    out = []
    for d in sorted((ROOT / "runs").glob("*/T*/*")):
        if not d.is_dir():
            continue
        for stage in ("first", "repair"):
            if (d / f"meta_{stage}.json").exists() and not (d / f"grade_{stage}.json").exists():
                out.append((str(d), stage))
    return out


def worker(items, q):
    from graders import grade
    from render import Renderer, prepare, save_gif
    R = Renderer()
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
            prepare(page, ROOT / "tasks" / tid)
            fr, err, logs = R.render(page, spec["width"], spec["height"])
            if fr is None:
                res.update(status="RUNTIME", error=err, logs=logs[-8:])
            else:
                save_gif(fr, d / f"anim_{stage}.gif", 0.5)
                if spec["graders"]:
                    g = grade(fr, ROOT / "tasks" / tid)
                    res.update(status="PASS" if g["pass"] else "FAIL", grades=g)
                else:
                    res.update(status="HUMAN")
        (d / f"grade_{stage}.json").write_text(json.dumps(res, indent=1))
        q.put((str(d), stage, res["status"]))
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


def main(n=2):
    items = todo()
    if items:
        q = mp.Queue()
        ps = [mp.Process(target=worker, args=(items[i::n], q)) for i in range(n)]
        for p in ps:
            p.start()
        for _ in items:
            d, stage, st = q.get()
            print(Path(d).relative_to(ROOT), stage, st, flush=True)
        for p in ps:
            p.join()
    js = repair_jobs()
    print("repair jobs:", len(js))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 2)
