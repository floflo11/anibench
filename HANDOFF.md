# animbench — handoff for a new chat

Read this first, then the design doc: https://claude.ai/artifact/Cv7BuksqSPRVYJRgUz98Qe
(Character Animation Eval — Design Spec & Cost Estimate). The doc is the source of truth for
tasks T01–T24, the output contract, graders G1–G6, broken-copy validation, demo and write-up plan.

## Goal
Vals Hacks Track 1 benchmark. Submission due Sun Nov 15, 2:00 PM PT (target 1:45 PM).
Iris wants to wake up to a ready-to-submit, ready-to-present result. Do NOT submit on
hackathon.vals.ai. Push only to a PRIVATE GitHub repo she names.

## Decisions made
- Models: Claude Sonnet 5.5 and GPT-6.1 Sol only (via OpenRouter; resolve exact slugs from
  /api/v1/models). First run a cheap open-source model as a smoke test.
- Key file: ~/Projects/animbench/env (OPENROUTER_API_KEY). Never print it; add `env` to .gitignore.
- Work in the device workspace: $HOME/mnt/Projects/animbench (needs network allowlist:
  openrouter.ai, pypi.org, files.pythonhosted.org, registry.npmjs.org, github.com).
- No video-model judge. Six image-math graders, validated with a reference animator + broken copies.
- Tier 3 (T22–T24) is human-labeled only.

## Images (already prepared, in images/)
- lineup_task.png 1200x600 (4 kids A1–A4, left to right). Source was transparent; composited on white.
- toddlers_task.png 1024x683 (B1 left in red jacket, B2 right in navy jacket).
- annotations/*_fg.png = foreground masks (white = character) from the original alpha.
- Background colour for graders: white (255,255,255).

## Rough annotation coordinates (working-size pixels, x,y) — refine before use
Lineup:
- A1 boy plaid (x~50–265): raised hand box x193–268,y115–197; wrist (233,192); elbow (240,260);
  head x75–200,y5–150; neck (145,150).
- A2 girl pigtails (x~300–570): raised hand x500–565,y155–228; wrist (520,226); elbow (540,258);
  left pigtail x305–365,y95–240 tie (355,110); right pigtail x465–515,y100–235 tie (480,105)
  (right pigtail sits next to the hand — careful); legs x350–490,y360–600.
- A3 small boy striped (x~605–865): raised hand x755–820,y195–258; wrist (780,258); elbow (780,318);
  head x635–760,y105–245; neck (695,250).
- A4 girl white dress (x~840–1150): raised hand x1075–1140,y160–235; wrist (1098,235);
  elbow (1100,300); earrings at (967,218) and (1062,205), earlobes (968,195),(1062,185);
  veil x840–960,y30–460, top (920,80); hat x880–1090,y20–140.
Toddlers:
- B1 red jacket (x~70–470): raised hand (viewer's left) x70–150,y120–205; wrist (120,200);
  arm runs to shoulder ~(190,230); hat x150–465,y5–190; head under hat.
- B2 navy jacket (x~525–1000): raised hand x870–960,y120–200; wrist (885,200);
  shoulder ~(830,240); hat x555–840,y0–190.

## Build order (see doc Timeline)
1. Harness: Playwright Chromium (software WebGL), load page, wait ANIM_READY, setTime(i*2/48)
   for i=0..48, capture canvas -> frames + GIF/MP4.
2. Graders G1–G6 (thresholds in doc). Reference animator (canvas or three.js) using masks+pivots.
   Broken copies: whole image, missed thumb, hole left, frozen, center pivot, no loop, wrong arm.
3. Runner: OpenRouter, image + instruction + contract -> index.html; up to 3 revision turns with
   render errors and a frame contact sheet as feedback. Concurrency ~8. Log tokens and cost.
4. Smoke test (open-source model, 2 tasks) -> pilot (T01,T07,T13 x Sonnet, Sol) -> full 24 x 3 tries.
5. Results: pass rates per model/tier, failure rate per grader, GIF library, charts.
6. Harbor task export for Valkyrie (vendor three.js), write-up, slide deck, README.

## Status at handoff (session 1, ~3:10 AM PT)
- Repo: github.com/floflo11/anibench (private), branch main. Mirror folder: ~/Projects/animbench.
- vendor/ holds three.js r188dev (three.module.js imports ./three.core.js).
- Done: design doc, images prepared, foreground masks, rough coordinates above.
- Not done: everything in "Build order". Start at step 1.
- Network in session 1 was blocked for openrouter.ai, pypi, npm. First thing: test
  `curl -s -o /dev/null -w '%{http_code}' https://openrouter.ai/api/v1/models` (expect 200).
