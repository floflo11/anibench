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
