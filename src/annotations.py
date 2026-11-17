"""Annotation files (schema v1) -> part masks and pivots -> tasks.

An annotation file `annotations/<image_id>.json` describes one image: its parts as polygons,
pivots, the parent hierarchy, exclusions, optional keep (skull) masks and metadata.
The format is documented in docs/annotation_schema.md.

Coordinates: x right, y down, in image pixels. Pixel (i, j) has its centre at (i, j), so the
top-left pixel covers [-0.5, 0.5] x [-0.5, 0.5]. A pixel belongs to a polygon when its centre
lies inside it (even-odd rule within one polygon; the polygons of a part are unioned).

Mask of a part (in this order):
    region = fill(polygons) & ~fill(holes)        # holes: optional, default []
    if clip == "foreground":  region &= foreground
    region &= ~E                                  # E = union of dilate(fill(x.polygons), exclude_margin)
                                                  #     over the parts x named in `exclude`
    if outline_px > 0:  mask = dilate(region, outline_px) & foreground & ~E
    else:               mask = region
`dilate` is scipy's binary dilation with the 4-connected cross, `iterations` = px.

Usage:
    python src/annotations.py validate annotations/*.json
    python src/annotations.py tasks [--tasks annotations/tasks_pilot.json] [--out tasks]
"""
import argparse
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
ANN_DIR = ROOT / "annotations"
SCHEMA_VERSION = 1
CLIP_VALUES = ("foreground", "none")
MASK_ROLES = ("keep",)
DEFAULT_OUTLINE_PX = 3
DEFAULT_EXCLUDE_MARGIN = 4
META_KEYS = ("style", "subject", "source", "license")


class AnnotationError(ValueError):
    """Raised for an annotation file that does not follow schema v1."""


# --------------------------------------------------------------------------------------------
# validation


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and np.isfinite(v)


def _check_point(p, where):
    if not (isinstance(p, (list, tuple)) and len(p) == 2 and all(_is_num(c) for c in p)):
        raise AnnotationError(f"{where}: a point must be [x, y] numbers, got {p!r}")


def _check_polygons(polys, where):
    if not isinstance(polys, list) or not polys:
        raise AnnotationError(f"{where}: 'polygons' must be a non-empty list of polygons")
    for k, poly in enumerate(polys):
        if not isinstance(poly, list) or len(poly) < 3:
            n = len(poly) if isinstance(poly, list) else "?"
            raise AnnotationError(f"{where}: polygon {k} has {n} points; a polygon needs at least 3")
        for p in poly:
            _check_point(p, f"{where}: polygon {k}")


