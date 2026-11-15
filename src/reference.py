"""Reference animator + broken copies, used to prove the graders work.

For each scored task, writes validation/<task>/<variant>/ with layer PNGs and an index.html
that animates them with three.js following the same output contract the models get.

Variants: ref, whole, missed_thumb, hole, frozen, center_pivot, no_loop, wrong_part
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from tasks import HAT_PIVOT_T14, PARTS, load_part  # noqa: E402

VARIANTS = ["ref", "whole", "missed_thumb", "hole", "frozen", "center_pivot", "no_loop", "wrong_part"]
DECOY = {"lineup": "A3_hand", "toddlers": "B2_arm"}
DECOY_ALT = {"lineup": "A1_hand", "toddlers": "B1_hand"}

PAGE = """<!doctype html><html><head><style>body{margin:0;background:#fff}canvas{display:block}</style></head><body>
<script type="module">
import * as THREE from './vendor/three.module.js';
const CFG = %(cfg)s;
const W = CFG.W, H = CFG.H;
const r = new THREE.WebGLRenderer({antialias:false, preserveDrawingBuffer:true});
r.setPixelRatio(1); r.setSize(W, H); r.setClearColor(0xffffff, 1); r.toneMapping = THREE.NoToneMapping;
document.body.appendChild(r.domElement);
const scene = new THREE.Scene();
const cam = new THREE.OrthographicCamera(0, W, 0, -H, -10, 10);
const root = new THREE.Group(); scene.add(root);
const loader = new THREE.TextureLoader();
function tex(url){ return new Promise(res => loader.load(url, t => { t.colorSpace = THREE.SRGBColorSpace; t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; res(t); })); }
function layer(t, z){ const m = new THREE.Mesh(new THREE.PlaneGeometry(W, H), new THREE.MeshBasicMaterial({map:t, transparent:true})); m.position.set(W/2, -H/2, z); return m; }
const movers = [];
(async () => {
  root.add(layer(await tex(CFG.base), 0));
  for (const [i, L] of CFG.layers.entries()) {
    const pivot = new THREE.Group(); pivot.position.set(L.px, -L.py, 0);
    const m = layer(await tex(L.url), 0.01 * (i + 1)); m.position.x -= L.px; m.position.y += L.py;
    pivot.add(m); root.add(pivot); movers.push({g: pivot, mesh: m, L});
  }
  window.setTime = (t) => {
    const ph = CFG.noLoop ? t / 2 : Math.sin(2 * Math.PI * t / 2);
    const ph2 = CFG.noLoop ? t / 2 : 0.5 - 0.5 * Math.cos(2 * Math.PI * t / 2);
    root.rotation.z = 0; root.position.set(0, 0, 0);
    for (const {g, mesh, L} of movers) {
      g.rotation.z = 0; g.scale.set(1, 1, 1); g.position.set(L.px, -L.py, 0); mesh.visible = true;
      if (CFG.frozen) continue;
      if (L.kind === 'rotate') g.rotation.z = -L.amp * Math.PI / 180 * ph;
      else if (L.kind === 'lift') g.position.y += L.amp * ph2;
      else if (L.kind === 'squash') g.scale.y = 1 - L.amp * ph2;
      if (CFG.hole && ph > 0.3) mesh.visible = false;
    }
    if (CFG.whole) { root.rotation.z = 0.02 * ph; }
    r.render(scene, cam);
  };
  window.setTime(0); window.ANIM_READY = true;
})();
</script></body></html>
"""


def rgba_layer(img, mask):
    a = np.zeros((*mask.shape, 4), np.uint8)
    a[..., :3] = img
    a[..., 3] = mask * 255
    return Image.fromarray(a)


def tip_disc(mask, pivot, r=9):
    ys, xs = np.nonzero(mask)
    d = (xs - pivot[0]) ** 2 + (ys - pivot[1]) ** 2
    i = np.argmax(d)
    yy, xx = np.ogrid[:mask.shape[0], :mask.shape[1]]
    return (xx - xs[i]) ** 2 + (yy - ys[i]) ** 2 <= r * r


def build_variant(spec, variant, out):
    out.mkdir(parents=True, exist_ok=True)
    tdir = ROOT / "tasks" / spec["id"]
    img = np.array(Image.open(tdir / "image.png").convert("RGB"))
    base = img.copy()
    W, H = spec["width"], spec["height"]
    kind = spec["kind"]
    parts = list(spec["parts"])
    if variant == "wrong_part":
        decoy = DECOY[spec["image"]]
        parts = [decoy if decoy not in parts else DECOY_ALT[spec["image"]]]
        kind = "rotate"
    layers = []
    for i, pid in enumerate(parts):
        m = load_part(pid)
        piv = PARTS[pid]["pivot"]
        if kind == "rotate_hat":
            piv = HAT_PIVOT_T14
        if piv is None:  # body: pivot at the feet centre
            ys, xs = np.nonzero(m)
            piv = (int(xs.mean()), int(ys.max()))
        sprite_mask = m.copy()
        if variant == "missed_thumb":
            sprite_mask &= ~tip_disc(m, piv)
        erase = sprite_mask
        if kind == "rotate_hat" or kind == "translate_up":
            # fill the uncovered skull with a sampled hair colour
            skull = load_part(pid.replace("_hat", "_skull"))
            hair = np.array([40, 30, 25])
            base[erase] = 255
            base[skull] = hair
        else:
            base[erase] = 255
        if variant == "center_pivot":
            ys, xs = np.nonzero(m)
            piv = (int(xs.mean()), int(ys.mean()))
        rgba_layer(img, sprite_mask).save(out / f"layer{i}.png")
        amp = spec["amp"]
        if kind in ("rotate", "rotate_hat", "flutter"):
            L = dict(kind="rotate", amp=amp if kind != "flutter" else 6)
        elif kind == "translate_up":
            L = dict(kind="lift", amp=amp)
        elif kind == "jump":
            L = dict(kind="lift", amp=amp)
        else:  # body squat/bounce
            L = dict(kind="squash", amp=0.12)
        L.update(url=f"./layer{i}.png", px=int(piv[0]), py=int(piv[1]))
        layers.append(L)
    if variant in ("frozen", "whole"):
        base = img.copy()
        layers = [] if variant == "frozen" else layers
        if variant == "whole":
            layers = []
    Image.fromarray(base).save(out / "base.png")
    cfg = dict(W=W, H=H, base="./base.png", layers=layers, whole=variant == "whole",
               frozen=variant == "frozen", hole=variant == "hole", noLoop=variant == "no_loop")
    (out / "index.html").write_text(PAGE % {"cfg": json.dumps(cfg)})


def build_all():
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    for spec in idx:
        if not spec["graders"]:
            continue
        for v in VARIANTS:
            build_variant(spec, v, ROOT / "validation" / spec["id"] / v)


if __name__ == "__main__":
    build_all()
