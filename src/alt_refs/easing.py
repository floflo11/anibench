"""Easing style: the part is a THREE.Sprite cut to its bounding box, anchored on the joint with
sprite.center and turned with material.rotation. Varies the motion curve (sine, ease-in-out cubic,
bounce settle) and the amplitude (low / typical / high end of the plausible range).

Also used by the pivot style: the same page with the anchor moved to a different, reasonable reading of
the joint (pivot_shift='inward' along the part, or 'lateral' across it).
"""
import numpy as np

from .common import base_image, js, rgba, save_png

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff}</style></head>
<body><script type="module">
import * as THREE from './vendor/three.module.js';
const C = __CFG__;
const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(C.W, C.H);
renderer.toneMapping = THREE.NoToneMapping;
renderer.setClearColor(0xffffff, 1);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
// y up, origin at the image's bottom-left: image (x, y) -> world (x, H - y)
const camera = new THREE.OrthographicCamera(0, C.W, C.H, 0, -100, 100);

function loadTex(src) {
  return new THREE.TextureLoader().loadAsync(src).then(t => {
    t.colorSpace = THREE.SRGBColorSpace;
    t.magFilter = THREE.NearestFilter; t.minFilter = THREE.NearestFilter; t.generateMipmaps = false;
    return t;
  });
}
const easeInOutCubic = x => x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;
const easeOutCubic = x => 1 - Math.pow(1 - x, 3);
// swings: signed, 0 at rest (u = 0 and u = 1)
const SWING = {
  sine: u => Math.sin(2 * Math.PI * u),
  cubic: u => { const q = u * 4, i = Math.min(3, Math.floor(q)), e = easeInOutCubic(q - i);
                return [e, 1 - e, -e, -(1 - e)][i]; },
  bounce: u => { if (u < 0.2) return easeOutCubic(u / 0.2);
                 const v = (u - 0.2) / 0.8; return (1 - v) * Math.exp(-2.5 * v) * Math.cos(3 * Math.PI * v); },
};
// one-sided pulses for lifts and squashes: 0 at rest, peak 1
const PULSE = {
  sine: u => 0.5 - 0.5 * Math.cos(2 * Math.PI * u),
  cubic: u => u < 0.5 ? easeInOutCubic(2 * u) : easeInOutCubic(2 - 2 * u),
  bounce: u => { if (u < 0.55) { const a = u / 0.55; return 4 * a * (1 - a); }
                 if (u < 0.75) { const a = (u - 0.55) / 0.2; return 0.18 * 4 * a * (1 - a); }
                 return 0; },
};

(async () => {
  const bg = new THREE.Mesh(new THREE.PlaneGeometry(C.W, C.H),
                            new THREE.MeshBasicMaterial({ map: await loadTex(C.base) }));
  bg.position.set(C.W / 2, C.H / 2, 0);
  scene.add(bg);
  const sprites = [];
  for (const [i, P] of C.parts.entries()) {
    const mat = new THREE.SpriteMaterial({ map: await loadTex(P.src), transparent: true, depthTest: false });
    const s = new THREE.Sprite(mat);
    s.center.set((P.ax - P.x0) / P.w, (P.y0 + P.h - P.ay) / P.h);   // anchor (joint) in sprite UV
    s.position.set(P.ax, C.H - P.ay, 1 + i);
    s.scale.set(P.w, P.h, 1);
    s.renderOrder = 1 + i;
    scene.add(s);
    sprites.push({ s, P });
  }
  window.setTime = (t) => {
    const u = ((t / 2) % 1 + 1) % 1;
    for (const { s, P } of sprites) {
      s.material.rotation = 0; s.position.y = C.H - P.ay; s.scale.set(P.w, P.h, 1);
      if (P.mode === 'rot') s.material.rotation = P.amp * Math.PI / 180 * SWING[C.curve](u);
      else if (P.mode === 'lift') s.position.y += P.amp * PULSE[C.curve](u);
      else s.scale.y = P.h * (1 - P.amp * PULSE[C.curve](u));
    }
    renderer.render(scene, camera);
  };
  window.setTime(0);
  window.ANIM_READY = true;
})();
</script></body></html>
"""


def shifted_pivot(part, how):
    d = float(np.clip(0.08 * part.length, 4, 10))
    ax, ay = part.axis
    dx, dy = (ax, ay) if how == "inward" else (-ay, ax)
    return (round(part.pivot[0] + d * dx), round(part.pivot[1] + d * dy))


def build(info, out, curve, level, pivot_shift=None):
    save_png(base_image(info, "white"), out / "base.png")
    parts = []
    for i, p in enumerate(info["parts"]):
        x0, y0, x1, y1 = p.bbox
        rgba(info["img"], p.mask, p.bbox).save(out / f"sprite{i}.png")
        ax, ay = p.pivot if pivot_shift is None else shifted_pivot(p, pivot_shift)
        parts.append(dict(src=f"./sprite{i}.png", x0=x0, y0=y0, w=x1 - x0, h=y1 - y0, ax=float(ax), ay=float(ay),
                          mode=p.mode, amp=round(p.amount(level), 4)))
    cfg = dict(W=info["W"], H=info["H"], base="./base.png", curve=curve, parts=parts)
    (out / "index.html").write_text(PAGE.replace("__CFG__", js(cfg)))
