"""Reference animator + broken copies, used to prove the graders work.

For each scored task, writes validation/<task>/<variant>/ with layer PNGs and an index.html
that animates them with three.js following the same output contract the models get.

Variants: ref, whole, missed_thumb, hole, frozen, center_pivot, no_loop, wrong_part, and three
detached-part copies for G2b: detach_small (a 20-60 px piece of the far end stays behind),
detach_tip (the far end moves with the part but drifts 6 px away from it), gap_seam (the part is
cut at the pivot; the parent-side stub stays put and the rest drifts 2 px out, opening a seam).
The drift follows ph2 = 0.5 - 0.5 cos(pi t): zero at t = 0 and t = 2 (so G6 does not see it),
largest at t = 1.
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
from graders import foreground  # noqa: E402
from tasks import HAT_PIVOT_T14, PARTS, load_part  # noqa: E402

VARIANTS = ["ref", "whole", "missed_thumb", "hole", "frozen", "center_pivot", "no_loop", "wrong_part",
            "detach_small", "detach_tip", "gap_seam"]
# variants that only make sense for some task kinds (default: every kind)
VARIANT_KINDS = {"gap_seam": ("rotate", "rotate_hat", "flutter")}  # needs a joint to open a seam at
TIP_DRIFT = 6   # px, detach_tip
SEAM_PX = 2     # px, gap_seam
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
      if (L.off) { g.position.x += L.off[0] * ph2; g.position.y -= L.off[1] * ph2; }
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


def small_tip(mask, fg, pivot, lo=20, hi=60, want=40):
    """A disc at the far end of the part whose visible (fg) pixels number lo..hi, closest to want.
    None if no radius gives a piece in range."""
    best = None
    for r in range(1, 16):
        piece = tip_disc(mask, pivot, r) & mask
        n = int((piece & fg).sum())
        if lo <= n <= hi and (best is None or abs(n - want) < abs(best[0] - want)):
            best = (n, piece)
    return None if best is None else best[1]


def far_end(mask, pivot, frac=0.8):
    """Part pixels at least frac * (largest distance from the pivot) away from it."""
    ys, xs = np.nonzero(mask)
    d = np.hypot(xs - pivot[0], ys - pivot[1])
    keep = d >= frac * d.max()
    out = np.zeros_like(mask)
    out[ys[keep], xs[keep]] = True
    return out


def away(mask, pivot):
    """Unit vector (x, y) from the pivot towards the centroid of mask."""
    ys, xs = np.nonzero(mask)
    a = np.array([xs.mean() - pivot[0], ys.mean() - pivot[1]], float)
    n = np.linalg.norm(a)
    return a / n if n > 0 else np.array([0.0, -1.0])


def seam_split(mask, pivot):
    """Cut the part along the line through the pivot, perpendicular to pivot -> part centroid.
    Returns (stub on the parent side, rest, unit axis)."""
    a = away(mask, pivot)
    yy, xx = np.indices(mask.shape)
    proj = (xx - pivot[0]) * a[0] + (yy - pivot[1]) * a[1]
    return mask & (proj < 0), mask & (proj >= 0), a


def variants_for(spec):
    return [v for v in VARIANTS if spec["kind"] in VARIANT_KINDS.get(v, (spec["kind"],))]


def plan_variant(spec, variant):
    """Work out a variant without writing anything.
    Returns (img, base, layers, keep): layers is a list of (sprite mask, layer params as passed to
    the page); keep is the part's own pixels left in the base (the piece left behind, the stub)."""
    tdir = ROOT / "tasks" / spec["id"]
    img = np.array(Image.open(tdir / "image.png").convert("RGB"))
    base = img.copy()
    kind = spec["kind"]
    parts = list(spec["parts"])
    if variant == "wrong_part":
        decoy = DECOY[spec["image"]]
        parts = [decoy if decoy not in parts else DECOY_ALT[spec["image"]]]
        kind = "rotate"
    layers = []
    keep = np.zeros(img.shape[:2], bool)
    for i, pid in enumerate(parts):
        m = load_part(pid)
        piv = PARTS[pid]["pivot"]
        if kind == "rotate_hat":
            piv = HAT_PIVOT_T14
        if piv is None:  # body: pivot at the feet centre
            ys, xs = np.nonzero(m)
            piv = (int(xs.mean()), int(ys.max()))
        sprite_mask = m.copy()
        drift = None  # (mask, offset) of a second layer that drifts away from the sprite
        if variant == "missed_thumb":
            sprite_mask &= ~tip_disc(m, piv)
        elif variant == "detach_small":
            piece = small_tip(m, foreground(img), piv)
            if piece is None:
                raise ValueError(f"{spec['id']} {pid}: no 20-60 px tip piece")
            sprite_mask &= ~piece
        elif variant == "detach_tip":
            tip = far_end(m, piv)
            sprite_mask &= ~tip
            drift = (tip, away(tip, piv) * TIP_DRIFT)
        elif variant == "gap_seam":
            stub, rest, a = seam_split(m, piv)
            sprite_mask = np.zeros_like(m)  # the stub is neither moved nor erased: it stays in the base
            drift = (rest, a * SEAM_PX)
        erase = sprite_mask | drift[0] if drift else sprite_mask
        keep |= m & ~erase
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
        if sprite_mask.any():
            layers.append((sprite_mask, L))
        if drift is not None:
            layers.append((drift[0], dict(L, url=f"./layer{i}d.png", off=[round(float(c), 3) for c in drift[1]])))
    if variant in ("frozen", "whole"):
        base = img.copy()
        layers = []
    return img, base, layers, keep


