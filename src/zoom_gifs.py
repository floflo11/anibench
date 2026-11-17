"""Full-resolution zoomed GIFs of the region that should move, for slides and the README."""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from render import Renderer, prepare

def zbox(task, aspect=16 / 9, pad=40):
    a = np.array(Image.open(ROOT / "tasks" / task / "allowed.png")) > 127
    return zbox_mask(a, aspect, pad)

def zbox_mask(a, aspect=16 / 9, pad=40):
    """Box (x0, y0, x1, y1) of the given aspect around the True pixels of mask `a`, padded, inside the image."""
    W, H = a.shape[1], a.shape[0]
    ys, xs = np.nonzero(a)
    x0, y0, x1, y1 = xs.min() - pad, ys.min() - pad, xs.max() + pad, ys.max() + pad
    cx, cy, w, h = (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0, y1 - y0
    if w / h < aspect: w = h * aspect
    else: h = w / aspect
    w, h = min(w, W), min(h, H)
    x0 = int(min(max(0, cx - w / 2), W - w)); y0 = int(min(max(0, cy - h / 2), H - h))
    return (x0, y0, int(x0 + w), int(y0 + h))

def main(runs):
    R = Renderer()
    out = ROOT / "results/zoom"; out.mkdir(exist_ok=True)
    for run in runs:
        model, task, k = run.split("/")
        d = ROOT / "runs" / model / task / k
        stage = "repair" if (d / "page_repair").exists() else "first"
        spec = json.loads((ROOT / "tasks" / task / "spec.json").read_text())
        page = d / f"page_{stage}"
        prepare(page, ROOT / "tasks" / task)
        fr, err, _ = R.render(page, spec["width"], spec["height"])
        box = zbox(task)
        ims = [Image.fromarray(f).crop(box).resize((960, 540), Image.LANCZOS) for f in fr[:-1]]
        p = out / f"{model}_{task}_{k}.gif"
        ims[0].save(p, save_all=True, append_images=ims[1:], duration=int(2000 / len(ims)), loop=0, optimize=True)
        print(p, box)
    R.close()

if __name__ == "__main__":
    main(sys.argv[1:])
