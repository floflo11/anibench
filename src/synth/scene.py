"""Parametric layered 2D characters and scenes.

A scene holds 1-3 front-facing characters. Each character is built from parts (head, torso, upper arm,
forearm, hand, fingers + thumb, legs, shoes, hair, ears, and accessories: hat, earrings, tail, scarf), each
rasterised to its own anti-aliased RGBA layer. Because the image is the over-composite of the layers, every
part's exact mask (full and visible) and every joint pivot are known by construction.

Style presets: chibi (big round head), lanky (tall, thin), robot (boxy, metallic), animal (cat / bear / fox).
"""
from dataclasses import dataclass, field

import numpy as np
from PIL import Image

from .draw import Capsule, Detail, Ellipse, Layer, Poly, light_of, render_part, rrect, shade_of

STYLES = ["chibi", "lanky", "robot", "animal"]
MOTIONS = ["wave", "wiggle_fingers", "bend_elbow", "raise_arm", "nod", "tip_hat", "swing_earring", "wag_tail"]
MOTION_STYLES = {m: STYLES for m in MOTIONS}
MOTION_STYLES["swing_earring"] = ["chibi", "lanky", "robot"]
# amplitude (deg) and phase: "sym" = sin swing about rest, "one" = rest -> amp -> rest
MOTION_AMP = {"wave": (25, "sym"), "wiggle_fingers": (20, "sym"), "bend_elbow": (30, "one"), "raise_arm": (30, "one"),
              "nod": (10, "sym"), "tip_hat": (15, "one"), "swing_earring": (20, "sym"), "wag_tail": (20, "sym")}

# ---------------------------------------------------------------- palettes (name, rgb)
SKIN = [(255, 226, 200), (248, 208, 172), (232, 182, 142), (204, 146, 106), (164, 110, 76), (120, 80, 56)]
HAIR = [(58, 42, 38), (112, 72, 44), (34, 32, 42), (214, 166, 92), (178, 68, 48), (96, 70, 140), (236, 210, 140),
        (70, 110, 160)]
SHIRT = [("red", (226, 86, 82)), ("orange", (244, 152, 72)), ("yellow", (247, 208, 96)), ("green", (112, 184, 112)),
         ("teal", (72, 172, 172)), ("blue", (84, 134, 214)), ("purple", (152, 112, 204)), ("pink", (240, 144, 176)),
         ("cream", (234, 226, 206)), ("grey", (150, 154, 164))]
PANTS = [(62, 72, 112), (84, 84, 96), (128, 94, 64), (52, 112, 142), (150, 70, 70), (70, 120, 80)]
SHOES = [(72, 52, 46), (42, 42, 52), (204, 72, 62), (244, 244, 244), (70, 110, 190)]
ROBOT = [("silver", (196, 204, 214)), ("teal", (116, 196, 192)), ("orange", (242, 164, 86)), ("blue", (124, 164, 224)),
         ("mint", (164, 222, 184)), ("yellow", (240, 212, 100))]
FUR = {"cat": [("orange", (242, 162, 92)), ("grey", (164, 164, 176)), ("cream", (240, 222, 190)), ("black", (78, 72, 84))],
       "bear": [("brown", (164, 112, 78)), ("honey", (214, 160, 92)), ("snowy", (228, 222, 210))],
       "fox": [("orange", (236, 128, 62)), ("red", (206, 92, 60)), ("silver", (180, 184, 196))]}
HAT = [("black", (60, 52, 72)), ("red", (204, 72, 72)), ("blue", (72, 112, 184)), ("yellow", (242, 202, 92)),
       ("green", (92, 162, 122)), ("cream", (236, 228, 208)), ("purple", (132, 92, 172))]
GEM = [("gold", (242, 192, 64)), ("red", (222, 52, 64)), ("blue", (72, 124, 232)), ("green", (60, 172, 112)),
       ("pink", (244, 120, 180)), ("silver", (210, 214, 224))]
SCARF = [(222, 74, 74), (72, 132, 212), (246, 196, 76), (96, 176, 120), (180, 110, 200)]
BLUSH = (240, 116, 128)
INK = (46, 38, 54)

NOUN = {"chibi": "kid", "lanky": "tall person", "robot": "robot"}


@dataclass
class PartInfo:
    name: str
    parent: str = None
    joint: tuple = None     # pivot where it articulates on its parent; None = rigidly attached
    char: int = 0


@dataclass
class Scene:
    width: int
    height: int
    layers: list
    parts: dict
    chars: list = field(default_factory=list)
    task: dict = field(default_factory=dict)
    seed: int = 0

    def __post_init__(self):
        self._cache = {}

    def index(self, name):
        for i, L in enumerate(self.layers):
            if L.name == name:
                return i
        raise KeyError(name)

    def _full(self, name):
        L = self.layers[self.index(name)]
        out = np.zeros((self.height, self.width, 4), np.uint8)
        h, w = L.rgba.shape[:2]
        out[L.y0:L.y0 + h, L.x0:L.x0 + w] = L.rgba
        return out

    def alpha(self, name):
        return self._full(name)[..., 3]

    def rgb(self, name):
        return self._full(name)[..., :3]

    def full_mask(self, name):
        return self.alpha(name) > 0

    def owner(self):
        """Index of the layer that owns each pixel (-1 = background).

        Owner = top-most layer with alpha >= 128; for faint anti-aliased edge pixels with no such layer,
        the layer with the largest alpha there.
        """
        if "owner" not in self._cache:
            H, W = self.height, self.width
            own = np.full((H, W), -1, np.int32)
            best = np.zeros((H, W), np.int32)
            for i, L in enumerate(self.layers):
                h, w = L.rgba.shape[:2]
                a = L.rgba[..., 3].astype(np.int32)
                sl = (slice(L.y0, L.y0 + h), slice(L.x0, L.x0 + w))
                o, b = own[sl], best[sl]
                strong = a >= 128
                weak = (a > 0) & ~strong & (b < 128) & (a > b)
                o[strong | weak] = i
                b[strong] = 255
                b[weak] = a[weak]
            self._cache["owner"] = own
        return self._cache["owner"]

    def visible_mask(self, name):
        return self.owner() == self.index(name)

    def composite(self):
        if "comp" not in self._cache:
            canvas = Image.new("RGBA", (self.width, self.height), (255, 255, 255, 255))
            for L in self.layers:
                canvas.alpha_composite(Image.fromarray(L.rgba), dest=(L.x0, L.y0))
            self._cache["comp"] = np.array(canvas.convert("RGB"))
        return self._cache["comp"]

    def chain_length(self, name):
        n, p = 0, self.parts[name]
        while p.parent is not None:
            if p.joint is not None:
                n += 1
            p = self.parts[p.parent]
        return n


# ---------------------------------------------------------------- geometry helpers

def unit(a):
    return np.array([np.cos(a), np.sin(a)])


def rot(v, deg):
    t = np.deg2rad(deg)
    c, s = np.cos(t), np.sin(t)
    return np.array([c * v[0] - s * v[1], s * v[0] + c * v[1]])


def norm(v):
    return v / max(np.hypot(*v), 1e-9)


def cross2(a, b):
    return float(a[0] * b[1] - a[1] * b[0])


def sd_ellipse(p, c, rx, ry):
    q = (np.asarray(p, float) - c)
    k = np.hypot(q[0] / rx, q[1] / ry)
    return (k - 1) * np.hypot(*q) / max(k, 1e-6)


def dome(cx, by, rx, ry, drop=0.0):
    """Upper half-ellipse sitting on the line y = by (extended down by drop)."""
    t = np.linspace(np.pi, 2 * np.pi, 33)
    pts = [(cx + rx * np.cos(a), by + ry * np.sin(a)) for a in t]
    return Poly(pts + [(cx + rx, by + drop), (cx - rx, by + drop)], 0.0)


def sd_box(p, c, hw, hh):
    q = np.abs(np.asarray(p, float) - c) - np.array([hw, hh])
    return np.hypot(*np.maximum(q, 0)) + min(max(q[0], q[1]), 0)


