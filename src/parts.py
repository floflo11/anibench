"""Part masks and pivots for the six characters, in working-size pixel coordinates.

Each part = rough region (bbox or polygon) intersected with the character foreground and,
where needed, a colour rule (skin / dark hair / red). Pivots are joint centres.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {
    "lineup": ROOT / "images/lineup_task.png",
    "toddlers": ROOT / "images/toddlers_task.png",
}


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
        # nearest labelled pixel
        ys, xs = np.nonzero(lab)
        i = np.argmin((xs - x) ** 2 + (ys - y) ** 2)
        v = lab[ys[i], xs[i]]
    return lab == v


def clean(m, close=2):
    m = ndimage.binary_closing(m, iterations=close)
    m = ndimage.binary_fill_holes(m)
    return m


def build():
    parts = {}  # (image, part_id) -> dict(mask=..., pivot=(x,y))
    for name in IMAGES:
        rgb, fg = load(name)
        S = fg.shape
        lab, n = ndimage.label(fg)
        P = {}

        def char_at(x, y):
            return component_at(fg, x, y)

        if name == "lineup":
            A1, A2, A3, A4 = char_at(150, 300), char_at(420, 350), char_at(730, 350), char_at(1000, 400)
            P["A1_body"] = dict(mask=A1, pivot=None)
            P["A2_body"] = dict(mask=A2, pivot=None)
            P["A3_body"] = dict(mask=A3, pivot=None)
            P["A4_body"] = dict(mask=A4, pivot=None)
            # A1 raised hand, wrist pivot
            m = A1 & box_mask(S, 190, 108, 275, 197) & skin(rgb)
            P["A1_hand"] = dict(mask=clean(component_at(m, 232, 160)), pivot=(232, 192))
            # A1 head (cut at neck line), neck pivot
            m = A1 & poly_mask(S, [(60, 0), (205, 0), (205, 112), (192, 150), (60, 150)])
            P["A1_head"] = dict(mask=clean(m), pivot=(145, 148))
            # A2 raised forearm + hand, elbow pivot (no dark hair)
            m = A2 & poly_mask(S, [(500, 148), (578, 148), (578, 275), (520, 275), (508, 245)]) & ~dark(rgb)
            P["A2_forearm"] = dict(mask=clean(component_at(m, 535, 200)), pivot=(538, 256))
            # A2 pigtails (dark hair), hair-tie pivots
            m = A2 & box_mask(S, 300, 100, 362, 248) & dark(rgb)
            P["A2_pigtailL"] = dict(mask=clean(component_at(m, 330, 170)), pivot=(352, 112))
            m = A2 & box_mask(S, 462, 100, 522, 242) & dark(rgb)
            P["A2_pigtailR"] = dict(mask=clean(component_at(m, 490, 170)), pivot=(480, 108))
            # A3 raised hand, wrist pivot
            m = A3 & box_mask(S, 748, 188, 828, 260) & skin(rgb)
            P["A3_hand"] = dict(mask=clean(component_at(m, 787, 225)), pivot=(781, 256))
            # A3 head, neck pivot
            m = A3 & poly_mask(S, [(620, 90), (752, 90), (752, 240), (620, 240)])
            P["A3_head"] = dict(mask=clean(m), pivot=(695, 246))
            # A4 raised forearm + hand (skin), elbow pivot
            m = A4 & box_mask(S, 1068, 150, 1148, 305) & skin(rgb)
            P["A4_forearm"] = dict(mask=clean(component_at(m, 1105, 210)), pivot=(1099, 296))
            # A4 earrings (red + hook), earlobe pivots
            m = A4 & box_mask(S, 953, 192, 982, 236) & (red(rgb) | (rgb.max(2) < 200))
            P["A4_earringL"] = dict(mask=clean(component_at(A4 & box_mask(S, 953, 192, 982, 236) & red(rgb), 967, 218), 1), pivot=(967, 197))
            P["A4_earringR"] = dict(mask=clean(component_at(A4 & box_mask(S, 1048, 180, 1077, 226) & red(rgb), 1062, 206), 1), pivot=(1062, 187))
            # A4 veil: lace left of the body
            m = A4 & poly_mask(S, [(835, 40), (930, 40), (950, 120), (935, 250), (925, 330), (940, 470), (835, 470)]) & ~skin(rgb) & ~dark(rgb)
            P["A4_veil"] = dict(mask=clean(m, 3), pivot=(925, 95))
        else:
            B1, B2 = char_at(300, 350), char_at(750, 350)
            P["B1_body"] = dict(mask=B1, pivot=None)
            P["B2_body"] = dict(mask=B2, pivot=None)
            # B1 raised hand (viewer's left), wrist pivot
            m = B1 & box_mask(S, 62, 112, 158, 206) & skin(rgb)
            P["B1_hand"] = dict(mask=clean(component_at(m, 110, 160)), pivot=(122, 198))
            # B1 hat
            hat = [(142, 150), (160, 105), (200, 62), (212, 22), (258, 2), (352, 2), (402, 28), (448, 48), (476, 80), (476, 170), (445, 200), (414, 186), (402, 130), (345, 92), (280, 90), (232, 105), (206, 160), (186, 204), (150, 196)]
            P["B1_hat"] = dict(mask=clean(B1 & poly_mask(S, hat)), pivot=(305, 175))
            P["B1_skull"] = dict(mask=ellipse_mask(S, 305, 140, 92, 62) & poly_mask(S, hat), pivot=None)
            # B2 whole raised arm, shoulder pivot
            arm = [(790, 222), (862, 196), (870, 112), (975, 112), (975, 215), (905, 255), (862, 305), (812, 305), (796, 262)]
            P["B2_arm"] = dict(mask=clean(B2 & poly_mask(S, arm)), pivot=(808, 262))
            # B2 head incl. hat, neck pivot
            m = B2 & poly_mask(S, [(540, 0), (850, 0), (850, 228), (540, 228)]) & ~poly_mask(S, arm)
            P["B2_head"] = dict(mask=clean(m), pivot=(690, 238))
            hat2 = [(553, 152), (558, 110), (588, 70), (612, 18), (660, 0), (742, 0), (790, 18), (818, 66), (842, 100), (838, 152), (802, 172), (790, 125), (760, 98), (690, 92), (630, 98), (600, 122), (592, 178), (565, 178)]
            P["B2_hat"] = dict(mask=clean(B2 & poly_mask(S, hat2)), pivot=(640, 140))
            P["B2_skull"] = dict(mask=ellipse_mask(S, 690, 128, 100, 62) & poly_mask(S, hat2), pivot=None)
        for k, v in P.items():
            if not (k.endswith("_body") or k.endswith("_skull")):
                # include the drawn outline around each part
                v["mask"] = ndimage.binary_dilation(v["mask"], iterations=3) & fg
            parts[(name, k)] = v
    return parts


def save(parts):
    out = ROOT / "annotations/parts"
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for (img, pid), v in parts.items():
        Image.fromarray((v["mask"] * 255).astype("uint8")).save(out / f"{pid}.png")
        meta[pid] = dict(image=img, pivot=v["pivot"], area=int(v["mask"].sum()))
    (ROOT / "annotations/parts.json").write_text(json.dumps(meta, indent=1))
    return meta


def overlay(parts):
    cols = [(255, 0, 0), (0, 160, 0), (0, 0, 255), (255, 140, 0), (160, 0, 160), (0, 160, 160), (200, 200, 0)]
    for name in IMAGES:
        rgb, _ = load(name)
        img = rgb.astype(float).copy()
        i = 0
        for (n, pid), v in parts.items():
            if n != name or pid.endswith("_body") or pid.endswith("_skull"):
                continue
            c = np.array(cols[i % len(cols)])
            img[v["mask"]] = img[v["mask"]] * 0.35 + c * 0.65
            i += 1
        im = Image.fromarray(img.clip(0, 255).astype("uint8"))
        d = ImageDraw.Draw(im)
        for (n, pid), v in parts.items():
            if n == name and v["pivot"]:
                x, y = v["pivot"]
                d.ellipse([x - 4, y - 4, x + 4, y + 4], outline=(0, 0, 0), width=2)
                d.text((x + 6, y - 6), pid, fill=(0, 0, 0))
        im.save(f"/tmp/overlay_{name}.png")


if __name__ == "__main__":
    p = build()
    meta = save(p)
    overlay(p)
    for k, v in meta.items():
        print(k, v)
