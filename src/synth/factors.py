"""Controlled difficulty factors of a synthetic task, measured exactly from the layers."""
import numpy as np
from scipy import ndimage


def target_masks(sc):
    vis = np.zeros((sc.height, sc.width), bool)
    full = np.zeros_like(vis)
    for n in sc.task["targets"]:
        vis |= sc.visible_mask(n)
        full |= sc.full_mask(n)
    return vis, full


def compute_factors(sc):
    """target_area_px: visible pixels of the moving part(s) (= target.png).
    target_full_area_px: pixels the part(s) would cover if nothing were in front.
    occlusion_pct: share of the full part hidden by other (non-moving) parts in front.
    chain_length: articulated joints from the torso (root) to the moving part.
    min_dist_px: gap in px between the visible target and the nearest visible part that is neither moving nor the
        part it is attached to (0 = touching). Measured over the whole image (other characters included).
    """
    t = sc.task
    vis, full = target_masks(sc)
    excl = set(t["targets"]) | set(t.get("attach", []))
    other = np.zeros_like(vis)
    for L in sc.layers:
        if L.name not in excl:
            other |= sc.visible_mask(L.name)
    if other.any() and vis.any():
        dist = ndimage.distance_transform_edt(~other)
        gap = max(0.0, float(dist[vis].min()) - 1.0)
    else:
        gap = float(max(sc.width, sc.height))
    fa = int(full.sum())
    root = t["movers"][0]["root"]
    ch = sc.chars[t["char"]] if sc.chars else {}
    f = dict(target_area_px=int(vis.sum()), target_full_area_px=fa,
             occlusion_pct=round(100.0 * (1 - (vis & full).sum() / max(fa, 1)), 2),
             chain_length=int(sc.chain_length(root)), min_dist_px=round(gap, 2),
             style=ch.get("style"), seed=int(sc.seed))
    return f
