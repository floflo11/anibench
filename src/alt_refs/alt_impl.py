"""Different implementation techniques.

canvas2d: one full-size 2D canvas used as a THREE.CanvasTexture and redrawn every frame. The part is cut out
  in the browser (image.png masked with destination-in compositing) and drawn with 2D-context transforms
  (bilinear smoothing on). The motion is keyframed: THREE.AnimationClip + NumberKeyframeTracks with smooth
  (cubic) interpolation, sampled with AnimationMixer.setTime. Nearest-colour fill.
shader: a single full-screen quad with a ShaderMaterial that inverse-maps every output pixel: for each part,
  p -> M^-1 p, and if the source pixel is inside the part's mask (one R-channel label texture) it shows the
  source colour, else the filled background. Textures are raw (no colour conversion), sampled at texel
  centres. Motion is a swing with a second harmonic ("wobble"), a smooth trapezoid lift, a parabolic jump and
  a cosine squat. White fill (sampled hair colour on the skull).
"""
import numpy as np
from PIL import Image

from .common import base_image, js, save_png

CANVAS_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>body{margin:0;background:#fff}canvas{display:block}</style></head>
<body><script type="module">
import * as THREE from './vendor/three.module.js';
const K = __CFG__;
const img = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = rej; i.src = src; });

const paint = document.createElement('canvas'); paint.width = K.W; paint.height = K.H;
const ctx = paint.getContext('2d');
ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';

const view = new THREE.WebGLRenderer({ preserveDrawingBuffer: true });
view.setPixelRatio(1); view.setSize(K.W, K.H); view.toneMapping = THREE.NoToneMapping;
document.body.appendChild(view.domElement);
const scene = new THREE.Scene();
const cam = new THREE.OrthographicCamera(-0.5, 0.5, 0.5, -0.5, 0, 1);
const tex = new THREE.CanvasTexture(paint);
tex.colorSpace = THREE.SRGBColorSpace; tex.minFilter = tex.magFilter = THREE.NearestFilter; tex.generateMipmaps = false;
scene.add(new THREE.Mesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: tex })));

// one rig object per part, keyframed: position.x = angle (deg), position.y = lift (px), scale.y = squash
function clipFor(P, name) {
  const A = P.amp, tr = [];
  if (P.mode === 'rot' && P.one) tr.push(new THREE.NumberKeyframeTrack(name + '.position[x]', [0, 0.5, 1.0, 1.5, 2], [0, -A, -0.9 * A, 0, 0]));  // canvas: - = up
  else if (P.mode === 'rot') tr.push(new THREE.NumberKeyframeTrack(name + '.position[x]', [0, 0.45, 1.0, 1.45, 2], [0, A, 0, -0.85 * A, 0]));
  else if (P.action === 'jump') tr.push(new THREE.NumberKeyframeTrack(name + '.position[y]', [0, 0.25, 0.5, 0.75, 1.0, 1.25, 2], [0, 0, 0.75 * A, A, 0.75 * A, 0, 0]));
  else if (P.mode === 'lift') tr.push(new THREE.NumberKeyframeTrack(name + '.position[y]', [0, 0.6, 1.1, 1.7, 2], [0, A, A, 0, 0]));
  else tr.push(new THREE.NumberKeyframeTrack(name + '.scale[y]', [0, 0.2, 0.7, 1.1, 1.6, 2], [1, 1, 1 - A, 1 - A, 1, 1]));
  tr.forEach(x => x.setInterpolation(THREE.InterpolateSmooth));
  return new THREE.AnimationClip('c_' + name, 2, tr);
}

