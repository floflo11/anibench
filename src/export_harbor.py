"""Export the scored tasks in Harbor format for upload to Valkyrie.

harbor/<task-name>/
  task.toml, instruction.md
  environment/Dockerfile (+ image.png, vendor/ copied into /app)
  tests/test.sh, tests/grade_app.py, tests/{graders.py, render.py, spec.json, masks}
  solution/solve.sh (+ reference layers) -> writes the reference animation to /app

The verifier renders /app/index.html with headless Chromium (software WebGL), runs the six checks,
writes /logs/verifier/reward.txt (1 = all applicable checks pass) and reward.json (per-check detail).

Usage:
  python3 src/export_harbor.py                         legacy dataset (anibench/core) -> harbor/, unchanged
  python3 src/export_harbor.py --setting single        protocol setting -> build/harbor-single/
  python3 src/export_harbor.py --setting feedback --out /tmp/x [--tasks T01,T02]

Settings (docs/protocol.md): single (write /app/index.html once, no code), feedback (single + one run of
the grader's renderer via `anibench-preview`, harbor_template/preview.py), agent (full tool use, fixed
budget; the agent sees exactly what the legacy core dataset shows). The settings exports also record
audit counters in reward.json (preview_calls, probe_tests_visible) so protocol compliance and
grader isolation can be checked from Valkyrie results.
"""
import argparse
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "harbor"
TEMPLATE = ROOT / "harbor_template"
SETTINGS = ("single", "feedback", "agent")

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
# Valkyrie reads reward.json as numbers only: overall reward plus 1/0 per applicable check
nums = {"reward": 1.0 if res.get("status") == "PASS" else 0.0}
for k, v in (res.get("grades") or {}).items():
    if k != "pass":
        nums[k] = 1.0 if v.get("ok") else 0.0
