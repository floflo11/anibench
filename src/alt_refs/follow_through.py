"""Follow-through style: each part is a THREE.SkinnedMesh (a finely subdivided plane over the part's box)
driven by a bone chain laid along the part, so distal segments trail the proximal ones (overlapping action).

  * swings with a chain (hand: palm -> fingers; forearm: forearm -> hand -> fingers; whole arm: upper arm ->
    forearm -> hand; pigtail and earring: 2-3 segments; veil: 4 segments, a travelling wave): every bone
    swings with the same rhythm, each `lag` seconds behind its parent, under an envelope that starts and
    ends at rest;
  * rigid parts (heads, the tipped hat): one bone with a damped overshoot (the part settles);
  * jumps: feet -> hips -> head bones translate with a lag, so the body stretches on take-off and the upper
    body lands late;
  * squats/bounces: the hips bone drops, legs compress smoothly between feet and hips, the head lags;
  * hat lift: the hat rises and tilts a little behind the motion, then settles.

Skin weights blend smoothly across each joint (no seams). Nearest-colour fill for the uncovered area.
"""
from .common import base_image, js, rgba, save_png

# bone joints as fractions of the part length along its axis, and the blend half-width at each joint
CHAINS = {
    "wave_hand": ([0.0, 0.45], 0.08),
    "wave_forearm": ([0.0, 0.55, 0.8], 0.06),
    "swing_arm": ([0.0, 0.45, 0.78], 0.06),
    "earring": ([0.0, 0.6], 0.1),
    "pigtail": ([0.0, 0.4, 0.7], 0.08),
    "flutter": ([0.0, 0.25, 0.5, 0.75], 0.1),
    "head": ([0.0], 0.0),
    "hat_tilt": ([0.0], 0.0),
    "hat_lift": ([0.0], 0.0),
    "jump": ([0.0, 0.4, 0.75], 0.18),
    "squat": ([0.0, 0.45, 0.8], 0.06),    # feet->hips is a full ramp (legs compress); band at the neck
    "bounce": ([0.0, 0.45, 0.8], 0.06),
}

