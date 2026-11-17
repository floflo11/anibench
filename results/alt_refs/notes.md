## Findings

- **Most valid alternate animations pass.** 223 of 242 runs pass every admitted check. Of the 19 failures,
  7 are real rule breaks (b) and 12 are false fails (a).
- **The false fails come in four kinds:**
  1. *G5 on textured joints* (5 runs: T08 x4, T04). Pixels at the pivot move 2 to 4 px under a correct or
     reasonable pivot. On hair or lace, so small a shift changes 26% to 50% of the pixels in the 10 px joint
     disc, above `G5_MAX = 0.20`. Of these, 3 are pivot-shift runs at the edge of rule 7, and 2 use the exact
     pivot at large amplitude or with stretch.
  2. *G1 on squash and stretch* (3 runs: T13, T14, T16). The allowed region is built from rigid poses + 10 px
     (22 px for jumps), so a cartoon squash that widens the hat or body 10% to 15% steps outside it. A probe at
     k = 0.13 (inside rule 4) still fails all three; k = 0.10 passes T13 and T14 but not T16.
  3. *G2 on faint halos* (3 runs, T17). A 79 px, 1 to 2 px wide light-grey strip of hair halo outside the
     A2_body mask stays behind when the body lowers and counts as a new piece.
  4. *G2 on pale texture* (1 run, T15). The pale stripes of the shirt sit at the foreground threshold, so a
     smoothly stretched shirt changes its internal piece count.
- **The real breaks are not all the style's fault.** 4 of the 7 (T10) come from the shared annotation: the
  B2_head mask includes a sleeve sliver, so at some head poses a ~65 px fleck tears off the raised sleeve
  (the reference and the plain sine at 8 deg happen to pass).
  2 more are genuine style excesses: a 110 px hat lift that leaves 69% of the hat off-canvas, and a 15%
  earring stretch that pulls the bead off its chain. The last (T07 at 35 deg) is invalid because the chain is
  not in the earring mask, but G3 flagged it for an unrelated reason (the bead occluding the cheek).
- **By style:** no false fails for the two alternative techniques (canvas2d bilinear + keyframes; inverse-mapping
  shader) or for the sine easings (typical and small amplitude). The false fails cluster at the edges of the
  envelope: strong squash (4), shifted pivots (3) and the largest amplitude (1). The other 4 are the T17 halo
  and T15 pale-stripe G2 cases, which hit easing-bounce, follow-through and mild squash.

## Threshold recommendations for the grader owner (graders.py unchanged here)

Evaluated in `results/alt_refs/whatif.json` (`python3 src/alt_refs/whatif.py`) on the failing alternate runs
and on the reference and its targeted broken copies for the same tasks:

| Change | Clears (a) failures | Keeps (b) failing | Reference still passes | Broken copies still caught | Verdict |
| --- | --- | --- | --- | --- | --- |
| **G1:** grow the allowed region by `ceil(0.075 x larger extent of the target)` px (room for +-15% squash/stretch), or build it from poses scaled 0.85 to 1.15 about the anchor | 3/3 | (no G1 (b)) | 3/3 | whole 3/3, wrong part 3/3 | Recommend |
| **G2:** ignore pieces whose median contrast to white is < 80 | 4/4 | 5/5 | 12/12 | missed thumb 3/4 (loses T18: its cut disc is the pale cream hat) | Recommend, or keep 80 for halos only and rely on G2b for detached pieces |
| G2: 3x3 opening before counting | 1/4 | 4/5 | 11/12 (breaks T17) | 4/4 | Reject |
| **G5:** raise `G5_MAX` from 0.20 to 0.30 | 2/5 | n/a | 13/13 | center pivot 12/12 (smallest caught value 0.35) | Recommend |
| G5: change detection on blurred images (sigma 1.5) | 0/5 | n/a | 12/13 (breaks T08) | 12/12 | Reject |

Further recommendations, not tested here:

- **G5 on T08 (pigtails), and textured joints in general:** the 3 remaining T08 failures (0.375 to 0.495)
  overlap the center-pivot values on other tasks (0.35 to 0.49), so no single global threshold separates
  them. Replace the changed-pixel fraction with a displacement test: track the joint disc (phase correlation or
  template match over +-8 px) and fail if it moves more than ~4 px. Or give T08 its own cap (center pivot gives
  1.0 there).
- **G3 on tiny parts (T07 earrings, 345 px):** the net-foreground measure counts a part that swings in front
  of other foreground (cheek, veil) as lost area. The reference already scores 0.41 against the 0.5 limit.
  Measure the part's own area (for example, foreground in the region minus foreground of the original outside
  the target), or normalise by `max(target area, 1000)`.
- **Annotation fixes (owner of annotations/):** (1) the B2_head mask includes a sliver of the raised navy
  sleeve near (850, 195). Remove it, or every T10 solution that uses the mask tears the sleeve. (2) The A4
  earring masks contain only the bead, not the gold chain from the lobe. Include the chain, or every T07
  rotation leaves the chain hanging while the bead swings, a visible defect that no check catches at
  moderate amplitude (false pass). (3) The faint hair halo outside A2_body (around x=348-386, y=168-219) is
  what G2 trips on in T17.
- **Reference validity (owner of src/reference.py):** T14's reference swings the hat both ways (`sin`), so
  half the loop tips the hat down over the eyes, against "tilt his hat up and back". Make it one-sided. Its
  70 px T13 lift also puts 35% of the hat above the canvas (the hat starts at y=7).

## Caveats

- Classification is one annotator's judgment against `docs/alt_refs.md`, made by looking at the evidence images and
  frame strips. The borderline calls are the pivot-shift runs (T04, T08), which rest on rule 7's 10 px
  tolerance. Count them as (b) and the false-fail rate drops from 12/242 to 9/242.
- The what-if was run only on failing alternate runs and the reference set. After any threshold change,
  re-run the full suite (`python3 src/alt_refs/run.py render --force`) and the admission
  (`src/validate.py`, `src/admission.py`) to check that no passing run flips.
- The styles use the same hand-drawn masks as the reference, so they share its mask artifacts. A
  model-made cut-out would have different ones.
