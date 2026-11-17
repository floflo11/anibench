# Annotation schema v1

One file per image: `annotations/<image_id>.json`. It says where each movable part is, where it
pivots, how parts nest, and what the image is. Task definitions live separately in
`annotations/tasks_*.json` (see the end of this page). Code: `src/annotations.py`. Tool:
`tools/annotator.html` (guide: `docs/annotating.md`).

```json
{
  "schema_version": 1,
  "image_id": "toddlers",
  "image": {"path": "images/toddlers_task.png", "width": 1024, "height": 683},
  "foreground": "annotations/toddlers_fg.png",
  "outline_px": 3,
  "exclude_margin": 4,
  "metadata": {"style": "photo cutout on white", "subject": "two toddlers", "source": "...", "license": "CC0"},
  "parts": [
    {"name": "B1_body", "pivot": null, "parent": null, "clip": "foreground", "outline_px": 0,
     "polygons": [[[x, y], [x, y], [x, y], ...]]},
    {"name": "B1_hand", "pivot": [122, 198], "parent": "B1_body", "exclude": ["B1_hat"],
     "description": "raised hand; pivot at the wrist", "polygons": [[...]]}
  ],
  "masks": [
    {"name": "B1_skull", "role": "keep", "part": "B1_hat", "polygons": [[...]]}
  ]
}
```

## Coordinates

x to the right, y down, in image pixels. Pixel `(i, j)` has its **centre** at `(i, j)` (the same
convention as the pivots and the prompts). A pixel is inside a polygon when its centre is inside
(even-odd rule within one polygon). The polygons of one part are unioned. Vertices may be
fractional. Polygons need not be closed explicitly (the last point joins the first).

## Top-level fields

| field | required | meaning |
|---|---|---|
| `schema_version` | yes | `1` |
| `image_id` | yes | short id, unique across files; tasks refer to it |
| `image.path`, `.width`, `.height` | yes | path relative to the repo root; size in pixels |
| `foreground` | no | path of a mask PNG (white = character). If absent, the foreground is every pixel whose darkest channel is < 245 (non-white) |
| `outline_px` | no (3) | default outline growth for parts, see below |
| `exclude_margin` | no (4) | default margin around excluded parts |
| `metadata` | yes | `style`, `subject`, `source`, `license` (strings; `"unknown"` if not known). Extra keys such as `annotator`, `notes` are allowed |
| `parts` | yes | non-empty list of parts |
| `masks` | no | extra masks (currently only `role: "keep"`) |

## Parts

| field | required | meaning |
|---|---|---|
| `name` | yes | unique across all annotation files (tasks refer to parts by name). Convention: `<character>_<part>`, e.g. `C3_hand`, `C3_body` |
| `polygons` | yes | non-empty list of polygons; each polygon is a list of ≥ 3 `[x, y]` points |
| `pivot` | yes (may be `null`) | joint the part rotates about, `[x, y]`; `null` for a part with no joint (a whole character) |
| `parent` | yes (may be `null`) | name of the part this one is attached to (hand → body, hat → head); `null` for a whole character |
| `exclude` | no (`[]`) | names of parts carved out of this one |
| `holes` | no | polygons subtracted from `polygons` |
| `clip` | no (`"foreground"`) | `"foreground"`: intersect with the foreground; `"none"`: use the polygons as is |
| `outline_px` | no | overrides the top-level default (use `0` for whole characters) |
| `exclude_margin` | no | overrides the top-level default |
| `description` | no | free text |

**Mask of a part**, in this order:

```
region = fill(polygons) & ~fill(holes)
if clip == "foreground":  region &= foreground
E      = union over x in exclude of dilate(fill(x.polygons), exclude_margin)
region &= ~E
mask   = dilate(region, outline_px) & foreground & ~E     if outline_px > 0, else region
```

`dilate` is a binary dilation with the 4-connected cross, repeated `px` times
(`scipy.ndimage.binary_dilation(m, iterations=px)`). The outline step pulls the part's drawn
outline (dark line pixels just outside the colour fill) into the part, but never beyond the
foreground and never into an excluded part. `exclude` uses the excluded part's raw polygons
(before clipping and outline).

Validation (`python src/annotations.py validate annotations/*.json`) rejects: wrong
`schema_version`, a missing `pivot` or `parent` key, a polygon with < 3 points, non-numeric
points, unknown parent or exclude names, a part excluding itself, parent cycles, duplicate names,
bad `clip`, missing metadata strings.

## Masks (`masks`)

| field | meaning |
|---|---|
| `name` | unique name (e.g. `B1_skull`) |
| `role` | `"keep"`: region under `part` that must stay filled when the part moves away (e.g. the skull under a lifted hat). Written as `skull.png` for every task whose target parts include `part` |
| `part` | the part it belongs to |
| `polygons` | as for parts |
| `clip` | default `"none"` |

## Task definitions (`annotations/tasks_*.json`)

```json
{"schema_version": 1, "tasks": [
  {"id": "T01", "tier": 1, "image": "lineup", "instruction": "Make the boy ... wave ...",
   "parts": ["A1_hand"], "kind": "rotate", "amp": 25},
  {"id": "T14", "...": "...", "kind": "rotate_hat", "amp": 15, "pivot": [560, 160]}
]}
```

`kind` is one of `rotate` (about each part's pivot), `rotate_hat` (about the task's `pivot`),
`translate_up`, `jump`, `body`, `flutter`, `human` (no automatic graders). `amp` is degrees for
the rotations and pixels otherwise. `pivot` (optional) overrides the parts' pivots. The graders,
allowed region and prompt follow from `kind` in `src/tasks.py`.

Generate: `python src/tasks.py [--tasks annotations/tasks_pilot.json] [--out tasks]` (or
`python src/annotations.py tasks ...`). Note: this rewrites `spec.json["graders"]` with the full
list; re-run `src/admission.py` afterwards to narrow it again.

## The migrated pilot images

`annotations/lineup.json` and `annotations/toddlers.json` were produced from the old hand-coded
`src/parts.py` by `scripts/migrate_legacy_parts.py`. The old parts used colour rules (skin, dark
hair, red) and morphology, which polygons cannot express directly, so the migration traces each
part's cleaned region into exact pixel-corner polygons (vertices at half-integers) with
`clip: "none"`; whole characters use the traced component outline with `clip: "foreground"`
(plus one 6-px `holes` entry for a foreign foreground island inside A2's outline), and the B1 hat
keeps its original drawn polygon. The script and `tests/test_annotations.py` check that every
part mask and every file in `tasks/T01..T24` is reproduced byte-identically (0 px difference).
The traced polygons have many vertices; new annotations need only a few clicks per part.
