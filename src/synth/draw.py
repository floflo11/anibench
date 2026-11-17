"""Shape primitives and part rasterisation for the synthetic characters.

Every part is a union of primitives (capsules, ellipses, rounded polygons) drawn with a flat fill, a soft
cel-shadow band and a dark outline, supersampled SS x and box-filtered down, so edges are anti-aliased.
A part becomes a Layer: an RGBA crop plus its offset in the scene.
"""
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw

SS = 4                    # supersampling factor
OUTLINE = (46, 38, 54)    # outline ink (warm near-black)
SHADE_INK = (60, 40, 110)  # shadows lean cool


@dataclass
class Layer:
    name: str
    rgba: np.ndarray      # (h, w, 4) uint8
    x0: int = 0
    y0: int = 0


# ---------------------------------------------------------------- primitives (1x float coords, y down)

def _arc(cx, cy, r, a0, a1, n=20):
    t = np.linspace(a0, a1, n)
    return np.stack([cx + r * np.cos(t), cy + r * np.sin(t)], 1)


class Prim:
    def poly(self, d=0.0):
        """Polygon (N, 2) of the shape grown by d px."""
        raise NotImplementedError


class Capsule(Prim):
    """Tapered capsule from p0 (radius r0) to p1 (radius r1)."""

    def __init__(self, p0, p1, r0, r1=None):
        self.p0, self.p1 = np.asarray(p0, float), np.asarray(p1, float)
        self.r0, self.r1 = float(r0), float(r1 if r1 is not None else r0)

    def poly(self, d=0.0):
        r0, r1 = self.r0 + d, self.r1 + d
        v = self.p1 - self.p0
        L = np.hypot(*v)
        if L < 1e-6:
            return _arc(*self.p0, max(r0, r1), 0, 2 * np.pi, 48)
        a = np.arctan2(v[1], v[0])
        # tangent angle offset for unequal radii
        s = np.clip((r0 - r1) / L, -0.99, 0.99)
        phi = np.arccos(s)
        end1 = _arc(*self.p1, r1, a - phi, a + phi, 24)
        end0 = _arc(*self.p0, r0, a + phi, a + 2 * np.pi - phi, 24)
        return np.concatenate([end1, end0])


class Ellipse(Prim):
    def __init__(self, c, rx, ry, rot=0.0):
        self.c, self.rx, self.ry, self.rot = np.asarray(c, float), float(rx), float(ry), float(rot)

    def poly(self, d=0.0):
        t = np.linspace(0, 2 * np.pi, 72, endpoint=False)
        x, y = (self.rx + d) * np.cos(t), (self.ry + d) * np.sin(t)
        c, s = np.cos(self.rot), np.sin(self.rot)
        return np.stack([self.c[0] + c * x - s * y, self.c[1] + s * x + c * y], 1)


class Poly(Prim):
    """Polygon with filleted corners (radius r); growing by d offsets the rounded outline outward."""

    def __init__(self, pts, r=0.0):
        self.pts, self.r = np.asarray(pts, float), float(r)

    def poly(self, d=0.0):
        P = self.pts
        n = len(P)
        # orientation: make it counter-clockwise in y-down coords consistently
        area = 0.5 * np.sum(P[:, 0] * np.roll(P[:, 1], -1) - np.roll(P[:, 0], -1) * P[:, 1])
        sgn = 1.0 if area > 0 else -1.0
        out = []
        for i in range(n):
            a, b, c = P[i - 1], P[i], P[(i + 1) % n]
            u, w = a - b, c - b
            lu, lw = np.hypot(*u), np.hypot(*w)
            if lu < 1e-6 or lw < 1e-6:
                continue
            u, w = u / lu, w / lw
            cosang = np.clip(np.dot(u, w), -0.999, 0.999)
            ang = np.arccos(cosang)
            r = min(self.r, 0.45 * min(lu, lw) * np.tan(ang / 2))
            # fillet centre lies on the bisector
            bis = u + w
            bis /= max(np.hypot(*bis), 1e-9)
            cross = u[0] * w[1] - u[1] * w[0]
            convex = (cross * sgn) < 0
            if r > 0.05:
                dc = r / np.sin(ang / 2)
                cen = b + bis * dc
                t0 = b + u * (r / np.tan(ang / 2)) - cen
                t1 = b + w * (r / np.tan(ang / 2)) - cen
                a0, a1 = np.arctan2(t0[1], t0[0]), np.arctan2(t1[1], t1[0])
                da = (a1 - a0 + np.pi) % (2 * np.pi) - np.pi
                rr = r + d if convex else max(r - d, 0.0)
                tt = np.linspace(a0, a0 + da, 10)
                out.extend(np.stack([cen[0] + rr * np.cos(tt), cen[1] + rr * np.sin(tt)], 1))
            else:
                out.append(b - bis * d * (1 if convex else -1) / max(np.sin(ang / 2), 0.2))
        return np.asarray(out)


def rrect(c, w, h, r, rot=0.0):
    c = np.asarray(c, float)
    x, y = w / 2, h / 2
    pts = np.array([(-x, -y), (x, -y), (x, y), (-x, y)])
    cs, sn = np.cos(rot), np.sin(rot)
    pts = np.stack([c[0] + cs * pts[:, 0] - sn * pts[:, 1], c[1] + sn * pts[:, 0] + cs * pts[:, 1]], 1)
    return Poly(pts, r)


# ---------------------------------------------------------------- painting


