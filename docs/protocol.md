# anibench evaluation protocol

The pre-protocol results compare one agent (Claude Code on Valkyrie, 21 tasks) with single-shot chat
models (8 to 21 tasks), one run each, with no confidence intervals. The protocol below replaces that.
Every model runs the same tasks in the same three settings, with k samples per task. Every number comes
with a task-level bootstrap CI, and model comparisons use paired CIs on shared tasks.

## 1. Settings

All three settings are exported from the same `tasks/` by `src/export_harbor.py --setting <name>`. Each one
is a separate Harbor dataset, `anibench/<setting>`. In every setting the task text, image, contract,
verifier, checks and the 900 s wall-clock budget (`task.toml [agent] timeout_sec`) are the same. Only the
paragraph after the task text and the tools in the image change. Text samples are in
`harbor_samples/<setting>/anibench-t01/`.

| Setting | Dataset | What the agent may do | Extra in the image | Turn cap (`TURNS_<setting>`) |
| --- | --- | --- | --- | --- |
| `single` | `anibench/single` | Look at `/app/image.png`, write `/app/index.html` once, stop. No code (beyond writing the file), no rendering, no revisions. | nothing | 5 |
| `feedback` | `anibench/feedback` | `single`, plus one run of `anibench-preview` after writing, then revise and stop. | `/opt/anibench/{preview.py, render.py}` and `/usr/local/bin/anibench-preview` | 10 |
| `agent` | `anibench/agent` | Full tool use (any code, any rendering) within the budget. | nothing | 40 |

- The `agent` setting shows the agent exactly the legacy `anibench/core` task: `instruction.md` and
  `environment/` are byte-identical (tested). Only the verifier's audit counters and the oracle probe differ.
- **Preview tool** (`harbor_template/preview.py`). It renders `/app/index.html` with the grader's own
  `render.py`: same Chromium build and flags (software WebGL via SwiftShader), viewport = image size,
  device scale factor 1, the largest canvas captured with `toDataURL`, composited on white. It saves 6
  frames at t = 0, 0.4, 0.8, 1.2, 1.6, 2.0 s (frame i at t = 2i/5) to `/app/preview/frame_0.png …
  frame_5.png`, prints page console errors, and writes `/app/preview/error.txt` if the page does not
  become ready. Calls are logged to `/var/lib/anibench/preview_calls`. After the first call the tool
  refuses to run, and a call made before `index.html` exists still counts.
- **No grader leak.** `environment/` is the Docker build context. It holds only `Dockerfile`, `image.png`,
  `vendor/three*.js` and, for `feedback`, the preview tool (renderer only, no `graders.py`, spec or masks).
  `tests/test_export.py` checks this for all 21 tasks and 3 settings. Harbor uploads `tests/` to `/tests`
  only for the verifier, after the agent finishes, and `solution/` only for the oracle. Two probes confirm
  this on Valkyrie, because it cannot be tested from here:
  - The oracle's `solve.sh` records whether `/tests` exists during the agent phase.
  - `anibench-preview` records the same.
  - The verifier reports both as `probe_tests_visible` (0 = not visible).

### Audit counters in `reward.json` (settings exports only)
`reward.json` stays numbers-only: `reward`, one 1/0 per applicable check, plus:
- `preview_calls`: how many times the agent ran `anibench-preview` (feedback; > 1 = attempted reuse,
  which the tool refused).
- `probe_tests_visible`: 1 if `/tests` was visible to the agent phase. It must be 0 everywhere. Oracle
  runs always record it; agent runs record it only when they called the preview.

`src/import_valkyrie.py` copies these into each `grade_first.json` under `audit`.

### Instruction compliance
The `single` and `feedback` limits are instructions plus a turn cap, not a sandbox: an agent with a shell
could still run code. Before reporting, check compliance:
- In `feedback`, check `preview_calls` (0, 1, or more than 1).
- In all settings, read the agent trajectories in `out/<label>/outputs/`.

Report the share of runs that broke the rules, and give results with and without them.

## 2. Samples, models and harnesses
- **k = 3** samples per (model, setting, task). Each sample is a separate Valkyrie run with fresh
  containers. `K` in `scripts/run.sh` sets it.
- Every model runs **all** scored tasks (21 now; the frozen test split later) in all three settings. A
  run that does not finish gets reward 0 and counts as a failed sample, not a missing one.
