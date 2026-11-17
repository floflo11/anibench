# Where to spend the next 9 weeks: decision memo

Prepared 2026-11-17. Deadline: ICML 2027 abstract Jan 14, full paper Jan 22 ([ICML 2027 dates](https://icml.cc/Conferences/2027/Dates)), "Datasets, Evaluations and Benchmarks" type, whose stated criteria are enabling new questions, revealing hidden phenomena and making comparisons more reliable, not producing state-of-the-art numbers ([contribution types](https://icml.cc/Conferences/2027/ContributionTypes)). Evidence comes from `landscape.md` and `trends.md`; paper keys refer to `refs.bib`.

## The candid read

1. **The intersection anibench occupies is still empty, but both of its parent spaces filled up this year.** Code-generated animation got five benchmarks between September and November 2026, one of which (MotionGraphicsBench, Figma and Stanford, 7 Nov) also animates an existing image and also uses deterministic verification. Agent side effects got at least nine deterministic-oracle benchmarks in 2026, one at NeurIPS 2026. Localized editing with a separate preservation score now exists for SVG (Vector-Bench), web pages (MT-Web2Code) and code (over-editing).
2. **So "judge-free" and "separates change from side effects" are no longer novel claims by themselves.** What is still unique: raster input, preservation checked on every pixel of every frame against a swept region, part integrity and connectivity, pivots, and a grader validated in both directions. That is a narrower claim than the current README makes.
3. **The biggest reviewer risk is "niche"**: cartoon hands in three.js, next to benchmarks about deleted files and real Lottie designs. The paper needs at least one result that people outside character animation care about.
4. **The biggest asset is the validated grader plus the seeded corruptions.** They give free ground truth for experiments other papers cannot run cheaply (for example, how small a side effect a VLM judge can see).

## Candidate directions

Scores are judgments from the evidence above. "Effort" is in person-weeks of the 9 available, assuming the current agent workflow.

### (a) Keep the focused localized-animation benchmark and polish it (the current plan)

- **Novelty:** medium. Unique intersection (section 2 above), but MotionGraphicsBench will be the first comparison every reviewer makes, and it reports 32 models and a human-agreement number that anibench does not yet have.
- **Timing fit:** good. WS6 to WS9 already target Jan 10.
- **Effort:** as planned (most of the 9 weeks).
- **Risk:** medium. Reception risk ("niche", "why not just SVG"), not execution risk.
- **Likely reception:** fine if the paper leads with a finding, weak if it leads with the benchmark. A DEB reviewer will ask what scientific claim the scores support.
- **Industry relevance:** medium and rising. Design-tool companies (Figma wrote MotionGraphicsBench; Anthropic ships Claude Design; HeyGen built Code2Video) care about editing existing assets without breaking them.

### (b) Generalize to a family of side-effect-free edits across modalities

- **Novelty:** low per modality, medium as a unified framework. Each modality now has a 2026 benchmark: SVG (Vector-Bench, 40 tasks), web (MT-Web2Code, 102 tasks), code (over-editing, 400 tasks), documents (DocOps preservation predicates), app state (Agent-Diff closed-world diff). A cross-modal framework with one change-versus-preservation protocol does not exist, but it would be judged against all of them at once.
- **Timing fit:** poor. Building three good new modalities with validated graders in 9 weeks, while also finishing the animation core, would produce several thin benchmarks instead of one strong one.
- **Effort:** high (6+ weeks for even two new modalities done properly).
- **Risk:** high. Breadth invites "each part is weaker than the specialist benchmark".
- **Likely reception:** mixed; ambitious but easy to attack.
- **Industry relevance:** high in principle.
- **Verdict:** right idea for a follow-up paper (NeurIPS 2027 Evaluations and Datasets, or a journal), wrong for Jan 22. Keep only D1's static local edit family as a control, because it isolates "cannot localize" from "cannot animate".

### (c) Position as an RL environment with verifiable rewards and show training gains

- **Novelty:** medium-high. We found no visual RL work that rewards preservation; all visual rewards are similarity to a target (RLRF, UniCoder, Visual-ERM), and SimuScene's code-to-animation RL uses a VLM judge. The over-editing paper found RL beats SFT for edit fidelity in code, which is suggestive.
- **Timing fit:** poor to fair. Needs a VLM policy that writes three.js, Chromium rendering in the RL loop (seconds per rollout), and enough base-model success to get signal. Pilot data shows weak open models near 0 of 21, so rewards would be sparse unless partial credit is used, and partial credit is easier to hack.
- **Effort:** 3 to 5 weeks plus compute, with a real chance of a null result.
- **Risk:** high. A small or negative result in a benchmark paper costs space and invites "why include this".
- **Likely reception:** strong if gains transfer to held-out characters and to another benchmark (for example MotionGraphicsBench or Vector-Bench); otherwise neutral.
- **Industry relevance:** high (trend 3: labs want verifiers more than benchmarks).
- **Verdict:** keep the plan's Jan 2 go/no-go, but shrink the goal: show the reward is hard to hack (WS10 red-team results) and that best-of-n with the grader as a filter improves pass rates. That gives the "usable as a reward" claim cheap support without training. Do full RL after the deadline.

### (d) Compare image-to-video models with the same checks

- **Novelty:** medium-high. Regional image-animation papers measure static-region preservation with user studies, whole-frame consistency or tracker distances (Follow-Your-Click, Through-The-Mask, Time-to-Move). SNF-Bench (Aug 2026) shows whole-frame motion metrics reward drift. No one has applied pixel-exact isolation, integrity and pivot checks to video models.
- **Timing fit:** fair. Needs 3 or 4 models (open-weight I2V plus one or two commercial ones with region or motion-brush control) on 30 to 60 tasks.
- **Effort:** about 2 weeks, plus API cost.
- **Risk:** medium. Video models re-encode every pixel through a VAE, so G1 Isolation and G6 Fidelity will fail almost everything at current thresholds. The result could read as "video models fail a test built for programs", which is unfair unless the checks get a calibrated noise floor (measure each model's reconstruction error on a "do nothing" prompt and set thresholds above it). Also a licensing and terms check for commercial outputs.
- **Likely reception:** good for breadth and for the CV audience; it turns "code versus pixels" into a figure people remember.
- **Industry relevance:** high (video generation is a large product area).
- **Verdict:** worth doing as a secondary experiment if a noise-floor protocol is fixed first; drop if it slips past Dec 24.

### (e) Frame as agent safety or collateral damage

- **Novelty:** low. The space is crowded (Agent-Diff, OverEager-Bench, SNARE, UnderSpecBench, AmPermBench, OverAct, SABench, SideTaskBench, ParanoiaEval, all 2026). Those measure discrete, consequential actions; anibench's side effects are pixels in a cartoon.
- **Timing fit:** good (it is a writing choice).
- **Effort:** low.
- **Risk:** high on reception. A safety reviewer will find the stakes low and ask why there is no authorization model; anibench's failures come from poor localization, not from overreach.
- **Industry relevance:** high for the topic, low for this evidence.
- **Verdict:** use the side-effect vocabulary and cite SABench and Agent-Diff as the action-level counterpart, but do not make safety the frame. Say clearly that anibench measures the *capability* to localize, and that the action-level benchmarks measure *policy*.

### (f) Better option: make the paper about what judges and arenas cannot see

This combines pieces already in the plan (E4 judge comparison, E8 rank correlation, the procedural difficulty factors) into the headline, instead of treating them as appendix experiments.

- **Core experiment 1, judge blindness (cheap, new).** The seeded corruptions are labeled failures with a known size (a 20 px fragment, a 2 px seam, a hole, a moved background). Render them next to valid animations and ask frontier VLM judges, including the rubric style used by ArtifactsBench and VibeVideoBench, whether the animation is correct. Plot detection rate against side-effect size. Prediction from WorldBench and DLEBench: judges miss small side effects that pixel checks catch at 100%. This directly answers trend 4 with free ground truth; no other benchmark has labeled corruptions at controlled sizes. Effort: about 1 week, small API cost.
- **Core experiment 2, arenas do not measure locality.** E8 already collects WebDev Arena and Design Arena ratings. If anibench rank correlation with them is low (the pilot hints at it: models within a few Elo of each other differ widely on anibench), that is a "hidden phenomenon" in the DEB sense. Effort: analysis only once WS8 runs.
- **Core experiment 3, why models fail.** Use the procedural split's recorded factors (part area, occlusion, chain length, distance to the nearest part) plus a cheap probe that asks the same model to point at the pivot and outline the part (PointArena-style). Then attribute failures to grounding versus structure versus execution. This turns "models fail" into an explanation, which the construct-validity review [bean2025constructvalidity] and ICML's DEB criteria ask for. Effort: 1 to 2 weeks, mostly analysis.
- **Novelty:** high for experiment 1, medium for 2 and 3.
- **Timing fit:** good; all reuse planned runs.
- **Risk:** low to medium. Experiment 1 could show judges do fine, which is still a publishable negative for our motivation; we should run a 50-clip pilot by Dec 5 to know early.
- **Likely reception:** good. It gives the paper a claim beyond "here is a new benchmark", and it differentiates from MotionGraphicsBench, which reports judge agreement on balanced data but not detection as a function of side-effect size.
- **Industry relevance:** high. Everyone using VLM judges or arenas to pick models for design work wants to know what they miss.

## Ranked recommendation

1. **(a) plus (f): keep the focused benchmark and lead with what judges and arenas miss.** Highest expected value per week. It uses the one asset nobody else has (validated grader plus sized corruptions), answers the obvious MotionGraphicsBench comparison with a result rather than a feature list, and stays inside the existing schedule. Concretely: pilot the judge-blindness experiment by Dec 5; make the procedural difficulty analysis and the pointing probe part of WS8; promote E4 and E8 to main-text figures.
2. **(d) image-to-video comparison, as a secondary experiment, gated.** Fix a noise-floor protocol by Dec 10; run 3 to 4 models on about 40 tasks by Dec 24; drop if late. It broadens the audience at modest cost.
3. **(c) RL, reduced to a reward-validity claim.** Red-team results plus grader-filtered best-of-n by Jan 8. Full RL training after the deadline.
4. **(b) cross-modal family, deferred.** Keep the static-edit control in this paper; plan the family for the next venue, where it can build on Vector-Bench and MT-Web2Code rather than compete with them.
5. **(e) safety framing, as vocabulary only.** Cite the action-level benchmarks; do not claim safety stakes the evidence does not support.

## Must-do items regardless of direction

- Cite and directly compare with MotionGraphicsBench [ma2026motiongraphicsbench] in the introduction, with a table row each for MoVer, Vector-Bench, MT-Web2Code, SABench and SNF-Bench.
- Report a human-agreement number for the grader (E4), because MotionGraphicsBench reports 93.3%.
- Remove claims that 2026 work now contradicts (listed at the end of `landscape.md`).
- Do not make model rankings the headline; four frontier releases landed in the three weeks before this memo, so any table will be stale by review time.

## What would change this recommendation

- If the judge-blindness pilot shows frontier judges catch small side effects reliably, drop experiment 1 from the headline and move (d) up.
- If another raster-input animation benchmark appears before January, the differentiation would rest on grader validation and the failure analysis; (f) still holds, (a) alone would not.
- If a partner offers RL compute and a base model that already passes about 20% of tasks, (c) becomes viable as a main result.