def validate(ann):
    """Raise AnnotationError if `ann` (a parsed JSON dict) is not a valid schema-v1 annotation."""
    if not isinstance(ann, dict):
        raise AnnotationError("annotation must be a JSON object")
    if ann.get("schema_version") != SCHEMA_VERSION:
        raise AnnotationError(f"schema_version must be {SCHEMA_VERSION}, got {ann.get('schema_version')!r}")
    if not isinstance(ann.get("image_id"), str) or not ann["image_id"]:
        raise AnnotationError("'image_id' must be a non-empty string")
    img = ann.get("image")
    if not isinstance(img, dict) or not isinstance(img.get("path"), str):
        raise AnnotationError("'image' must be an object with 'path', 'width', 'height'")
    for k in ("width", "height"):
        if not isinstance(img.get(k), int) or isinstance(img.get(k), bool) or img[k] <= 0:
            raise AnnotationError(f"image.{k} must be a positive integer")
    if "foreground" in ann and ann["foreground"] is not None and not isinstance(ann["foreground"], str):
        raise AnnotationError("'foreground' must be a path string or null")
    for k in ("outline_px", "exclude_margin"):
        if k in ann and (not isinstance(ann[k], int) or isinstance(ann[k], bool) or ann[k] < 0):
            raise AnnotationError(f"'{k}' must be a non-negative integer")
    meta = ann.get("metadata")
    if not isinstance(meta, dict):
        raise AnnotationError("'metadata' must be an object with style, subject, source, license")
    for k in META_KEYS:
        if not isinstance(meta.get(k), str):
            raise AnnotationError(f"metadata.{k} must be a string (use \"unknown\" if not known)")

    parts = ann.get("parts")
    if not isinstance(parts, list) or not parts:
        raise AnnotationError("'parts' must be a non-empty list")
    names = []
    for i, p in enumerate(parts):
        if not isinstance(p, dict):
            raise AnnotationError(f"parts[{i}] must be an object")
        name = p.get("name")
        if not isinstance(name, str) or not name:
            raise AnnotationError(f"parts[{i}]: 'name' must be a non-empty string")
        where = f"part {name!r}"
        if name in names:
            raise AnnotationError(f"{where}: duplicate part name")
        names.append(name)
        _check_polygons(p.get("polygons"), where)
        if p.get("holes"):
            _check_polygons(p["holes"], f"{where} (holes)")
        if "pivot" not in p:
            raise AnnotationError(f"{where}: missing 'pivot' (use null for a part with no joint, e.g. a whole character)")
        if p["pivot"] is not None:
            _check_point(p["pivot"], f"{where}: pivot")
        if "parent" not in p:
            raise AnnotationError(f"{where}: missing 'parent' (use null for a top-level part)")
        if p["parent"] is not None and not isinstance(p["parent"], str):
            raise AnnotationError(f"{where}: 'parent' must be a part name or null")
        exc = p.get("exclude", [])
        if not isinstance(exc, list) or not all(isinstance(e, str) for e in exc):
            raise AnnotationError(f"{where}: 'exclude' must be a list of part names")
        if p.get("clip", "foreground") not in CLIP_VALUES:
            raise AnnotationError(f"{where}: 'clip' must be one of {CLIP_VALUES}")
        for k in ("outline_px", "exclude_margin"):
            if k in p and (not isinstance(p[k], int) or isinstance(p[k], bool) or p[k] < 0):
                raise AnnotationError(f"{where}: '{k}' must be a non-negative integer")
    by_name = {p["name"]: p for p in parts}
    for p in parts:
        where = f"part {p['name']!r}"
        if p["parent"] is not None:
            if p["parent"] not in by_name:
                raise AnnotationError(f"{where}: parent {p['parent']!r} is not a part")
            seen, cur = {p["name"]}, p["parent"]
            while cur is not None:
                if cur in seen:
                    raise AnnotationError(f"{where}: parent chain has a cycle")
                seen.add(cur)
                cur = by_name[cur]["parent"]
        for e in p.get("exclude", []):
            if e not in by_name:
                raise AnnotationError(f"{where}: exclude {e!r} is not a part")
            if e == p["name"]:
                raise AnnotationError(f"{where}: a part cannot exclude itself")

    masks = ann.get("masks", [])
    if not isinstance(masks, list):
        raise AnnotationError("'masks' must be a list")
    for i, m in enumerate(masks):
        if not isinstance(m, dict) or not isinstance(m.get("name"), str) or not m["name"]:
            raise AnnotationError(f"masks[{i}] must be an object with a non-empty 'name'")
        where = f"mask {m['name']!r}"
        if m["name"] in by_name or m["name"] in [x.get("name") for x in masks[:i]]:
            raise AnnotationError(f"{where}: name already used")
        if m.get("role") not in MASK_ROLES:
            raise AnnotationError(f"{where}: 'role' must be one of {MASK_ROLES}")
        if m.get("part") not in by_name:
            raise AnnotationError(f"{where}: 'part' must name the part it belongs to")
        _check_polygons(m.get("polygons"), where)
        if m.get("clip", "none") not in CLIP_VALUES:
            raise AnnotationError(f"{where}: 'clip' must be one of {CLIP_VALUES}")
    return ann


def load(path):
    """Read and validate an annotation file. Returns the dict (with '_path' set)."""
    path = Path(path)
    try:
        ann = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise AnnotationError(f"{path}: not valid JSON: {e}") from e
    try:
        validate(ann)
    except AnnotationError as e:
        raise AnnotationError(f"{path.name}: {e}") from None
    ann["_path"] = str(path)
    return ann


def load_dir(ann_dir=ANN_DIR):
    """All annotation files in a directory, keyed by image_id (files named tasks_*.json are skipped)."""
    out = {}
    for f in sorted(Path(ann_dir).glob("*.json")):
        if f.name.startswith("tasks_") or f.name == "parts.json":
            continue
        a = load(f)
        if a["image_id"] in out:
            raise AnnotationError(f"{f.name}: image_id {a['image_id']!r} is used twice")
        out[a["image_id"]] = a
    return out


