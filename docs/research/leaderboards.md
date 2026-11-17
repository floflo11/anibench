# Public leaderboard scores for E8 (rank correlation)

Retrieved 2026-11-17. Purpose: public scores for the models we have run on anibench, on the existing benchmarks closest to ours, so E8 can compute rank correlations.

## Sources and how reliable they are

The official leaderboard pages could not be read directly from this session:

- `lmarena.ai/leaderboard/webdev` returned a stale page ("Last Updated Jan 9, 2026", 34 models) with organizations but no model names.
- `arena.ai/.../leaderboard/code/webdev` failed with a client error.
- `www.designarena.ai/leaderboard/3d-design` was blocked by the session's URL policy.
- `artifactsbenchmark.github.io/leaderboard.html` renders with JavaScript only, so it returned no table.

All numbers below therefore come from **BenchmarkList** (benchmarklist.com), a third-party site that publishes timestamped static snapshots of these leaderboards and names the upstream source. Before the paper uses them, someone should check them against the official pages in a browser on the same day and record any differences. Arena scores change daily.

## Benchmarks chosen

1. **WebDev Arena** (Arena, formerly LMArena; code/webdev board). Pairwise human votes on generated web apps [chiang2024chatbotarena]. This is the closest large public signal for "model writes a page that renders well". Snapshot of `arena.ai/leaderboard/code`, scraped 2026-11-16 09:17 UTC, 157 models.
2. **Design Arena, 3D Design** (designarena.ai). Pairwise human votes on 3D scenes, which are mostly three.js. This is closest to our output format. Snapshot of `https://www.designarena.ai/leaderboard/3d-design`, scraped 2026-11-15 09:17 UTC, 181 models.
3. **Design Arena, SVG Design**. Pairwise votes on generated SVG, the closest vector graphics signal. Snapshot scraped 2026-11-15, per the BenchmarkList page.
4. (Extra) **Design Arena, Web Design Overall**. Snapshot scraped 2026-11-16 09:17 UTC, 197 rows.

Not usable:

- **ArtifactsBench** has no overlap with our models. Its project page lists results up to 2025-10-27 (for example MiniMax-M2 66.8, DeepSeek-V3.2 55.8), and the llm-stats.com aggregator lists 4 self-reported scores, none for our models.
- **Arena Vision** (snapshot 2026-11-10, 25 models) contains none of our seven models; Qwen3.8-Max is the only Qwen 3.8 entry.
- WorldCoder-Bench, P3D-Bench and 3DCodeBench report results in their papers (May and June 2026), which predate most of our models. We did not find maintained leaderboards for them.

## Table

"Match" is exact when the leaderboard name is the same model we ran, and near when only the family matches (different size, mode or release). Use only exact rows in the main E8 analysis.

