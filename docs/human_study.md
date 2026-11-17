# Human study (E4): do the pixel checks agree with people?

The paper's claim is that anibench's deterministic pixel checks catch the failures a person sees. E4 tests it:
about 600 rendered clips, 3 raters each, rate pass/fail and name the defect. We then compare the human
majority with the pixel checks and with multimodal LLM judges that answer the same questions.

| Step | Tool | Output |
| --- | --- | --- |
| 1. Sample and render clips | `src/study/make_clips.py` | `rater/` bundle (manifest + clips), `key.json`, `judge_media/` |
| 2. Split into rater batches (optional) | `make_clips.py --split` | `batches/bNN/` |
| 3. Raters rate | `tools/rater.html` | one CSV/JSON export per rater (and batch) |
| 4. Judges rate | `src/study/judge_prompt.md`, `judge_schema.json` | one JSONL per judge (API calls are not part of this repo) |
| 5. Analyze | `src/study/analyze.py` | `results.json`, `table.tex`, `confusion.png`, `per_clip.csv`, `summary.md` |

A dry run of the whole chain (20 clips, simulated raters) is in `results/study_dryrun/`; see the end of this page.

## 1. Sampling

- **Pool.** Every graded run under `runs/<model>/<task>/<try>/` that produced frames: all models, all three
  settings (`single`, `feedback`, `agent`; older runs are `chat`/`core`), all scored tasks, all k samples.
  The repair turn's output is used when there was one (as `report.py` does). Runs with no HTML, a runtime
  error or no grades (tasks T22–T24) are left out; `--include-ungraded` keeps the last group.
  Runs graded on Valkyrie must have their `index_<stage>.html` (or frames) copied into the run dir first.
- **Stratified sample.** `--n 600 --seed 0` picks runs greedily so that tasks, models, overall pass/fail and
  each check's pass/fail are as balanced as the pool allows (`stratified_sample`). Rare outcomes, such as
  passes or G4 failures, are therefore over-sampled up to an even split. The numbers in the paper are
  agreement rates on this sample, not on the natural distribution of outputs; say so in the text. If a
  natural-distribution estimate is needed too, re-weight clips by stratum (the key has every field needed).
- **Anonymity.** Clip ids are salted hashes (`c` + 8 hex characters); the salt is random unless given and is
  stored only in `key.json`. The rater manifest has task, instruction, sizes and paths, never the model,
  setting or grader result. Raters get only the `rater/` folder (or a batch folder). The tool warns if a
  `key.json` is in the folder it opens.
- **Attention checks.** Five fixed clips are added to every study and every batch: two reference solutions
  that pass (T01 wave, T09 nod) and three obvious failures (T06 whole image rotates, T02 nothing moves,
  T20 the wrong hand waves). They are built from `src/reference.py` variants under `build/attention/`, look
  like any other clip, and are flagged with the expected answer only in `key.json`. A rater who gets fewer
  than 4 of 5 right is excluded (`--min-attention`); attention clips never enter the agreement numbers.

```bash
python3 src/study/make_clips.py --out build/study/e4 --n 600 --seed 0 --study-id anibench-e4-v1
python3 src/study/make_clips.py --out build/study/e4 --split 100      # 6 batches of 100 + 5 attention clips
```

Rendering takes about 8 s per clip (one Chrome, same renderer and flags as the grader). The rater bundle is
about 0.65 MB per clip (H.264 MP4, CRF 12, 3 loops), so 600 clips are about 400 MB; `judge_media/` is about
1.6 MB per clip. `build/` is gitignored; do not commit clips.

### What a clip looks like

Four synchronized panels: the original still (top left), the animation (top right), and the same zoom box
around the target part (the `zoom_gifs.py` box, from `allowed.png`) for the original and the animation
(bottom). The 2-second loop is 24 frames at 12 fps (frame 25 of the render is t = 2 s, which equals t = 0 for a
correct loop, so it is dropped); the MP4 holds 3 cycles so the browser's own loop seam comes only every 6 s.
Without ffmpeg the clip is a lossless animated WebP (no frame stepping or slow motion in the tool).

## 2. Rater instructions

The full text is built into the tool (Help, `?`). In short:

> Each clip shows a still image and an animation made from it. The animation was supposed to move one named
> part (the instruction above the clip) and nothing else, as a seamless 2-second loop. Watch at least two loops.
> **Did the animation do what was asked without breaking anything else?** Yes means the part moves as asked
> and you cannot see anything else change or break. If No, tick every problem you see:

| Code | Shown to raters | Pixel check |
| --- | --- | --- |
| `outside_moved` | Something outside the part moved | G1 isolation |
| `tore_split` | The part tore, split or left a piece behind | G2 integrity, G2b connectivity |
| `size_shape` | The part changed size or shape | G3 area |
| `barely_moves` | The part barely moves (or does not move) | G4 motion |
| `wrong_pivot` | The part rotates around the wrong point | G5 pivot |
| `loop_jump` | Jump at the loop, or the first frame differs from the image | G6 loop/fidelity |
| `other` | Other (describe) | none |

> Then say how sure you are: 1 unsure, 2 fairly sure, 3 certain.

The codes live in `src/study/common.py`; the tool, the judge schema and the prompt use the same list (tested).

Recommendations for the session: a 5-minute briefing with the Help text; a laptop or desktop screen at least
1280 px wide; Chrome, Edge or Firefox; no phones. Raters should not be told which models are in the study or
how the checks work.

## 3. Running the rating

1. Give each rater `tools/rater.html` (a single file) and their folder (`rater/` or `batches/bNN/`), zipped.
   Or host both on any static server and send `rater.html?manifest=bNN/manifest.json&rater=R07`.
