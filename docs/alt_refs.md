# Alternate valid animations (WS7, task 2.2)

Reviewers will ask whether the checks accept only *our* style of animation. To measure that, we built several
animators that are independent of `src/reference.py`, each producing animations a human would accept, and
graded them with the unchanged checks. A failure on one of these animations is a candidate **false fail**.

This page defines, *before* the full run, what "valid" means for each task type. The false-fail analysis in
`results/alt_refs/false_fail.md` classifies every failure against these definitions. (The definitions were
written after a 2-task smoke test; that test showed two edge cases, a hat lifted mostly out of the frame and
leftover anti-aliased pixels from the part masks, and both are now ruled on explicitly below.)

## What the animators may read

They stand in for a skilled human who cuts the part out by hand. They read:

- `tasks/<id>/image.png`, the image a model is given;
- the instruction, as the structured paraphrase in `annotations/tasks_pilot.json` (`kind`, `parts`, and the
  pivot that the instruction names, which is only T14's "left end of the brim");
- the hand-drawn part masks, joint pivots and head (keep) masks in `annotations/*.json`, the same ones
  `src/reference.py` uses.

They never read the grader's files (`spec.json`, `allowed.png`, `target.png`, `skull.png`), the task's `amp`,
or any grader constant. Each style picks its own amplitude from the table below. `tests/test_alt_refs.py`
checks this: pages build from a folder that holds only `image.png`, and changing `amp` changes nothing.

## Global validity rules (all task types)

An animation is **valid** if a careful human animator, shown the instruction and the result, would accept it
as doing what was asked with no visible side effects:

1. **Rest pose:** at t = 0 the frame shows the original image. At t = 2 s the loop closes on the same frame.
2. **Only the named part moves.** Every other character, every other body part and the background stay put.
   The area the part uncovers may show white background or a plausible continuation of what is behind it
   (sleeve, skin, hair or the head under a hat). Changes to that area count as part of the motion, not as
   side effects.
3. **The part stays whole and attached.** No piece of the part is left behind, no piece detaches, and no hole
   or seam opens inside it. At its joint (wrist, elbow, shoulder, neck, ear lobe, the hair tie, the head for
   a veil) it stays attached, though a joint may bend smoothly over a few pixels as skin would.
4. **Shape:** rigid motion, or mild non-rigid cartoon deformation (squash and stretch, bending along a bone
   chain). A part may scale by at most ±15% along one axis, and its area may change by at most ±15%.
   Squats and bounces are the exception: lowering the body is the action itself, so the amplitude table
   governs it.
5. **Amplitude in the plausible range** for the action (table below). The motion must be readable at normal
   viewing size.
6. **Stays in frame:** at least half of the part stays inside the canvas in every frame (a hat lifted
   mostly out of the picture is no longer a visible hat lift).
7. **Pivot:** a rotation's pivot lies at a reasonable reading of the joint, within
   `clip(0.08 x part length, 4, 10)` px of the annotated pivot (the far edge versus the middle of a wrist
   crease, for example). Anything further out reads as rotating about the wrong place.
8. **Timing is free:** any easing, any number of beats, overshoot and settle, anticipation, holds and
   phase lag between segments are all valid, provided rules 1 to 7 hold in every frame.

**Tolerated artifacts.** A 1 to 3 px faint anti-aliasing halo outside the hand-drawn mask may stay behind
when the part moves. Every solution that uses the provided masks shows it, including the reference that
admits the checks, and at normal size it is visible only as a faint ghost edge. A remnant that reads as a
piece of the part (solid colour, recognisable shape) is not tolerated.

## Per task type: the valid envelope

| Action | Tasks | Valid motion | Plausible amplitude (low / typical / high) |
| --- | --- | --- | --- |
| Wave the hand at the wrist | T01, T03, T05, T20, T21, T12 (A1, A3) | Swing about the wrist in the image plane, one or both directions. Fingers may trail | 15 / 25 / 40 deg |
| Wave the forearm at the elbow | T02, T04, T12 (A2, A4) | Swing about the elbow. The hand may lag | 12 / 20 / 32 deg |
| Swing the whole arm at the shoulder | T06 | Swing about the shoulder. Forearm and hand may lag | 8 / 15 / 25 deg |
| Earrings swing | T07 | Pendulum about the ear lobe, both earrings, in or out of phase | 10 / 22 / 35 deg |
| Pigtails swing | T08 | Swing about the hair tie, may bend along the length | 6 / 12 / 20 deg |
| Nod or tilt the head | T09, T10, T11 | Rotation about the neck (an in-plane nod), may overshoot and settle. T10: the hat moves with the head | 5 / 8 / 14 deg |
| Lift the hat and settle it back | T13 | Hat rises and comes back down, may tilt a few degrees, may squash on landing. The head under it stays (hair or skin where the hat was) | 30 / 60 / 110 px, limited by rule 6 |
| Tip the hat about the brim | T14 | Rotation about the left brim end, may overshoot | 8 / 15 / 25 deg |
| Jump | T15, T16 | The whole character leaves the ground and lands. May crouch first, stretch in flight, squash on landing, small rebound. Other characters stay still | 35 / 70 / 120 px |
| Squat, or bounce at the knees | T17, T18 | The body lowers toward the feet and comes back up. The feet stay planted. May be a uniform squash, a squash that widens to keep volume, or legs that compress while the upper body drops rigidly | squat 6 / 12 / 20 % of height; bounce 3 / 6 / 10 % |
| Veil flutters | T19 | Swing or travelling wave along the veil from where it attaches. The tip moves the most | 15 / 30 / 50 px of tip travel |

## The styles (src/alt_refs/)

| Variant | Technique | What it varies |
| --- | --- | --- |
| `easing-sine_typ` | `THREE.Sprite` cut to the part's box, anchored with `sprite.center`, white fill | Control: a sine at typical amplitude |
| `easing-sine_small` | same | Sine, low end of the range |
| `easing-cubic_large` | same | Ease-in-out cubic beats, high end of the range |
| `easing-bounce` | same | Fast swing out, damped settle; lifts get a small rebound hop |
| `squash_stretch-mild` / `-strong` | Hand-composed `Matrix4` per frame on a joint-local quad, linear filtering, nearest-colour fill | Scale along the motion axis (k = 0.08 / 0.15), area preserving: stretch out and squash back, crouch, stretch and land-squash for jumps, widening squats |
| `follow_through-lag` / `-drag` | `THREE.SkinnedMesh` (subdivided plane) on a bone chain, smooth skin weights | Distal segments lag (0.10 / 0.22 s). Rigid parts overshoot and settle. Jumps stretch the body. Squats compress the legs, and the head lags |
| `alt_impl-canvas2d` | A 2D canvas redrawn every frame as a `CanvasTexture`. The part is masked in the browser and drawn with bilinear 2D transforms. Keyframed with `AnimationClip` + `AnimationMixer.setTime` | Asymmetric keyframes, holds |
| `alt_impl-shader` | One full-screen `ShaderMaterial` that inverse-maps every pixel through each part's transform (label texture, raw colours) | Swing with a second harmonic, trapezoid lift, parabolic jump |
| `pivot-inward` / `-lateral` | The easing page with the anchor moved along or across the part, by `clip(0.08 L, 4, 10)` px (rule 7) | Pivot placement (rotations only; not applicable to lifts, jumps and squats) |

Every style except the pivot style runs on every admitted task (T01 to T21; T22 to T24 have no automatic
checks). Each run is graded with the task's admitted checks (`spec.json` `graders`, as narrowed in
`validation/admission.md`).

