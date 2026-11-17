"""Alternate valid animators for the false-fail analysis (WS7, task 2.2).

Each style writes <out>/index.html (+ PNG layers) for one task, following the same output contract a model
gets (tasks/<id>/prompt.md). They are written independently of src/reference.py and differ from it in
technique, timing, amplitude and how the uncovered area is filled. See docs/alt_refs.md for what counts as
a valid animation per task type and for which inputs the styles may read (src/alt_refs/common.py).

    from alt_refs import VARIANTS, build, applicable
    build("T01", "easing-sine_small", out_dir)
"""
from pathlib import Path

from . import alt_impl, easing, follow_through, squash_stretch
from .common import task_info

VARIANTS = {
    # easing: motion curves and amplitudes (Sprite + sprite.center anchor; white fill)
    "easing-sine_typ": dict(style="easing", curve="sine", level="typ"),
    "easing-sine_small": dict(style="easing", curve="sine", level="lo"),
    "easing-cubic_large": dict(style="easing", curve="cubic", level="hi"),
    "easing-bounce": dict(style="easing", curve="bounce", level="typ"),
    # squash and stretch: non-rigid scale along the motion axis, anchored at the joint (matrix transforms)
    "squash_stretch-mild": dict(style="squash_stretch", k=0.08),
    "squash_stretch-strong": dict(style="squash_stretch", k=0.15),
    # follow-through: SkinnedMesh bone chains with distal lag (overlapping action)
    "follow_through-lag": dict(style="follow_through", lag=0.10),
    "follow_through-drag": dict(style="follow_through", lag=0.22),
    # different implementation techniques
    "alt_impl-canvas2d": dict(style="alt_impl", tech="canvas2d"),
    "alt_impl-shader": dict(style="alt_impl", tech="shader"),
    # different but reasonable pivot placement (rotations only)
    "pivot-inward": dict(style="pivot", shift="inward"),
    "pivot-lateral": dict(style="pivot", shift="lateral"),
}
STYLES = sorted({v["style"] for v in VARIANTS.values()})


def applicable(tid, variant):
    v = VARIANTS[variant]
    if v["style"] != "pivot":
        return True
    from .common import MODE, action_for, task_defs
    d = task_defs()[tid]
    return d["kind"] != "human" and all(MODE[action_for(p, d["kind"], d["instruction"])] == "rot" for p in d["parts"])


def build(tid, variant, out, task_dir=None):
    """Write the page for task `tid` in style `variant` to directory `out`. Returns the index.html path."""
    v = dict(VARIANTS[variant])
    style = v.pop("style")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    info = task_info(tid, task_dir)
    if style == "easing":
        easing.build(info, out, **v)
    elif style == "pivot":
        easing.build(info, out, curve="sine", level="typ", pivot_shift=v["shift"])
    elif style == "squash_stretch":
        squash_stretch.build(info, out, **v)
    elif style == "follow_through":
        follow_through.build(info, out, **v)
    elif style == "alt_impl":
        alt_impl.build(info, out, **v)
    else:
        raise ValueError(variant)
    return out / "index.html"
