# anibench

**AI can write a whole 3D animation, but ask it to wave a cartoon hand and the thumb falls off.**

We introduce anibench, a benchmark for localized character animation. Each task gives a model a still character image and asks it to animate one named part (a hand wave, a hat tip, earrings swinging) as a looping three.js scene. We have tested 21 tasks across six characters. Each submission is rendered to frames and scored with 6 deterministic pixel checks, including:

* Isolation: nothing outside the target part changes.
* Integrity: the part doesn’t tear or leave holes.
* Area preservation: the part keeps its size.
* Motion: the part actually moves.
* Pivot: it rotates around the right joint.
* Loop and fidelity: the last frame matches the first, and frame 0 matches the source image.

To check that the grader is sound, we pair every task with a reference solution and seven deliberately broken variants. The reference passes all 21 tasks. Where a check is designed to apply, the grader catches 100% of whole-body, hole, frozen and wrong-part failures. It catches 20 of 21 non-looping animations and 12 of 13 misplaced pivots. Even so, frontier models often fail. Claude Sonnet 5.5, running as an agent in Claude Code, passes 12 of 21 tasks (57%). Other models, each given one attempt through OpenRouter, range from 60% (Kimi K3.1 Pro) to 0% (Nemotron). These errors are obvious to any human viewer, yet models commonly make them, which makes localized animation a simple, verifiable test of spatial understanding.

Built for Vals Hacks Track 1.

- Write-up: [WRITEUP.md](WRITEUP.md)
- Results: [results/README.md](results/README.md), GIFs in `results/library/`, demo video `results/demo.mp4`
- Grader validation: [validation/admission.md](validation/admission.md)
- Harbor tasks for Valkyrie: [`harbor/`](harbor/)
- Morning checklist: [MORNING.md](MORNING.md)

Headline: Nemotron 3.5 Super VL passed 0/21 scored runs; Qwen 3.8 27B solved the T01 wave in a smoke test.
