"""One-off migration: the hand-coded part definitions (formerly src/parts.py) -> annotations/*.json.

The legacy definitions below are kept verbatim from src/parts.py (git history: commit 86c8160)
so the migration can be re-run and audited. Each legacy part was a rough region intersected with
the foreground and colour rules (skin / dark hair / red), cleaned (closing + hole fill), then
grown by a 3 px outline. Colour rules cannot be expressed as polygons, so the migration traces
the *cleaned region* of each part into exact pixel-corner polygons; the schema-v1 pipeline then
re-applies the outline step. The script asserts that every resulting mask equals the legacy mask.

    python scripts/migrate_legacy_parts.py          # writes annotations/lineup.json, toddlers.json
    python scripts/migrate_legacy_parts.py --check  # only verify, write nothing
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402

IMAGES = {
    "lineup": ROOT / "images/lineup_task.png",
    "toddlers": ROOT / "images/toddlers_task.png",
}

META = {
    "lineup": dict(style="photo cutout on white", subject="four children standing in a row (A1-A4, left to right)",
                   source="pilot image prepared for anibench v1 (transparent source composited on white)",
                   license="unknown"),
    "toddlers": dict(style="photo cutout on white", subject="two toddlers in jackets and hats (B1 left, B2 right)",
                     source="pilot image prepared for anibench v1", license="unknown"),
}
DESCRIPTIONS = {
    "A1_body": "boy on the far left (whole character)",
    "A2_body": "girl with pigtails (whole character)",
    "A3_body": "small boy in the striped shirt (whole character)",
    "A4_body": "girl in the white dress, far right (whole character)",
    "A1_hand": "raised hand; pivot at the wrist",
    "A1_head": "head, cut at the neck line; pivot at the neck",
    "A2_forearm": "raised forearm and hand; pivot at the elbow",
    "A2_pigtailL": "left pigtail (viewer's left); pivot at the hair tie",
    "A2_pigtailR": "right pigtail (viewer's right); pivot at the hair tie",
    "A3_hand": "raised hand; pivot at the wrist",
    "A3_head": "head; pivot at the neck",
    "A4_forearm": "raised forearm and hand; pivot at the elbow",
    "A4_earringL": "red earring (viewer's left); pivot at the earlobe",
    "A4_earringR": "red earring (viewer's right); pivot at the earlobe",
    "A4_veil": "lace veil left of the body; pivot at the top of the veil",
    "B1_body": "toddler in the red jacket (whole character)",
    "B2_body": "toddler in the navy jacket (whole character)",
    "B1_hand": "raised hand (viewer's left); pivot at the wrist",
    "B1_hat": "hat",
    "B2_arm": "whole raised arm; pivot at the shoulder",
    "B2_head": "head including the hat; pivot at the neck",
    "B2_hat": "hat",
}
PARENTS = {
    "A1_hand": "A1_body", "A1_head": "A1_body", "A2_forearm": "A2_body", "A2_pigtailL": "A2_body",
    "A2_pigtailR": "A2_body", "A3_hand": "A3_body", "A3_head": "A3_body", "A4_forearm": "A4_body",
    "A4_earringL": "A4_body", "A4_earringR": "A4_body", "A4_veil": "A4_body", "B1_hand": "B1_body",
    "B1_hat": "B1_body", "B2_arm": "B2_body", "B2_head": "B2_body", "B2_hat": "B2_head",
}


# ---- legacy helpers (verbatim) ---------------------------------------------------------------
def load(name):
    rgb = np.array(Image.open(IMAGES[name]).convert("RGB")).astype(int)
    fg = np.array(Image.open(ROOT / f"annotations/{name}_fg.png")) > 127
    return rgb, fg


def poly_mask(shape, pts):
    im = Image.new("L", (shape[1], shape[0]), 0)
    ImageDraw.Draw(im).polygon([tuple(p) for p in pts], fill=255)
    return np.array(im) > 0


def box_mask(shape, x0, y0, x1, y1):
    m = np.zeros(shape, bool)
    m[y0:y1, x0:x1] = True
    return m


def ellipse_mask(shape, cx, cy, rx, ry):
    yy, xx = np.mgrid[0:shape[0], 0:shape[1]]
    return ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2 <= 1


def skin(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 140) & (r > g + 10) & (g > b - 5) & ((r - b) > 35) & (r < 256)


def dark(rgb):
    return rgb.max(2) < 95


def red(rgb):
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    return (r > 120) & (g < 100) & (b < 100) & (r - g > 60)


def component_at(mask, x, y):
    lab, _ = ndimage.label(mask)
    v = lab[y, x]
    if v == 0:
        ys, xs = np.nonzero(lab)
        i = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        v = lab[ys[i], xs[i]]
    return lab == v


def clean(m, close=2):
    m = ndimage.binary_closing(m, iterations=close)
    m = ndimage.binary_fill_holes(m)
    return m


def legacy_build():
    """The legacy src/parts.py build(), returning per part: final mask, pivot, pre-outline region."""
    parts = {}
    for name in IMAGES:
        rgb, fg = load(name)
        S = fg.shape
        P = {}

        def char_at(x, y):
            return component_at(fg, x, y)

        if name == "lineup":
            A1, A2, A3, A4 = char_at(150, 300), char_at(420, 350), char_at(730, 350), char_at(1000, 400)
            P["A1_body"] = dict(mask=A1, pivot=None)
            P["A2_body"] = dict(mask=A2, pivot=None)
            P["A3_body"] = dict(mask=A3, pivot=None)
            P["A4_body"] = dict(mask=A4, pivot=None)
            m = A1 & box_mask(S, 190, 108, 275, 197) & skin(rgb)
            P["A1_hand"] = dict(mask=clean(component_at(m, 232, 160)), pivot=(232, 192))
            m = A1 & poly_mask(S, [(60, 0), (205, 0), (205, 112), (192, 150), (60, 150)])
            P["A1_head"] = dict(mask=clean(m), pivot=(145, 148))
            m = A2 & poly_mask(S, [(500, 148), (578, 148), (578, 275), (520, 275), (508, 245)]) & ~dark(rgb)
            P["A2_forearm"] = dict(mask=clean(component_at(m, 535, 200)), pivot=(538, 256))
            m = A2 & box_mask(S, 300, 100, 362, 248) & dark(rgb)
            P["A2_pigtailL"] = dict(mask=clean(component_at(m, 330, 170)), pivot=(352, 112))
            m = A2 & box_mask(S, 462, 100, 522, 242) & dark(rgb)
            P["A2_pigtailR"] = dict(mask=clean(component_at(m, 490, 170)), pivot=(480, 108))
            m = A3 & box_mask(S, 748, 188, 828, 260) & skin(rgb)
            P["A3_hand"] = dict(mask=clean(component_at(m, 787, 225)), pivot=(781, 256))
            m = A3 & poly_mask(S, [(620, 90), (752, 90), (752, 240), (620, 240)])
            P["A3_head"] = dict(mask=clean(m), pivot=(695, 246))
            m = A4 & box_mask(S, 1068, 150, 1148, 305) & skin(rgb)
            P["A4_forearm"] = dict(mask=clean(component_at(m, 1105, 210)), pivot=(1099, 296))
            P["A4_earringL"] = dict(mask=clean(component_at(A4 & box_mask(S, 953, 192, 982, 236) & red(rgb), 967, 218), 1), pivot=(967, 197))
            P["A4_earringR"] = dict(mask=clean(component_at(A4 & box_mask(S, 1048, 180, 1077, 226) & red(rgb), 1062, 206), 1), pivot=(1062, 187))
            m = A4 & poly_mask(S, [(835, 40), (930, 40), (950, 120), (935, 250), (925, 330), (940, 470), (835, 470)]) & ~skin(rgb) & ~dark(rgb)
            P["A4_veil"] = dict(mask=clean(m, 3), pivot=(925, 95))
        else:
            B1, B2 = char_at(300, 350), char_at(750, 350)
            P["B1_body"] = dict(mask=B1, pivot=None)
            P["B2_body"] = dict(mask=B2, pivot=None)
            hat_b1 = [(142, 150), (160, 105), (200, 62), (212, 22), (258, 2), (352, 2), (402, 28), (448, 48), (476, 80), (476, 170), (445, 200), (414, 186), (402, 130), (345, 92), (280, 90), (232, 105), (206, 160), (186, 204), (150, 196)]
            m = B1 & box_mask(S, 62, 112, 152, 206) & skin(rgb) & ~ndimage.binary_dilation(poly_mask(S, hat_b1), iterations=6)
            P["B1_hand"] = dict(mask=clean(component_at(m, 110, 160)), pivot=(122, 198))
            hat = hat_b1
            P["B1_hat"] = dict(mask=clean(B1 & poly_mask(S, hat)), pivot=(305, 175), poly=poly_mask(S, hat))
            P["B1_skull"] = dict(mask=ellipse_mask(S, 305, 140, 92, 62) & poly_mask(S, hat), pivot=None)
            arm = [(790, 222), (862, 196), (870, 112), (975, 112), (975, 215), (905, 255), (862, 305), (812, 305), (796, 262)]
            P["B2_arm"] = dict(mask=clean(B2 & poly_mask(S, arm)), pivot=(808, 262))
            m = B2 & poly_mask(S, [(540, 0), (850, 0), (850, 228), (540, 228)]) & ~poly_mask(S, arm)
            P["B2_head"] = dict(mask=clean(m), pivot=(690, 238))
            hat2 = [(553, 152), (558, 110), (588, 70), (612, 18), (660, 0), (742, 0), (790, 18), (818, 66), (842, 100), (838, 152), (802, 172), (790, 125), (760, 98), (690, 92), (630, 98), (600, 122), (592, 178), (565, 178)]
            P["B2_hat"] = dict(mask=clean(B2 & poly_mask(S, hat2)), pivot=(640, 140))
            P["B2_skull"] = dict(mask=ellipse_mask(S, 690, 128, 100, 62) & poly_mask(S, hat2), pivot=None)
        for k, v in P.items():
            v["region"] = v["mask"]
            if not (k.endswith("_body") or k.endswith("_skull")):
                grow = ndimage.binary_dilation(v["mask"], iterations=3) & fg
                if k == "B1_hand":
                    grow &= ~ndimage.binary_dilation(poly_mask(S, hat_b1), iterations=4)
                v["mask"] = grow
            parts[(name, k)] = v
    return parts


# ---- migration -------------------------------------------------------------------------------
def migrate():
    legacy = legacy_build()
    out = {}
    for name in IMAGES:
        _, fg = load(name)
        H, W = fg.shape
        ann = dict(schema_version=1, image_id=name,
                   image=dict(path=f"images/{name}_task.png", width=W, height=H),
                   foreground=f"annotations/{name}_fg.png", outline_px=3, exclude_margin=4,
                   metadata=dict(META[name], annotator="migrated from src/parts.py by scripts/migrate_legacy_parts.py",
                                 notes="Polygons are exact pixel traces of the legacy colour-rule regions, "
                                       "so they have many vertices; new annotations should use a few clicks per part."),
                   parts=[], masks=[])
        for (img, pid), v in legacy.items():
            if img != name:
                continue
            if pid.endswith("_skull"):
                hat = pid.replace("_skull", "_hat")
                ann["masks"].append(dict(name=pid, role="keep", part=hat, clip="none",
                                         description=f"skull under {hat}; must stay filled when the hat moves",
                                         polygons=A.trace(v["region"])))
                continue
            part = dict(name=pid, description=DESCRIPTIONS[pid],
                        pivot=list(v["pivot"]) if v["pivot"] else None, parent=PARENTS.get(pid))
            if pid.endswith("_body"):
                # whole character = 4-connected foreground component: trace its outline with holes
                # filled, clip to the foreground, and cut out any other foreground islands in its holes
                filled = ndimage.binary_fill_holes(v["region"])
                islands = filled & fg & ~v["region"]
                part.update(clip="foreground", outline_px=0, polygons=A.trace(filled))
                if islands.any():
                    part["holes"] = A.trace(islands)
            elif "poly" in v:
                # drawn polygon only (B1 hat): raw polygon, clipped to the foreground; this is also
                # the region B1_hand excludes
                part.update(clip="foreground", polygons=A.trace(v["poly"]))
            else:
                part.update(clip="none", polygons=A.trace(v["region"]))
            if pid == "B1_hand":
                part["exclude"] = ["B1_hat"]
            out.setdefault(name, ann)["parts"].append(part)
        # verify exact reproduction
        ms = A.masks(A.validate(json.loads(json.dumps(ann))))
        for (img, pid), v in legacy.items():
            if img == name:
                diff = int((ms[pid] != v["mask"]).sum())
                assert diff == 0, f"{pid}: {diff} px differ from the legacy mask"
                assert A.pivots(ann).get(pid) == (tuple(v["pivot"]) if v["pivot"] else None) or pid.endswith("_skull")
        out[name] = ann
    return out


def dumps(ann):
    """JSON with one polygon per line (keeps files diffable without one line per coordinate)."""
    def fmt_poly(poly):
        return "[" + ", ".join(f"[{_n(x)}, {_n(y)}]" for x, y in poly) + "]"

    def fmt_polys(polys, ind):
        return "[\n" + ",\n".join(ind + "  " + fmt_poly(p) for p in polys) + "\n" + ind + "]"

    def fmt_obj(o, ind):
        items = []
        for k, v in o.items():
            if k in ("polygons", "holes"):
                s = fmt_polys(v, ind + "  ")
            elif isinstance(v, dict):
                s = json.dumps(v, indent=None)
            else:
                s = json.dumps(v)
            items.append(f'{ind}  "{k}": {s}')
        return "{\n" + ",\n".join(items) + "\n" + ind + "}"

    lines = []
    for k, v in ann.items():
        if k in ("parts", "masks"):
            s = "[\n" + ",\n".join("    " + fmt_obj(o, "    ") for o in v) + "\n  ]"
        elif k == "metadata":
            s = json.dumps(v, indent=4).replace("\n}", "\n  }")
        else:
            s = json.dumps(v)
        lines.append(f'  "{k}": {s}')
    return "{\n" + ",\n".join(lines) + "\n}\n"


def _n(v):
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    anns = migrate()
    for name, ann in anns.items():
        text = dumps(ann)
        assert json.loads(text) == ann
        path = ROOT / f"annotations/{name}.json"
        if a.check:
            print(name, "OK", "(file up to date)" if path.exists() and json.loads(path.read_text()) == ann else "(file differs)")
        else:
            path.write_text(text)
            print("wrote", path.relative_to(ROOT), len(ann["parts"]), "parts", len(ann["masks"]), "masks",
                  f"{len(text) // 1024} KB")


if __name__ == "__main__":
    main()
