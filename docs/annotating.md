# Annotating an image for anibench

You mark the parts of each character that a task can ask a model to move, with a polygon and a
pivot per part. Budget: about 5–10 minutes per image. Format details: `docs/annotation_schema.md`.

## Setup

1. Put the image in `images/` (PNG, white background, characters not touching each other).
   If the image came with transparency, also save its alpha as a white-on-black mask
   `annotations/<image_id>_fg.png`; otherwise the foreground is "every non-white pixel", which
   fails on white clothing.
2. Open `tools/annotator.html` in Chrome (double-click it; it works offline from `file://`).
3. **Load image…** (or drop the file on the page). `image_id` and the path are filled in from the
   file name; check them. Fill in the foreground path if you made one.
4. Fill in **metadata**: `style` (e.g. "flat cartoon", "watercolour", "photo cutout"), `subject`
   (one line), `source` (URL, or generator + prompt), `license` (CC0, CC-BY-4.0, own, …) and your
   name. Do not annotate images whose license you do not know.

## Per character

Number the characters left to right: `C1`, `C2`, … Name parts `<character>_<part>`, e.g.
`C1_body`, `C1_hand`, `C2_pigtailL` (L/R = viewer's left/right). Names must be unique across all
images, so for a new image use a fresh prefix if the old ones are taken (e.g. `P3C1_hand`).

1. **N**, type `C1_body`, **Enter**. Click a rough outline around the whole character, **Enter**.
   It can be loose: it is clipped to the foreground. Bodies get no pivot and no parent
   (the "whole character" box is ticked automatically for `*_body`).
2. For each movable part: **N**, type the name, **Enter**. The parent defaults to `C1_body`;
   change it if the part hangs off another part (a hat on a head → parent `C1_head`).
   Click the polygon, **Enter** (or click the first point). **P** then click the pivot
   (or **Shift+click**).
3. **Export JSON** (Ctrl+S) and save the file as `annotations/<image_id>.json`.
   Export is blocked while the Problems box shows errors; read the warnings too.

Undo a point with **Backspace** (with no polygon open, Backspace reopens the last one);
**Esc** drops the open polygon; **Ctrl+Z / Ctrl+Y** undo and redo anything. Drag a vertex of
the selected part to move it. Zoom with the wheel, pan with Space+drag or right-drag, **F** fits.
The work is autosaved in the browser; **Restore autosave** brings it back after a crash.
To edit an existing file: load the image, then **Import JSON…**.

## What counts as a part

- It moves **as one piece about one joint**: a hand (wrist), forearm + hand (elbow), whole arm
  (shoulder), head (neck), pigtail (hair tie), earring (earlobe), hat (brim), tail (base), ear.
- It is **clearly visible** and you can name it in one unambiguous instruction ("the girl with
  pigtails' raised forearm"). Skip parts that are mostly hidden or under ~150 px in area.
- A part that is wholly in front of something else is ideal (a raised hand against the
  background). A part whose motion would reveal unseen pixels (a lifted hat) is fine, but give
  it a **keep mask** (below).
- Prefer the parts a person would animate: raised hands and arms, heads, hair, accessories.
  Aim for 2–5 parts per character.

## Drawing the polygon

- Trace the **visible silhouette of the part only**. Where it meets its parent, cut straight
  across at the joint (across the wrist, across the neck), not further into the parent.
- Against the background you may be loose: the polygon is clipped to the foreground. Against
  other parts of the character be accurate to about 1–2 px. Zoom in for small parts.
- Do **not** trace the dark drawn outline separately: every part automatically grows by 3 px
  inside the foreground to take in its outline. So stop the polygon at the inside of the
  outline where the part meets another part, and anywhere outside it against the background.
- Several polygons per part are allowed (they are unioned), e.g. a head whose hair is split
  by a raised hand. **H** before drawing makes the next polygon a hole cut out of the part.
- If the part touches another part it must not swallow (a hand in front of a hat brim), tick
  that part under **exclude**: its polygon, grown by 4 px, is carved out of this part.

## Where the pivot goes

On the joint, at the centre of the cut between the part and its parent: the middle of the
wrist for a hand, the elbow for a forearm, the shoulder for a whole arm, the base of the neck
for a head, the knot for a pigtail, the earlobe for an earring. For a hat, the centre of the
brim where it sits on the head. The pivot must lie inside the image and normally on or just
inside the part.

## Keep (skull) masks

For a part that may be lifted off and reveal what was under it (hats, masks, a held object),
select the part, press **K** and draw the region under it that must stay filled (for a hat:
the top of the head hidden by the crown). It is exported as a `keep` mask named
`<name>_skull` for `*_hat` parts, `<name>_keep` otherwise, and becomes `skull.png` in tasks.

## Check, then add tasks

```
python src/annotations.py validate annotations/<image_id>.json
python src/annotations.py preview annotations/<image_id>.json --out /tmp   # look at the PNG
```

The preview shows the final masks (after clipping, exclusion and the 3 px outline) and pivots.
Fix anything that leaks into a neighbour. Then add tasks for the image to an
`annotations/tasks_*.json` file and run `python src/tasks.py --tasks <file> --out <dir>`.