(out / "reward.json").write_text(json.dumps(nums))
(out / "details.json").write_text(json.dumps(res, indent=1))
(out / "reward.txt").write_text("1" if res.get("status") == "PASS" else "0")
print(json.dumps(res, indent=1))
'''

SOLVE_SH = """#!/bin/bash
cp /solution/ref/* /app/
"""

APP_NOTE = ("\n\n---\nYou are working in `/app`. The image is `/app/image.png` and three.js is at "
            "`/app/vendor/three.module.js` (it imports `./three.core.js` next to it). Write your answer to "
            "`/app/index.html`. You may inspect the image with any tools available in the container.\n")

# ---------- protocol settings (docs/protocol.md) ----------
# Everything below is used only with --setting; the legacy export above is unchanged.

ENV_NOTE = ("\n\n---\nYou are working in `/app`. The image is `/app/image.png` and three.js is at "
            "`/app/vendor/three.module.js` (it imports `./three.core.js` next to it).\n")

SETTING_NOTE = {
    "single": ENV_NOTE + (
        "\n**Setting: single attempt.** You may look at `/app/image.png`, but do not run any code (beyond what it takes "
        "to write the file): no scripts, "
        "no image-analysis programs, no browser, no rendering or testing of your page. Write your complete "
        "answer to `/app/index.html` in one step, then stop. Do not revise the file after writing it.\n"),
    "feedback": ENV_NOTE + (
        "\n**Setting: one preview.** You may look at `/app/image.png`. Do not run any code (beyond what it takes to "
        "write the file) except the preview tool below: no scripts, no image-analysis programs, no browser.\n\n"
        "After writing `/app/index.html` you may run `anibench-preview` **once**. It renders your page with the "
        "grader's renderer (headless Chromium, software WebGL, the same viewport and settings) and saves 6 frames, "
        "at t = 0, 0.4, 0.8, 1.2, 1.6 and 2.0 s, to `/app/preview/frame_0.png` ... `/app/preview/frame_5.png`. "
        "It prints any page errors. Look at the frames, revise `/app/index.html` if needed, then stop. "
        "The tool refuses to run a second time.\n"),
    "agent": APP_NOTE,  # identical to the legacy core dataset
}

# the feedback setting adds the preview tool; nothing from tests/ (grader, spec, masks) goes into the image
PREVIEW_DOCKER = """COPY anibench/ /opt/anibench/
RUN chmod 755 /opt/anibench/anibench-preview && ln -sf /opt/anibench/anibench-preview /usr/local/bin/anibench-preview \\
 && mkdir -p /var/lib/anibench && chmod 777 /var/lib/anibench
"""

PREVIEW_SH = r"""#!/bin/bash
# anibench-preview: render /app/index.html like the grader and save 6 frames to /app/preview/
[ -d /ms-playwright ] && export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
for c in /usr/bin/python3 /usr/local/bin/python3 $(which -a python3 2>/dev/null); do
  if [ -x "$c" ] && "$c" -c "import playwright, numpy, PIL" 2>/dev/null; then exec "$c" /opt/anibench/preview.py "$@"; fi
done
echo "anibench-preview: no python3 with playwright, numpy and pillow found" >&2
exit 1
"""

# oracle runs: record whether /tests or the grader was visible during the agent phase
SOLVE_SH_PROBE = """#!/bin/bash
mkdir -p /var/lib/anibench 2>/dev/null
{ [ -e /tests ] && echo 1 || echo 0; } > /var/lib/anibench/tests_visible_at_solve 2>/dev/null || true
cp /solution/ref/* /app/
"""

AUDIT = """# protocol audit counters (settings exports only); numbers only, absent if never recorded
audit = {}
st = Path("/var/lib/anibench")
if (st / "preview_calls").exists():
    audit["preview_calls"] = float(len((st / "preview_calls").read_text().split()))
probes = [p for p in (st / "tests_visible_at_solve", st / "tests_visible_at_preview") if p.exists()]
if probes:
    audit["probe_tests_visible"] = float(max(int(p.read_text().strip() or 0) for p in probes))
nums.update(audit)
res["audit"] = audit
"""
GRADE_APP_SETTING = GRADE_APP.replace('(out / "reward.json").write_text', AUDIT + '(out / "reward.json").write_text', 1)
assert GRADE_APP_SETTING != GRADE_APP


def copy_ref(tid, slugname, dest, out):
    """Reference layers for the oracle. validation/*/ref/*.png is gitignored, so for a scratch export from
    a clean checkout fall back to the committed legacy harbor/ copy (never when writing harbor/ itself)."""
    ref = ROOT / "validation" / tid / "ref"
    for f in ref.glob("*"):
        if f.suffix in (".png", ".html") and f.name not in ("image.png",):
            shutil.copy(f, dest / f.name)
    legacy = OUT / slugname / "solution/ref"
    if out.resolve() != OUT.resolve() and legacy.exists():
        for f in legacy.glob("*"):
            if not (dest / f.name).exists():
                shutil.copy(f, dest / f.name)


def slug(spec):
    return f"anibench-{spec['id'].lower()}"


def main(setting=None, out=None, tasks=None):
    if setting is not None and setting not in SETTINGS:
        raise ValueError(f"unknown setting {setting!r}; choose from {SETTINGS}")
    out = Path(out) if out else (OUT if setting is None else ROOT / "build" / f"harbor-{setting}")
    if out.exists():
        shutil.rmtree(out)
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    names = []
    for spec in idx:
        if not spec["graders"]:
            continue
        tid = spec["id"]
        if tasks and tid not in tasks:
            continue
        tdir = ROOT / "tasks" / tid
        d = out / slug(spec)
        (d / "environment/vendor").mkdir(parents=True)
        (d / "tests").mkdir()
        (d / "solution/ref").mkdir(parents=True)
        shutil.copy(tdir / "image.png", d / "environment/image.png")
        for f in ("three.module.js", "three.core.js"):
            shutil.copy(ROOT / "vendor" / f, d / "environment/vendor" / f)
        dockerfile = DOCKERFILE
        if setting == "feedback":
            tool = d / "environment/anibench"
            tool.mkdir()
            shutil.copy(TEMPLATE / "preview.py", tool / "preview.py")
            shutil.copy(ROOT / "src/render.py", tool / "render.py")  # the renderer only: no graders, spec or masks
            (tool / "anibench-preview").write_text(PREVIEW_SH)
            dockerfile += PREVIEW_DOCKER
        (d / "environment/Dockerfile").write_text(dockerfile)
        note = APP_NOTE if setting is None else SETTING_NOTE[setting]
        instr = (tdir / "prompt.md").read_text().replace(
            "Return only the complete HTML file in a single ```html code block.", "").rstrip() + note
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
checks = {json.dumps(spec['graders'])}{"" if setting is None else chr(10) + f'setting = "{setting}"'}

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
        (d / "tests/grade_app.py").write_text(GRADE_APP if setting is None else GRADE_APP_SETTING)
        if setting is None:
            ref = ROOT / "validation" / tid / "ref"
            for f in ref.glob("*"):
                if f.suffix in (".png", ".html") and f.name not in ("image.png",):
                    shutil.copy(f, d / "solution/ref" / f.name)
        else:
            copy_ref(tid, slug(spec), d / "solution/ref", out)
        (d / "solution/solve.sh").write_text(SOLVE_SH if setting is None else SOLVE_SH_PROBE)
        for sh in (d / "tests/test.sh", d / "solution/solve.sh", d / "environment/anibench/anibench-preview"):
            if sh.exists():
                sh.chmod(0o755)
        names.append(slug(spec))
    title = "anibench — Harbor tasks" + ("" if setting is None else f" (setting: {setting}, see docs/protocol.md)")
    (out / "README.md").write_text(
        f"# {title}\n\n" + f"{len(names)} scored tasks. Upload with the Valkyrie CLI from this folder.\n\n"
        "Each task: the agent writes `/app/index.html`; `tests/test.sh` renders it in headless Chromium and runs the six checks; "
        "reward 1 = all applicable checks pass. `solution/solve.sh` installs the reference animation (oracle).\n")
    print(len(names), "tasks exported to", out)
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--setting", choices=SETTINGS, help="protocol setting; omit for the legacy core export to harbor/")
    ap.add_argument("--out", help="output folder (default: harbor/ for legacy, build/harbor-<setting>/ otherwise)")
    ap.add_argument("--tasks", help="comma-separated task ids (default: all scored tasks)")
    a = ap.parse_args()
    main(a.setting, a.out, a.tasks.split(",") if a.tasks else None)