# ---------------------------------------------------------------- style proportions (units of u = scale)
GEOM = {
    "chibi": dict(head=(0, -68), hrx=22, hry=19.5, N=(0, -44), neck=(0, -52), neck_r=4.5,
                  torso=dict(top=-51, bot=-21, thw=10.5, bhw=14, r=6), hip=6.5, hip_y=-25, foot_y=-6.5, leg_r=5,
                  shoe=(7.2, 4.2), sh=(9.2, -46.5), arm_r=4, L1=13.5, L2=12.5, pr=5.0, pl=3.5, nf=3, fl=5.4,
                  fr=1.65, tl=4.2, tr=1.75, ear=(21.3, -63.5, 3.6, 4.6), height=96),
    "lanky": dict(head=(0, -88), hrx=8.6, hry=10.6, N=(0, -71.5), neck=(0, -80), neck_r=2.8,
                  torso=dict(top=-76, bot=-44, thw=10, bhw=7.6, r=3.2), hip=4.2, hip_y=-46, foot_y=-3.6, leg_r=3.1,
                  shoe=(5.2, 2.9), sh=(7.8, -73), arm_r=2.4, L1=17, L2=15.5, pr=3.0, pl=2.6, nf=4, fl=3.6,
                  fr=0.78, tl=2.8, tr=0.86, ear=(9.0, -86.5, 1.8, 2.6), height=100),
    "robot": dict(head=(0, -77), hw=15, hh=11, N=(0, -58.5), neck=(0, -66), neck_r=3.6,
                  torso=dict(c=(0, -47), w=30, h=26, r=5), hip=7, hip_y=-36, foot_y=-7, leg_r=4.2,
                  shoe=(6.6, 3.2), sh=(13.2, -56), arm_r=3.2, L1=13.5, L2=12.5, pr=4.3, pl=3.2, nf=3, fl=4.2,
                  fr=1.45, tl=3.6, tr=1.5, ear=(17.5, -77, 2.3, 4.6), height=96),
    "animal": dict(head=(0, -66), hrx=20, hry=17, N=(0, -44), neck=(0, -50), neck_r=4.5,
                   torso=dict(top=-50, bot=-18, thw=10, bhw=14.5, r=9), hip=7, hip_y=-22, foot_y=-6, leg_r=5,
                   shoe=(6.6, 4.1), sh=(9.2, -45), arm_r=4, L1=12, L2=11.5, pr=4.6, pl=3.0, nf=3, fl=3.2,
                   fr=1.65, tl=3.0, tr=1.65, ear=None, height=92),
}