PAGE = r"""<!doctype html>
<html><head><meta charset="utf-8"><style>body{margin:0;background:#ffffff}</style></head>
<body><script type="module">
import * as THREE from './vendor/three.module.js';
const S = __CFG__;
const renderer = new THREE.WebGLRenderer({ preserveDrawingBuffer: true });
renderer.setPixelRatio(1); renderer.setSize(S.W, S.H);
renderer.toneMapping = THREE.NoToneMapping; renderer.setClearColor('#ffffff', 1);
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
const camera = new THREE.OrthographicCamera(0, S.W, 0, -S.H, -50, 50);   // world = (x, -y)

const getTexture = (url) => new THREE.TextureLoader().loadAsync(url).then((tx) => {
  tx.colorSpace = THREE.SRGBColorSpace; tx.minFilter = tx.magFilter = THREE.NearestFilter;
  tx.generateMipmaps = false; return tx; });
const smooth = (a, b, x) => { if (b <= a) return x >= a ? 1 : 0; const t = Math.min(1, Math.max(0, (x - a) / (b - a))); return t * t * (3 - 2 * t); };
const envelope = (t) => Math.pow(Math.sin(Math.PI * t / 2), 2);            // 0 at t = 0 and 2
const wrap = (t) => ((t % 2) + 2) % 2;
function window01(u, a, b) { return (u >= a && u <= b) ? (u - a) / (b - a) : -1; }

function makeRig(P, tex, z) {
  const w = P.x1 - P.x0, h = P.y1 - P.y0;
  const geo = new THREE.PlaneGeometry(w, h, Math.max(1, Math.ceil(w / 4)), Math.max(1, Math.ceil(h / 4)));
  geo.translate(P.x0 + w / 2, -(P.y0 + h / 2), z);
  const ax = P.axis[0], ay = -P.axis[1];                  // axis in world coords
  const nb = P.joints.length;
  const pos = geo.attributes.position, n = pos.count;
  const idx = new Uint16Array(n * 4), wts = new Float32Array(n * 4);
  for (let v = 0; v < n; v++) {
    const s = ((pos.getX(v) - P.jx) * ax + (pos.getY(v) + P.jy) * ay) / P.len;
    // membership of each bone: steps up at its joint, down at the next one
    const m = [];
    for (let b = 0; b < nb; b++) {
      const lo = b === 0 ? 0 : (P.ramp && b === 1 ? smooth(0, P.joints[1], s) : smooth(P.joints[b] - P.band, P.joints[b] + P.band, s));
      const hi = b + 1 < nb ? (P.ramp && b === 0 ? smooth(0, P.joints[1], s) : smooth(P.joints[b + 1] - P.band, P.joints[b + 1] + P.band, s)) : 0;
      m.push(b === 0 ? 1 - hi : lo - hi);
    }
    const order = m.map((x, b) => [x, b]).sort((p, q) => q[0] - p[0]).slice(0, 4);
    let tot = 0; for (const [x] of order) tot += Math.max(0, x);
    order.forEach(([x, b], k) => { idx[v * 4 + k] = b; wts[v * 4 + k] = tot > 0 ? Math.max(0, x) / tot : (k === 0 ? 1 : 0); });
  }
  geo.setAttribute('skinIndex', new THREE.Uint16BufferAttribute(idx, 4));
  geo.setAttribute('skinWeight', new THREE.Float32BufferAttribute(wts, 4));
  const bones = [];
  let prev = null;
  for (let b = 0; b < nb; b++) {
    const bone = new THREE.Bone();
    const d = P.joints[b] * P.len - (b ? P.joints[b - 1] * P.len : 0);
    if (b === 0) bone.position.set(P.jx, -P.jy, 0); else bone.position.set(ax * d, ay * d, 0);
    bone.userData.rest = bone.position.clone();
    if (prev) prev.add(bone);
    bones.push(bone); prev = bone;
  }
  const mesh = new THREE.SkinnedMesh(geo, new THREE.MeshBasicMaterial({ map: tex, transparent: true, depthTest: false }));
  mesh.frustumCulled = false;
  mesh.add(bones[0]);
  mesh.updateMatrixWorld(true);
  mesh.bind(new THREE.Skeleton(bones));
  return { mesh, bones, P };
}

function pose(rig, t) {
  const { bones, P } = rig;
  for (const b of bones) { b.rotation.z = 0; b.position.copy(b.userData.rest); }
  const u = wrap(t) / 2, deg = Math.PI / 180;
  if (P.mode === 'rot' && bones.length > 1) {          // chain: same rhythm, each segment lags its parent
    const share = [0.75, 0.3, 0.25, 0.2];
    bones.forEach((b, i) => {
      b.rotation.z = -P.amp * deg * share[i] * envelope(wrap(t)) * Math.sin(2 * Math.PI * (wrap(t) - i * S.lag) + P.phase);
    });
  } else if (P.mode === 'rot' && P.one) {             // hat tip: up (counter-clockwise), back, small dip, settle
    const e = S.lag > 0.15 ? 0.6 : 0.7;
    const g = u < e ? 0.5 - 0.5 * Math.cos(2 * Math.PI * u / e) : -0.1 * Math.sin(Math.PI * (u - e) / (1 - e));
    bones[0].rotation.z = P.amp * deg * g;
  } else if (P.mode === 'rot') {                        // rigid part: swing out, overshoot and settle
    const g = Math.sin(4 * Math.PI * u) * Math.exp(-(S.lag > 0.15 ? 2 : 3) * u) / 0.72;
    bones[0].rotation.z = -P.amp * deg * g;
  } else if (P.action === 'hat_lift') {
    const q = window01(u, 0.05, 0.9);
    if (q >= 0) {
      bones[0].position.y += P.amp * (0.5 - 0.5 * Math.cos(2 * Math.PI * q));
      bones[0].rotation.z = 4 * deg * Math.sin(2 * Math.PI * q) * Math.sin(Math.PI * q);
    }
  } else if (P.mode === 'lift') {                      // jump: feet lead, hips and head follow
    const H = (uu) => { const q = window01(((uu % 1) + 1) % 1, 0.05, 0.7); return q < 0 ? 0 : 4 * q * (1 - q); };
    const y = bones.map((_, i) => P.amp * H(u - i * S.lag / 2));
    bones.forEach((b, i) => { b.position.y += y[i] - (i ? y[i - 1] : 0); });
  } else {                                              // squat / bounce: hips drop, head lags
    const D = (uu) => { const q = window01(((uu % 1) + 1) % 1, 0.0, 0.75); return q < 0 ? 0 : 0.5 - 0.5 * Math.cos(2 * Math.PI * q); };
    const drop = P.amp * P.len;
    const y = [0, -drop * D(u), -drop * D(u - S.lag / 2)];
    bones.forEach((b, i) => { if (i) b.position.y += y[i] - y[i - 1]; });
  }
}

(async () => {
  const bg = new THREE.Mesh(new THREE.PlaneGeometry(S.W, S.H), new THREE.MeshBasicMaterial({ map: await getTexture(S.base) }));
  bg.position.set(S.W / 2, -S.H / 2, -1);
  scene.add(bg);
  const rigs = [];
  for (const [i, P] of S.parts.entries()) {
    const rig = makeRig(P, await getTexture(P.tex), 0);
    rig.mesh.renderOrder = i + 1;
    scene.add(rig.mesh); rigs.push(rig);
  }
  window.setTime = (t) => { for (const r of rigs) pose(r, t); scene.updateMatrixWorld(true); renderer.render(scene, camera); };
  window.setTime(0);
  window.ANIM_READY = true;
})();
</script></body></html>
"""


def build(info, out, lag):
    save_png(base_image(info, "nearest"), out / "base.png")
    parts = []
    for i, p in enumerate(info["parts"]):
        x0, y0, x1, y1 = p.bbox
        rgba(info["img"], p.mask, p.bbox).save(out / f"skin{i}.png")
        joints, band = CHAINS[p.action]
        parts.append(dict(tex=f"./skin{i}.png", x0=x0, y0=y0, x1=x1, y1=y1, jx=p.pivot[0], jy=p.pivot[1],
                          axis=list(p.axis), len=p.length, joints=joints, band=band,
                          ramp=p.action in ("squat", "bounce"), mode=p.mode, one=p.one_sided, action=p.action,
                          amp=round(p.amount("typ"), 4), phase=0.0))
    cfg = dict(W=info["W"], H=info["H"], base="./base.png", lag=lag, parts=parts)
    (out / "index.html").write_text(PAGE.replace("__CFG__", js(cfg)))
