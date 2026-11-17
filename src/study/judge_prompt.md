# anibench judge prompt (v1)

Fixed prompt for multimodal LLM judges in the human study (E4). It asks exactly what human raters are asked in
`tools/rater.html`, with the same defect codes, and requires strict JSON matching `src/study/judge_schema.json`.
Use it verbatim; only fill the `{...}` fields. Temperature 0 where the API allows it; one call per clip; no
other system prompt. If the reply is not valid JSON or fails the schema, retry once with the same prompt plus
the line "Your previous reply was not valid. Reply with the JSON object only."; if it fails again, record the
clip as missing for that judge (it counts against the judge's coverage, which `analyze.py` reports).

## Inputs (per clip, from `rater/manifest.json`)

Attach the media in this order and keep the captions:

- **Video-capable judges:** `video` (the clip raters see: four panels, original still | animation on top, zoom of
  the original | zoom of the animation below; 2-second loop, played 3 times at 12 frames per second).
- **Image-only judges:** four images: `still` ("original image"), `still_zoom` ("zoom of the original"),
  `sheet_full` ("animation frames, full image") and `sheet_zoom` ("animation frames, zoomed"). Each sheet shows
  9 frames left to right, top to bottom, labelled with their time; times are in `sheet_times`. The 2-second
  loop restarts after the last frame (t = 1.92 s), so the animation then returns to the frame at t = 0.

## Prompt

---

You are checking a short animation made from a still image.

Someone was asked to animate ONE named part of the image as a seamless 2-second loop. The request was:

> {instruction}

Only the named part may move. Everything else must stay exactly as in the original image. The part should move
as asked, keep its size and shape, stay in one piece, turn around the natural joint, and the loop should restart
without a visible jump. The first frame (t = 0) should look exactly like the original image.

{media_description}

Answer the same questions a human rater answers:

1. Did the animation do what was asked without breaking anything else? (`pass`: true or false)
2. If not, what went wrong? Pick every code that applies (`defects`; empty if `pass` is true):
   - `outside_moved`: something outside the named part moved, shifted, flickered or changed, even slightly
     (another body part, another person, the whole image).
   - `tore_split`: the part tore, split or left a piece behind: a gap, seam or hole opens, a piece (for example
     a finger or thumb) stays behind or detaches, or a copy of the part remains in its old place.
   - `size_shape`: the part changed size or shape: it grows, shrinks, stretches, is cropped or is distorted
     beyond what the motion explains.
   - `barely_moves`: the named part does not move, or moves so little that the motion is hard to see.
   - `wrong_pivot`: the part rotates around the wrong point (for example a hand that should bend at the wrist
     turns around its centre or around the elbow), or the wrong part moves.
   - `loop_jump`: a visible jump or snap when the loop restarts, or the first frame already differs from the
     original image.
   - `other`: any other problem; describe it in `other_text`.
3. How sure are you? (`confidence`: 1 = unsure, 2 = fairly sure, 3 = certain)

Judge only what you can see. If the named part moves as asked and you cannot see anything else change or
break, answer `pass: true`. If you are unsure, still answer and use `confidence: 1`.

Reply with ONE JSON object and nothing else (no markdown fences, no extra text), with exactly these fields:

{"clip_id": "{clip_id}", "pass": true or false, "defects": [codes], "other_text": "", "confidence": 1|2|3,
"reason": "one or two sentences naming what you saw"}

---

`{media_description}` is one of:

- Video: "The attached video has four panels. Top left: the original image (still). Top right: the animation.
  Bottom left: a zoom of the original around the named part. Bottom right: the same zoom of the animation. The
  2-second loop plays three times."
- Images: "Image 1 is the original image. Image 2 is a zoom of the original around the named part. Image 3 shows
  9 frames of the animation (full image) at the times written above each frame. Image 4 shows the same frames
  zoomed on the same area as image 2. After the last frame (t = 1.92 s) the loop restarts at t = 0."

## Collecting the outputs

Write one JSONL file per judge (`judges/<judge-name>.jsonl`, one object per line, as returned), then:

```bash
python3 src/study/analyze.py --key build/study/<name>/key.json --ratings ratings/*.json \
    --judges judges/*.jsonl --out results/study
```

`analyze.validate_judge_record` checks each object against the schema rules; invalid objects should be retried
as above before analysis.
