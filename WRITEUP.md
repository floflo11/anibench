# anibench: can models animate one part of a picture without breaking the rest?

**Vals Hacks, Track 1 (Build Your Own Eval).** Code: `github.com/floflo11/anibench`.

## Summary

Models write three.js that runs, but they cut out the wrong pixels, rotate around the wrong joint and tear hands off.
anibench gives a model a still image of cartoon characters plus one instruction ("wave his raised hand from the wrist",
"make her earrings swing", "lift her hat") and asks for a three.js page that animates only that part. We render the page
to 25 frames and score it with **eight image-math checks**, not a model judge.

- **Claude Sonnet 5.5 (Claude Code, Valkyrie): 12/21 first-try runs passed (57%).**
- **Kimi K3.1 Pro: 3/15 first-try runs passed (20%).**
- **Qwen 3.8 27B: 3/15 first-try runs passed (20%).**
- **DeepSeek V4 Flash Vision: 1/13 first-try runs passed (8%).**
- **Grok 4.7: 1/14 first-try runs passed (7%).**
- **Gemini 4 Carbon: 0/8 first-try runs passed (0%).**
- **Nemotron 3.5 Super VL: 0/21 first-try runs passed (0%).**
- In the single-shot setting (image in the prompt, one answer plus one repair turn), models failed in visible, specific ways:
  Nemotron flipped or shifted the image in 9 of 21 first-try runs and left the canvas blank in 4;
  Gemini 4 Carbon and DeepSeek often spent their whole 32k-token budget reasoning and never wrote the file.
