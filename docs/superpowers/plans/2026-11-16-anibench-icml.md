# anibench → ICML 2027: Implementation Plan

> For agentic workers: follow superpowers-style subagent-driven development. One fresh subagent per task, in its own git worktree/branch. TDD where code is involved (write the failing test, see it fail, implement, see it pass, commit). The main agent reviews every branch twice (spec compliance, then code quality) before merging to `main`.

**Goal:** Submit a benchmark paper to ICML 2027 (abstract and author list Jan 14, full paper Jan 22, AoE) under the "Datasets, Evaluations and Benchmarks" contribution type.

**Thesis:** anibench measures whether a model can *make a local change without side effects*. Animating one named part of a character is the visual instance: the asked-for change must happen (motion, pivot, loop), and everything else must not change (isolation, integrity, area). Pixel checks make side effects measurable exactly, with no model judge.

**Architecture:** Unchanged at the core. A task = image + part masks + pivot + instruction. A model writes a three.js page exposing `window.setTime(t)`. We render 25 frames in pinned headless Chromium and run deterministic checks (`src/graders.py`). Harbor tasks run on Valkyrie.

**Tech stack:** Python 3 (numpy, scipy, scikit-image, Pillow, pytest), Playwright + Chromium, three.js (vendored), Harbor, Valkyrie CLI. No network in the sandbox beyond git; model calls run on Valkyrie.

**Defaults chosen (change any of them):**
- D1. Animation stays the core task family. A small **static local edit** family (recolor, resize or rotate one part, 1 frame) is added as a control. It separates "can't localize" from "can't animate".
- D2. Images come from two sources:
    - (a) Raster illustrations: newly generated or CC0, annotated with a polygon tool.
    - (b) A **synthetic layered-character generator** with exact masks. It lets part size, occlusion and chain length vary under control, for E5.
- D3. All model runs go through Valkyrie. Iris launches them from her terminal.
- D4. Paper text is written by the authors. Agents produce code, data, figures, tables and outlines, and AI use gets disclosed per ICML rules.

---

## Workstreams and gates

| WS | What | Owner | Gate (done when) | Target |
|---|---|---|---|---|
| WS1 | Grader v2 | agent | Every mutation type is caught ≥ 90% where the check applies; detached-part detection ≥ 90%; reference passes 100% | Nov 29 |
| WS2 | Task pipeline (annotator + converter) | agent | The existing 24 tasks regenerate byte-identically from JSON annotations; 10 new images annotated in < 10 min each | Nov 29 |
| WS3 | Synthetic characters | agent | ≥ 100 synthetic tasks; the reference passes all of them; difficulty factors are recorded per task | Dec 6 |
| WS4 | Eval protocol and stats | agent | Three settings (single-shot, render-feedback, agent) exported to Harbor; k samples; bootstrap CIs in reports | Dec 6 |
| WS5 | Research and framing | agent | refs.bib ≥ 40 entries; locality/side-effect literature memo; public leaderboard table for E8 | Nov 23 |
| WS6 | Scale to 300+ tasks | Iris + agents | ≥ 300 admitted tasks (≥ 150 raster, ≥ 100 synthetic, ≥ 50 static edits); dev/test split frozen | Dec 20 |
| WS7 | Valid reference animations | agents + Iris review | 2 to 3 valid animations per task in ≥ 2 styles; false-fail rate reported | Dec 24 |
| WS8 | Model sweep (E1 to E3, E8) | Iris launches, agents analyze | ≥ 8 models × 3 settings × k=3 on the test split | Jan 8 |
| WS9 | Human study + judges (E4) | Iris recruits raters, agents build the UI and analysis | 600 clips × 3 raters; κ per check; judge comparison table | Jan 10 |
| WS10 | Red-team the checks (E7) | agent | Exploit list plus patches; regression tests for each exploit | Jan 3 |
| WS11 | RL pilot (E6, optional) | agent + compute | Go/no-go Jan 2; in the paper only if ready by Jan 18 | Jan 18 |
| WS12 | Paper | Iris writes; agents build figures and tables | Abstract Jan 14, PDF Jan 22 | Jan 22 |

Human decisions needed: co-authors (before Jan 14), raw image source (D2a), rater recruitment, budget approval ($5.5k–13.5k), Valkyrie launches.

---

## Wave 1 (dispatched Nov 16): detailed tasks

### Task 1.1: Grader v2 (WS1). Branch `grader-v2`
**Files:** modify `src/graders.py`, `src/validate.py`, `src/reference.py` (mutations); create `tests/test_graders.py`, `tests/conftest.py`.
- [ ] Write pytest fixtures: tiny synthetic frames (e.g. 64×64) with a known part, so the tests run in seconds without Chromium.
- [ ] Failing test: a part that splits into two pieces mid-animation (a detached "thumb" of ≥ 20 px) must fail a new check **G2b Connectivity**. A whole part moving rigidly must pass.
- [ ] Implement G2b. On every frame, the moving part's foreground inside the allowed region must keep the same number of connected components as frame 0, using the 8-connected label count with a min-size filter. Report it as a separate key; it folds into the overall pass.
- [ ] Add mutations to `validate.py`: `detach_small` (a 20–60 px piece left behind), `detach_tip` (the far end of the part offset), `gap_seam` (a 2-px seam opened at the pivot).
- [ ] Re-run the full validation (`python3 src/validate.py`), regenerate `validation/admission.md`, and record the detection rate per mutation type.
- [ ] Gate: missed-thumb class ≥ 90%, every other class ≥ 90% where applicable, reference 100%. If not met, tune thresholds and document why.
- [ ] Commit with test results in the message.