# --------------------------------------------------------------------------------------------
# geometry


def fill(polygons, shape):
    """Boolean mask (H, W) of pixels whose centre lies inside any polygon (even-odd per polygon)."""
    H, W = shape
    out = np.zeros(shape, bool)
    for poly in polygons:
        P = np.asarray(poly, float)
        x0, y0 = P[:, 0], P[:, 1]
        x1, y1 = np.roll(x0, -1), np.roll(y0, -1)
        rows, cols = [], []
        for a, b, c, d in zip(x0, y0, x1, y1):
            if b == d:
                continue
            lo, hi = (b, d) if b < d else (d, b)
            ys = np.arange(max(0, int(np.ceil(lo))), min(H, int(np.ceil(hi))))  # lo <= y < hi
            if not len(ys):
                continue
            xs = a + (ys - b) * (c - a) / (d - b)
            rows.append(ys)
            cols.append(np.clip(np.ceil(xs), 0, W).astype(int))  # pixels x >= crossing toggle
        if not rows:
            continue
        acc = np.zeros((H, W + 1), np.int32)
        np.add.at(acc, (np.concatenate(rows), np.concatenate(cols)), 1)
        out |= (np.cumsum(acc[:, :W], axis=1) % 2).astype(bool)
    return out


# turn priority for tracing: right, straight, left (in y-down screen coordinates)
_DIRS = [(1, 0), (0, 1), (-1, 0), (0, -1)]  # right, down, left, up; index+1 = turn right


def trace(mask):
    """Exact polygon outlines of a boolean mask (outer boundaries of 4-connected components).

    Vertices lie on pixel corners (half-integer coordinates), so fill(trace(m)) == m for any
    mask without holes. Raises ValueError if the mask has holes (they cannot be expressed as a
    union of polygons); fill them or describe them with `exclude`.
    """
    m = np.pad(np.asarray(mask, bool), 1)
    # corner coordinates: pixel (x, y) of the padded array covers corners (x, y)..(x+1, y+1)
    out_edges = {}

    def add(sx, sy, d):
        out_edges.setdefault((sx, sy), []).append(d)

    ys, xs = np.nonzero(m[1:-1, 1:-1])
    xs, ys = xs + 1, ys + 1
    for x, y in zip(xs.tolist(), ys.tolist()):
        if not m[y - 1, x]:
            add(x, y, 0)          # top edge, going right
        if not m[y, x + 1]:
            add(x + 1, y, 1)      # right edge, going down
        if not m[y + 1, x]:
            add(x + 1, y + 1, 2)  # bottom edge, going left
        if not m[y, x - 1]:
            add(x, y + 1, 3)      # left edge, going up
    edges = {(v, d) for v, ds in out_edges.items() for d in ds}
    unused = set(edges)
    loops = []
    while unused:
        e0 = min(unused, key=lambda e: (e[0][1], e[0][0], e[1]))
        v, d = e0
        pts = []
        while True:
            unused.discard((v, d))
            w = (v[0] + _DIRS[d][0], v[1] + _DIRS[d][1])
            for t in (1, 0, 3):  # right turn, straight, left turn
                nd = (d + t) % 4
                if (w, nd) in edges:
                    break
            else:
                raise RuntimeError("trace: dead end")  # cannot happen for a valid edge set
            if nd != d:
                pts.append(w)
            v, d = w, nd
            if (v, d) == e0:
                break
        # orientation: outer boundaries run clockwise on screen (positive shoelace in y-down)
        P = np.array(pts, float)
        area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
        if area < 0:
            raise ValueError("trace: mask has a hole; fill it or describe it with 'exclude'")
        loops.append([[px - 1.5, py - 1.5] for px, py in pts])  # unpad, corner -> centre coords
    loops.sort(key=lambda L: (min(p[1] for p in L), min(p[0] for p in L)))
    return loops


def dilate(m, px):
    return ndimage.binary_dilation(m, iterations=px) if px > 0 else m.copy()


# --------------------------------------------------------------------------------------------
# masks


def image_path(ann):
    return ROOT / ann["image"]["path"]