(async () => {
  const [src, base] = await Promise.all([img(K.image), img(K.base)]);
  const rigRoot = new THREE.Object3D();
  const mixer = new THREE.AnimationMixer(rigRoot);
  const parts = [];
  for (const [i, P] of K.parts.entries()) {
    const m = await img(P.mask);
    const cut = document.createElement('canvas'); cut.width = K.W; cut.height = K.H;
    const c = cut.getContext('2d');
    c.drawImage(src, 0, 0);
    c.globalCompositeOperation = 'destination-in';
    c.drawImage(m, 0, 0);
    const rig = new THREE.Object3D(); rig.name = 'rig' + i; rigRoot.add(rig);
    const act = mixer.clipAction(clipFor(P, rig.name), rig);
    act.setLoop(THREE.LoopRepeat, Infinity); act.play();
    parts.push({ cut, rig, P });
  }
  window.setTime = (t) => {
    mixer.setTime(((t % 2) + 2) % 2);
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.drawImage(base, 0, 0);
    for (const { cut, rig, P } of parts) {
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      const ang = rig.position.x, lift = rig.position.y, sq = rig.scale.y;
      if (ang !== 0 || lift !== 0 || sq !== 1) {
        ctx.translate(P.px, P.py - lift);
        ctx.rotate(ang * Math.PI / 180);
        ctx.scale(1, sq);
        ctx.translate(-P.px, -P.py);
      }
      ctx.drawImage(cut, 0, 0);
    }
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    tex.needsUpdate = true;
    view.render(scene, cam);
  };
  window.setTime(0);
  window.ANIM_READY = true;
})();
</script></body></html>
"""

SHADER_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><style>body{margin:0;background:#fff}</style></head>
<body><script type="module">
import * as THREE from './vendor/three.module.js';
const Q = __CFG__;
const r = new THREE.WebGLRenderer({ preserveDrawingBuffer: true, antialias: false });
r.setPixelRatio(1); r.setSize(Q.W, Q.H); r.toneMapping = THREE.NoToneMapping;
document.body.appendChild(r.domElement);
const raw = (u) => new THREE.TextureLoader().loadAsync(u).then(t => {
  t.colorSpace = THREE.NoColorSpace; t.minFilter = t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; return t; });

const frag = `
precision highp float;
uniform sampler2D uBase, uImg, uLab; uniform vec2 uSize; uniform mat3 uInv[4]; uniform int uN;
vec2 uvOf(vec2 p) { return vec2(p.x / uSize.x, 1.0 - p.y / uSize.y); }
void main() {
  vec2 p = vec2(gl_FragCoord.x, uSize.y - gl_FragCoord.y);     // image coords of this pixel's centre
  vec4 col = texture2D(uBase, uvOf(p));
  for (int k = 0; k < 4; k++) {
    if (k >= uN) break;
    vec2 q = (uInv[k] * vec3(p, 1.0)).xy;
    if (q.x < 0.0 || q.y < 0.0 || q.x >= uSize.x || q.y >= uSize.y) continue;
    q = floor(q) + 0.5;                                         // nearest source texel
    float lab = floor(texture2D(uLab, uvOf(q)).r * 255.0 / 60.0 + 0.5);
    if (abs(lab - float(k + 1)) < 0.5) col = texture2D(uImg, uvOf(q));
  }
  gl_FragColor = vec4(col.rgb, 1.0);
}`;

(async () => {
  const uni = { uBase: { value: await raw(Q.base) }, uImg: { value: await raw(Q.image) }, uLab: { value: await raw(Q.labels) },
                uSize: { value: new THREE.Vector2(Q.W, Q.H) }, uN: { value: Q.parts.length },
                uInv: { value: [0, 1, 2, 3].map(() => new THREE.Matrix3()) } };
  const mat = new THREE.ShaderMaterial({ uniforms: uni, fragmentShader: frag,
    vertexShader: 'void main(){ gl_Position = vec4(position.xy, 0.0, 1.0); }' });
  const scene = new THREE.Scene();
  const quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2), mat); quad.frustumCulled = false; scene.add(quad);
  const cam = new THREE.Camera();
  const fwd = new THREE.Matrix3(), T = new THREE.Matrix3();
  const swing = (u) => (0.8 * Math.sin(2 * Math.PI * u) + 0.2 * Math.sin(4 * Math.PI * u)) / 0.94;
  const trap = (u) => { const s = (x) => x <= 0 ? 0 : x >= 1 ? 1 : x * x * (3 - 2 * x);
                        return s((u - 0.05) / 0.3) * (1 - s((u - 0.6) / 0.3)); };
  const jump = (u) => (u > 0.1 && u < 0.7) ? 4 * ((u - 0.1) / 0.6) * (1 - (u - 0.1) / 0.6) : 0;
  window.setTime = (t) => {
    const u = ((t / 2) % 1 + 1) % 1;
    Q.parts.forEach((P, k) => {
      let a = 0, dy = 0, sy = 1;
      if (P.mode === 'rot' && P.one) a = -P.amp * Math.PI / 180 * (0.5 - 0.5 * Math.cos(2 * Math.PI * u));  // - = up
      else if (P.mode === 'rot') a = P.amp * Math.PI / 180 * swing(u);
      else if (P.action === 'jump') dy = -P.amp * jump(u);
      else if (P.mode === 'lift') dy = -P.amp * trap(u);
      else sy = 1 - P.amp * (0.5 - 0.5 * Math.cos(2 * Math.PI * u));
      // forward map in image coords (y down): translate(pivot + dy) * rotate(a) * scaleY(sy) * translate(-pivot)
      const c = Math.cos(a), s = Math.sin(a);
      fwd.set(1, 0, P.px, 0, 1, P.py + dy, 0, 0, 1);
      fwd.multiply(T.set(c, -s, 0, s, c, 0, 0, 0, 1));
      fwd.multiply(T.set(1, 0, 0, 0, sy, 0, 0, 0, 1));
      fwd.multiply(T.set(1, 0, -P.px, 0, 1, -P.py, 0, 0, 1));
      uni.uInv.value[k].copy(fwd).invert();
    });
    r.render(scene, cam);
  };
  window.setTime(0);
  window.ANIM_READY = true;
})();
</script></body></html>
"""


def build(info, out, tech):
    parts = []
    if tech == "canvas2d":
        save_png(base_image(info, "nearest"), out / "base.png")
        for i, p in enumerate(info["parts"]):
            a = np.zeros((info["H"], info["W"], 4), np.uint8)
            a[..., 3] = p.mask.astype(np.uint8) * 255
            Image.fromarray(a).save(out / f"mask{i}.png")
            parts.append(dict(mask=f"./mask{i}.png", px=p.pivot[0], py=p.pivot[1], mode=p.mode, one=p.one_sided, action=p.action,
                              amp=round(p.amount("typ"), 4)))
        cfg = dict(W=info["W"], H=info["H"], image="./image.png", base="./base.png", parts=parts)
        page = CANVAS_PAGE
    elif tech == "shader":
        save_png(base_image(info, "white"), out / "base.png")
        lab = np.zeros((info["H"], info["W"]), np.uint8)
        for i, p in enumerate(info["parts"]):
            lab[p.mask] = 60 * (i + 1)
            parts.append(dict(px=p.pivot[0], py=p.pivot[1], mode=p.mode, one=p.one_sided, action=p.action,
                              amp=round(p.amount("typ"), 4)))
        Image.fromarray(np.stack([lab] * 3, -1)).save(out / "labels.png")
        cfg = dict(W=info["W"], H=info["H"], image="./image.png", base="./base.png", labels="./labels.png", parts=parts)
        page = SHADER_PAGE
    else:
        raise ValueError(tech)
    (out / "index.html").write_text(page.replace("__CFG__", js(cfg)))