| Benchmark | Our model | Leaderboard name | Score (Elo) | Rank | Match | Snapshot date | Source URL |
|---|---|---|---|---|---|---|---|
| WebDev Arena | Claude Sonnet 5.5 | Claude Sonnet 5.5 (xHigh) | 1772.23 | 3 / 157 | exact (mode differs) | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Claude Sonnet 5.5 | Claude Sonnet 5.5 (High) | 1715.82 | 10 / 157 | exact (mode differs) | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Gemini 4 Carbon | Gemini 4 Carbon (High) | 1768.34 | 4 / 157 | exact | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Kimi K3.1 Pro | Kimi K3.1 Pro (Max) | 1686.23 | 13 / 157 | exact | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Grok 4.7 | Grok 4.7 (xHigh) | 1640.09 | 25 / 157 | exact | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Qwen 3.8 27B | Qwen3.8-27B | 1589.91 | 41 / 157 | exact | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | DeepSeek V4 Flash Vision | DeepSeek-V4-Flash (High) | 1581.61 | 45 / 157 | near (no Vision variant listed) | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| WebDev Arena | Nemotron 3.5 Super VL | NVIDIA-Nemotron-3.5-Super-VL-120B-A12B (NVFP4) | 1400.96 | 104 / 157 | exact (quantized) | 2026-11-16 | https://benchmarklist.com/arenas/arena_ai_code/ |
| Design Arena 3D | Kimi K3.1 Pro | Kimi K3.1 Pro | 1441 | 6 / 181 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | Gemini 4 Carbon | Gemini 4 Carbon | 1429 | 8 / 181 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | Claude Sonnet 5.5 | Claude Sonnet 5.5 | 1401 | 11 / 181 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | Grok 4.7 | Grok 4.7 | 1253 | 41 / 181 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | Nemotron 3.5 Super VL | Nemotron 3.5 Super VL | 1119 | 100 / 181 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | Qwen 3.8 27B | Qwen3.8 Max | 1317 | 25 / 181 | near (different size) | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena 3D | DeepSeek V4 Flash Vision | DeepSeek-V4-Flash | 1168 | 82 / 181 | near | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_3d/ |
| Design Arena SVG | Kimi K3.1 Pro | Kimi K3.1 Pro | 1329 | 7 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_svg/ |
| Design Arena SVG | Claude Sonnet 5.5 | Claude Sonnet 5.5 | 1300 | 12 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_svg/ |
| Design Arena SVG | Grok 4.7 | Grok 4.7 | 1270 | 27 | exact | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_svg/ |
| Design Arena SVG | DeepSeek V4 Flash Vision | DeepSeek-V4-Flash | 1145 | 75 | near | 2026-11-15 | https://benchmarklist.com/arenas/design_arena_svg/ |
| Design Arena Web (overall) | Kimi K3.1 Pro | Kimi K3.1 Pro | 1350 | 11 / 197 | exact | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | Gemini 4 Carbon | Gemini 4 Carbon | 1349 | 12 / 197 | exact | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | Claude Sonnet 5.5 | Claude Sonnet 5.5 | 1345 | 14 / 197 | exact | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | Grok 4.7 | Grok 4.7 | 1266 | 45 / 197 | exact | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | Nemotron 3.5 Super VL | Nemotron 3.5 Super VL | 1140 | 129 / 197 | exact | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | Qwen 3.8 27B | Qwen3.8 Max | 1286 | 33 / 197 | near | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |
| Design Arena Web (overall) | DeepSeek V4 Flash Vision | DeepSeek-V4-Flash | 1195 | 88 / 197 | near | 2026-11-16 | https://benchmarklist.com/arenas/design_arena/ |

Missing from the SVG snapshot: Qwen 3.8 (any size), Gemini 4 Carbon (only Gemini 4 Argon, rank 6, 1340) and Nemotron 3.5 Super VL (only Nemotron 3 Ultra, rank 111, 1060).

## Overlap with our seven models

| Benchmark | Exact | Near | Missing |
|---|---|---|---|
| WebDev Arena | 6 | 1 (DeepSeek) | 0 |
| Design Arena 3D | 5 | 2 (Qwen, DeepSeek) | 0 |
| Design Arena Web overall | 5 | 2 (Qwen, DeepSeek) | 0 |
| Design Arena SVG | 3 | 1 (DeepSeek) | 3 |

## Notes for E8

- With 5 to 7 models, a Spearman correlation has a very wide confidence interval. Report it with a bootstrap or exact permutation p-value, and treat it as descriptive.
- Gemini 4 Carbon is a confound. It ranks 4th on WebDev Arena and 8th on Design Arena 3D, but scored 0/8 on anibench because it spent its whole 32k-token budget reasoning and never wrote a file. Any correlation will be dominated by this unless E8 uses a run setting with a larger budget, or reports results with and without budget failures.
- Our runs mix settings: Claude Sonnet 5.5 ran as an agent (Claude Code, Valkyrie), the others single-shot through OpenRouter. Correlate within one setting.
- Arena entries are often listed per reasoning mode (High, xHigh, Max). Record the mode used in our runs and pick the matching row.
- Our DeepSeek run used "V4 Flash Vision"; no leaderboard lists a Vision variant. Our Qwen run used the 27B model; only WebDev Arena lists Qwen3.8-27B.
