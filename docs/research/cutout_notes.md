# The cut-out step: working notes

Retrieved 2026-11-17 (all pages below opened on that date unless noted). Keys refer to `refs.bib`; keys marked (existing) were already in the bibliography before this pass. Dates are arXiv submission dates unless a venue is given. Numbers are copied from the opened page; where a page did not state something, these notes say so. "My arithmetic" marks differences computed here, not stated by the source.

Working hypothesis under test: the core capability anibench measures is the cut-out step (find the part's pixels and its joint, cut cleanly including thin structures, fill the revealed area).

## Q1. Text-referred part segmentation by general multimodal models

**Object vs. part gap, quantified.**

- OP-HRG [mehrab2026ophrg] (existing; https://arxiv.org/html/2607.15374, Jul 2026), Table 1, gIoU. SAM 3 with a text prompt: 85.32 on Pascal objects, 33.05 on PascalPart, 53.89 on PartImageNet, 71.06 on InstructPart. Zero-shot Qwen3-VL-4B + SAM 2 with the object-then-part prompt: 36.91 objects, 12.83 PascalPart. Their RL-trained 4B model: 87.50 objects, 38.59 PascalPart. Object-minus-PascalPart gap (my arithmetic, across different benchmarks): about 52 points for SAM 3 and 49 points for the best model. The paper reports no GPT or Gemini numbers on part benchmarks.
- GroundingSuite / GSEval [hu2025groundingsuite] (https://openaccess.thecvf.com/content/ICCV2025/html/Hu_GroundingSuite_Measuring_Complex_Multi-Granular_Pixel_Grounding_ICCV_2025_paper.html, ICCV 2025; table from https://arxiv.org/html/2503.10596v3). 3,800 images, four subsets (stuff, part, multi-object, single-object). Table 2, zero-shot gIoU, the part subset is the lowest for every segmentation model: LISA-7B 21.2 part vs 42.8 single vs 85.2 stuff; GLaMM 16.5 vs 42.1; EVF-SAM 23.1 vs 54.5; PSALM 10.0 vs 36.9. A box-accuracy table (Table 3) covers Gemini-1.5-Pro, GPT-4o, Qwen2.5-VL, InternVL; the fetch tool had to infer that table's column headers, so I do not quote it in the memo.
- InstructPart [wan2025instructpart] (https://arxiv.org/html/2505.18291v1, 23 May 2025; no venue on page). 2,400 images, 44 part classes. Object-part queries, gIoU: LISA 34.46, MiniGPT-v2 35.65, Grounded-SAM 34.33, VLPart 22.06, Shikra 4.50. GPT-4V on a 226-sample subset: 14.14 gIoU with grid prompting, 25.41 with Set-of-Mark. Fine-tuning on 1,800 samples raises LISA from 32.11 to 71.26 gIoU on task-reasoning queries. The paper notes models "either obtain the entire object area or miss" the part. No size or thinness breakdown.
- PARTONOMY [blume2025partonomy] (existing; https://arxiv.org/abs/2505.20759v3). 862 part labels; LISA-13B 5.9% gIoU. A NeurIPS 2025 proceedings page exists (https://proceedings.nips.cc/paper_files/paper/2025/hash/3175dfe6e0eff29fb6e152fb763d89d1-Abstract-Conference.html, seen in search results, not opened); the existing bib entry is left as a preprint.
- MRES / RefCOCOm [wang2024mres] (https://mlanthology.org/cvpr/2024/wang2024cvpr-unveiling, CVPR 2024, pp. 12998-13008). Introduces part-level referring segmentation (RefCOCOm benchmark, MRES-32M data). Abstract gives no numbers. Follow-up UniRES++ (arXiv 2504.01954, Apr 2025) not added.

**Models that emit geometry as text (no mask decoder).**

- PolyFormer [liu2023polyformer] (CVF open access, CVPR 2023, pp. 18653-18663): polygon vertices as an autoregressive sequence; argues for regressing floating-point coordinates rather than quantizing them.
- VistaLLM (arXiv 2312.12423): adaptive, gradient-aware sampling of mask contours into sequences, contrasted with uniform sampling. No venue on the page and no sampling ablation numbers in the abstract. Not added to refs.bib.
- Text4Seg [lan2025text4seg] (https://proceedings.iclr.cc/paper_files/paper/2025/hash/04d8c25cbf0d5e1b70d64e672ac92637-Abstract-Conference.html, ICLR 2025): masks as per-patch text labels ("semantic descriptors"); a 16x16 grid is "competitive"; row-wise run-length encoding shortens descriptors by 74%. Relevance: a 16x16 grid on a 512 px image is a 32 px cell, far coarser than a thumb.
- LLMSeg [hamdi2026llmseg] (https://arxiv.org/abs/2610.29409 and html v1, 21 Oct 2026, "preprint"). Training-free: a Gemini-3.7-Flash backend detects a box, then traces closed B-spline or polygon loops whose control points are emitted as JSON in absolute pixel coordinates, then iteratively refines around residual errors with focus boxes. ReasonSeg val 71.5 cIoU. Ablation (Table 4): without refinement 67.2 vs 74.7 cIoU on ReasonSeg val, 64.6 vs 79.8 on RefCOCO val (2.0 vs 14.6 model calls). Forcing polygons (degree 1) instead of splines: 73.1 vs 74.7 on ReasonSeg, within run-to-run SD. Against SAM 3 on matched subsets: box AP on LVIS close (64.2 vs 69.1), mask AP far behind (47.2 vs 62.2; COCO 50.5 vs 59.2). The author lists "imprecise pixel-level boundaries" as a limitation. No Boundary IoU or thin-structure analysis. *Reading:* a frontier model finds the instance about as well as a specialist but traces its boundary worse, and needs many zoomed calls to get close.
- Ramachandran et al. [ramachandran2025gpt4ovision] (https://arxiv.org/html/2507.01955v3; v1 2 Jul 2025, v3 1 May 2026; no venue on page). Prompt chains make API-only models do standard vision tasks. COCO semantic segmentation via SLIC superpixels classified by the model: GPT-4o 44.89 mIoU, Gemini 2.0 Flash 43.04, Claude 3.5 Sonnet 32.05, versus specialist OneFormer 65.52; the oracle through the same chain reaches 83.41 (so the superpixel chain caps boundaries). Detection AP: GPT-4o 31.87 vs Co-DETR 80.23. Models are better at semantic than geometric tasks; o3 improves geometric tasks. Direct marking on the full image without crops scores 25.79 mIoU vs 40.97 without the crop level (ablation).
- PixelArena (arXiv 2512.16303, Dec 2025): Gemini 3 Pro Image produces high-fidelity semantic masks zero-shot through image generation. Abstract gives no numbers. Not added.
- Gemini 2.5 conversational segmentation (Google Developers Blog, 21 Jul 2025, https://developers.googleblog.com/conversational-image-segmentation-gemini-2-5/): API returns JSON with box_2d, mask and label; the post gives no accuracy figures. Company blog, not in refs.bib.

**Thin structures and boundaries.**

- Deep Interactive Thin Object Selection [liew2021thinobject] (https://mlanthology.org/wacv/2021/liew2021wacv-deep/, WACV 2021, pp. 305-314). Interactive segmenters "often fail" on thin, elongated parts (insect legs, spokes); causes are lack of data and severe pixel imbalance between thin and non-thin regions. ThinObject-5K dataset; IoU_thin metric; +30% IoU_thin at four clicks.
- HQ-SAM [ke2023hqsam] (https://neurips.cc/virtual/2023/poster/71673, NeurIPS 2023): SAM's masks degrade on objects with intricate structures; fix trained on 44K fine-grained masks.
- Boundary IoU [cheng2021boundaryiou] (https://mlanthology.org/cvpr/2021/cheng2021cvpr-boundary, CVPR 2021, pp. 15334-15342; definition from https://ar5iv.arxiv.org/html/2103.16562): IoU restricted to mask pixels within distance d of each contour, default d = 2% of the image diagonal. Mask IoU is insensitive to boundary error on large objects because interior area grows quadratically and contour linearly (their horse example: blobby edges, 89% Mask IoU).
- No MLLM paper found that reports a thin-structure or boundary metric for part segmentation. This is a gap, not a negative result.

## Q2. Coordinate precision, resolution, joints

- PointArena [cheng2025pointarena] (existing; https://arxiv.org/html/2505.09990). Point-Bench accuracy (point inside the target mask), Table 1: GPT-4o 29.5% average, Gemini-2.5-Flash 46.8%. Molmo-72B and Gemini-2.5-Pro within 0.43 points (not significant). Pointing supervision helps most: LLaVA variants without it score 4.8 to 17.4%; Qwen2.5-VL-7B with PixMo data 52.3% vs Qwen2-VL-7B 17.4%. Point-Act: Molmo-7B-D outperforms GPT-4o by 65% on real-robot use. Claude "consistently underperform[s]" (no number).
- Molmo and PixMo [deitke2025molmo] (https://mlanthology.org/cvpr/2025/deitke2025cvpr-molmo, CVPR 2025, pp. 91-104): open VLM trained with a 2D pointing dataset. 47 authors; entered with "and others".
- ScreenSpot-Pro [li2025screenspotpro] (https://mlanthology.org/iclrw/2025/li2025iclrw-screenspotpro, ICLR 2025 workshop LLM_Reason_and_Plan; arXiv 4 Apr 2025). High-resolution professional screens with small targets: best existing grounding model 18.9%; narrowing the search area (ScreenSeekeR cascaded search) reaches 48.1% without training. The pages opened do not give the target-area fraction.
- MLLMs Know Where to Look [zhang2025wheretolook] (https://proceedings.iclr.cc/paper_files/paper/2025/hash/aaa0ac4253da75faf9b0dc0dda062612-Abstract-Conference.html, ICLR 2025): accuracy drops when the subject is small, causally; attention still lands on the right region; training-free cropping from the model's own attention recovers accuracy.
- Vision language models are blind [rahmanzadehgervi2024blind] (CVF ACCV 2024 page, pp. 18-34; numbers from https://arxiv.org/abs/2407.06581v3): four VLMs average 58.07% on seven trivial geometric tasks (overlapping circles, line intersections); best 77.84% (Claude 3.5 Sonnet).
- PyVision [zhao2025pyvision] (https://neurips.cc/virtual/2025/127984, NeurIPS 2025 workshop on Multi-Turn Interactions in LLMs): letting the model write and run Python tools gives Claude-4.0-Sonnet +31.1% on VLMsAreBlind-mini and GPT-4.1 +7.8% on V*.

**Keypoints and joints.**

- LocLLM [wang2024locllm] (https://mlanthology.org/cvpr/2024/wang2024cvpr-locllm, CVPR 2024, pp. 614-623): first LLM that outputs keypoint coordinates as text from an image and instruction.
- PoseLLM [zhang2025posellm] (https://arxiv.org/html/2507.09139; date and venue not on the opened page). COCO val AP with ground-truth boxes: PoseLLM 77.8, LocLLM 77.4, ViTPose 77.4, HRNet 76.8. So a fine-tuned LLM emitting coordinates as text matches heatmap specialists on human joints. No results for general-purpose MLLMs.
- CapeLLM (ICCV 2025, pp. 22889-22898): category-agnostic pose estimation with an MLLM, SOTA on MP-100 per the abstract; no numbers on page. Not added.
- Transfer Learning for Pose Estimation of Illustrated Characters [chen2022illustratedpose] (CVF WACV 2022, pp. 793-802; numbers from https://ar5iv.labs.arxiv.org/html/2108.01819). A COCO-pretrained keypoint model scores PCKh@50 0.696 on illustrated characters; domain transfer with 4,000 annotated illustrations reaches 0.787. Joints on drawings need domain data.
- Animated Drawings (existing key smith2023animateddrawings; details below in Q5): pose mAP 0.09 without fine-tuning on children's drawings, 0.85 to 0.90 after.
- I found no paper that evaluates frontier general-purpose MLLMs (GPT, Gemini, Claude) on zero-shot joint localization with PCK. This is a gap.

## Q3. Tool use for segmentation

- SAM 3 [carion2025sam3] (https://arxiv.org/abs/2511.16719, 20 Nov 2025, v2 28 Mar 2026; no venue on page). Concept prompts are "simple noun phrases"; the page says nothing about part concepts. SAM 3 Agent (Appendix G of https://arxiv.org/html/2511.16719v2, read at offset 500000): an MLLM planner with four tools (segment_phrase, examine_each_mask, select_masks_and_return, report_no_mask). ReasonSeg test gIoU: 74.0 with Gemini 2.5 Pro, 70.8 with Qwen2.5-VL-72B, versus 57.5 for Seg-Zero-7B. OmniLabel AP 44.4 (Qwen3-VL-235B Thinking) vs 32.0 best prior. The appendix does not report the same MLLMs without the tool, so the tool's own gain is not isolated.
- But a text-prompted SAM call does not solve parts: SAM 3 (text) scores 33.05 gIoU on PascalPart against 85.32 on Pascal objects [mehrab2026ophrg, Table 1].
- Seg-Zero [liu2025segzero] (https://huggingface.co/papers/2503.06520, 9 Mar 2025): a reasoning model emits positional prompts for a frozen segmenter; zero-shot ReasonSeg 57.5, +18% over LISA-7B.
- SegAgent [zhu2025segagent] (CVF CVPR 2025, pp. 3686-3696): the MLLM emits text click points to an interactive segmenter over several steps, imitating annotators; no decoder or special tokens. No numbers in the abstract.
- LLMSeg (Q1): iterative zoomed refinement is the largest gain (+7.5 cIoU ReasonSeg, +15.2 RefCOCO), at about 7x the model calls.
- Visual Sketchpad [hu2024sketchpad] (NeurIPS 2024): drawing with detection and segmentation tools gives +8.6% on vision tasks on average; GPT-4o with Sketchpad 80.3% on V*Bench.
- ViperGPT [suris2023vipergpt] (ICCV 2023, pp. 11888-11898): the model writes Python against an API of vision modules; no training.
- PyVision [zhao2025pyvision] (Q2): model-written Python tools, +31.1% for Claude-4.0-Sonnet on VLMsAreBlind-mini.
- ScreenSpot-Pro (Q2): narrowing the search region 18.9% to 48.1%.
- Classical image-processing code beats a learned segmenter on drawings: Animated Drawings [smith2023animateddrawings] (existing; numbers from https://arxiv.org/pdf/2303.12741v2): on 571 random demo drawings, an adaptive-threshold, morphological-closing, flood-fill pipeline yields an animation-ready mask in 42.4% of cases, versus 24.7% for a fine-tuned Mask R-CNN (2,500 training samples). All three stages (box, mask, pose) succeed in 39.4% vs 23.3%. Failure modes of the classical pipeline: body parts drawn separately, limbs touching at non-joint points, non-watertight outlines. This is the most direct evidence that a code-writing agent's "flood fill" route is viable on line art, and also that it is not reliable.
- I found no study that measures an LLM agent writing classical segmentation code (thresholds, flood fill) for a named part. Gap.

## Q4. Layers, amodal completion, revealed-region fill

- See-through [lin2026seethrough] (existing; https://arxiv.org/html/2602.03749v1): 19 semantic RGBA layers per anime character, each "fully inpainted", trained from Live2D models; LaMa fills depth-split strata. Table 1: full model LPIPS 0.1549, PSNR 18.30 vs a SAM+LaMa baseline LPIPS 0.2880, PSNR 12.28, FID 81.1 vs 18.4. No joints or pivots. Note: the HTML author line reads "... Chun Wang, Stephen Choy ...", while the existing bib entry has "Choy, Stephen Chun Wang"; worth a re-check by the authors.
- Bunraku [chen2026bunraku] (existing; https://arxiv.org/html/2607.27348v1): stage 1 initialized from Qwen-Image-Layered and fine-tuned on 10K Live2D models with an 8x32 layer taxonomy and an occlusion-mask loss (lambda_occ = 0.1). Deformation is per-vertex keypose offsets, not skeletal pivots; per-vertex direction cosine 0.768 mean on 50 held-out characters. No layer IoU or inpainting metric in the part read.
- Qwen-Image-Layered [yin2025qwenimagelayered] (https://arxiv.org/abs/2512.15603, 17 Dec 2025): variable-count RGBA decomposition trained on PSD-derived data; abstract claims better decomposition, no numbers.
- LayerDiffuse [zhang2024layerdiffuse] (https://lllyasviel.github.io/pages/layerdiffuse; ACM TOG 43(4), Art. 100, SIGGRAPH 2024): latent transparency, 1M layer pairs, 97% user preference over generate-then-matte.
- pix2gestalt [ozguroglu2024pix2gestalt] (CVPR 2024, pp. 3931-3940): zero-shot amodal completion by diffusion, including artwork.
- Open-World Amodal Appearance Completion [ao2025amodal] (CVPR 2025, pp. 6490-6499): training-free segmentation, occlusion analysis and inpainting; outputs RGBA objects.
- O-Bench [liu2025obench] (https://arxiv.org/abs/2508.04059, 6 Aug 2025): 22 MLLMs show a significant gap to humans on occlusion perception; scaling and "thinking" do not close it. No numbers on the abstract page.
- LaMa [suvorov2022lama] (WACV 2022, pp. 2149-2159): standard large-mask inpainter.
- Image-editing benchmarks (existing ye2025imgedit, qian2025giebench): removal is a scored edit type but judged by GPT-4o or masks, and models over-modify. None asks a code-writing model to fill a revealed region.
- Gap: no benchmark measures whether a general model, without a generative inpainter, can fill the region a moved part reveals.

## Q5. Cut-out and puppet animation from a single image

- Animated Drawings [smith2023animateddrawings] (existing). Segmentation: classical pipeline (above). Joints: 17 COCO keypoints from a fine-tuned top-down heatmap model; pose mAP 0.09 without fine-tuning, 0.85 with 2,000 clean samples, 0.90 with 177,666 noisy samples. Evaluation is "animation-ready" success judged by visual inspection on 571 drawings: pose 90.2%, image-processing mask 42.4%, Mask R-CNN mask 24.7%. Users edited 20% of masks in a 5,000-image sample. This is the one prior evaluation of segmentation through the animation it enables.
- ARAP [igarashi2005arap] (https://www-ui.is.s.u-tokyo.ac.jp/~takeo/research/rigid; ACM TOG 24(3), SIGGRAPH 2005): handle-driven deformation of a 2D triangle mesh, no skeleton needed; two closed-form steps (rotation, then scale).
- Illustrated-character pose [chen2022illustratedpose] (Q2): COCO-trained keypoints transfer poorly to drawings (PCKh@50 0.696 to 0.787 with 4,000 annotated drawings).
- See-through and Bunraku (Q4): layer decomposition with inpainting; deformers or vertex offsets rather than joints. Neither reports a joint or pivot error metric.
- Articulate-Anything [le2025articulateanything] (existing; ICLR 2025 proceedings page): VLM-written articulation code with an actor-critic loop over rendered results; 75% success on PartNet-Mobility vs 8.7-11.6% for prior work. Joint parameters are judged through the rendered result, not a coordinate error.
- DrawingSpinUp (SIGGRAPH Asia 2024, project page https://lordliang.github.io/DrawingSpinUp): 3D route; qualitative evaluation only. Not added.

## Q6. Measuring cut-out quality directly

- Region: Mask IoU; insensitive to boundary error on large parts [cheng2021boundaryiou].
- Boundary: Boundary IoU [cheng2021boundaryiou], default d = 2% of image diagonal (about 27 px on our 1200x600 pilot images, too wide for a 3,000 px hand; use a part-relative or fixed small d). Boundary F-measure / contour accuracy as in DAVIS [perazzi2016davis]; Boundary IoU paper notes boundary F can jump from 1 to 0 and saturates for small objects with large d.
- Thin structures: IoU_thin [liew2021thinobject]; clDice, skeleton overlap that guarantees topology preservation [shit2021cldice].
- Joints: PCK-style normalized distance (as reported by PoseLLM, chen2022illustratedpose).
- Through an action: Animated Drawings' animation-ready rate; PointArena's Point-Act (pointing used to drive a robot, rated by users); Articulate-Anything's simulation success. None of these measures segmentation through a deterministic, automatically checked action.

### Pilot descriptors (my computation on tasks/T01-T24 target masks, 2026-11-17)

Target area: median 14,834 px (min 345, T07 earrings; max 168,764). Fraction of target pixels removed by a 7x7 opening (structures narrower than about 7 px): median 0.5%, hands 1.4% to 3.1%, earrings 13.3%. Largest inscribed radius: hands 18 to 30 px. So the pilot contains few thin structures in the morphological sense; the detached-thumb failure arises at extremities (tips far from the joint), not at sub-7-px structures. This motivates an extremity-recall metric in addition to thin recall.

## Q7. Synthesis (see sections/cutout.tex for the argued version)

- Not solved for parts. Whole-object localization by frontier models is close to specialists at the box level (LLMSeg box AP 64.2 vs SAM 3 69.1), but part-level masks are weak for every class of system (GSEval part 10 to 23 gIoU; PascalPart 33 gIoU even for SAM 3; InstructPart 4.5 to 35.7 gIoU), and boundaries lag (LLMSeg mask AP 47.2 vs 62.2).
- Weakest measured sub-step: boundary-accurate part extent, including extremities. Joint estimation on drawings is an unmeasured risk for general models (specialists need domain data: mAP 0.09 untuned on children's drawings). Fill is unmeasured for general models; specialized generative decomposers exist.
- Tools: large measured gains from zooming and segmenter calls, but text-prompted SAM does not resolve parts; point-prompted segmenters would reduce the task to localization plus pivot plus fill.