def foreground(ann):
    """Foreground mask: the file named by 'foreground', else non-white pixels of the image."""
    shape = (ann["image"]["height"], ann["image"]["width"])
    if ann.get("foreground"):
        fg = np.array(Image.open(ROOT / ann["foreground"]).convert("L")) > 127
    else:
        rgb = np.array(Image.open(image_path(ann)).convert("RGB"))
        fg = rgb.min(2) < 245
    if fg.shape != shape:
        raise AnnotationError(f"{ann['image_id']}: foreground is {fg.shape[::-1]}, image is {shape[::-1]}")
    return fg


def masks(ann, fg=None):
    """{name: bool mask} for every part and every extra mask (keep/skull) of one annotation."""
    shape = (ann["image"]["height"], ann["image"]["width"])
    if fg is None:
        fg = foreground(ann)
    default_outline = ann.get("outline_px", DEFAULT_OUTLINE_PX)
    default_margin = ann.get("exclude_margin", DEFAULT_EXCLUDE_MARGIN)
    by_name = {p["name"]: p for p in ann["parts"]}
    raw = {n: fill(p["polygons"], shape) for n, p in by_name.items()}
    out = {}
    for n, p in by_name.items():
        region = raw[n].copy()
        if p.get("holes"):
            region &= ~fill(p["holes"], shape)
        if p.get("clip", "foreground") == "foreground":
            region &= fg
        margin = p.get("exclude_margin", default_margin)
        E = np.zeros(shape, bool)
        for e in p.get("exclude", []):
            E |= dilate(raw[e], margin)
        region &= ~E
        outline = p.get("outline_px", default_outline)
        out[n] = (dilate(region, outline) & fg & ~E) if outline > 0 else region
    for m in ann.get("masks", []):
        r = fill(m["polygons"], shape)
        if m.get("clip", "none") == "foreground":
            r &= fg
        out[m["name"]] = r
    return out


def pivots(ann):
    return {p["name"]: (tuple(p["pivot"]) if p["pivot"] is not None else None) for p in ann["parts"]}


def keep_mask_name(ann, part):
    """Name of the keep (skull) mask attached to `part`, or None."""
    for m in ann.get("masks", []):
        if m["role"] == "keep" and m["part"] == part:
            return m["name"]
    return None


@lru_cache(maxsize=None)
def _library(ann_dir):
    anns = load_dir(ann_dir)
    lib = {}
    for img_id, ann in anns.items():
        ms = masks(ann)
        pv = pivots(ann)
        order = []  # each part followed by the keep masks attached to it
        for p in ann["parts"]:
            order += [p["name"]] + [m["name"] for m in ann.get("masks", []) if m["part"] == p["name"]]
        for name in order:
            mk = ms[name]
            if name in lib:
                raise AnnotationError(f"part/mask name {name!r} is used in two images")
            lib[name] = dict(image=img_id, mask=mk, pivot=pv.get(name))
    return anns, lib


def library(ann_dir=ANN_DIR):
    """(annotations by image_id, {part_or_mask_name: {image, mask, pivot}}) for a directory."""
    return _library(str(Path(ann_dir).resolve()))


# --------------------------------------------------------------------------------------------
# task generation


def generate_tasks(task_file=None, out_dir=None, ann_dir=ANN_DIR):
    """Write tasks/<ID>/ for every task in `task_file` (see src/tasks.py for the writer)."""
    sys.path.insert(0, str(ROOT / "src"))
    import tasks as T

    return T.build(out=out_dir, task_file=task_file, ann_dir=ann_dir)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="validate annotation files and print part areas")
    v.add_argument("files", nargs="+")
    t = sub.add_parser("tasks", help="generate task directories")
    t.add_argument("--tasks", default=None, help="task definition file (default annotations/tasks_pilot.json)")
    t.add_argument("--out", default=None, help="output directory (default tasks/)")
    a = ap.parse_args(argv)
    if a.cmd == "validate":
        bad = 0
        for f in a.files:
            if Path(f).name.startswith("tasks_") or Path(f).name == "parts.json":
                continue
            try:
                ann = load(f)
                ms = masks(ann)
                print(f"OK  {f}: " + ", ".join(f"{k}={int(v.sum())}px" for k, v in ms.items()))
            except (AnnotationError, OSError) as e:
                bad += 1
                print(f"ERR {e}")
        return 1 if bad else 0
    idx = generate_tasks(a.tasks, a.out)
    for s in idx:
        print(s["id"], s["kind"], s["graders"], s["pivots"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
