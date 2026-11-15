"""Export the scored tasks in Harbor format for upload to Valkyrie.

harbor/<task-name>/
  task.toml, instruction.md
  environment/Dockerfile (+ image.png, vendor/ copied into /app)
  tests/test.sh, tests/grade_app.py, tests/{graders.py, render.py, spec.json, masks}
  solution/solve.sh (+ reference layers) -> writes the reference animation to /app

The verifier renders /app/index.html with headless Chromium (software WebGL), runs the six checks,
writes /logs/verifier/reward.txt (1 = all applicable checks pass) and reward.json (per-check detail).
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "harbor"

DOCKERFILE = """FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy
RUN pip install --no-cache-dir numpy pillow scipy
WORKDIR /app
COPY image.png /app/image.png
COPY vendor/ /app/vendor/
"""

TEST_SH = r"""#!/bin/bash
set -u
mkdir -p /logs/verifier
LOG=/logs/verifier/grade_log.txt
{ echo "PATH=$PATH"; which -a python3 2>/dev/null; } > "$LOG"
[ -d /ms-playwright ] && export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
PY=""
for c in /usr/bin/python3 /usr/local/bin/python3 $(which -a python3 2>/dev/null); do
  if [ -x "$c" ] && "$c" -c "import playwright, numpy, PIL, scipy" 2>/dev/null; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  PY=/usr/bin/python3; [ -x "$PY" ] || PY=$(command -v python3)
  echo "installing grader packages into $PY" >> "$LOG"
  "$PY" -m pip install -q playwright==1.49.0 numpy pillow scipy >> "$LOG" 2>&1 \
    || "$PY" -m pip install -q --break-system-packages playwright==1.49.0 numpy pillow scipy >> "$LOG" 2>&1
fi
echo "using $PY" >> "$LOG"
"$PY" -c "from playwright.sync_api import sync_playwright as s; p=s().start(); b=p.chromium.launch(); b.close(); p.stop()" >> "$LOG" 2>&1 \
  || "$PY" -m playwright install chromium >> "$LOG" 2>&1
cd /tests
"$PY" /tests/grade_app.py /app /tests >> "$LOG" 2>&1
if [ ! -f /logs/verifier/reward.txt ]; then echo 0 > /logs/verifier/reward.txt; fi
tail -40 "$LOG"
"""

GRADE_APP = '''import json, os, shutil, sys, tempfile
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
'''

SOLVE_SH = """#!/bin/bash
cp /solution/ref/* /app/
"""

APP_NOTE = ("\n\n---\nYou are working in `/app`. The image is `/app/image.png` and three.js is at "
            "`/app/vendor/three.module.js` (it imports `./three.core.js` next to it). Write your answer to "
            "`/app/index.html`. You may inspect the image with any tools available in the container.\n")


def slug(spec):
    return f"anibench-{spec['id'].lower()}"


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    names = []
    for spec in idx:
        if not spec["graders"]:
            continue
        tid = spec["id"]
        tdir = ROOT / "tasks" / tid
        d = OUT / slug(spec)
        (d / "environment/vendor").mkdir(parents=True)
        (d / "tests").mkdir()
        (d / "solution/ref").mkdir(parents=True)
        shutil.copy(tdir / "image.png", d / "environment/image.png")
        for f in ("three.module.js", "three.core.js"):
            shutil.copy(ROOT / "vendor" / f, d / "environment/vendor" / f)
        (d / "environment/Dockerfile").write_text(DOCKERFILE)
        instr = (tdir / "prompt.md").read_text().replace(
            "Return only the complete HTML file in a single ```html code block.", "").rstrip() + APP_NOTE
        (d / "instruction.md").write_text(instr)
        toml = f'''schema_version = "1.3"

[task]
name = "anibench/{slug(spec)}"
description = "{spec['instruction'].replace('"', "'")}"
keywords = ["animation", "three.js", "vision", "code-generation", "tier-{spec['tier']}"]

[metadata]
benchmark = "anibench"
task_id = "{tid}"
tier = {spec['tier']}
image = "{spec['image']}"
checks = {json.dumps(spec['graders'])}

[verifier]
timeout_sec = 600

[agent]
timeout_sec = 900

[environment]
build_timeout_sec = 900
cpus = 2
memory_mb = 4096
workdir = "/app"
'''
        (d / "task.toml").write_text(toml)
        for f in ("graders.py", "render.py"):
            shutil.copy(ROOT / "src" / f, d / "tests" / f)
        for f in ("spec.json", "image.png", "allowed.png", "target.png", "skull.png"):
            if (tdir / f).exists():
                shutil.copy(tdir / f, d / "tests" / f)
        (d / "tests/test.sh").write_text(TEST_SH)
        (d / "tests/grade_app.py").write_text(GRADE_APP)
        ref = ROOT / "validation" / tid / "ref"
        for f in ref.glob("*"):
            if f.suffix in (".png", ".html") and f.name not in ("image.png",):
                shutil.copy(f, d / "solution/ref" / f.name)
        (d / "solution/solve.sh").write_text(SOLVE_SH)
        for sh in (d / "tests/test.sh", d / "solution/solve.sh"):
            sh.chmod(0o755)
        names.append(slug(spec))
    (OUT / "README.md").write_text(
        "# anibench — Harbor tasks\n\n" + f"{len(names)} scored tasks. Upload with the Valkyrie CLI from this folder.\n\n"
        "Each task: the agent writes `/app/index.html`; `tests/test.sh` renders it in headless Chromium and runs the six checks; "
        "reward 1 = all applicable checks pass. `solution/solve.sh` installs the reference animation (oracle).\n")
    print(len(names), "tasks exported to", OUT)


if __name__ == "__main__":
    main()
