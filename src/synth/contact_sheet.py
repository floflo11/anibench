"""Contact sheet of synthetic task images: the target character of each task, labelled.

Usage: python src/synth/contact_sheet.py [tasks_dir] [n] [out_png]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def target_crop(td, spec, pad=24):
    im = Image.open(td / "image.png").convert("RGB")
    n = spec["factors"]["n_chars"]
    tgt = np.array(Image.open(td / "target.png")) > 127
    xs = np.nonzero(tgt.any(0))[0]
    w = spec["width"] / n
    i = int(xs.mean() // w) if len(xs) else 0
    slot = np.array(im)[:, int(i * w):int((i + 1) * w)]
    fg = (255 - slot.astype(int)).max(-1) > 10
    ys, xs = np.nonzero(fg)
    y0, y1 = max(ys.min() - pad, 0), min(ys.max() + pad, slot.shape[0])
    x0, x1 = max(xs.min() - pad, 0), min(xs.max() + pad, slot.shape[1])
    return Image.fromarray(slot[y0:y1, x0:x1])


def main(tasks_dir=ROOT / "tasks_synth", n=30, out=ROOT / "results/synth_contact.png", cols=6, cell=300):
    tasks_dir = Path(tasks_dir)
    ids = sorted(p.name for p in tasks_dir.iterdir() if (p / "spec.json").exists())
    # spread the picks over the whole set (all motions and styles appear)
    pick = [ids[int(round(k))] for k in np.linspace(0, len(ids) - 1, min(n, len(ids)))]
    rows = (len(pick) + cols - 1) // cols
    lab = 34
    sheet = Image.new("RGB", (cols * cell, rows * (cell + lab)), "white")
    d = ImageDraw.Draw(sheet)
    for k, tid in enumerate(pick):
        td = tasks_dir / tid
        spec = json.loads((td / "spec.json").read_text())
        im = target_crop(td, spec)
        im.thumbnail((cell - 12, cell - 12), Image.LANCZOS)
        x, y = (k % cols) * cell, (k // cols) * (cell + lab)
        sheet.paste(im, (x + (cell - im.width) // 2, y + (cell - im.height) // 2))
        f = spec["factors"]
        d.text((x + 8, y + cell), f"{tid} {f['motion']} | {f['style']}", fill=(40, 40, 40))
        d.text((x + 8, y + cell + 14), f"area {f['target_area_px']} occ {f['occlusion_pct']:.0f}% chain {f['chain_length']} "
                                       f"gap {f['min_dist_px']:.0f}", fill=(110, 110, 110))
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, optimize=True)
    return out


if __name__ == "__main__":
    a = sys.argv[1:]
    main(Path(a[0]) if a else ROOT / "tasks_synth", int(a[1]) if len(a) > 1 else 30,
         Path(a[2]) if len(a) > 2 else ROOT / "results/synth_contact.png")
