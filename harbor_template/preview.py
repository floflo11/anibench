"""anibench preview tool (feedback setting). Installed in the task image as /opt/anibench/preview.py and run
through the `anibench-preview` wrapper.

Renders /app/index.html with the grader's renderer (render.py: same Chromium flags, viewport, device scale
factor, canvas capture and white compositing as the verifier) and saves 6 frames, t = 0, 0.4, ..., 2.0 s,
to /app/preview/frame_0.png ... frame_5.png. It has no access to the grader, the spec or the masks
(they are only uploaded to /tests for the verifier, after the agent finishes).

It runs once per task: every call is logged to /var/lib/anibench/preview_calls, and after the first call
it refuses. The verifier copies the call count into reward.json as `preview_calls`.
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ANIBENCH_CHROME", "")  # use Playwright's bundled Chromium, as the verifier does
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

APP = Path(os.environ.get("ANIBENCH_APP", "/app"))
STATE = Path(os.environ.get("ANIBENCH_STATE", "/var/lib/anibench"))
N_PREVIEW = 6
LIMIT = 1


def record_call():
    """Log this call; return how many calls there were before it."""
    STATE.mkdir(parents=True, exist_ok=True)
    log = STATE / "preview_calls"
    before = len(log.read_text().split()) if log.exists() else 0
    with open(log, "a") as f:
        f.write("call\n")
    # grader isolation probe: the agent phase must not see /tests or /solution
    (STATE / "tests_visible_at_preview").write_text("1" if Path("/tests").exists() else "0")
    return before


def main():
    before = record_call()
    if before >= LIMIT:
        print(f"anibench-preview: already used ({before} earlier call). It runs once per task.", file=sys.stderr)
        return 2
    html = APP / "index.html"
    if not html.exists():
        print(f"anibench-preview: {html} not found. Write it first (this call counted as your one preview).",
              file=sys.stderr)
        return 1
    import render  # noqa: E402  (imported late so the call is logged even if Playwright is broken)
    from PIL import Image

    render.N_FRAMES = N_PREVIEW  # frame i at t = i * 2 / (N - 1)
    w, h = Image.open(APP / "image.png").size
    root = Path(tempfile.mkdtemp())
    run = root / "run"
    shutil.copytree(APP, run, ignore=shutil.ignore_patterns("preview"))
    render.ROOT = root
    R = render.Renderer()
    try:
        frames, err, logs = R.render(run, w, h)
    finally:
        R.close()
    out = APP / "preview"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir()
    for line in logs[-20:]:
        print("page:", line)
    if frames is None:
        (out / "error.txt").write_text(err + "\n" + "\n".join(logs[-20:]) + "\n")
        print(f"anibench-preview: {err}")
        return 1
    for i, f in enumerate(frames):
        Image.fromarray(f).save(out / f"frame_{i}.png")
        print(f"frame_{i}.png  t = {i * 2 / (N_PREVIEW - 1):.1f} s")
    print(f"saved {len(frames)} frames ({w}x{h}) to {out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
