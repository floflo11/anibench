# Status board (main agent)

Updated: 2026-11-16 (evening)

| Task | Branch | Agent | State | Gate result | Notes |
|---|---|---|---|---|---|
| 1.1 Grader v2 | grader-v2 | grader | merged | partial pass: every real split caught (missed thumb 11/11, detach 45/45); raw missed thumb 11/20 because 9 copies never come apart (the tip slides past while touching); reference 100% | Re-grading model runs: 8 flips (5 real detachments incl. kimi/qwen T06, 2 dragged shirt strips, 1 borderline). Blind spot for tips that slide past while still touching: a rigid-motion residual check is queued for grader v3 |
| 1.2 Task pipeline | task-pipeline | pipeline | merged (3ace338) | pass: T01-T24 regenerate byte-identical; 119 tests | New images need a foreground mask; source/license of the two pilot images unknown (Iris) |
| 1.3 Synthetic characters | synthetic | synth | merged (1292de3) | pass: 160 tasks, reference 160/160 in Chrome, 129 tests | Follow-ups: G3 penalizes legit occlusion changes (47 seeds rejected, biased against occluded parts); mutation validation not yet run on synth tasks; distance factor weak (0 in 74%); G5 scored on 76/160; poses all front-facing |
| 1.4 Protocol and stats | protocol | protocol | merged (4198842) | pass: 39 tests, no leaks | Valkyrie turn-cap flags TODO; Terminus 2 can't see images in single/feedback (Iris decides); re-export after grader-v2 |
| 1.5 Research and framing | research | research | merged | pass: 58 verified refs, locality memo, leaderboard table | Leaderboard numbers come from a third-party snapshot, so verify them in a browser; Gemini token-budget failures confound E8; WorldCoder-Bench also uses mutation-tested checks, so claim pixel-level side effects plus part integrity instead |
| 2.1 Rater UI + analysis | rater-ui | rater | merged | pass: 158 tests total, 20-clip dry run end to end | Valkyrie runs need HTML imported before clipping; Iris to review rater question wording; ~0.5 min/clip, ~$400-530 for 600 clips x 3 raters |
| 2.2 Alternate valid animations | alt-refs | altrefs | merged (39d5a20) | pass: 229 tests; false-fail 12/242 (5.0%) | Threshold fixes for G1/G2/G5/G3 and annotation fixes are in the grader v3 queue |

## Follow-up queue (main agent)
- Grader v3 (after grader-v2 merges), one agent:
  - an occlusion-aware G3, normalized for tiny parts
  - G1: grow the allowed region by 7.5% of the part's extent
  - G2: ignore faint pieces (contrast < 80)
  - G5: raise the max to 0.30, plus a displacement-based joint test for textured joints such as T08
  - annotation fixes: T10's head mask includes part of the sleeve; T07's earring masks leave out the chain, and its pivot sits outside the mask
  - reference bug: T14 tips the hat both ways
  - a rigid-motion residual check for still remnants that slide past while touching (T03, T05, T21 fingers; T07; T09-T11 heads)
  - give synthetic tasks G2b and re-admit them
  - officially re-grade runs/ and results/ with the new grader; fix build_writeup.py prose (it still says 7 broken copies)
  - re-run the mutation suite (including on synthetic tasks) and the alternate animations, and report false-fail and detection rates side by side
- Import index.html/frames from Valkyrie run outputs so agent runs can be clipped for the study
- Synth v2: more poses, characters overlapping each other, a better proximity factor

## Waiting on Iris
- Co-authors (author list locks Jan 14)
- Raster image source (generate new vs CC0)
- Budget approval ($5.5k–13.5k)
- Terminus 2 fairness: run single/feedback via direct APIs? (recommended)
- Turn-cap kwarg names for claude_code / codex agents
- Source and license of the two pilot images