def build_variant(spec, variant, out):
    out.mkdir(parents=True, exist_ok=True)
    img, base, layers, _ = plan_variant(spec, variant)
    for mask, L in layers:
        rgba_layer(img, mask).save(out / L["url"][2:])
    Image.fromarray(base).save(out / "base.png")
    cfg = dict(W=spec["width"], H=spec["height"], base="./base.png", layers=[L for _, L in layers],
               whole=variant == "whole", frozen=variant == "frozen", hole=variant == "hole",
               noLoop=variant == "no_loop")
    (out / "index.html").write_text(PAGE % {"cfg": json.dumps(cfg)})


def place(mask, L, t, n_frames=25):
    """Where the page's layer L puts mask's pixels at time t (inverse nearest-neighbour mapping,
    the same transform as setTime: pivot group = translate(pivot + lift + drift) * rotate * scale)."""
    ph, ph2 = math.sin(math.pi * t), 0.5 - 0.5 * math.cos(math.pi * t)
    th = L["amp"] * math.pi / 180 * ph if L["kind"] == "rotate" else 0.0
    sy = 1 - L["amp"] * ph2 if L["kind"] == "squash" else 1.0
    dx, dy = (L["off"][0] * ph2, L["off"][1] * ph2) if "off" in L else (0.0, 0.0)
    if L["kind"] == "lift":
        dy -= L["amp"] * ph2
    ys, xs = np.nonzero(mask)
    pad = int(np.hypot(xs - L["px"], ys - L["py"]).max() * abs(math.sin(th))) + int(abs(dx)) + int(abs(dy)) + 3
    y0, y1 = max(0, ys.min() - pad), min(mask.shape[0], ys.max() + pad + 1)
    x0, x1 = max(0, xs.min() - pad), min(mask.shape[1], xs.max() + pad + 1)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(float)
    qx, qy = xx + 0.5 - L["px"] - dx, yy + 0.5 - L["py"] - dy
    c, s = math.cos(th), math.sin(th)
    sx_, sy_ = c * qx + s * qy, (-s * qx + c * qy) / sy
    ix, iy = np.floor(sx_ + L["px"]).astype(int), np.floor(sy_ + L["py"]).astype(int)
    ok = (ix >= 0) & (ix < mask.shape[1]) & (iy >= 0) & (iy < mask.shape[0])
    out = np.zeros_like(mask)
    sub = np.zeros(yy.shape, bool)
    sub[ok] = mask[iy[ok], ix[ok]]
    out[y0:y1, x0:x1] = sub
    return out


def oracle_split(spec, variant, n_frames=25):
    """Ground truth for the detachment copies, independent of the graders: draw only the part
    (no scenery) the way the page does, frame by frame, and count its 8-connected pieces with the
    same size floors as G2b. Returns dict(split=bool, base=pieces in the original, worst=max pieces)."""
    from graders import G2B_MIN, part_pieces
    img, _, layers, keep = plan_variant(spec, variant)
    fg = foreground(img)
    target = np.any([load_part(p) for p in spec["parts"]], axis=0)
    skull = None
    if spec["kind"] in ("translate_up", "rotate_hat"):
        skull = np.any([load_part(p.replace("_hat", "_skull")) for p in spec["parts"]], axis=0)
        keep &= ~skull
    none = np.zeros_like(fg)
    n0 = part_pieces(fg & target & (~skull if skull is not None else True), none, target, G2B_MIN)
    worst = 0
    for i in range(n_frames):
        t = i * 2 / (n_frames - 1)
        canvas = fg & keep
        for mask, L in layers:
            canvas |= place(mask & fg, L, t)
        worst = max(worst, part_pieces(canvas, none, np.ones_like(fg), G2B_MIN))
    return dict(split=bool(worst > n0), base=int(n0), worst=int(worst))


def build_all():
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    for spec in idx:
        if not spec["graders"]:
            continue
        for v in variants_for(spec):
            build_variant(spec, v, ROOT / "validation" / spec["id"] / v)


if __name__ == "__main__":
    build_all()
