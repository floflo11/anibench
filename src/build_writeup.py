"""Generate WRITEUP.md and README.md from results/summary.json and validation/admission.json."""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def pct(a, b):
    return f"{(a / b * 100):.0f}%" if b else "n/a"


def main():
    summ = json.loads((ROOT / "results/summary.json").read_text())
    adm = json.loads((ROOT / "validation/admission.json").read_text())
    rows = list(csv.DictReader(open(ROOT / "results/runs.csv")))
    caught = adm["caught"]
    cats = json.loads((ROOT / "results/nemotron_categories.json").read_text())
    nem = summ.get("nemotron")
    qwen_rows = [r for r in rows if r["model"] == "qwen"]
    nem_rows = [r for r in rows if r["model"] == "nemotron" and r["tier"] in ("1", "2")]
    # fidelity: frame 0 did not match the original image
    fid = 0
    for r in nem_rows:
        g = json.loads((ROOT / "runs/nemotron" / r["task"] / r["try_"] / f"grade_{r['stage']}.json").read_text())
        if g.get("grades", {}).get("G6", {}).get("first_vs_orig", 0) > 0.05:
            fid += 1
    order = sorted(summ, key=lambda m: -(summ[m]["pass_rate"] or 0))
    ranking = "\n".join(f"- **{summ[m]['label']}: {summ[m]['passed']}/{summ[m]['n']} first-try runs passed ({pct(summ[m]['passed'], summ[m]['n'])}).**" for m in order if summ[m]["n"] >= 5)
    kept_total = sum(len(v["kept"]) for v in adm["tasks"].values())
    all_total = sum(len(v["kept"]) + len(v["dropped"]) for v in adm["tasks"].values())

    gf = nem["grader_fail"] if nem else {}
    names = {"G1": "Isolation", "G2": "Integrity", "G3": "Area", "G4": "Motion", "G5": "Pivot", "G6": "Loop and fidelity"}
    fail_lines = "\n".join(f"| {k} {names[k]} | {gf[k]['failed']}/{gf[k]['n']} ({pct(gf[k]['failed'], gf[k]['n'])}) |" for k in names if k in gf)
    qwen_txt = ", ".join(f"{r['task']}: {r['status']}" for r in qwen_rows)

    w = f"""# anibench: can models animate one part of a picture without breaking the rest?

**Vals Hacks, Track 1 (Build Your Own Eval).** Code: `github.com/floflo11/anibench`.

## Summary

Models write three.js that runs, but they cut out the wrong pixels, rotate around the wrong joint and tear hands off.
anibench gives a model a still image of cartoon characters plus one instruction (\"wave his raised hand from the wrist\",
\"make her earrings swing\", \"lift her hat\") and asks for a three.js page that animates only that part. We render the page
to 25 frames and score it with **six image-math checks**, not a model judge.

{ranking}
- In the single-shot setting (image in the prompt, one answer plus one repair turn), models failed in visible, specific ways:
  Nemotron flipped or shifted the image in {cats.get('image flipped or shifted', 0)} of {len(nem_rows)} runs and left the canvas blank in {cats.get('blank canvas', 0)};
  Gemini 4 Carbon and DeepSeek often spent their whole 32k-token budget reasoning and never wrote the file.
- On Valkyrie, the reference solutions score **21/21**, so the packaging and checks hold up inside the platform.
- Every check is validated before use: a reference animation must pass it, and deliberately broken copies must fail it.

## Why this benchmark

Code-generation benchmarks mostly check that code runs. Animation adds a visual contract that is easy to state and hard to
meet: move *this* part, around *this* joint, and leave every other pixel alone. Closest prior work tests different things:
WorldCoder-Bench checks interactive three.js worlds through exposed state, Animation2Code turns recorded web animations back into
code, and Lottie/SVG benchmarks animate from text with no source image to preserve. Classic pipelines (Meta's Animated Drawings,
AniClipart) cut out and rig drawings without a model writing code; we borrow their failure stages: cut-out, pivot, motion, isolation.

## Tasks

24 tasks on two images (six characters). 21 are scored automatically; 3 (thumbs up, walk, clap) need pixels that don't exist in
the image and are human-labeled only.

| Tier | Tasks | What makes them hard |
| --- | --- | --- |
| 1 (12) | Waves from wrist, elbow or shoulder; nods; head tilt; earrings; pigtails; four kids waving at once | One rigid part, an exact pivot, everything else frozen |
| 2 (9) | Hat lift and tilt; jump; squat; knee bounce; veil flutter; left/right wording | Uncovering hidden pixels, whole-body motion, isolation, viewer-vs-character left/right |
| 3 (3) | Thumbs up, walk in place, clap | Not scorable from pixels; demo material |

**Output contract** (same for every task): one HTML file, three.js from a local copy, canvas exactly the image size at pixel ratio 1,
frame 0 identical to the image, a 2-second seamless loop, and `window.setTime(t)` that renders time `t` synchronously.

## Checks

Frames are rendered in headless Chromium with software WebGL, by calling `setTime` at 25 evenly spaced times.

| Check | Fails when | Catches |
| --- | --- | --- |
| G1 Isolation | Pixels change outside the region the moving part can sweep | Wrong part, whole image moving, other characters moving |
| G2 Integrity | New separate pieces appear in the moving region | Detached fingers, torn fragments |
| G3 Area | Foreground lost or gained by more than half the part's own area (hats: the head under it must stay filled) | Holes, missing or duplicated parts |
| G4 Motion | Under 20% of the part's pixels change at peak | Frozen output, motion declared but not drawn |
| G5 Pivot | Over 20% of the part's pixels at the joint change | Rotating around the wrong point |
| G6 Loop and fidelity | Frame at t=2 differs from t=0, or frame 0 differs from the image | Loop jumps, flipped or shifted images |

### Validation (before any model ran)

For each of the 21 scored tasks we built a reference animation from hand-made part masks and pivots, plus 7 broken copies.
A check counts for a task only if the reference passes it ({kept_total} of {all_total} task-check pairs kept; see
`validation/admission.md`). Broken copies caught where an intended check applies:

| Broken copy | Caught |
| --- | --- |
""" + "\n".join(f"| {k.replace('_', ' ')} | {v[0]}/{v[1]} |" for k, v in caught.items()) + f"""

The weakest check is **G2 on small fragments**: a leftover piece that keeps touching the moving part is not separated.

## Results

""" + (ROOT / "results/README.md").read_text().split("\n", 2)[2].replace("charts/", "results/charts/").replace("`library/`", "`results/library/`").replace("`runs.csv`", "`results/runs.csv`") + f"""

### Failure rate per check ({nem['label'] if nem else ''})

| Check | Runs failing |
| --- | --- |
{fail_lines}

### What the failures look like

- **Hand at the knee (T01).** The model whited out a box where the hand was, then drew the hand waving at the boy's knee: it used
  image coordinates in a y-up camera.
- **Head disappears (T09, \"nod\").** Most of the head vanishes; G2 and G3 fail.
- **White bar through the face (T14, hat tilt).** The cut-out rectangle is blanked and never refilled; G1 fails.
- **Gap at the wrist (T21).** The hand rotates away from the forearm, leaving a white gap; G5 fails.
- **Floating fingers (T03).** A rectangular cut leaves fingertips behind; G1, G5, G6 fail.

All runs are in `results/library/` as GIFs.

## Limits

- One model ran the full set. Claude Sonnet 5.5 and GPT-6.1 Sol were planned but the OpenRouter account had no credits overnight;
  the runner is ready to add them (`runs/jobs/full.json`).
- Single-turn generation with one repair turn for outputs that don't run. An agent that renders and looks at its own output
  might do much better; that's the natural next experiment.
- Checks are tolerant of faint artifacts (e.g. a light halo around a cut-out), and G2 misses small attached fragments.
- Masks and pivots are hand-annotated on two images; more images and characters would make results more general.
- No check scores motion quality (natural vs. robotic). Next step: a video-model judge, validated against human labels.

## Reproduce

```bash
python3 src/parts.py && python3 src/tasks.py      # masks, tasks
python3 src/reference.py && python3 src/validate.py && python3 src/admission.py   # grader validation
python3 src/jobs.py make full sonnet,sol 3        # job list; run with src/browser_runner.js or any OpenRouter client
python3 src/jobs.py ingest <results.json> && python3 src/grade_runs.py && python3 src/report.py
python3 src/export_harbor.py                      # Harbor tasks for Valkyrie
```
"""
    (ROOT / "WRITEUP.md").write_text(w)
    overview = (ROOT / "OVERVIEW.md").read_text().strip()
    readme = f"""# anibench

{overview}

Built for Vals Hacks Track 1.

- Write-up: [WRITEUP.md](WRITEUP.md)
- Results: [results/README.md](results/README.md), GIFs in `results/library/`, demo video `results/demo.mp4`
- Grader validation: [validation/admission.md](validation/admission.md)
- Harbor tasks for Valkyrie: [`harbor/`](harbor/)
- Morning checklist: [MORNING.md](MORNING.md)

Headline: {nem['label'] if nem else ''} passed {nem['passed'] if nem else 0}/{nem['n'] if nem else 0} scored runs; Qwen 3.8 27B solved the T01 wave in a smoke test.
"""
    (ROOT / "README.md").write_text(readme)
    print("written")


if __name__ == "__main__":
    main()