- **On Valkyrie** (agent setting: Claude Code, which can open the image and iterate), Claude Sonnet 5.5 passed **12/21 (57%)**; reference solutions score **21/21**. It passed T01 in a separate smoke run and failed it here, so results vary run to run. The GPT-6.1 Sol run did not start before the deadline (the CLI returned no run ID). Its grades come from the Valkyrie verifier at the time (grader v1) and could not be re-graded here: the run's HTML was not imported.
- Gemini 4 Carbon is left out of the table: in 8 of 8 completed runs it used the whole 32k-token budget reasoning and returned no file.
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
| G1 Isolation | Pixels change outside the region the moving part can sweep (grown by 7.5% of the part's size, room for squash and stretch) | Wrong part, whole image moving, other characters moving |
| G2 Integrity | New separate pieces (not faint halos) appear in the moving region | Detached fingers, torn fragments |
| G2b Connectivity | The part itself, isolated from its neighbours, splits into more pieces than it started with | A fingertip or thumb that comes apart while still touching the arm |
| G2c Residual | A piece of the part stays exactly where it was while the part's fitted rigid motion carries it 10+ px away | A tip left behind that the moving part slides past, ghost copies |
| G3 Area | More than half the part is missing (by its fitted pose and by its pixel count; pixels hidden behind other parts are not missing), or the region gains more than half the part's area of new foreground (hats: the head under it must stay filled) | Holes, vanished or duplicated parts |
| G4 Motion | Under 20% of the part's pixels change at peak | Frozen output, motion declared but not drawn |
| G5 Pivot | Over 30% of the part's pixels at the joint change and its fitted motion does not keep the joint within 4 px | Rotating around the wrong point |
| G6 Loop and fidelity | Frame at t=2 differs from t=0, or frame 0 differs from the image | Loop jumps, flipped or shifted images |

### Validation (before any model ran)

For each of the 21 scored tasks we built a reference animation from hand-made part masks and pivots, plus 10 broken copies
(whole image, missed thumb, hole, frozen, center pivot, no loop, wrong part, and three detachment copies).
A check counts for a task only if the reference passes it (153 of 161 task-check pairs kept; see
`validation/admission.md`). Broken copies caught where an intended check applies:

| Broken copy | Caught |
| --- | --- |
| whole | 21/21 |
| missed thumb | 15/21 |
| hole | 21/21 |
| frozen | 21/21 |
| center pivot | 16/16 |
| no loop | 20/21 |
| wrong part | 21/21 |
| detach small | 15/21 |
| detach tip | 20/21 |
| gap seam | 13/16 |

Every copy whose part really comes apart is caught except two on the lace veil (T19), where the connectivity checks are
dropped. Remaining blind spots: a missed piece that ends up hidden under the moving part (heads, jumps), a 6-degree veil
flutter, and T07's no-loop copy (the earrings are too small for G6). The same checks run on synthetic layered characters,
and on valid alternate animations in five styles to measure false fails; see `results/grader_v3.md`.

## Results

| Model | Scored runs | Passed | Tier 1 | Tier 2 | Didn't run | Cost |
| --- | --- | --- | --- | --- | --- | --- |
| DeepSeek V4 Flash Vision | 13 | 1 (8%) | 0/9 | 1/4 | 12 | $0.549 |
| Grok 4.7 | 14 | 1 (7%) | 0/10 | 1/4 | 12 | $1.415 |
| Kimi K3.1 Pro | 15 | 3 (20%) | 2/11 | 1/4 | 0 | $3.113 |
| Nemotron 3.5 Super VL | 21 | 0 (0%) | 0/12 | 0/9 | 0 | $0 |
| Qwen 3.8 27B | 15 | 3 (20%) | 2/10 | 1/5 | 1 | $0.458 |
| Claude Sonnet 5.5 (Claude Code, Valkyrie) | 21 | 12 (57%) | 6/12 | 6/9 | 0 | not reported |

## Failure rate per check

| Check | DeepSeek V4 Flash Vision | Grok 4.7 | Kimi K3.1 Pro | Nemotron 3.5 Super VL | Qwen 3.8 27B | Claude Sonnet 5.5 (Claude Code, Valkyrie) |
| --- | --- | --- | --- | --- | --- | --- |
| G1 Isolation | 0/1 | 0/2 | 2/15 | 16/21 | 5/14 | 4/21 |
| G2 Integrity | 0/0 | 1/2 | 4/10 | 4/14 | 1/9 | 3/12 |
| G2b Connectivity | 0/1 | 1/2 | 9/14 | 7/20 | 4/13 | 0/0 |
| G2c Residual | 0/1 | 1/1 | 6/14 | 3/19 | 2/12 | 0/0 |
| G3 Area | 0/1 | 0/2 | 1/15 | 12/21 | 4/14 | 3/21 |
| G4 Motion | 0/1 | 0/2 | 0/15 | 1/21 | 3/14 | 1/21 |
| G5 Pivot | 0/1 | 1/1 | 4/14 | 13/16 | 4/12 | 5/13 |
| G6 Loop/fidelity | 0/1 | 0/2 | 1/15 | 17/21 | 4/14 | 3/21 |

![pass rate](results/charts/pass_rate.png)

![failures](results/charts/failures_by_check.png)

Per-run detail: `results/runs.csv`. Every run's animation: `results/library/`.


### Failure rate per check (Nemotron 3.5 Super VL)

| Check | Runs failing |
| --- | --- |
| G1 Isolation | 16/21 (76%) |
| G2 Integrity | 4/14 (29%) |
| G2b Connectivity | 7/20 (35%) |
| G2c Residual | 3/19 (16%) |
| G3 Area | 12/21 (57%) |
| G4 Motion | 1/21 (5%) |
| G5 Pivot | 13/16 (81%) |
| G6 Loop and fidelity | 17/21 (81%) |

### What the failures look like

- **Hand at the knee (T01).** The model whited out a box where the hand was, then drew the hand waving at the boy's knee: it used
  image coordinates in a y-up camera.
- **Head disappears (T09, "nod").** Most of the head vanishes; G2 and G3 fail.
- **White bar through the face (T14, hat tilt).** The cut-out rectangle is blanked and never refilled; G1 fails.
- **Gap at the wrist (T21).** The hand rotates away from the forearm, leaving a white gap; G5 fails.
- **Floating fingers (T03).** A rectangular cut leaves fingertips behind; G1, G5, G6 fail.

All runs are in `results/library/` as GIFs.

## Limits

- Single-shot models (OpenRouter) and the Claude Code agent (Valkyrie) are different setups; compare within a setup. Some single-shot runs were lost to network drops, so run counts differ by model.
- Single-turn generation with one repair turn for outputs that don't run. An agent that renders and looks at its own output
  might do much better; that's the natural next experiment.
- Checks are tolerant of faint artifacts (e.g. a light halo around a cut-out). G2b counts a repaint of the uncovered area in a
  neighbouring colour as a loose piece, its main source of false fails on valid animations (`results/grader_v3.md`).
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
