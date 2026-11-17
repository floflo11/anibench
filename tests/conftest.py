"""Tiny synthetic tasks for grader tests (no Chrome needed).

Scene: a 64x64 white canvas, a static grey "forearm" (not part of the target) and a dark
"hand" (the target part) touching it. Frames are built by pasting the hand at an offset
over a base where its original footprint has been erased to white, the same way the
reference animator layers a sprite over an erased base.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

S = 64
WHITE = 255
ARM = (150, 150, 150)
HAND = (60, 40, 30)


def rect(y0, y1, x0, x1):
    m = np.zeros((S, S), bool)
    m[y0:y1, x0:x1] = True
    return m


def write_task(d, image, target, allowed, graders=("G2b",), skull=None, **spec_extra):
    d = Path(d)
    d.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image).save(d / "image.png")
    Image.fromarray((target * 255).astype(np.uint8)).save(d / "target.png")
    Image.fromarray((allowed * 255).astype(np.uint8)).save(d / "allowed.png")
    if skull is not None:
        Image.fromarray((skull * 255).astype(np.uint8)).save(d / "skull.png")
    spec = dict(id="TX", width=S, height=S, kind="rotate", amp=10, parts=["hand"],
                graders=list(graders), pivots=[[32, 40]], area_tol=0.5, blob_allow=0)
    spec.update(spec_extra)
    (d / "spec.json").write_text(json.dumps(spec))
    return d


def paint(base, mask, colour):
    out = base.copy()
    out[mask] = colour
    return out


def shifted(mask, dy, dx):
    out = np.zeros_like(mask)
    ys, xs = np.nonzero(mask)
    ys, xs = ys + dy, xs + dx
    ok = (ys >= 0) & (ys < S) & (xs >= 0) & (xs < S)
    out[ys[ok], xs[ok]] = True
    return out


class Scene:
    """A forearm (rows 40-60) with a hand (rows 20-40) sitting on top of it."""

    def __init__(self, hand_pieces):
        self.arm = rect(40, 60, 26, 38)
        self.pieces = hand_pieces
        self.hand = np.any(hand_pieces, axis=0)
        self.image = paint(paint(np.full((S, S, 3), WHITE, np.uint8), self.arm, ARM), self.hand, HAND)
        self.erased = paint(self.image, self.hand, (WHITE,) * 3)
        self.allowed = rect(4, 63, 4, 60)

    def frame(self, offsets):
        """offsets: one (dy, dx) per hand piece; pieces are pasted over the erased base."""
        f = self.erased.copy()
        for m, (dy, dx) in zip(self.pieces, offsets):
            f[shifted(m, dy, dx)] = HAND
        return f

    def frames(self, offsets_per_frame):
        return np.stack([self.frame(o) for o in offsets_per_frame])


def sway(n=9, amp=6):
    """dx per frame: 0 -> amp -> 0 -> -amp -> 0 (a seamless loop)."""
    return [int(round(amp * np.sin(2 * np.pi * i / (n - 1)))) for i in range(n)]


@pytest.fixture
def one_piece_hand():
    # palm (rows 26-40) plus a "thumb" (rows 20-26) on its left: one connected piece
    palm = rect(26, 40, 28, 36)
    thumb = rect(20, 26, 28, 32)  # 24 px
    return Scene([palm, thumb])


@pytest.fixture
def two_piece_part():
    # two separate earrings, each 6x6 = 36 px, not touching the arm
    a = rect(10, 16, 14, 20)
    b = rect(10, 16, 40, 46)
    sc = Scene([a, b])
    return sc


@pytest.fixture
def thumb_on_arm():
    # palm sits on the forearm; the thumb hangs off its left side and also touches the forearm.
    # If the palm sways sideways and the thumb stays behind, the whole region is still one
    # blob (thumb -> forearm -> palm), so G2 cannot see the detached thumb.
    palm = rect(26, 40, 28, 36)
    thumb = rect(30, 41, 24, 28)  # 44 px, touches both the palm and the forearm
    return Scene([palm, thumb])


# ---------------------------------------------------------------- textured rotating parts (grader v3)

class RotScene:
    """A 128x128 canvas: a static textured 'forearm' and a textured 'hand' attached at a wrist pivot.
    Frames rotate the hand sprite about a pivot (nearest neighbour, inverse mapping) over a base where its
    footprint has been erased to white, like the reference animator. Textures are seeded noise."""
    N = 128

    def __init__(self, hand=None, arm=None, seed=0, hand_rgb=(150, 80, 50), arm_rgb=(60, 70, 140), texture="noise"):
        n = self.N
        yy, xx = np.mgrid[:n, :n]
        self.arm = arm if arm is not None else ((xx >= 56) & (xx < 72) & (yy >= 70) & (yy < 118))
        self.hand = hand if hand is not None else ((((xx - 64) / 14.0) ** 2 + ((yy - 44) / 26.0) ** 2) <= 1) & (yy < 70)
        rng = np.random.default_rng(seed)
        if texture == "strands":  # hair-like: 2 px strands along the part's axis
            tex = np.where((xx // 2) % 2 == 0, -55, 55)[..., None] + rng.integers(-10, 11, (n, n, 1))
        else:
            tex = rng.integers(-45, 46, (n, n, 1))
        img = np.full((n, n, 3), 255, np.int16)
        img[self.arm] = (np.array(arm_rgb) + tex)[self.arm]
        img[self.hand] = (np.array(hand_rgb) + tex)[self.hand]
        self.image = np.clip(img, 0, 255).astype(np.uint8)
        self.pivot = (64, 69)
        self.allowed = ((xx - 64) ** 2 + (yy - 69) ** 2 <= 62 ** 2) & (yy < 80)

    def frame(self, deg, pivot=None, keep=None, hide=False, occluder=None, base=None, erase=True):
        """Rotate the hand by deg about pivot. keep: hand pixels that stay put (left behind).
        occluder: (mask, rgb image) drawn on top of everything (a static part in front).
        erase=False leaves the original hand in place under the moving copy (ghosting)."""
        n = self.N
        px, py = pivot or self.pivot
        moving = self.hand & ~keep if keep is not None else self.hand
        out = (base if base is not None else self.image).copy()
        if erase:
            out[moving] = 255
        if not hide:
            yy, xx = np.mgrid[:n, :n].astype(float)
            t = np.deg2rad(deg)
            sx = np.cos(t) * (xx - px) + np.sin(t) * (yy - py) + px
            sy = -np.sin(t) * (xx - px) + np.cos(t) * (yy - py) + py
            ix, iy = np.rint(sx).astype(int), np.rint(sy).astype(int)
            ok = (ix >= 0) & (ix < n) & (iy >= 0) & (iy < n)
            src = np.zeros((n, n), bool)
            src[ok] = moving[iy[ok], ix[ok]]
            out[src] = self.image[iy[src], ix[src]]
        if occluder is not None:
            m, rgb = occluder
            out[m] = rgb[m]
        return out

    def swing(self, amp=20, n=13, **kw):
        degs = [amp * np.sin(2 * np.pi * i / (n - 1)) for i in range(n)]
        return np.stack([self.frame(d, **kw) for d in degs])


@pytest.fixture
def rot_scene():
    return RotScene()


def write_rot_task(d, sc, graders, amp=20, **extra):
    """Task files for a RotScene (pivot at the wrist)."""
    return write_task(d, sc.image, sc.hand, sc.allowed, graders=graders, pivots=[list(sc.pivot)], amp=amp,
                      width=sc.N, height=sc.N, **extra)
