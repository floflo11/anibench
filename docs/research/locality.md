# Locality and side effects: how four fields measure them

Retrieved 2026-11-17. Keys refer to `refs.bib`. Claims about what a paper measures come from the paper page opened on that date; where the page did not say, this memo says so.

Every field that edits something asks two questions: did the requested change happen, and did anything else change? The fields differ in how they define "anything else", how they test it, and whether the two answers are kept apart.

## 1. Image editing

Three ways to score preservation appear in current benchmarks.

- **Pixel or feature metrics outside a mask.** PIE-Bench computes PSNR, LPIPS, MSE and SSIM only in the area outside a hand-annotated edit mask, plus a DINO self-similarity structure distance [ju2024directinversion]. I2EBench has one such dimension out of 16, Region Accuracy, which whites out the edited area and computes SSIM between input and output [ma2024i2ebench]. MagicBrush compares the output to a human-made target image with L1, L2, CLIP-I and DINO; only the mask-provided setting restricts L1 and L2 to the mask [zhang2023magicbrush].
- **A model judge.** ImgEdit-Bench has a "detail preservation" score for regions that should stay the same, but GPT-4o assigns it on a 1 to 5 scale, and it is capped by the instruction-adherence score [ye2025imgedit]. GEdit-Bench uses VIEScore-style semantic consistency, perceptual quality and overall scores from GPT-4.1 and Qwen2.5-VL, with no explicit preservation metric [liu2025step1xedit].
- **Humans.** EditBench relies on human ratings of mask-based inpainting [wang2023imageneditor]. AnyEdit is a large editing dataset and model; it is a source of edit types rather than a preservation metric [yu2025anyedit].

**What it misses.** The image is one static frame, so the mask is just the edit region. Nobody asks what region a change is allowed to sweep through over time. Feature metrics (LPIPS, DINO, CLIP) tolerate small shifts, so a slightly moved background can still score well. Judges couple preservation with adherence. No benchmark checks that the edited object itself stays whole (an edited hand that loses a finger can still match the prompt).

## 2. Model (knowledge) editing

This field states locality most clearly. An edit is scored on three axes: reliability (the edit took), generalization (paraphrases also changed) and locality (everything else stayed the same) [yao2023editingllms].

- ROME's CounterFact measures specificity with a Neighborhood Score: for nearby subjects that share the edited relation, the original answer must still beat the new one [meng2022rome]. The authors note that zsRE's specificity test, which samples unrelated facts at random, is not sensitive, because damage concentrates on close neighbors.
- MEND measures locality as disagreement (KL) between the pre-edit and post-edit model on randomly sampled unrelated inputs [mitchell2022mend]. MEMIT extends this to editing many facts at once [meng2023memit].
- Later work shows the cost of edits that look local in these tests: repeated edits cause gradual and then sudden forgetting [gupta2024forgetting], and editing harms general abilities on downstream tasks [gu2024editingharms].
- RippleEdits makes the reverse point. Some things must change along with the edit (related facts), so "nothing else changed" is the wrong test for them [cohen2024rippleedits].

