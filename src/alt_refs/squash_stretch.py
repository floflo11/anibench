"""Squash-and-stretch style: the part is a hand-built BufferGeometry quad in joint-local coordinates whose
world matrix is composed by hand each frame (matrixAutoUpdate = false):

    M = T(joint) * R(swing) * R(axis) * S(along, across) * R(-axis)

so the part stretches along its own axis while moving and stays pinned at the joint. Swings stretch on the
way out and squash on the way back; lifts and jumps anticipate (crouch), stretch in flight and squash on
landing; squats and bounces widen as they compress. k is the peak deformation (0.08 mild, 0.15 strong).
Textures use linear filtering and the uncovered area gets a nearest-colour fill.
"""
from .common import base_image, js, rgba, save_png

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>html,body{margin:0;background:#fff;overflow:hidden}</style></head>
<body><script type="module">
import * as THREE from './vendor/three.module.js';
const cfg = __CFG__;
const gl = new THREE.WebGLRenderer({ preserveDrawingBuffer: true, antialias: false, alpha: false });
gl.setPixelRatio(1); gl.setSize(cfg.W, cfg.H); gl.toneMapping = THREE.NoToneMapping;
gl.setClearColor(0xffffff);
document.body.appendChild(gl.domElement);
const scene = new THREE.Scene();
const cam = new THREE.OrthographicCamera(-cfg.W / 2, cfg.W / 2, cfg.H / 2, -cfg.H / 2, 0.1, 10);
cam.position.z = 5;
// image px -> world (centred, y up)
const wx = x => x - cfg.W / 2, wy = y => cfg.H / 2 - y;

function quad(x0, y0, x1, y1, jx, jy) {
  // corners relative to the joint, in world orientation
  const g = new THREE.BufferGeometry();
  const L = x0 - jx, R = x1 - jx, T = jy - y0, B = jy - y1;
  g.setAttribute('position', new THREE.Float32BufferAttribute([L, B, 0, R, B, 0, R, T, 0, L, T, 0], 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute([0, 0, 1, 0, 1, 1, 0, 1], 2));
  g.setIndex([0, 1, 2, 0, 2, 3]);
  return g;
}
const texLoader = new THREE.TextureLoader();
const load = src => new Promise((ok, bad) => texLoader.load(src, t => {
  t.colorSpace = THREE.SRGBColorSpace; t.generateMipmaps = false;
  t.minFilter = THREE.LinearFilter; t.magFilter = THREE.LinearFilter; ok(t); }, undefined, bad));

// motion profiles, u in [0, 1)
function swing(u, k) {               // angle factor and stretch along the axis
  const a = Math.sin(2 * Math.PI * u);
  return [a, 1 + k * Math.sin(4 * Math.PI * u)];   // out: stretch, back: squash
}
function hop(u, k, crouch) {         // height factor and vertical stretch
  if (crouch && u < 0.15) return [0, 1 - k * Math.sin(Math.PI * u / 0.15)];
  const a = crouch ? 0.15 : 0.0, b = 0.85;
  if (u < b && u >= a) { const q = (u - a) / (b - a); return [4 * q * (1 - q), 1 + k * Math.pow(Math.sin(2 * Math.PI * q), 2)]; }
  return [0, 1 - k * Math.sin(Math.PI * (u - b) / (1 - b))];
}

const M = new THREE.Matrix4(), tmp = new THREE.Matrix4();
function compose(m, jx, jy, ang, axisAng, sAlong, sAcross, dy, z) {
  m.makeTranslation(wx(jx), wy(jy) + dy, z);
  m.multiply(tmp.makeRotationZ(ang));
  m.multiply(tmp.makeRotationZ(axisAng));
  m.multiply(tmp.makeScale(sAlong, sAcross, 1));
  m.multiply(tmp.makeRotationZ(-axisAng));
  return m;
}

(async () => {
  const back = new THREE.Mesh(new THREE.PlaneGeometry(cfg.W, cfg.H), new THREE.MeshBasicMaterial({ map: await load(cfg.base) }));
  scene.add(back);
  const items = [];
  for (const [i, p] of cfg.parts.entries()) {
    const mesh = new THREE.Mesh(quad(p.x0, p.y0, p.x1, p.y1, p.jx, p.jy),
      new THREE.MeshBasicMaterial({ map: await load(p.tex), transparent: true, depthWrite: false }));
    mesh.matrixAutoUpdate = false;
    mesh.renderOrder = i + 1;
    scene.add(mesh);
    items.push({ mesh, p });
  }
  window.setTime = function (t) {
    const u = ((t % 2) + 2) % 2 / 2;
    for (const { mesh, p } of items) {
      let ang = 0, dy = 0, along = 1, across = 1, axisAng = p.axisAng;
      if (p.mode === 'rot') {
        const [a, s] = swing(u, cfg.k);
        ang = -a * p.amp * Math.PI / 180; along = s; across = 1 / s;
      } else if (p.mode === 'lift') {
        const [h, s] = hop(u, cfg.k, p.crouch);
        dy = h * p.amp; axisAng = Math.PI / 2; along = s; across = 1 / s;
      } else {                     // squat / bounce, anchored at the feet
        const c = p.amp * (0.5 - 0.5 * Math.cos(2 * Math.PI * u));
        axisAng = Math.PI / 2; along = 1 - c; across = 1 + (1 / (1 - c) - 1) * Math.min(1, cfg.k / 0.15);
      }
      compose(mesh.matrix, p.jx, p.jy, ang, axisAng, along, across, dy, p.z);
      mesh.matrixWorldNeedsUpdate = true;
    }
    gl.render(scene, cam);
  };
  window.setTime(0);
  window.ANIM_READY = true;
})();
</script></body></html>
"""


def build(info, out, k):
    import math
    save_png(base_image(info, "nearest"), out / "base.png")
    parts = []
    for i, p in enumerate(info["parts"]):
        x0, y0, x1, y1 = p.bbox
        rgba(info["img"], p.mask, p.bbox).save(out / f"part_{i}.png")
        parts.append(dict(tex=f"./part_{i}.png", x0=x0, y0=y0, x1=x1, y1=y1, jx=p.pivot[0], jy=p.pivot[1],
                          mode=p.mode, amp=round(p.amount("typ"), 4), crouch=p.action == "jump",
                          axisAng=math.atan2(-p.axis[1], p.axis[0]), z=0.01 * (i + 1)))
    cfg = dict(W=info["W"], H=info["H"], base="./base.png", k=k, parts=parts)
    (out / "index.html").write_text(PAGE.replace("__CFG__", js(cfg)))