### Task 1.2: Task pipeline (WS2). Branch `task-pipeline`
**Files:** create `tools/annotator.html` (single file, no network), `src/annotations.py`, `tests/test_annotations.py`; read `src/parts.py`, `src/tasks.py`, `annotations/`.
- [ ] Define `annotations/<image_id>.json` schema v1:
    - Image path and size.
    - Parts: each with name, polygon list, pivot [x, y], parent, and `exclude` (the names of parts carved out of it).
    - Optional skull/keep masks.
    - Style, subject and license fields.
- [ ] Failing test: converting the JSON for the current A1–A4 and B1–B2 characters reproduces the masks in `tasks/T01..T24` exactly (or ≤ 0.1% pixel difference, documented).
- [ ] Implement `src/annotations.py`, covering JSON to masks and pivots and task generation. It reuses the `tasks.py` writer, and `parts.py` becomes a thin legacy shim.
- [ ] Build `tools/annotator.html`:
    - Load an image, click polygons per part, click the pivot, choose a parent, export JSON.
    - Keyboard shortcuts.
    - Works from `file://`.
- [ ] Write `docs/annotating.md` as a one-page guide for annotators.
- [ ] Commit.

### Task 1.3: Synthetic layered characters (WS3). Branch `synthetic`
**Files:** create `src/synth/` (generator), `tests/test_synth.py`, and `tasks_synth/` output (gitignored except a 10-task sample).
- [ ] Design a parametric 2D character as layered shapes, with flat colours and outlines, in a few style presets. It has a head, torso, arms (upper arm, forearm, hand, fingers), legs and accessories (hat, earring, tail). Exact per-part masks and joint pivots come from construction.
- [ ] Controlled factors, recorded per task in `spec.json`:
    - Target part area (px).
    - Occlusion (%).
    - Chain length (1 to 4 joints).
    - Distance to the nearest non-target part.
    - Style preset.
- [ ] Failing test: generated masks are disjoint where expected, pivots lie on the part boundary, and the composite PNG equals the layer union.
- [ ] Output tasks in the existing format (`spec.json`, `image.png`, `allowed.png`, `target.png`, optional `skull.png`, `prompt.md`).
- [ ] Run `src/reference.py` and the graders on ≥ 30 generated tasks. The reference must pass 100%; fix the generator if not.
- [ ] Commit, including a contact-sheet PNG of 30 characters.

### Task 1.4: Eval protocol and statistics (WS4). Branch `protocol`
**Files:** modify `src/export_harbor.py`, `src/report.py`; create `src/stats.py`, `harbor_template/preview.py`, `tests/test_stats.py`.
- [ ] `src/stats.py` with tests:
    - pass@1 from k samples.
    - Task-level bootstrap 95% CI (10k resamples, fixed seed).
    - Paired bootstrap for model-vs-model differences.
    - Partial-credit score (the share of checks passed).
- [ ] Export three settings as separate Harbor datasets:
    - `single`: instruction says to write `/app/index.html` and stop; the agent turn budget is minimal.
    - `feedback`: adds `preview.py`, which renders 6 frames to `/app/preview/*.png` so the agent can look once.
    - `agent`: full tools and a fixed budget.
  Document the exact Valkyrie commands in `docs/protocol.md`.
- [ ] `report.py` reports CIs and partial credit per model × setting, and per-check failure rates.
- [ ] Commit.

### Task 1.5: Research and framing (WS5). No code; writes `docs/research/`
- [ ] `docs/research/refs.bib`: ≥ 40 verified entries, each with a URL or DOI, and nothing invented. Cover:
    - Visual code generation (Design2Code, ArtifactsBench, Code3DBench, WorldCoder-Bench, P3D-Bench).
    - SVG and Lottie animation (VAnim, LiveSVG, Graphic-Design-Bench, AniClipart, LogoMotion).
    - Articulation (Articulate-Anything).
    - Image-editing benchmarks that score unedited-region preservation.
    - Knowledge-editing "locality / specificity" metrics (ROME, MEMIT and successors).
    - Code-edit regression benchmarks.
    - LLM-as-judge reliability.
    - Benchmark methodology (contamination, saturation).
- [ ] `docs/research/locality.md`: a 1–2 page memo on how "locality / side effects" is measured across those fields. This is the related-work backbone for the thesis.
- [ ] `docs/research/leaderboards.md`: public scores for the models we'll test on 2–3 existing benchmarks (with source URLs and dates), for E8 rank correlation.
- [ ] Commit to branch `research`.

---

## Wave 2 (starts as Wave 1 merges, ~Nov 30), to be detailed then
- WS6 scaling: annotate raster images (needs Iris's image source decision), generate synthetic and static-edit tasks, admission, dev/test split, canary string.
- WS7 valid references in multiple styles, plus a false-fail analysis.
- WS10 red-teaming the checks.
- WS9 rater UI (a single HTML page; clips → labels CSV) and the analysis script.

## Wave 3 (Dec 14 to Jan 10)
- WS8 sweep on Valkyrie, plus analysis notebooks producing every paper table and figure from `results/`.
- WS9 study run and the judge comparison.
- WS11 RL pilot, go/no-go Jan 2.

## Wave 4 (Jan 10 to Jan 22)
- Figures and tables frozen Jan 12. Iris writes. An anonymized repo mirror. AI disclosure statement. Impact statement. Final checks.

## Tracking
- The task list in the app holds one item per subagent and per gate.
- `docs/superpowers/status.md` is updated by the main agent after each review: branch, state, gate result, follow-ups.