def _mix(a, b, t):
    return tuple(int(round(x * (1 - t) + y * t)) for x, y in zip(a, b))


def shade_of(col, amt=0.16):
    """Cel-shadow tone. Kept within ~20 levels per channel so it reads as shading, not as a different part."""
    s = _mix(col, SHADE_INK, amt)
    return tuple(int(np.clip(c - np.clip(c - x, -20, 20), 0, 255)) for c, x in zip(col, s))


def light_of(col, amt=0.35):
    return _mix(col, (255, 255, 255), amt)


@dataclass
class Detail:
    kind: str                 # "fill" | "line" | "outlined"
    prims: list = field(default_factory=list)
    col: tuple = (0, 0, 0)
    width: float = 1.0        # line width (1x px) for "line"; outline width for "outlined"
    pts: list = None          # polyline for "line"
    clip: bool = True


class Canvas:
    """SS-scale drawing surface for one part's local crop."""

    def __init__(self, x0, y0, w, h):
        self.x0, self.y0, self.w, self.h = x0, y0, w, h

    def to_local(self, P):
        P = np.asarray(P, float)
        return [((x - self.x0) * SS, (y - self.y0) * SS) for x, y in P]

    def mask(self, prims, d=0.0):
        im = Image.new("L", (self.w * SS, self.h * SS), 0)
        dr = ImageDraw.Draw(im)
        for p in prims:
            dr.polygon(self.to_local(p.poly(d)), fill=255)
        return np.array(im) > 127

    def line_mask(self, pts, width):
        im = Image.new("L", (self.w * SS, self.h * SS), 0)
        dr = ImageDraw.Draw(im)
        loc = self.to_local(pts)
        wpx = max(1, int(round(width * SS)))
        dr.line(loc, fill=255, width=wpx, joint="curve")
        r = wpx / 2
        for x, y in (loc[0], loc[-1]):
            dr.ellipse([x - r, y - r, x + r, y + r], fill=255)
        return np.array(im) > 127


def bbox_of(prims, pad):
    P = np.concatenate([p.poly(pad) for p in prims])
    x0, y0 = np.floor(P.min(0)).astype(int) - 2
    x1, y1 = np.ceil(P.max(0)).astype(int) + 2
    return x0, y0, x1 - x0, y1 - y0


def render_part(name, prims, fill, ow=2.4, details=(), shade=0.25, shade_dir=(1.0, 0.8), outline=OUTLINE,
                extent=(), W=None, H=None):
    """Rasterise a part. Returns a Layer clipped to the canvas (W, H) if given.

    shade: shadow band width as a fraction of the part's smaller bbox side (0 = no shading).
    extent: extra prims that only enlarge the crop (for unclipped details).
    """
    x0, y0, w, h = bbox_of(list(prims) + list(extent), ow + 1)
    cv = Canvas(x0, y0, w, h)
    inner = cv.mask(prims)
    outer = cv.mask(prims, ow)
    rgb = np.empty(inner.shape + (3,), np.uint8)
    rgb[:] = fill
    if shade > 0:
        ys, xs = np.nonzero(inner)
        if len(xs):
            side = min(xs.max() - xs.min(), ys.max() - ys.min())
            k = max(1, int(round(shade * side)))
            dx, dy = int(round(k * shade_dir[0])), int(round(k * shade_dir[1]))
            sh = np.zeros_like(inner)
            # pixel p is lit if p + (dx, dy) is still inside the part
            src = np.zeros_like(inner)
            src[:inner.shape[0] - dy if dy else None, :inner.shape[1] - dx if dx else None] = inner[dy:, dx:]
            sh = inner & ~src
            rgb[sh] = shade_of(fill)
    alpha = outer.copy()
    for dt in details:
        if dt.kind == "line":
            m = cv.line_mask(dt.pts, dt.width)
        else:
            m = cv.mask(dt.prims)
        if dt.kind == "outlined":
            mo = cv.mask(dt.prims, dt.width)
            if dt.clip:
                mo &= inner
            rgb[mo] = outline
            if not dt.clip:
                alpha |= mo
        if dt.clip:
            m &= inner
        else:
            alpha |= m
        rgb[m] = dt.col
    ring = outer & ~inner
    rgb[ring] = outline
    a = (alpha * 255).astype(np.uint8)
    im = Image.fromarray(np.dstack([rgb, a]), "RGBA").resize((w, h), Image.BOX)
    arr = np.array(im)
    arr[arr[..., 3] == 0] = 0
    L = Layer(name=name, rgba=arr, x0=int(x0), y0=int(y0))
    if W is not None:
        L = clip_layer(L, W, H)
    return L


def clip_layer(L, W, H):
    x0, y0 = max(L.x0, 0), max(L.y0, 0)
    x1, y1 = min(L.x0 + L.rgba.shape[1], W), min(L.y0 + L.rgba.shape[0], H)
    if x1 <= x0 or y1 <= y0:
        return Layer(L.name, np.zeros((1, 1, 4), np.uint8), 0, 0)
    return Layer(L.name, L.rgba[y0 - L.y0:y1 - L.y0, x0 - L.x0:x1 - L.x0].copy(), x0, y0)


def full_canvas(L, W, H, ch=None):
    """Place a layer's crop on a full (H, W[, 4]) canvas."""
    out = np.zeros((H, W, 4), np.uint8)
    h, w = L.rgba.shape[:2]
    out[L.y0:L.y0 + h, L.x0:L.x0 + w] = L.rgba
    return out if ch is None else out[..., ch]