2. The rater opens `rater.html` (double-click works; it runs from `file://` and makes no network requests),
   enters their rater ID and opens the folder.
3. Clips come in a random order seeded by rater ID, so raters see different orders. Answers autosave to the
   browser's localStorage after every change; reopening the page with the same rater ID and folder resumes.
   If storage is blocked (some private windows), a banner says so and the page warns before closing.
4. Keys: `Y`/`N` answer, `O T S B R L X` toggle defects (after No), `1 2 3` confidence, `Enter` save and next,
   `[`/`]` previous/next clip, `Space` play/pause, `Z` speed (1x, 0.5x, 0.25x), `,` `.` step a frame,
   `0` first frame, `?` help. A clip cannot be saved before it has been on screen for 4 s
   (`?minwatch=<ms>` changes this for pilots).
5. At the end the rater clicks Export JSON (or CSV) and sends the file. Each row has the rater ID, study ID,
   clip ID, position, answer, defects (list and one 0/1 column per code), other text, confidence,
   first-shown and answered timestamps, active time on the clip (ms, paused while the tab is hidden), the
   number of visits and edits.

### Time and pay estimate

Watching two loops takes 4 s and answering 10–20 s; with occasional slow-motion checks we expect **about
25–35 s per clip (0.5 min)**, to be confirmed in the pilot (the exports record time per clip;
`analyze.py` reports each rater's median). Per rater-batch of 105 clips that is 45–60 min plus a 5-minute
briefing, a sensible single session.

| Design | Ratings | Rater time | Cost at $20/h (+ ~33% platform fee) |
| --- | --- | --- | --- |
| 600 clips × 3 raters, 6 batches of 100 + 5 attention | 1,890 | ≈ 15–20 h (incl. briefings) | ≈ $400–$530 |
| Pilot: 60 clips × 3 raters | 195 | ≈ 2 h | ≈ $55 |

Pay by batch (a fixed amount per completed batch, e.g. $20 per 105 clips) rather than per clip, so speed is
not rewarded. Bonus or re-run raters who fail attention checks according to the platform's rules; decide
this before the study.

## 4. Judges

`src/study/judge_prompt.md` is the fixed prompt; it asks the rater's questions with the same codes and
requires one JSON object per clip matching `src/study/judge_schema.json`. Video-capable models get the rater
clip; image-only models get the original, its zoom and two 3×3 contact sheets (`judge_media/`). One call per
clip, temperature 0, one retry on invalid JSON, then the clip counts as missing for that judge (reported as
coverage). Calling the APIs is not part of this repo. Save each judge's answers as `judges/<name>.jsonl`.

## 5. Analysis

```bash
python3 src/study/analyze.py --key build/study/e4/key.json --ratings ratings/*.json ratings/*.csv \
    --judges judges/*.jsonl --out results/study
```

- **Inter-rater agreement:** Fleiss' kappa (variable raters per clip allowed) and Krippendorff's alpha
  (nominal), overall ("broken" = answered No) and per defect (ticked or not, a Yes counts as not ticked), with
  95% bootstrap CIs.
- **Human label:** strict majority of the kept raters per clip, overall and per defect (ties: no label).
- **Evaluators vs the human majority:** accuracy, precision and recall of "broken", F1, Cohen's kappa, with
  confusion counts. Rows: the pixel grader (overall pass, and per defect the mapped checks), each judge, and
  "Human (one vs. rest)": every single rating against the majority of the other raters on that clip, the
  ceiling an automatic evaluator can reasonably reach. Clips where no mapped check applies (e.g. G5 on T15)
  are skipped for that defect.
- **CIs:** percentile bootstrap that resamples tasks (clips of a task move together), 10,000 resamples,
  seed 0, the same convention as `src/stats.py`; `--boot-unit clip` resamples clips.
- **Outputs:** `table.tex` (two booktabs tables, ready for `\input`), `confusion.png`, `per_clip.csv` (joins
  the key, so it names models: for the authors only), `results.json`, `summary.md`.

Primary result for the paper: Cohen's kappa of the pixel grader's overall verdict against the human majority,
next to the human one-vs-rest kappa and each judge's kappa. Secondary: the per-defect table, which shows which
check matches which human complaint.

## Dry run (Nov 2026)

```bash
python3 src/study/make_clips.py --out build/study/dryrun --n 20 --seed 0 --salt dryrun --study-id anibench-e4-dryrun
python3 src/study/fake_ratings.py --key build/study/dryrun/key.json --out build/study/dryrun/fake --raters 3 --lazy 1 --judges 1
python3 src/study/analyze.py --key build/study/dryrun/key.json --ratings build/study/dryrun/fake/ratings/*.json \
    --judges build/study/dryrun/fake/judges/*.json --out build/study/dryrun/analysis
```

20 clips from the 65 local runs (5 models, 18 tasks) plus the 5 attention clips. The ratings are
**simulated** (`fake_ratings.py`: the grader verdict plus noise; one inattentive rater who answers Yes to
everything and is excluded by the attention checks; one noisy fake judge), so the numbers only show that the
chain runs. The manifest, key, simulated exports and analysis outputs are committed in
`results/study_dryrun/` (no clips). The rater tool was also driven end to end on the real 25-clip bundle
(headless Chrome, H.264 playback) and its CSV export parsed by `analyze.py`.

Tests: `tests/test_study_clips.py`, `tests/test_rater_ui.py` (Playwright + Chrome), `tests/test_study_analyze.py`
(kappa and alpha against hand-computed and published values).
