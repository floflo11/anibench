# Morning checklist (Iris)

Submissions are due **2:00 PM** at hackathon.vals.ai. Target: submit by 1:45 PM.

## What's done
- 24 tasks (21 scored automatically, 3 human-labeled), part masks, renderer, six checks.
- Checks validated with a reference animation and 7 deliberately broken copies per task
  (`validation/admission.md`).
- Real model runs: **Nemotron 3.5 Super VL** (free on OpenRouter): 24 tasks + a 2nd try on the 12 Tier 1 tasks.
  **0/33 scored runs passed** (17 flipped/shifted the image, 6 blank canvas, 10 image right but animation wrong).
- Smoke test: **Qwen 3.8 27B passed T01** (correct wrist wave), so the tasks are solvable.
- Failure library (GIF per run) in `results/library/`, charts in `results/charts/`, demo video `results/demo.mp4`.
- Write-up: `WRITEUP.md`. Harbor tasks for Valkyrie: `harbor/` (21 tasks).
- Presentation deck (10 slides, with animated failure GIFs): https://claude.ai/artifact/KRASwPWRAWUyXjYzcaQ3Yg
- Design doc: https://claude.ai/artifact/Cv7BuksqSPRVYJRgUz98Qe

## Why Sonnet 5.5 and GPT-6.1 Sol are not in the results yet
Your OpenRouter account has **$0 credits** (free tier), so OpenRouter refused paid models.
Adding credits is a payment, so I left it for you.

## To add Sonnet 5.5 + Sol (about 30-40 min, est. $15-25)
1. Add credits on openrouter.ai (Settings > Credits). $25 covers 3 tries x 24 tasks x 2 models with margin.
2. Tell Claude in the chat: "credits added, run sonnet and sol". The runner is already loaded in the
   browser pane's openrouter.ai tab (`AB`), and the job list is `runs/jobs/full.json`.
   Claude pulls the outputs, grades them, and regenerates `results/`, `WRITEUP.md`, charts and the video.
   If the browser tab was closed, Claude re-injects `src/browser_runner.js`.

Alternative: run the Harbor tasks on Valkyrie with the hackathon's Claude/OpenAI credits (next section).

## Upload to Valkyrie (from your Terminal)
```bash
git clone https://github.com/floflo11/anibench && cd anibench/harbor
valkyrie login                 # if not already
valkyrie org use <team org>
# then follow quickstart step 3 to upload this folder as a dataset (Harbor task format)
```
Not tested here: I couldn't build Docker images in my sandbox. Check that one task builds and its oracle
(`solution/solve.sh`) scores 1 before uploading all 21.

## Submit (hackathon.vals.ai)
- Code repository: https://github.com/floflo11/anibench (private; add judges or make it public if required)
- Write-up: `WRITEUP.md`
- Demo video: `results/demo.mp4`

## Clean-up after the hackathon
- Your OpenRouter key is saved in the browser pane's openrouter.ai tab (localStorage `ab_key`).
  Rotate the key on openrouter.ai, or clear it with: `localStorage.removeItem('ab_key')`.
- Delete `~/Projects/animbench/env` if you no longer need it.
