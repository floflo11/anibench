import json, os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, "/tests")
os.environ.setdefault("ANIBENCH_CHROME", "")
import render
from graders import grade
app, tests = Path(sys.argv[1]), Path(sys.argv[2])
spec = json.loads((tests / "spec.json").read_text())
out = Path("/logs/verifier")
out.mkdir(parents=True, exist_ok=True)
res = {"task": spec["id"]}
if not (app / "index.html").exists():
    res["status"] = "NO_HTML"
else:
    root = Path(tempfile.mkdtemp())
    run = root / "run"
    shutil.copytree(app, run)
    render.ROOT = root
    R = render.Renderer()
    frames, err, logs = R.render(run, spec["width"], spec["height"])
    R.close()
    if frames is None:
        res.update(status="RUNTIME", error=err, logs=logs[-8:])
    else:
        g = grade(frames, tests)
        res.update(status="PASS" if g["pass"] else "FAIL", grades=g)
(out / "reward.json").write_text(json.dumps(res, indent=1))
(out / "reward.txt").write_text("1" if res.get("status") == "PASS" else "0")
print(json.dumps(res, indent=1))