class CharBuilder:
    """Builds one character as an ordered list of part specs (back to front)."""

    def __init__(self, ci, seed, style, cx, gy, u, knobs, W, H):
        self.ci, self.style, self.cx, self.gy, self.u = ci, style, cx, gy, u
        self.rng = np.random.default_rng(seed)
        self.k = knobs
        self.W, self.H = W, H
        self.g = GEOM[style]
        self.specs = []          # dicts: name, prims, fill, details, parent, joint, ow, shade, extent
        self.meta = dict(style=style)
        self.ow = float(np.clip(0.55 * u, 1.6, 2.8))

    # coordinates
    def P(self, x, y):
        return np.array([self.cx + x * self.u, self.gy + y * self.u])

    def n(self, part):
        return f"c{self.ci}_{part}"

    def add(self, part, prims, fill, parent=None, joint=None, details=(), shade=0.25, ow=None, extent=(), **kw):
        self.specs.append(dict(name=self.n(part), prims=prims, fill=fill, parent=parent and self.n(parent),
                               joint=None if joint is None else tuple(float(v) for v in joint), details=list(details),
                               shade=shade, ow=self.ow if ow is None else ow, extent=list(extent), **kw))

    # ------------------------------------------------------------ choices
    def choose(self, seq):
        return seq[int(self.rng.integers(len(seq)))]

    def palette(self):
        r, st = self.rng, self.style
        c = {}
        if st in ("chibi", "lanky"):
            c["skin"] = self.choose(SKIN)
            c["hair"] = self.choose(HAIR)
            c["shirt_name"], c["shirt"] = self.choose(SHIRT)
            c["pants"] = self.choose(PANTS)
            c["shoe"] = self.choose(SHOES)
            c["sleeve_long"] = bool(r.random() < 0.5)
        elif st == "robot":
            c["body_name"], c["body"] = self.choose(ROBOT)
            alt = [x for x in ROBOT if x[0] != c["body_name"]]
            c["accent_name"], c["accent"] = self.choose(alt)
            c["skin"] = c["body"]
            c["shirt"], c["shirt_name"] = c["accent"], c["accent_name"]
            c["pants"] = shade_of(c["body"], 0.5)
            c["shoe"] = (84, 92, 110)
            c["joint"] = (120, 128, 146)
        else:
            sp = self.choose(["cat", "bear", "fox"])
            self.meta["species"] = sp
            c["fur_name"], c["fur"] = self.choose(FUR[sp])
            c["skin"] = c["fur"]
            c["belly"] = light_of(c["fur"], 0.55)
            c["pants"] = c["fur"]
            c["shoe"] = light_of(c["fur"], 0.3)
            c["shirt_name"], c["shirt"] = self.choose(SHIRT)
            c["vest"] = bool(r.random() < 0.5)
        self.c = c
        return c

    # ------------------------------------------------------------ body parts
    def head_shape(self):
        g = self.g
        if self.style == "robot":
            c = self.P(*g["head"])
            return [rrect(c, 2 * g["hw"] * self.u, 2 * g["hh"] * self.u, 5 * self.u)], c, g["hw"] * self.u, g["hh"] * self.u
        c = self.P(*g["head"])
        rx, ry = g["hrx"] * self.u, g["hry"] * self.u
        if self.style == "lanky":  # slightly tapered jaw
            return [Ellipse(c, rx, ry), Ellipse(c + np.array([0, 0.25 * ry]), rx * 0.86, ry * 0.8)], c, rx, ry
        return [Ellipse(c, rx, ry)], c, rx, ry

    def head_sd(self, p):
        c, rx, ry = self.hc, self.hrx, self.hry
        if self.style == "robot":
            return sd_box(p, c, rx, ry) - 0.0
        return sd_ellipse(p, c, rx, ry)

    def build(self):
        g, u, r = self.g, self.u, self.rng
        c = self.palette()
        st = self.style
        self.head_prims, self.hc, self.hrx, self.hry = self.head_shape()
        k = self.k
        self.meta.update(knobs=dict(k))
        # accessories that the task needs are forced via knobs
        self.has_hat = k.get("hat", r.random() < 0.45)
        self.has_earrings = st != "animal" and k.get("earrings", r.random() < 0.35)
        self.has_tail = k.get("tail", st == "animal" or r.random() < 0.15)
        self.has_scarf = k.get("scarf", r.random() < 0.3)
        self.long_hair = st in ("chibi", "lanky") and k.get("long_hair", r.random() < 0.4)
        self.s = k.get("raised_side", self.choose([-1, 1]))   # viewer side of the raised arm
        self.order_tail()
        if self.long_hair:
            self.hair_back()
        arms = self.arm_geometry()
        for a in arms:
            if a["layer"] == "back":
                self.arm_parts(a)
        self.legs()
        self.neck()
        self.torso()
        if self.has_scarf:
            self.scarf()
        for a in arms:
            if a["layer"] == "front":
                self.arm_parts(a)
        self.ears_and_earrings()
        self.head()
        if st in ("chibi", "lanky"):
            self.hair_front()
        if self.has_hat:
            self.hat()
        for a in arms:
            if a["layer"] == "over":
                self.arm_parts(a)
        return self.specs, self.meta

    # tail is drawn first (behind everything)
    def order_tail(self):
        if not self.has_tail:
            return
        g, u, r = self.g, self.u, self.rng
        st = self.style
        side = self.k.get("tail_side", self.choose([-1, 1]))
        down = self.k.get("tail_down", r.random() < 0.4)
        tor = g["torso"]
        hy = g["hip_y"] + 2.5
        bx = 0.55 * (tor.get("bhw") or tor.get("w", 28) / 2)
        B = self.P(side * bx, hy)
        a0 = np.deg2rad(r.uniform(35, 60) if down else r.uniform(-35, -5))  # angle below horizontal
        d0 = np.array([side * np.cos(a0), np.sin(a0)])
        kind = {"animal": self.meta.get("species", "cat"), "chibi": "fox", "robot": "cable", "lanky": "devil"}[st]
        if kind == "bear":
            prims = [Ellipse(B + d0 * 4.2 * u, 4.4 * u, 4.2 * u)]
            jr = 4.4 * u
            col = self.c["fur"]
            det = []
        else:
            n = 7
            L = {"cat": 30, "fox": 26, "cable": 26, "devil": 30}[kind] * u
            curl = side * r.uniform(-9, -4) if not down else side * r.uniform(-8, -4)
            pts = [B]
            d = d0.copy()
            for i in range(n):
                d = rot(d, curl)
                pts.append(pts[-1] + d * L / n)
            if kind == "fox":
                rad = [2.4, 3.6, 4.8, 5.6, 5.8, 5.0, 3.6, 1.6]
            elif kind == "cat":
                rad = [2.3, 2.2, 2.1, 2.0, 1.9, 1.85, 1.8, 1.8]
            elif kind == "cable":
                rad = [1.3] * 8
            else:
                rad = [1.3, 1.2, 1.1, 1.0, 0.95, 0.9, 0.9, 0.9]
            prims = [Capsule(pts[i], pts[i + 1], rad[i] * u, rad[i + 1] * u) for i in range(n)]
            jr = rad[0] * u
            col = self.c["fur"] if st == "animal" else (self.c["hair"] if st == "chibi" else
                                                         ((84, 92, 110) if st == "robot" else (200, 50, 60)))
            det = []
            if kind in ("fox",) or (kind == "cat" and r.random() < 0.5):
                tip = pts[-1]
                det.append(Detail("fill", [Ellipse(tip, 3.2 * u, 3.2 * u)], (246, 242, 234)))
            if kind == "cable":
                plug = pts[-1] + d * 1.6 * u
                ang = np.arctan2(d[1], d[0])
                prims.append(rrect(plug, 4.4 * u, 3.4 * u, 0.8 * u, ang))
            if kind == "devil":
                tip = pts[-1]
                nn = np.array([-d[1], d[0]])
                prims.append(Poly([tip - nn * 2.6 * u, tip + d * 4.2 * u, tip + nn * 2.6 * u, tip - d * 0.6 * u], 0.5 * u))
        self.add("tail", prims, col, parent="torso", joint=B, details=det)
        self.meta["tail"] = dict(kind=kind, side=side, down=bool(down), base=B.tolist(), joint_r=jr + self.ow)

    def hair_back(self):
        u, c = self.u, self.c
        hc, rx, ry = self.hc, self.hrx, self.hry
        length = self.rng.uniform(0.9, 1.6) * ry
        prims = [rrect(hc + np.array([0, 0.25 * ry + length / 2 - 0.2 * ry]), 2.18 * rx, 1.35 * ry + length, 0.9 * rx)]
        self.add("hair_back", prims, c["hair"], parent="head", details=[], shade=0.12)
        self.meta["long_hair"] = True

    # ---------------- arms
    def arm_geometry(self):
        g, u, r, k = self.g, self.u, self.rng, self.k
        s = self.s
        L1, L2, pr, pl, fl = g["L1"] * u, g["L2"] * u, g["pr"] * u, g["pl"] * u, g["fl"] * u
        S_r = self.P(s * g["sh"][0], g["sh"][1])
        S_d = self.P(-s * g["sh"][0], g["sh"][1])
        hand_R = pr + 0.6 * fl
        # ---- raised arm: sample wrist positions, keep the one whose hand-to-anchor gap matches the knob
        want = k.get("hand_gap")  # in units of hand radius; None = random
        if want is None:
            want = r.choice([-0.5, 0.15, 1.0, 1.8])
        anchor = k.get("hand_anchor", "head")
        best, bestc = None, 1e18
        for _ in range(400):
            phi = np.deg2rad(r.uniform(-30, 70))  # from vertical-up toward the outside
            d = r.uniform(0.55, 0.97) * (L1 + L2)
            Wt = S_r + d * np.array([s * np.sin(phi), -np.cos(phi)])
            cosA = np.clip((L1 ** 2 + d ** 2 - L2 ** 2) / (2 * L1 * d), -1, 1)
            A = np.rad2deg(np.arccos(cosA))
            base = norm(Wt - S_r)
            cands = [S_r + L1 * rot(base, A), S_r + L1 * rot(base, -A)]
            E = max(cands, key=lambda e: e[1])  # elbow down
            if s * (E[0] - S_r[0]) < 0.15 * L1:
                continue
            fdir = norm(Wt - E)
            if fdir[1] > -0.35:
                continue
            hdir = rot(fdir, r.uniform(-14, 14))
            hc = Wt + hdir * (pl + 0.45 * fl)
            if anchor == "hat" and self.has_hat:
                gap = sd_ellipse(hc, self.hc + np.array([0, -1.05 * self.hry]), 1.15 * self.hrx, 0.5 * self.hry) - hand_R
            elif anchor == "ear" and self.g.get("ear"):
                ex = self.g["ear"]
                ep = self.P(-s * 0 + s * ex[0], ex[1] + 1.6 * ex[3] + 5)
                gap = np.hypot(*(hc - ep)) - hand_R - 2 * u
            else:
                gap = self.head_sd(hc) - hand_R
            cost = (gap / hand_R - want) ** 2 + 0.02 * r.random()
            if hc[1] > S_r[1] - 0.25 * L2:
                cost += 5
            if cost < bestc:
                best, bestc = (E, Wt, hdir), cost
        if best is None:  # fallback: plain raised pose
            E = S_r + L1 * norm(np.array([s * 1.0, -0.2]))
            Wt = E + L2 * np.array([0, -1.0])
            best = (E, Wt, np.array([0, -1.0]))
        E, Wt, hdir = best
        raised_layer = k.get("raised_layer", "front" if r.random() < 0.8 else "back")
        # ---- lowered arm
        a = np.deg2rad(k.get("down_angle", r.uniform(8, 30)))
        b = np.deg2rad(r.uniform(-4, 16))
        sd = -s
        E2 = S_d + L1 * np.array([sd * np.sin(a), np.cos(a)])
        W2 = E2 + L2 * np.array([sd * np.sin(a + b), np.cos(a + b)])
        h2 = rot(norm(W2 - E2), sd * r.uniform(-8, 4))
        down_layer = k.get("down_layer", "front" if r.random() < 0.75 else "back")
        arms = [dict(side=s, S=S_r, E=E, W=Wt, hdir=hdir, layer=raised_layer, raised=True),
                dict(side=sd, S=S_d, E=E2, W=W2, hdir=h2, layer=down_layer, raised=False)]
        self.meta["arms"] = arms
        return arms

    def arm_parts(self, a):
        g, u, c, st = self.g, self.u, self.c, self.style
        tag = "R" if a["side"] > 0 else "L"
        S, E, Wr, d = a["S"], a["E"], a["W"], a["hdir"]
        ar = g["arm_r"] * u
        sleeve = c["shirt"] if st in ("chibi", "lanky") else c["skin"]
        if st == "animal" and c.get("vest"):
            sleeve = c["fur"]
        fore_col = sleeve if (st in ("chibi", "lanky") and c["sleeve_long"]) else c["skin"]
        if st == "robot":
            sleeve = fore_col = c["body"]
        up_prims = [Capsule(S, E, ar)]
        self.add(f"upper_arm_{tag}", up_prims, sleeve, parent="torso", joint=S, shade=0.3)
        fore_prims = [Capsule(E, Wr, ar * 0.93, ar * 0.86)]
        det = []
        jr_fore = ar * 0.93
        if st == "robot":
            fore_prims.append(Ellipse(E, ar * 1.3, ar * 1.3))
            jr_fore = ar * 1.3
            det.append(Detail("outlined", [Ellipse(E, ar * 0.55, ar * 0.55)], c["joint"], width=0.5 * self.ow))
        elif st in ("chibi", "lanky") and c["sleeve_long"]:
            fd = norm(Wr - E)
            cuff = Wr - fd * 1.4 * u
            det.append(Detail("line", col=light_of(sleeve, 0.45), width=1.3 * u,
                              pts=[cuff - np.array([-fd[1], fd[0]]) * ar * 1.2, cuff + np.array([-fd[1], fd[0]]) * ar * 1.2]))
        self.add(f"forearm_{tag}", fore_prims, fore_col, parent=f"upper_arm_{tag}", joint=E, details=det, shade=0.3)
        # hand: palm capsule whose wrist end is a disc centred on the wrist pivot
        pr, pl, fl, fr = g["pr"] * u, g["pl"] * u, g["fl"] * u, g["fr"] * u
        nrm = np.array([-d[1], d[0]])
        med = np.array([-a["side"], 0.0])  # toward the body centre: the thumb side
        if np.dot(nrm, med) < 0:
            nrm = -nrm
        tip_c = Wr + d * pl
        nf = g["nf"]
        knuckles, fingers = [], []
        for i in range(nf):
            t = (i - (nf - 1) / 2) / max((nf - 1) / 2, 1)  # -1..1 (lateral .. medial)
            K = tip_c - d * (0.1 * pr) + nrm * (t * 0.5 * pr)
            length = (fl + 0.3 * pr) * (1.0 - 0.15 * abs(t) - (0.06 if t > 0.5 else 0)) * self.rng.uniform(0.94, 1.06)
            fd = rot(d, t * 11 * (1 if cross2(d, nrm) > 0 else -1))
            fingers.append((f"finger{i + 1}_{tag}", K, K + fd * length, fr))
            knuckles.append(K)
        T = Wr + d * (0.45 * pl) + nrm * (0.4 * pr)
        tdir = norm(rot(d, 52 if cross2(d, nrm) > 0 else -52))
        fingers.append((f"thumb_{tag}", T, T + tdir * (g["tl"] * u + 0.25 * pr), g["tr"] * u))
        skin = c["skin"]
        if st == "robot":
            skin = c["joint"]
        hand_name = f"hand_{tag}"
        for nm, K, tipp, rr in fingers:
            self.add(nm, [Capsule(K, tipp, rr, rr * 0.92)], skin, parent=hand_name, joint=K, shade=0.0,
                     ow=min(self.ow, 0.42 * rr + 0.6))
        hdet = []
        if st == "animal":
            hdet.append(Detail("fill", [Ellipse(Wr + d * (0.55 * pl), 0.45 * pr, 0.4 * pr, np.arctan2(d[1], d[0]))],
                               light_of(c["fur"], 0.5)))
        if st == "robot":
            hdet.append(Detail("fill", [Ellipse(Wr, 0.32 * pr, 0.32 * pr)], c["accent"]))
        self.add(hand_name, [Capsule(Wr, tip_c, pr)], c["skin"] if st != "robot" else c["accent"],
                 parent=f"forearm_{tag}", joint=Wr, details=hdet, shade=0.22)
        a.update(tag=tag, knuckles=[f[1] for f in fingers], finger_names=[f[0] for f in fingers],
                 finger_r=fr, pr=pr, ar=ar, jr_fore=jr_fore)

    def legs(self):
        g, u, c, st = self.g, self.u, self.c, self.style
        shorts = st == "chibi" and self.rng.random() < 0.5
        for sgn, tag in ((-1, "L"), (1, "R")):
            top = self.P(sgn * g["hip"], g["hip_y"])
            bot = self.P(sgn * (g["hip"] + 0.8), g["foot_y"])
            det = []
            if shorts:
                y = top[1] + 0.45 * (bot[1] - top[1])
                det.append(Detail("fill", [rrect((bot[0], (y + bot[1]) / 2 + 2 * u), 4 * g["leg_r"] * u, bot[1] - y + 4 * u, 0)],
                                  c["skin"] if st != "animal" else c["fur"]))
            if st == "robot":
                mid = (top + bot) / 2
                det.append(Detail("line", col=shade_of(c["pants"], 0.6), width=0.8 * u,
                                  pts=[mid - np.array([g["leg_r"] * u, 0]), mid + np.array([g["leg_r"] * u, 0])]))
            self.add(f"leg_{tag}", [Capsule(top, bot, g["leg_r"] * u, g["leg_r"] * u * 0.92)], c["pants"], parent="torso",
                     details=det, shade=0.3)
        for sgn, tag in ((-1, "L"), (1, "R")):
            sx, sy = g["shoe"]
            cpos = self.P(sgn * (g["hip"] + 1.6), g["foot_y"] + 2.0)
            if st == "robot":
                prims = [rrect(cpos, 2 * sx * u, 2 * sy * u, 1.4 * u)]
            else:
                prims = [Ellipse(cpos + np.array([sgn * 0.6 * u, 0]), sx * u, sy * u)]
            det = []
            if st in ("chibi", "lanky"):
                det.append(Detail("fill", [Ellipse(cpos + np.array([sgn * 1.2 * u, -0.9 * sy * u]), 0.45 * sx * u, 0.22 * sy * u)],
                                  light_of(c["shoe"], 0.4)))
            self.add(f"shoe_{tag}", prims, c["shoe"], parent=f"leg_{tag}", details=det, shade=0.25)

    def neck(self):
        g, u = self.g, self.u
        N = self.P(*g["N"])
        top = self.P(*g["neck"])
        col = self.c["skin"] if self.style != "robot" else self.c["joint"]
        det = []
        if self.style == "robot":
            for t in (0.3, 0.6):
                y = top + (N - top) * t
                det.append(Detail("line", col=shade_of(col, 0.7), width=0.6 * u,
                                  pts=[y - np.array([g["neck_r"] * u, 0]), y + np.array([g["neck_r"] * u, 0])]))
        self.add("neck", [Capsule(top, N, g["neck_r"] * u)], col, parent="torso", joint=N, details=det, shade=0.3)
        self.meta["neck"] = dict(N=N, r=g["neck_r"] * u)

    def torso(self):
        g, u, c, st, r = self.g, self.u, self.c, self.style, self.rng
        t = g["torso"]
        det = []
        if st == "robot":
            cc = self.P(*t["c"])
            prims = [rrect(cc, t["w"] * u, t["h"] * u, t["r"] * u)]
            det.append(Detail("outlined", [rrect(cc + np.array([0, -1 * u]), 16 * u, 11 * u, 2.2 * u)], (64, 74, 96), width=0.45 * self.ow))
            for i, col in enumerate([(240, 90, 90), (250, 210, 90), (110, 220, 140)]):
                det.append(Detail("fill", [Ellipse(cc + np.array([(i - 1) * 4.6 * u, -1 * u]), 1.4 * u, 1.4 * u)], col))
            det.append(Detail("fill", [rrect(cc + np.array([0, 8.5 * u]), t["w"] * u * 1.1, 2.4 * u, 0)], c["accent"]))
            fill = c["body"]
        else:
            top, bot, thw, bhw = t["top"], t["bot"], t["thw"], t["bhw"]
            pts = [self.P(-thw, top), self.P(thw, top), self.P(bhw, bot), self.P(-bhw, bot)]
            prims = [Poly(pts, t["r"] * u)]
            mid = self.P(0, (top + bot) / 2)
            if st == "animal":
                fill = c["fur"]
                det.append(Detail("fill", [Ellipse(self.P(0, bot + 0.42 * (top - bot)), 0.62 * bhw * u, 0.36 * (bot - top) * u)], c["belly"]))
                if c["vest"]:
                    for sg in (-1, 1):
                        det.append(Detail("fill", [Poly([self.P(sg * thw * 1.3, top - 2), self.P(sg * 2.2, top - 2),
                                                         self.P(sg * 3.5, bot + 6), self.P(sg * bhw * 1.3, bot + 6)], 1.2 * u)], c["shirt"]))
            else:
                fill = c["shirt"]
                pat = self.choose(["plain", "stripes", "buttons", "overalls", "emblem"])
                self.meta["pattern"] = pat
                if pat == "stripes":
                    sc = light_of(fill, 0.55) if sum(fill) < 600 else shade_of(fill, 0.9)
                    for i in range(6):
                        y = top + (i + 0.7) * (bot - top) / 6
                        det.append(Detail("fill", [rrect(self.P(0, y), 2 * bhw * u * 1.2, 0.36 * (bot - top) / 6 * u * 2.2, 0)], sc))
                elif pat == "buttons":
                    for i in range(3):
                        det.append(Detail("outlined", [Ellipse(self.P(0, top + (i + 1.2) * (bot - top) / 4.2), 0.95 * u, 0.95 * u)],
                                          light_of(fill, 0.6), width=0.4 * self.ow))
                elif pat == "overalls":
                    oc = self.choose(PANTS)
                    det.append(Detail("fill", [Poly([self.P(-0.75 * bhw, top + 0.45 * (bot - top)), self.P(0.75 * bhw, top + 0.45 * (bot - top)),
                                                     self.P(bhw + 1, bot + 1), self.P(-bhw - 1, bot + 1)], 1.0 * u)], oc))
                    for sg in (-1, 1):
                        det.append(Detail("line", col=oc, width=1.6 * u,
                                          pts=[self.P(sg * 0.55 * thw, top - 1), self.P(sg * 0.6 * bhw, top + 0.5 * (bot - top))]))
                elif pat == "emblem":
                    cc = self.P(0, top + 0.45 * (bot - top))
                    rr = 0.22 * (bot - top) * u
                    star = [cc + rr * (1 if i % 2 == 0 else 0.45) * unit(-np.pi / 2 + i * np.pi / 5) for i in range(10)]
                    det.append(Detail("fill", [Poly(star, 0.15 * u)], light_of(fill, 0.65)))
                if st == "lanky":
                    det.append(Detail("fill", [rrect(self.P(0, bot - 1.2), 2.4 * bhw * u, 2.4 * u, 0)], shade_of(c["pants"], 0.6)))
                # neckline
                det.append(Detail("fill", [Ellipse(self.P(0, top), (g["neck_r"] + 1.4) * u, (g["neck_r"] + 0.6) * u)], c["skin"]))
        self.add("torso", prims, fill, details=det, shade=0.22)

    def scarf(self):
        g, u, r = self.g, self.u, self.rng
        col = self.choose(SCARF)
        N = self.meta["neck"]["N"]
        ytop = (self.P(*g["neck"])[1] + N[1]) / 2 + 1.5 * u
        w = (g["neck_r"] + 4.2) * u
        if self.style == "lanky":
            w = (g["neck_r"] + 3.2) * u
        tail_side = self.choose([-1, 1])
        x0 = N[0] + tail_side * 0.45 * w
        L = r.uniform(12, 18) * u * (0.8 if self.style == "chibi" else 1)
        tilt = tail_side * r.uniform(2, 10)
        dd = rot(np.array([0, 1.0]), tilt)
        nn = np.array([-dd[1], dd[0]])
        wd = 2.6 * u if self.style != "lanky" else 2.0 * u
        tail = Poly([np.array([x0, ytop]) - nn * wd, np.array([x0, ytop]) + nn * wd,
                     np.array([x0, ytop]) + nn * wd * 1.1 + dd * L, np.array([x0, ytop]) - nn * wd * 1.1 + dd * L], 0.6 * u)
        stripe = light_of(col, 0.5)
        end = np.array([x0, ytop]) + dd * L
        det = [Detail("fill", [Poly([end - nn * 3 * u - dd * 3.2 * u, end + nn * 3 * u - dd * 3.2 * u,
                                     end + nn * 3 * u - dd * 1.8 * u, end - nn * 3 * u - dd * 1.8 * u], 0)], stripe)]
        band = Capsule(np.array([N[0] - w, ytop]), np.array([N[0] + w, ytop]), 2.7 * u if self.style != "lanky" else 2.1 * u)
        self.add("scarf_end", [tail], col, parent="torso", details=det, shade=0.25)
        self.add("scarf", [band], col, parent="torso",
                 details=[Detail("line", col=stripe, width=0.9 * u, pts=[np.array([N[0] - w, ytop]), np.array([N[0] + w, ytop])])],
                 shade=0.3)

    def ears_and_earrings(self):
        g, u, c, st, r = self.g, self.u, self.c, self.style, self.rng
        hc, rx, ry = self.hc, self.hrx, self.hry
        if st == "animal":
            sp = self.meta["species"]
            for sg, tag in ((-1, "L"), (1, "R")):
                if sp == "bear":
                    ec = hc + np.array([sg * 0.68 * rx, -0.78 * ry])
                    prims = [Ellipse(ec, 0.3 * rx, 0.3 * rx)]
                    det = [Detail("fill", [Ellipse(ec, 0.16 * rx, 0.16 * rx)], light_of(c["fur"], 0.45))]
                else:
                    tall = 1.55 if sp == "fox" else 1.25
                    b0 = hc + np.array([sg * 0.22 * rx, -0.8 * ry])
                    b1 = hc + np.array([sg * 0.92 * rx, -0.42 * ry])
                    tip = hc + np.array([sg * 0.78 * rx, -tall * ry])
                    prims = [Poly([b0, tip, b1], 0.12 * rx)]
                    inner = [b0 * 0.55 + b1 * 0.45 * 1 + (tip - (b0 + b1) / 2) * 0.0, tip * 0.8 + (b0 + b1) / 2 * 0.2]
                    m = (b0 + b1) / 2
                    det = [Detail("fill", [Poly([m + (b0 - m) * 0.55, m + (tip - m) * 0.72, m + (b1 - m) * 0.55], 0.06 * rx)],
                                  (246, 176, 186) if sp == "cat" else (250, 240, 230))]
                    if sp == "fox":
                        det.append(Detail("fill", [Ellipse(tip, 0.2 * rx, 0.22 * rx)], (70, 50, 50)))
                self.add(f"ear_{tag}", prims, c["fur"], parent="head", details=det, shade=0.2)
            return
        ex, ey, erx, ery = g["ear"]
        if st == "robot":
            ears = {}
            for sg, tag in ((-1, "L"), (1, "R")):
                ec = self.P(sg * ex, ey)
                ears[tag] = ec
            # antenna
            top = hc + np.array([0, -self.hry])
            tipp = top + np.array([0, -7 * u])
            self.add("antenna", [Capsule(top + np.array([0, 2 * u]), tipp, 0.55 * u), Ellipse(tipp, 1.9 * u, 1.9 * u)],
                     c["joint"], parent="head", details=[Detail("fill", [Ellipse(tipp, 1.9 * u, 1.9 * u)], c["accent"])], shade=0.0)
        if self.has_earrings:
            gem_name, gem = self.choose(GEM)
            self.meta["earring_colour"] = gem_name
            long_ = self.k.get("earring_long", r.random() < 0.5)
            shape = self.choose(["drop", "hoop", "ball"])
            self.meta["earrings"] = []
            for sg, tag in ((-1, "L"), (1, "R")):
                ec = self.P(sg * ex, ey)
                lobe = ec + np.array([0, 0.62 * ery * u])
                hook_len = ((3.2 if long_ else 1.6) + {'chibi': 0.6, 'lanky': 1.2, 'robot': 1.5}[st]) * u + 1.0 * ery * u
                bot = lobe + np.array([0, hook_len])
                hr = max(0.38 * u, 0.9)
                prims = [Capsule(lobe, bot, hr)]
                gr = (1.9 if long_ else 1.5) * u * (0.75 if st == "lanky" else 1.0)
                if shape == "drop":
                    prims.append(Poly([bot + np.array([0, -0.4 * gr]), bot + np.array([gr, gr * 1.3]), bot + np.array([0, 2.6 * gr]),
                                       bot + np.array([-gr, gr * 1.3])], 0.5 * gr))
                elif shape == "ball":
                    prims.append(Ellipse(bot + np.array([0, gr]), gr, gr))
                det = [Detail("fill", [Ellipse(bot + np.array([-0.3 * gr, 0.9 * gr]), 0.32 * gr, 0.32 * gr)], light_of(gem, 0.7))]
                if shape == "hoop":
                    hc2 = bot + np.array([0, 1.3 * gr])
                    prims = [Capsule(lobe, bot, hr)]
                    ring = Ellipse(hc2, 1.35 * gr, 1.35 * gr)
                    prims.append(ring)
                    det = [Detail("fill", [Ellipse(hc2, 0.75 * gr, 0.75 * gr)], (255, 255, 255))]
                self.add(f"earring_{tag}", prims, gem, parent=f"ear_{tag}", joint=lobe, details=det, shade=0.0,
                         ow=min(self.ow, 1.6), hoop=shape == "hoop")
                self.meta["earrings"].append(dict(tag=tag, lobe=lobe, joint_r=hr + 1.6, hook_len=hook_len))
        for sg, tag in ((-1, "L"), (1, "R")):
            ec = self.P(sg * ex, ey)
            if st == "robot":
                prims = [rrect(ec, 2 * erx * u, 2 * ery * u, 1.0 * u)]
                det = [Detail("fill", [Ellipse(ec, 0.6 * erx * u, 0.6 * erx * u)], c["accent"])]
                col = c["joint"]
            else:
                prims = [Ellipse(ec, erx * u, ery * u)]
                det = [Detail("fill", [Ellipse(ec + np.array([sg * 0.15 * erx * u, 0]), 0.45 * erx * u, 0.55 * ery * u)],
                              shade_of(c["skin"], 0.5))]
                col = c["skin"]
            self.add(f"ear_{tag}", prims, col, parent="head", details=det, shade=0.0)

    def head(self):
        g, u, c, st, r = self.g, self.u, self.c, self.style, self.rng
        hc, rx, ry = self.hc, self.hrx, self.hry
        det = []
        if st == "chibi":
            ex, ey = 0.36 * rx, 0.12 * ry
            iris = self.choose([(70, 48, 40), (40, 70, 120), (50, 110, 70), (40, 36, 50)])
            for sg in (-1, 1):
                e = hc + np.array([sg * ex, ey])
                det.append(Detail("fill", [Ellipse(e, 0.115 * rx, 0.175 * ry)], INK))
                det.append(Detail("fill", [Ellipse(e + np.array([0, 0.07 * ry]), 0.085 * rx, 0.09 * ry)], iris))
                det.append(Detail("fill", [Ellipse(e + np.array([-0.035 * rx, -0.06 * ry]), 0.045 * rx, 0.05 * ry)], (255, 255, 255)))
                det.append(Detail("fill", [Ellipse(hc + np.array([sg * 0.6 * rx, 0.38 * ry]), 0.13 * rx, 0.07 * ry)],
                                  tuple(int(0.55 * a + 0.45 * b) for a, b in zip(c["skin"], BLUSH))))
            m = hc + np.array([0, 0.42 * ry])
            if r.random() < 0.5:
                det.append(Detail("line", col=INK, width=0.75 * u, pts=[m + np.array([-0.1 * rx, -0.02 * ry]), m + np.array([-0.04 * rx, 0.04 * ry]),
                                                                       m + np.array([0.04 * rx, 0.04 * ry]), m + np.array([0.1 * rx, -0.02 * ry])]))
            else:
                det.append(Detail("outlined", [Ellipse(m + np.array([0, 0.02 * ry]), 0.07 * rx, 0.06 * ry)], (214, 90, 100), width=0.6 * u))
        elif st == "lanky":
            for sg in (-1, 1):
                e = hc + np.array([sg * 0.38 * rx, 0.02 * ry])
                det.append(Detail("fill", [Ellipse(e, 0.1 * rx, 0.12 * ry)], INK))
                det.append(Detail("fill", [Ellipse(e + np.array([-0.03 * rx, -0.04 * ry]), 0.035 * rx, 0.035 * ry)], (255, 255, 255)))
                det.append(Detail("line", col=shade_of(self.c["hair"], 0.6) if True else INK, width=0.55 * u,
                                  pts=[e + np.array([-0.16 * rx, -0.22 * ry]), e + np.array([0.0, -0.26 * ry]), e + np.array([0.16 * rx, -0.22 * ry])]))
            det.append(Detail("line", col=shade_of(c["skin"], 1.0), width=0.5 * u,
                              pts=[hc + np.array([0.0, 0.12 * ry]), hc + np.array([0.08 * rx, 0.3 * ry]), hc + np.array([-0.03 * rx, 0.32 * ry])]))
            m = hc + np.array([0, 0.5 * ry])
            det.append(Detail("line", col=INK, width=0.55 * u, pts=[m + np.array([-0.22 * rx, -0.02 * ry]), m + np.array([0, 0.06 * ry]),
                                                                   m + np.array([0.22 * rx, -0.02 * ry])]))
            if r.random() < 0.35:
                self.meta["glasses"] = True
                for sg in (-1, 1):
                    e = hc + np.array([sg * 0.38 * rx, 0.02 * ry])
                    det.append(Detail("outlined", [Ellipse(e, 0.27 * rx, 0.22 * ry)], light_of(c["skin"], 0.25), width=0.5 * u))
                    det.append(Detail("fill", [Ellipse(e, 0.1 * rx, 0.12 * ry)], INK))
                det.append(Detail("line", col=INK, width=0.5 * u, pts=[hc + np.array([-0.12 * rx, 0]), hc + np.array([0.12 * rx, 0])]))
        elif st == "robot":
            scr = rrect(hc + np.array([0, 0.08 * ry]), 1.45 * rx, 1.2 * ry, 0.28 * ry)
            det.append(Detail("outlined", [scr], (40, 50, 72), width=0.45 * self.ow))
            glow = self.choose([(120, 240, 236), (140, 250, 160), (255, 200, 90), (250, 130, 170)])
            for sg in (-1, 1):
                e = hc + np.array([sg * 0.33 * rx, -0.02 * ry])
                det.append(Detail("fill", [rrect(e, 0.22 * rx, 0.38 * ry, 0.1 * rx)], glow))
            det.append(Detail("line", col=glow, width=0.8 * u, pts=[hc + np.array([-0.22 * rx, 0.42 * ry]), hc + np.array([-0.08 * rx, 0.5 * ry]),
                                                                    hc + np.array([0.08 * rx, 0.5 * ry]), hc + np.array([0.22 * rx, 0.42 * ry])]))
            det.append(Detail("fill", [rrect(hc + np.array([0, -0.86 * ry]), 0.9 * rx, 0.12 * ry, 0.05 * ry)], light_of(c["body"], 0.5)))
            for sg in (-1, 1):
                det.append(Detail("fill", [Ellipse(hc + np.array([sg * 0.85 * rx, -0.75 * ry]), 0.05 * rx, 0.05 * rx)], shade_of(c["body"], 0.8)))
        else:
            sp = self.meta["species"]
            for sg in (-1, 1):
                e = hc + np.array([sg * 0.36 * rx, 0.05 * ry])
                det.append(Detail("fill", [Ellipse(e, 0.1 * rx, 0.15 * ry)], INK))
                det.append(Detail("fill", [Ellipse(e + np.array([-0.03 * rx, -0.05 * ry]), 0.04 * rx, 0.05 * ry)], (255, 255, 255)))
                det.append(Detail("fill", [Ellipse(hc + np.array([sg * 0.62 * rx, 0.38 * ry]), 0.12 * rx, 0.07 * ry)],
                                  tuple(int(0.6 * a + 0.4 * b) for a, b in zip(c["fur"], BLUSH))))
            muzzle = light_of(c["fur"], 0.6) if sp != "fox" else (248, 244, 236)
            det.append(Detail("fill", [Ellipse(hc + np.array([0, 0.42 * ry]), 0.3 * rx, 0.24 * ry)], muzzle))
            if sp == "fox":
                for sg in (-1, 1):
                    det.append(Detail("fill", [Ellipse(hc + np.array([sg * 0.55 * rx, 0.55 * ry]), 0.42 * rx, 0.34 * ry)], (248, 244, 236)))
            nose = hc + np.array([0, 0.3 * ry])
            det.append(Detail("fill", [Poly([nose + np.array([-0.09 * rx, -0.04 * ry]), nose + np.array([0.09 * rx, -0.04 * ry]),
                                             nose + np.array([0, 0.07 * ry])], 0.03 * rx)], (70, 48, 56) if sp != "cat" else (226, 110, 130)))
            m = hc + np.array([0, 0.42 * ry])
            det.append(Detail("line", col=INK, width=0.5 * u, pts=[m + np.array([-0.12 * rx, 0.04 * ry]), m + np.array([-0.05 * rx, 0.09 * ry]),
                                                                  m + np.array([0, 0.03 * ry]), m + np.array([0.05 * rx, 0.09 * ry]),
                                                                  m + np.array([0.12 * rx, 0.04 * ry])]))
            if sp == "cat":
                for sg in (-1, 1):
                    for dy in (-0.02, 0.1):
                        det.append(Detail("line", col=shade_of(c["fur"], 1.0), width=0.35 * u,
                                          pts=[hc + np.array([sg * 0.5 * rx, (0.4 + dy) * ry]), hc + np.array([sg * 0.9 * rx, (0.36 + 1.6 * dy) * ry])]))
                if self.c["fur_name"] == "orange":
                    for dx in (-0.12, 0, 0.12):
                        det.append(Detail("line", col=shade_of(c["fur"], 1.0), width=0.7 * u,
                                          pts=[hc + np.array([dx * rx, -0.95 * ry]), hc + np.array([dx * rx * 0.8, -0.72 * ry])]))
        self.add("head", self.head_prims, c["skin"], parent="torso", joint=self.meta["neck"]["N"], details=det, shade=0.18)

    def hair_front(self):
        u, c, r = self.u, self.c, self.rng
        hc, rx, ry = self.hc, self.hrx, self.hry
        style = self.choose(["bangs", "swoop", "short"])
        lock = self.k.get("lock_len", r.uniform(-0.1, 0.35))
        if self.k.get("lock_hook") and self.meta.get("earrings"):
            e = self.meta["earrings"][0]
            lock = float((e["lobe"][1] + r.uniform(0.35, 0.75) * e["hook_len"] - hc[1]) / ry)
        pts = []
        for t in np.linspace(np.deg2rad(168), np.deg2rad(372), 26):
            pts.append(hc + np.array([1.07 * rx * np.cos(t), 1.07 * ry * np.sin(t) - 0.02 * ry]))
        right = hc + np.array([1.0 * rx, lock * ry])
        left = hc + np.array([-1.0 * rx, lock * ry])
        inner_r = hc + np.array([0.74 * rx, (lock - 0.1) * ry])
        inner_l = hc + np.array([-0.74 * rx, (lock - 0.1) * ry])
        pts += [right, inner_r]
        if style == "bangs":
            n = 5
            xs = np.linspace(0.7, -0.7, 2 * n + 1)
            for i, x in enumerate(xs):
                y = -0.28 if i % 2 == 0 else -0.12
                pts.append(hc + np.array([x * rx, y * ry]))
        elif style == "swoop":
            sg = self.choose([-1, 1])
            seq = [(0.7, -0.15), (0.3, -0.4), (-0.2, -0.32), (-0.7, -0.05)] if sg > 0 else [(0.7, -0.05), (0.2, -0.32), (-0.3, -0.4), (-0.7, -0.15)]
            pts += [hc + np.array([x * rx, y * ry]) for x, y in seq]
        else:
            pts += [hc + np.array([x * rx, -0.45 * ry + 0.08 * ry * np.cos(x * 9)]) for x in np.linspace(0.7, -0.7, 9)]
        pts += [inner_l, left]
        det = [Detail("line", col=light_of(c["hair"], 0.35), width=1.1 * u,
                      pts=[hc + np.array([0.82 * rx * np.cos(t), 0.82 * ry * np.sin(t)]) for t in np.linspace(np.deg2rad(205), np.deg2rad(245), 6)])]
        self.add("hair_front", [Poly(pts, 0.6 * u)], c["hair"], parent="head", details=det, shade=0.15)
        self.meta["hair"] = style

    def hat(self):
        u, r = self.u, self.rng
        hc, rx, ry = self.hc, self.hrx, self.hry
        kind = self.k.get("hat_kind") or self.choose(["top", "bowler", "beanie", "party", "sun"])
        col_name, col = self.choose(HAT)
        band = self.choose([x for x in HAT if x[0] != col_name])[1]
        side = self.k.get("hat_side", self.choose(["left", "right"]))
        hw = rx
        by = hc[1] - (0.72 if self.style != "robot" else 0.95) * ry
        if self.style == "lanky":
            hw = 1.2 * rx
        det = []
        tilt = 0.0
        if kind == "top":
            bw, bt = 1.3 * hw, max(0.12 * hw, 1.2 * u)
            ch, cw = 1.05 * hw, 1.35 * hw
            crown = rrect((hc[0], by - ch / 2), cw, ch, 0.12 * hw)
            det.append(Detail("fill", [rrect((hc[0], by - 0.22 * ch), cw * 1.1, 0.22 * ch, 0)], band))
        elif kind == "bowler":
            bw, bt = 1.18 * hw, max(0.1 * hw, 1.1 * u)
            crown = dome(hc[0], by, 0.66 * hw, 0.7 * hw, 0.5 * bt)
            det.append(Detail("fill", [rrect((hc[0], by - 0.1 * hw), 1.5 * hw, 0.16 * hw, 0)], band))
        elif kind == "beanie":
            bw, bt = 1.06 * hw, max(0.17 * hw, 1.4 * u)
            crown = dome(hc[0], by, 0.98 * hw, 0.85 * hw, 0.5 * bt)
            for x in np.linspace(-0.7, 0.7, 6):
                det.append(Detail("line", col=shade_of(col, 1.0), width=0.5 * u,
                                  pts=[(hc[0] + x * hw, by - 0.2 * hw), (hc[0] + x * hw * 0.9, by - 0.62 * hw * (1 - x * x * 0.6))]))
        elif kind == "party":
            bw, bt = 0.78 * hw, max(0.1 * hw, 1.1 * u)
            crown = Poly([(hc[0] - 0.7 * hw, by), (hc[0] + 0.7 * hw, by), (hc[0] + 0.05 * hw, by - 1.45 * hw)], 0.12 * hw)
            for i, yy in enumerate((0.35, 0.8)):
                det.append(Detail("fill", [rrect((hc[0], by - yy * hw), 2 * hw, 0.16 * hw, 0)], band))
        else:  # sun hat
            bw, bt = 1.75 * hw, max(0.1 * hw, 1.1 * u)
            crown = dome(hc[0], by, 0.72 * hw, 0.62 * hw, 0.5 * bt)
            det.append(Detail("fill", [rrect((hc[0], by - 0.12 * hw), 1.6 * hw, 0.18 * hw, 0)], band))
        brim = Capsule((hc[0] - bw, by), (hc[0] + bw, by), bt)
        prims = [crown, brim]
        if kind in ("beanie", "party"):
            pom_c = (hc[0] + (0.05 * hw if kind == "party" else 0), by - (1.45 * hw if kind == "party" else 0.85 * hw))
            prims.append(Ellipse(pom_c, 0.22 * hw, 0.22 * hw))
            det.append(Detail("fill", [Ellipse(pom_c, 0.22 * hw, 0.22 * hw)], band))
        if kind == "beanie":
            det.append(Detail("fill", [Capsule((hc[0] - bw, by), (hc[0] + bw, by), bt)], light_of(col, 0.3) if sum(col) < 600 else shade_of(col, 1.0)))
        sgn = -1 if side == "left" else 1
        pivot = np.array([hc[0] + sgn * bw, by])
        self.add("hat", prims, col, parent="head", joint=pivot, details=det, shade=0.2)
        self.meta["hat"] = dict(kind=kind, colour=col_name, side=side, pivot=pivot.tolist(), joint_r=bt + self.ow)