**What it misses.** Locality is a sample of prompts, never the whole output space, and the sample determines the answer. Random far-away probes overstate locality; near neighbors are where side effects hide. Two lessons carry over to anibench. Test the adjacent parts (the forearm next to the waving hand, the other character's hand), not only far background. Separate "must move with it" (fingers ride with the hand, like ripple effects) from "must not move".

## 3. Code editing

- SWE-bench splits the check in two: FAIL_TO_PASS tests show that the requested fix works, and PASS_TO_PASS tests show that existing behavior did not break [jimenez2024swebench, chowdhury2024swebenchverified]. This is the closest structural match to our change checks (G4 to G6) versus preservation checks (G1 to G3). SWE-bench Multimodal extends the task to visual front-end repositories but keeps test-based grading [yang2025swebenchmm].
- Regression checks are only as strong as the tests. A differential testing study found that 29.6% of plausible SWE-bench patches behave differently from the reference fix, and test weaknesses inflate reported resolve rates by 6.2 points [wang2026solvedissues]. HumanEval+ shows that thin test suites inflate pass@k [liu2023evalplus]. Human review flagged 68.3% of 1,699 reviewed SWE-bench samples for removal, often for tests that could reject valid fixes [chowdhury2024swebenchverified].
- CanItEdit adds ExcessCode, the share of changed lines that the tests do not cover, as a direct measure of unrequested change [cassano2024canitedit].
- Mutation testing asks whether a test suite catches seeded faults, and Just et al. study whether such mutants stand in for real faults [just2014mutants].

**What it misses.** A side effect is visible only if some test exercises it. Diff size is a proxy, not a measure, of harm. The standard tool for checking the checker (mutation testing) is rarely applied to benchmark graders.

## 4. Visual code generation and animation

- Most visual code benchmarks score similarity to a reference or ask a judge: Design2Code [si2025design2code], Plot2Code [wu2024plot2code], ChartMimic [yang2024chartmimic], StarVector [rodriguez2025starvector], VGBench [zou2024vgbench], SVGenius [chen2025svgenius], SGP-GenBench [chen2025sgpgenbench], and Vision2Code with a VLM rubric [periasami2026vision2code]. ArtifactsBench renders interactive artifacts to screenshots over time and has an MLLM judge score them against per-task checklists [zhang2025artifactsbench]. WebGen-Bench uses a web-navigation agent to test features [lu2025webgenbench]. P3D-Bench mixes geometry and topology metrics with an MLLM judge [yang2026p3dbench]; 3DCodeBench uses render and shape similarity plus human Elo [gao2026threedcodebench]. Animation2Code scores appearance and timing similarity to a recorded web animation [ji2026animation2code].
- WorldCoder-Bench is the most rigorous: its StateProbe runs three.js worlds in a browser and checks hidden, mutation-hardened behavioral contracts on runtime state [lu2026worldcoderbench]. It checks what the program does, not which pixels changed.
- In animation, preservation is usually built into the method or measured against the whole still image. VAnim edits only selected SVG nodes, so untouched elements are preserved by construction, and it reports SSIM for "identity preservation" without saying whether it is masked [liang2026vanim]. LiveSVG computes LPIPS and SSIM "against the static reference rendering", also with no stated mask [levy2026livesvg]. AniClipart reports appearance preservation [wu2024aniclipart]. Graphic-Design-Bench scores Lottie output with frame SSIM and MSE against a reference, and uses unmasked-pixel preservation only for some non-animation tasks [deganutti2026graphicdesignbench]. A companion paper on design video notes that generators add "spurious motion to supposedly-static components", but defines no masked stability metric [deganutti2026designvideo]. AnimationBench scores character identity with a VLM judge [wu2026animationbench]. OmniLottie and LiveSketch generate animation from text or sketches [yang2026omnilottie, gal2023livesketch]; LogoMotion and Keyframer are LLM authoring tools evaluated mainly with user studies [liu2024logomotion, tseng2024keyframer].
- Articulation work has VLMs or LLMs write code for joints and scores the final object, for example articulation success on PartNet-Mobility [le2025articulateanything]; Real2Code predicts joints as code from part bounding boxes [mandi2024real2code]. Classic drawing animation (Animated Drawings) runs a fixed cut-out, rig and retarget pipeline with no model writing code [smith2023animateddrawings].

**What it misses.** Whole-frame similarity to the still image mixes the two questions into one number. Intended motion lowers the score, so a frozen output is rewarded and a correct wave is penalized. A judge can say a hand waves, but cannot reliably say whether 40 background pixels moved. No benchmark we found checks that the moving part stays in one piece, or that it rotates about the joint.

## 5. Judges, contamination and verifiable rewards

LLM judges show position, verbosity and self-enhancement bias [zheng2023judging], and later work documents and quantifies these and other judge biases [wang2024notfair, ye2025justice]. MLLM judges agree with humans on pairwise choices but drift on scores and rankings [chen2024mllmjudge]. A pixel test of "did anything outside region R change" needs no judge. Fresh tasks limit contamination [jain2025livecodebench, zhang2024gsm1k]; a procedural character generator gives the same benefit. Benchmark audits find graders that accept wrong outputs, for example one that counted empty responses as successes [zhu2025abc]; BetterBench proposes a broader quality assessment for benchmarks [reuel2024betterbench]. A deterministic grader also serves as a verifiable reward for RL [lambert2024tulu3]; SGP-GenBench already uses render-based rewards for SVG [chen2025sgpgenbench].

## Summary table

| Field | Change measured by | Preservation measured by | Main blind spot |
|---|---|---|---|
| Image editing | CLIP/judge adherence | Masked PSNR/SSIM/LPIPS (PIE-Bench, I2EBench), judge (ImgEdit) | Single frame; no part integrity; judge coupling |
| Model editing | Efficacy, paraphrase | Neighborhood / unrelated-prompt agreement | Sampled probes; far probes overstate locality |
| Code editing | FAIL_TO_PASS tests | PASS_TO_PASS tests, ExcessCode | Only tested behavior is visible |
| Visual code / animation | Similarity or judge | Whole-frame SSIM/LPIPS, by-construction, judge | Change and preservation entangled; no pivot or integrity check |

## Positioning statement (draft for the authors)

Each field that edits things asks whether the requested change happened and whether anything else changed, but in visual code generation the second question is either left to a model judge or folded into a whole-image similarity score that also penalizes the intended motion. anibench separates the two: motion, pivot and loop checks confirm the change, while isolation, integrity and area checks confirm that no pixel outside the region the part can sweep changes and that the part itself stays whole, all as deterministic image math over every frame. Like PASS_TO_PASS tests in code and neighborhood tests in model editing, our preservation checks probe the nearest places where side effects appear, and like mutation testing we validate each check against deliberately broken references before trusting it. The result is a judge-free, contamination-resistant measure of whether a model can make a local change without side effects, which can also serve as a verifiable reward.

## Closest prior work and how we differ

- VAnim [liang2026vanim] and LiveSVG [levy2026livesvg]: animate parts of an existing vector image and aim to preserve the rest. Their input is SVG structure, not raster pixels, preservation is guaranteed by the representation or measured with an unmasked SSIM/LPIPS, and neither checks pivots or part integrity.
- WorldCoder-Bench [lu2026worldcoderbench]: deterministic, mutation-hardened checks for three.js. It verifies program state and behavior, not pixel-level side effects.
- PIE-Bench [ju2024directinversion] and I2EBench Region Accuracy [ma2024i2ebench]: masked preservation metrics, but for single images and with no notion of a swept region over time.
