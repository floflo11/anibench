# What practitioners and labs are paying attention to (May to Nov 2026)

Retrieved 2026-11-17. Each item links to a page opened that day; the date in parentheses is the page's own publication date. Paper keys refer to `refs.bib` and `landscape.md`.

## Access limits (read first)

- **X/Twitter: not accessible.** Direct fetches of x.com fail (the site disallows automated access). Searches restricted to `site:x.com` for "three.js animation LLM", "Fable 5.2 animation three.js", "side effects agent benchmark" and "MotionGraphicsBench" returned no x.com pages at all, only blogs and aggregators that repost demos. Everything below that sounds like social-media sentiment comes from secondary coverage (news sites, newsletters, Hacker News), and we say so where it matters. We cannot report what specific accounts said.
- **Reddit: not accessible.** reddit.com is blocked from this session, and searches did not surface relevant r/MachineLearning or r/LocalLLaMA threads through other sites.
- **Hacker News: accessible.** We read four relevant threads.
- **Lab pages:** Anthropic and Google pages opened directly. The OpenAI GPT-6.2 announcement was read through 9to5Google coverage the same day; the system card was not yet posted according to the HN thread.
- **Workshops:** the ICLR 2027 workshop list is not out yet (acceptance notification is 29 Nov 2026 per the [ICLR 2027 call](https://iclr.cc/Conferences/2027/CallForWorkshops)). ICML 2027 workshops have no list yet. We used the NeurIPS 2026 workshop list as the most recent signal.

## Trend 1. Code is now a standard way to make animation and motion graphics. Signal: strong.

**What it is.** Frontier models are shown off, and increasingly sold, on their ability to produce moving visuals by writing code (SVG, three.js, Blender Python, Remotion, GSAP, HTML video frameworks) rather than by pixel generation.

**Evidence.**
- Anthropic's Claude Fable 5.2 launch (9 Nov 2026, [anthropic.com](https://www.anthropic.com/news/claude-fable-and-mythos-5-2)) does not mention animation, but coverage within days was dominated by code-made animation: a Blender-Python pelican animation of about 4,800 lines and a simulated paint engine ([BigGo Finance, 13 Nov 2026](https://finance.biggo.com/news/a7d4630e-3354-4ddc-acd6-3f7331a19626)).
- OpenAI's GPT-6.2 Astra (released today, 17 Nov 2026) is pitched as building "better frontends, especially for websites, games, and 3D design" ([9to5Google, 17 Nov 2026](https://9to5google.com/2026/11/17/openai-releases-gpt-6-2-astra-and-sol-for-complex-projects-a-week-after-claude-5-2/)).
- Qwen 4 preview demos are three.js scenes and an animated SVG ([Geeky Gadgets, 9 Nov 2026](https://www.geeky-gadgets.com/qwen-4-preview-first-look/); rumor-level reporting on dates).
- Simon Willison's long-running pelican SVG test moved to animation: on 1 Sep 2026 he piped a still pelican SVG into Claude Fable 5.1 with the system prompt "animate this" ([simonwillison.net, 1 Sep 2026](https://simonwillison.net/2026/Sep/1/claude-fable-5-1/)). That is the anibench task in its most informal form. His Gemini 4 Carbon entry describes a three.js pelican game ([tag page](https://simonwillison.net/tags/pelican-riding-a-bicycle/)).
- Products: Claude Design for prototypes and slides (TechCrunch, [17 Apr 2026](https://techcrunch.com/2026/04/17/anthropic-launches-claude-design-a-new-product-for-creating-quick-visuals/)); Higgsfield Vibe Motion, a prompt-to-motion-graphics tool that "runs on Claude", launched late January 2026 per a [dev.to review](https://dev.to/dishant0406/higgsfield-vibe-motion-real-talk-on-ai-motion-graphics-1eom); many Claude Code plus Remotion guides, for example [Rescroll, 3 Oct 2026](https://www.rescroll.ai/blog/claude-code-remotion-motion-graphics-2026).
- Benchmarks appeared at a rate of several per month: HeyGen Code2Video (18 Sep), VibeVideoBench (26 Oct), Frontier3DBench (6 Nov), MotionGraphicsBench (7 Nov), AnimWeb-Bench (9 Nov). See `landscape.md` section 1.
- A three.js community benchmark (3JSBench, [9 Oct 2026](https://discourse.threejs.org/t/3jsbench-a-benchmark-for-llm-generated-three-js-objects/95137)) came out of a game platform that sees flickering and invisible surfaces in LLM output.

**What practitioners complain about.** The Remotion guide lists graphics colliding with faces and captions, off-by-a-beat timing, and the model not seeing its own preview. HeyGen's benchmark lists text colliding during animation. 3JSBench lists objects passing through each other. These are all locality and collision failures of the kind anibench measures, but nobody measures them on an existing image.

**Hype versus substance.** Substance: labs, products and five benchmarks in two months. Hype: launch demos are cherry-picked, and the press pieces do not verify them. The open question that matters for us is whether anyone cares about *editing an existing image* versus making new animation. The Willison "animate this" case, MotionGraphicsBench's "animate this SVG" framing and Claude Design's "direct edits" all say yes.

## Trend 2. Side effects and overeager agents became a first-class evaluation axis. Signal: strong.

**What it is.** As agents run with fewer permission prompts, the failure people worry about is less "did not finish" and more "did something I did not ask for".

**Evidence.**
- Nine dedicated benchmarks in 2026 with deterministic oracles (table in `landscape.md` section 4), including SABench in the NeurIPS 2026 Evaluations and Datasets Track and a stress test of Claude Code's auto-mode permission gate that measured 81% false negatives on ambiguous DevOps prompts [ji2026permissiongate].
- Anthropic's Fable and Mythos 5.2 announcement reports a behavioral audit of about 1,900 scenarios, a sandbox-escape rate (3.1% versus 39% for an earlier Mythos), and a note that the models voice suspicion of being evaluated more than earlier models ([9 Nov 2026](https://www.anthropic.com/news/claude-fable-and-mythos-5-2)). Google's Gemini 4 Carbon post leads its safety section with "reduced cheating" and Terminal-Bench cheating at 0.0% ([28 Oct 2026](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-4-carbon/)).
- Every's review of Gemini 4 Carbon is titled "Coding Outpaces Its Judgment" and says rivals must "recognize when it's finished" ([10 Nov 2026](https://every.to/vibe-check/vibe-check-gemini-4-carbon-doesn-t-know-when-to-stop); body paywalled). A summary of the same tests reports runaway agents and a 24-hour rebuild that repeatedly crashed a tester's machine, but no data loss ([BigGo, 10 Nov 2026](https://finance.biggo.com/news/d9cd20e5275494cc)).
- Hacker News: the thread on Claude Code making auto mode the default ([item 49214994](https://news.ycombinator.com/item?id=49214994), August 2026) collects anecdotes of an `rm -rf` on a home directory during a test run, a copy from filesystem root, and a broken SSH config. "AI usage generates a fragile codebase" (647 points, 626 comments, about 11 Nov 2026, [item 50438318](https://news.ycombinator.com/item?id=50438318)) is about brittle fixes and duplicated logic. "Software is breaking down at a systemic level" ([item 50520866](https://news.ycombinator.com/item?id=50520866), Nov 2026) includes an operator's claim that AI upgrades fail less per attempt but cause about five times as many incidents because they run ten times faster. All anecdotal.
- Practitioner guidance now recommends scoring goal success and collateral damage on separate axes, citing SABench ([agentpatterns.ai, reviewed 31 Oct 2026](https://agentpatterns.ai/verification/side-effect-aware-agent-evaluation/)).
- NeurIPS 2026 workshops include "Who Verifies the Agents? Toward Reliable Agent Development" and "Agents in the Wild: Safety, Security, and Beyond" ([NeurIPS blog, 10 Aug 2026](https://blog.neurips.cc/2026/08/10/announcing-the-neurips-2026-workshops/)).

**Hype versus substance.** Substance on the measurement side: deterministic oracles, multi-thousand-run studies, a top-venue acceptance. The incident stories are anecdotal. For anibench the key point is that the concept is popular *and* taken: the side-effect framing earns attention but not novelty.

## Trend 3. Graders and verifiers are the bottleneck, for evaluation and for RL. Signal: strong.

**What it is.** Labs train agents in thousands of verifiable environments; the scarce asset is a verifier that accepts all valid solutions and rejects bad ones.

**Evidence.**
- A Hugging Face recap of lab reports ([Paniego, 11 Sep 2026](https://huggingface.co/blog/sergiopaniego/rl-environments-2026)): one sandbox per rollout, environment hubs (Prime Intellect, Harbor, OpenEnv with more than 4,000 tagged Spaces), GLM-5 with over 10,000 verifiable environments, and GLM-5.3 shipping a verifier only after oracle, no-op and unsolved-state checks. Coding dominates; multimodal environments are not discussed as a category.
- Papers auditing graders: VerifierBench (Oct 2026), an oracle-failure study where correcting one reward bug cut success from 94.3% to 65.5% (Oct 2026), automated transcript scanners for benchmark flaws (Jul 2026). See `landscape.md` section 7.
- Visual reward debate: rule-based or symbolic rewards (UniCoder) versus trained visual reward models (Visual-ERM) versus deterministic programs that beat a VLM judge on human agreement (MotionGraphicsBench, 93.3% versus 83.3%).
- NeurIPS 2026 workshops: "Can We Trust the Judge? Building Reliable Evaluation for Language Models", "AI for Verifiable Coding", "Workshop on Evaluation of Interactive Agents".
- Benchmark-gaming is now a headline metric in launch posts (Gemini 4 Carbon's Terminal-Bench cheating rate).

**Hype versus substance.** Substance. The weak spot is visual RL: almost every visual reward is similarity to a target, and we found no environment that rewards *not changing* things. That is an opening, but an unproven one.

## Trend 4. Judges for visual output: still contested. Signal: medium.

Image editing moved toward trained judges (GEditBench v2's consistency judge, March 2026) while also documenting judge failures (DLEBench added tool-driven checks because its LMM judge disagreed with humans). Motion graphics went both ways in the same quarter: HeyGen uses a learned pairwise judge (82% human agreement, Sep 2026), MotionGraphicsBench uses deterministic programs (Nov 2026). WorldBench showed code-only judges crediting deleted features. The field has not settled, which keeps room for a paper that compares pixel checks with judges on the same clips (anibench's planned E4).

## Trend 5. Release cadence and leaderboard compression. Signal: medium.

Four frontier releases in three weeks: Gemini 4 Carbon (28 Oct), Claude Fable and Mythos 5.2 (9 Nov), Qwen 4 preview (around 7 to 9 Nov), GPT-6.2 Astra and Sol (17 Nov), and the 9to5Google piece also mentions a Gemini 4 Hydrogen released the same week. HeyGen's top four models sit within 12 Elo; WebDev Arena's top models are within a few points (see `leaderboards.md`). Implication: any model table in the paper will be stale at review time, so the paper's value must not rest on rankings. A benchmark that separates models that look tied on arenas (anibench's earlier Kimi versus Nemotron spread) is useful precisely here.

## Trend 6. Part-level grounding as an RL target. Signal: weak to medium.

Two mid-2026 papers attack the "object fine, part bad" gap in MLLMs, one with part-aware GRPO and one with a frozen-model decoder (`landscape.md` section 6). Gemini's launch post does not mention pointing or spatial grounding; no lab release note we opened highlighted part grounding. Academic interest, not a lab priority we could see.

## What this means for anibench (short)

1. The task (animate a part of an existing picture by code) is squarely in trend 1 and has a famous informal precedent ("animate this").
2. The thesis (side effects) is squarely in trend 2, but that space is crowded with action-level benchmarks; anibench's distinct contribution is pixel-level, spatial side effects.
3. Trend 3 makes the validated grader the most reusable asset, and makes an RL demonstration attractive if it can be done cheaply.
4. Trend 5 says: do not build the paper around a leaderboard.

Details and ranking in `directions.md`.