# ---------------------------------------------------------------- scene


def char_extent(specs):
    P = np.concatenate([p.poly(2.5) for s in specs for p in s["prims"]])
    return P.min(0), P.max(0)


def knobs_for(motion, rng, style):
    """Difficulty knobs for the target character: occlusion ('none'/'some') and proximity ('near'/'far')."""
    occl = "some" if rng.random() < 0.5 else "none"
    prox = "near" if rng.random() < 0.5 else "far"
    k = dict(occl=occl, prox=prox)
    gap_far = float(rng.uniform(0.9, 2.0))
    gap_near = float(rng.uniform(0.0, 0.25))
    if motion in ("wave", "wiggle_fingers", "bend_elbow"):
        k["raised_layer"] = "front"
        k["hand_gap"] = float(rng.uniform(-0.8, -0.35)) if occl == "some" else (gap_near if prox == "near" else gap_far)
    elif motion in ("nod", "tip_hat"):
        if motion == "tip_hat":
            k["hat"] = True
            k["hand_anchor"] = "hat"
        if occl == "some":
            k["raised_layer"] = "over"
            k["hand_gap"] = float(rng.uniform(-1.0, -0.6))
        else:
            k["raised_layer"] = "front"
            k["hand_gap"] = gap_near if prox == "near" else gap_far
    elif motion == "raise_arm":
        k["down_layer"] = "back" if occl == "some" else "front"
        k["down_angle"] = float(rng.uniform(6, 12) if prox == "near" else rng.uniform(18, 32))
    elif motion == "swing_earring":
        k["earrings"] = True
        k["earring_long"] = prox == "near"
        if style == "robot":
            if occl == "some":
                k["raised_layer"] = "over"
                k["hand_anchor"] = "ear"
                k["hand_gap"] = float(rng.uniform(-0.6, -0.3))
        else:
            k["lock_hook"] = occl == "some"
            if occl != "some":
                k["lock_len"] = float(rng.uniform(-0.15, 0.1))
            k["long_hair"] = False
    elif motion == "wag_tail":
        k["tail"] = True
        k["tail_down"] = occl == "some"
    return k