- Harness. Claude Code (`claude_code-v1.0.0`) can open images, and Terminus 2 sees only terminal text.
  This matters most in `single` and `feedback`, where running code is not allowed: a Terminus 2 model can
  see neither the image nor the preview frames. Report harnesses as separate groups and compare models
  only within a harness (see Open questions).

## 3. Commands (run from the repo root, on the Mac with `valkyrie login`)

```bash
valkyrie org use hackathon-arena-horses-10639006c9

# 1. Export and upload the three datasets (writes build/harbor-<setting>/, gitignored)
scripts/run.sh push-protocol
#   = for s in single feedback agent; do
#       python3 src/export_harbor.py --setting $s
#       valkyrie dataset push anibench/$s build/harbor-$s --tag v1
#     done

# 2. Oracle on all three. Every task must score reward 1 with probe_tests_visible 0.
scripts/run.sh oracle-protocol
#   = valkyrie run start --agent oracle --dataset anibench/<setting>@v1 --provider modal --concurrency 8 --connect

# 3. Smoke test: one sample of T01 in each setting before spending on the sweep
#    (then delete runs/sonnet-cc/T01/{single,feedback,agent}-1 so the sweep starts clean)
K=1 IDS=anibench-t01 scripts/run.sh protocol claude

# 4. The sweep: K samples x 3 settings, imported into runs/ after each run, then report
K=3 scripts/run.sh protocol claude      # Claude Code + Sonnet 5.5, label sonnet-cc
K=3 scripts/run.sh protocol openai      # Codex + GPT-6.1 Sol, label sol-codex
K=3 scripts/run.sh protocol other       # each $OTHER_MODELS model via Terminus 2, label t2-<model>
```

Each run that `scripts/run.sh protocol` starts is equivalent to:

```bash
valkyrie run start --agent claude_code-v1.0.0 --dataset anibench/<setting>@v1 \
  --model anthropic/claude-sonnet-5-5 --provider modal --concurrency 8 \
  -s ANTHROPIC_API_KEY anthropic-api-key [-k <turn-cap-kwarg> <TURNS_setting>] --connect
valkyrie run results <run-id> --path out/<label>/results.json
valkyrie run outputs <run-id> --output-dir out/<label>/outputs
python3 src/import_valkyrie.py out/<label>/results.json sonnet-cc --setting <setting> --try <i>
```

For Codex use `--agent codex-v1.0.0 --model gpt-6.1-sol -s OPENAI_API_KEY openai-api-key`. For Terminus 2
use `--agent terminus2 --model openrouter/<model> -s OPENROUTER_API_KEY openrouter-api-key -k max_turns <N>`.

### Budget flags: what is known and what is not
- **Wall clock:** 900 s per task in every setting, from `task.toml`. It applies to any agent.
- **Turn cap for Terminus 2:** `-k max_turns N` (already used by `scripts/run.sh others`). The protocol
  passes 5 / 10 / 40.
- **TODO(valkyrie): turn cap for `claude_code-v1.0.0` and `codex-v1.0.0`.** Checked 2026-11-16: `valkyrie run start --help` only
  offers generic `-k/--kwarg KEY VALUE` passthrough and lists no agent-specific keys, so the name depends on the agent. Still to check:
  - The agent definitions in `vals-ai/public-agent-registry` (`examples/claude_code-v1.0.0`,
    `examples/codex-v1.0.0`), for a `max_turns` (Claude Code CLI `--max-turns`) or equivalent kwarg.

  Once it is known, set `CAP_KWARG_CLAUDE=<name>` / `CAP_KWARG_OPENAI=<name>`. While they are empty, those
  agents run with only the wall-clock budget, and the turn limit in `single`/`feedback` rests on the
  instruction alone.
- **Multiple attempts (checked 2026-11-16):** `valkyrie run start` has `-n/--count N` (1 to 10), which starts N
  independent runs. `scripts/run.sh` keeps one `run start` per sample so each run ID maps to one `--try i`
  import, but `-n K` is a valid alternative when importing by run ID.
- **Labels:** `-l/--label TEXT` attaches a label to a run. Use `<setting>-<model>-try<i>` to make runs easy to find.
- **Token or cost caps:** `run start --help` exposes none. Record cost per run from the console output.

## 4. Import and report
- `src/import_valkyrie.py <results.json> <label> --setting <s> --try <i>` writes
  `runs/<label>/T../<s>-<i>/grade_first.json` with `setting`, the per-check results and `audit`. Without
  `--setting` it behaves as before (legacy core runs go to try folder `1`).