### Fixes made to the styles during the run (T13 and T14 re-run with `--force`)

Reviewing the first failures showed two places where our own styles were not valid. We fixed both before
classifying, without looking at which checks the fixes would pass:

1. **T14 hat tip went both ways.** Every style swung the hat symmetrically, so for half the loop the hat
   tipped *down* over the boy's eyes. The instruction says "tilt his hat up and back". All styles now tip one
   way only (up), then return, optionally with a small settle. `src/reference.py` has the same two-way swing
   (`sin`), so the reference that admits T14 tips the hat into the face. That is a validity bug in the
   reference, reported to its owner rather than fixed here.
2. **The head under a hat.** The skull keep mask covers only the hat's lining band, so filling just that band
   left white wedges in the sides of the head once the hat moved. The styles now fill the convex hull of the
   skull and the visible head (both ears included): a flat sampled colour for the white-fill styles, and a
   nearest-colour fill for the others. The reference fills only the band.

## How failures are classified

For each failed check we look at the evidence image (original | the failing frame | offending pixels) and the
GIF, and ask whether the frame breaks one of the rules above:

- **(a) grader too strict:** the animation is valid under rules 1 to 8, so the check rejected an animation a
  human would accept.
- **(b) style broke the rule:** the frame violates a rule (for example, a squash beyond the area limit, the
  part mostly out of frame, a visible leftover piece, pixels moved outside the part).

A *false fail* is a run that failed only on checks classified (a). The false-fail rate is false fails /
runs. Graders are not changed here. Recommended threshold changes for the grader owner are listed in
`results/alt_refs/false_fail.md`.

## Reproduce

    python3 src/alt_refs/run.py render --tasks T01,T02,T03   # resumable, in chunks
    python3 src/alt_refs/run.py render                       # everything still missing
    python3 src/alt_refs/run.py report                       # false_fail.{md,json}
    python3 src/alt_refs/run.py gifs                         # example GIFs per style
    python3 -m pytest tests/test_alt_refs.py