def build_scene(seed, motion=None, style=None, n_chars=None, size=None):
    """Deterministic scene for (seed, motion). Returns a Scene whose .task describes the target motion."""
    rng = np.random.default_rng([int(seed), 7919])
    motion = motion or MOTIONS[int(rng.integers(len(MOTIONS)))]
    if n_chars is None:
        n_chars = int(rng.choice([1, 2, 3], p=[0.35, 0.4, 0.25]))
    W, H = (1024, 683) if n_chars == 1 else (1200, 600)
    ti = int(rng.integers(n_chars))
    styles = []
    for i in range(n_chars):
        if i == ti:
            styles.append(style or MOTION_STYLES[motion][int(rng.integers(len(MOTION_STYLES[motion])))])
        else:
            styles.append(STYLES[int(rng.integers(len(STYLES)))])
    seeds = [int(x) for x in rng.integers(0, 2 ** 31, n_chars)]
    size_f = size if size is not None else float(rng.uniform(0.62, 1.0))
    knobs = [knobs_for(motion, rng, styles[i]) if i == ti else {} for i in range(n_chars)]
    margin = int(rng.integers(14, 34))
    gy = H - margin
    slot = W / n_chars
    chars_specs, metas = [], []
    for i in range(n_chars):
        st = styles[i]
        f = size_f if i == ti else float(rng.uniform(0.7, 1.0))
        u = f * (H - margin - 16) / (GEOM[st]["height"] + 28)
        cx = slot * (i + 0.5)
        for _ in range(12):
            cb = CharBuilder(i, seeds[i], st, cx, gy, u, knobs[i], W, H)
            specs, meta = cb.build()
            lo, hi = char_extent(specs)
            # centre the character's extent in its slot, shrink if it does not fit
            x_lo, x_hi = slot * i + 8, slot * (i + 1) - 8
            shift = ((x_lo + x_hi) - (lo[0] + hi[0])) / 2
            fits = hi[0] - lo[0] <= x_hi - x_lo and lo[1] >= 6 and hi[1] <= H - 3
            if fits and abs(shift) <= 0.5:
                break
            cx += shift
            if not fits:
                u *= 0.92
        meta.update(u=u, cx=cx, builder=cb)
        chars_specs.append(specs)
        metas.append(meta)
    layers, parts = [], {}
    for i, specs in enumerate(chars_specs):
        parts[f"c{i}_torso"] = PartInfo(f"c{i}_torso", None, None, i)
        for s in specs:
            L = render_part(s["name"], s["prims"], s["fill"], ow=s["ow"], details=s["details"], shade=s["shade"],
                            extent=s["extent"], W=W, H=H)
            layers.append(L)
            if s["name"] != f"c{i}_torso":
                parts[s["name"]] = PartInfo(s["name"], s["parent"], s["joint"], i)
    sc = Scene(W, H, layers, parts, chars=[], seed=int(seed))
    for i, m in enumerate(metas):
        sc.chars.append({k: v for k, v in m.items() if k not in ("builder", "arms")})
    sc.task = define_task(sc, motion, ti, metas[ti])
    return sc