- Use the same label for a model across settings (`sonnet-cc`, `sol-codex`, `t2-<model>`). The setting
  lives in the try folder and the grade file.
- `python3 src/report.py` keeps the legacy outputs (`results/summary.json`, `runs.csv`, `README.md`, charts:
  first try of each model) and adds:
  - `results/protocol.md` and `results/protocol.json`: per model × setting, tasks, k, pass@1 [95% CI],
    partial credit [95% CI], runs with no output, and per-check failure rates. Also a paired comparison table:
    every pair of models within a setting, and every pair of settings within a model.
  - `results/charts/protocol_pass1.png`: pass@1 with CIs per model × setting.
  - Pre-protocol runs appear as two more settings: `core` (Valkyrie legacy dataset) and `chat` (local
    single-shot API runs, with one repair turn for pages that did not run). They are never pooled with
    the protocol settings.
  - Not scored: tier 3 (human-labelled) tasks and `API_ERROR` runs (an infrastructure failure, not a model
    failure). They are counted in the `Excluded` column.

## 5. Statistics (`src/stats.py`, tested in `tests/test_stats.py`)
Notation: task t has n_t samples, c_t of which pass (reward 1 = every applicable check passes).

- **pass@1.** Per task, p̂_t = c_t / n_t. This is the unbiased pass@k estimator
  1 − C(n−c, k) / C(n, k) at k = 1. `stats.pass_at_k` gives any k ≤ n. The score is the mean of
  p̂_t over tasks, so every task has equal weight, whatever its k.
- **Partial credit.** For one run, the share of the task's applicable checks that passed. A check is not
  applicable to a task when its result is absent or null, and it is left out of both numerator and
  denominator. A run with no gradable output (no HTML, runtime error, timeout) scores 0. It is averaged
  over the task's samples, then over tasks.
- **Per-check failure rate.** For check G: failed / graded, over the runs where G was graded. Runs with no
  output are left out here and reported separately as "No output". Checks are read from the grade files,
  so new checks (e.g. `G2b` from grader v2) show up without code changes.
- **95% CI.** Percentile bootstrap over **tasks**: 10,000 resamples with replacement of the per-task values,
  fixed seed 0. Samples are averaged within a task before resampling, so the CI reflects task-set variance
  plus the averaged sample noise. With 21 tasks the CIs are wide (±15–20 pp). That is expected, and the
  reason to scale to 300+ tasks.
  When every task scores 0 (or 1) the bootstrap CI collapses to [0, 0]. For such cells, also give the count
  (e.g. 0/21 tasks) and, if needed, an exact binomial bound over tasks (95% upper bound ≈ 3/n).
- **Paired comparison.** For two cells A and B (two models in one setting, or two settings for one model),
  take the tasks both ran and the per-task differences d_t = A_t − B_t. Report mean(d) with a percentile
  bootstrap CI that resamples tasks (10,000 resamples, seed 0) and `P(Δ ≤ 0)`, the share of resamples
  where A is not better. Pairing removes the task-difficulty variance shared by both cells, so the CI is
  much tighter than the difference of two unpaired CIs. A difference is significant at 5% (two-sided)
  when its CI excludes 0.
- **Many comparisons.** The table lists every pair, so expect about 1 in 20 CIs to exclude 0 by chance.
  For paper claims, pre-register the few comparisons that matter (e.g. feedback − single per model, and
  the top two models per setting), or apply a Holm correction to `P(Δ ≤ 0)`.

## 6. Open questions for Iris
1. **Image access in Terminus 2.** Under the `single`/`feedback` no-code rule, Terminus 2 models are blind.
   Options:
   - (a) Run `single` for non-Claude/Codex models through the chat API path instead (image in the prompt,
     `src/jobs.py` + browser runner). This breaks D3 (all runs on Valkyrie).
   - (b) Allow image inspection by code in every setting.
   - (c) Report Terminus 2 only in `agent`.
2. **Codex image viewing.** Check that `codex-v1.0.0` can view `/app/image.png` and the preview PNGs. If it
   cannot, it is blind in `single` and `feedback` too.
3. **Turn cap values.** 5 / 10 / 40 are placeholders. Set them after the smoke test shows how many turns a
   write plus a preview really take for each harness.
