"""Legacy shim: part masks and pivots, now read from the schema-v1 annotation files.

The hand-coded definitions that used to live here were migrated to annotations/lineup.json and
annotations/toddlers.json by scripts/migrate_legacy_parts.py (which keeps the original code).
This module keeps the old interface: build() -> {(image, part_id): {mask, pivot}}, and
`python src/parts.py` rewrites annotations/parts/*.png and annotations/parts.json.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import annotations as A  # noqa: E402


def build(ann_dir=A.ANN_DIR):
    _, lib = A.library(ann_dir)
    return {(v["image"], pid): dict(mask=v["mask"].copy(), pivot=v["pivot"]) for pid, v in lib.items()}


def save(parts):
    out = ROOT / "annotations/parts"
    out.mkdir(parents=True, exist_ok=True)
    meta = {}
    for (img, pid), v in parts.items():
        Image.fromarray((v["mask"] * 255).astype("uint8")).save(out / f"{pid}.png")
        meta[pid] = dict(image=img, pivot=list(v["pivot"]) if v["pivot"] else None, area=int(v["mask"].sum()))
    (ROOT / "annotations/parts.json").write_text(json.dumps(meta, indent=1))
    return meta


def overlay(parts, out_dir="/tmp"):
    """Debug overlay of every movable part and pivot per image -> <out_dir>/overlay_<image>.png."""
    from PIL import ImageDraw

    anns, _ = A.library()
    cols = [(255, 0, 0), (0, 160, 0), (0, 0, 255), (255, 140, 0), (160, 0, 160), (0, 160, 160), (200, 200, 0)]
    for name, ann in anns.items():
        img = np.array(Image.open(A.image_path(ann)).convert("RGB")).astype(float)
        i = 0
        for (n, pid), v in parts.items():
            if n != name or v["pivot"] is None:
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
        im.save(f"{out_dir}/overlay_{name}.png")


if __name__ == "__main__":
    p = build()
    meta = save(p)
    overlay(p)
    for k, v in meta.items():
        print(k, v)