def define_task(sc, motion, ti, meta):
    """Moving sets (layers that rotate together about one pivot) for the motion on character ti."""
    pre = f"c{ti}_"
    names = {L.name for L in sc.layers}
    amp, phase = MOTION_AMP[motion]
    arms = meta["arms"]
    up = next(a for a in arms if a["raised"])
    down = next(a for a in arms if not a["raised"])
    movers, attach = [], []

    def hand_set(a):
        return [pre + n for n in a["finger_names"]] + [pre + f"hand_{a['tag']}"]

    if motion == "wave":
        movers.append(dict(parts=hand_set(up), root=pre + f"hand_{up['tag']}", pivot=up["W"], amp=amp, phase=phase,
                           joint_r=up["pr"] + 3))
        attach = [pre + f"forearm_{up['tag']}"]
    elif motion == "wiggle_fingers":
        for j, (nm, K) in enumerate(zip(up["finger_names"], up["knuckles"])):
            rr = (meta["builder"].g["tr"] if nm.startswith("thumb") else meta["builder"].g["fr"]) * meta["u"]
            movers.append(dict(parts=[pre + nm], root=pre + nm, pivot=K, amp=amp * (1 if j % 2 == 0 else -1), phase=phase,
                               joint_r=rr + 3))
        attach = [pre + f"hand_{up['tag']}"]
    elif motion == "bend_elbow":
        S, E, Wr = up["S"], up["E"], up["W"]
        a, b = Wr - E, S - E
        ang = np.rad2deg(np.arccos(np.clip(np.dot(norm(a), norm(b)), -1, 1)))
        A = float(min(amp, max(ang - 40, 12)))
        sgn = 1 if cross2(a, b) > 0 else -1
        movers.append(dict(parts=[pre + f"forearm_{up['tag']}"] + hand_set(up), root=pre + f"forearm_{up['tag']}",
                           pivot=E, amp=sgn * A, phase=phase, joint_r=up["jr_fore"] + 3))
        attach = [pre + f"upper_arm_{up['tag']}"]
    elif motion == "raise_arm":
        movers.append(dict(parts=[pre + f"upper_arm_{down['tag']}", pre + f"forearm_{down['tag']}"] + hand_set(down),
                           root=pre + f"upper_arm_{down['tag']}", pivot=down["S"], amp=-down["side"] * amp, phase=phase,
                           joint_r=down["ar"] + 3))
        attach = [pre + "torso"]
    elif motion == "nod":
        group = [n for n in (pre + x for x in ("hair_back", "neck", "earring_L", "earring_R", "ear_L", "ear_R", "antenna",
                                                "head", "hair_front", "hat")) if n in names]
        movers.append(dict(parts=group, root=pre + "head", pivot=meta["neck"]["N"], amp=amp, phase=phase,
                           joint_r=meta["neck"]["r"] + 3))
        attach = [pre + "torso"]
    elif motion == "tip_hat":
        h = meta["hat"]
        movers.append(dict(parts=[pre + "hat"], root=pre + "hat", pivot=np.array(h["pivot"]),
                           amp=(-amp if h["side"] == "left" else amp), phase=phase, joint_r=h["joint_r"] + 1))
        attach = [n for n in (pre + "head", pre + "hair_front", pre + "antenna") if n in names]
    elif motion == "swing_earring":
        for e in meta["earrings"]:
            movers.append(dict(parts=[pre + f"earring_{e['tag']}"], root=pre + f"earring_{e['tag']}", pivot=e["lobe"],
                               amp=amp, phase=phase, joint_r=e["joint_r"] + 2))
        attach = [pre + "ear_L", pre + "ear_R"]
    elif motion == "wag_tail":
        t = meta["tail"]
        movers.append(dict(parts=[pre + "tail"], root=pre + "tail", pivot=np.array(t["base"]), amp=amp, phase=phase,
                           joint_r=t["joint_r"] + 1))
        attach = [pre + "torso"]
    for mv in movers:
        mv["pivot"] = tuple(float(v) for v in mv["pivot"])
        mv["amp"] = float(mv["amp"])
        mv["joint_r"] = float(mv["joint_r"])
    targets = sorted({p for mv in movers for p in mv["parts"]}, key=lambda n: sc.index(n))
    return dict(motion=motion, char=ti, targets=targets, attach=attach, movers=movers)
