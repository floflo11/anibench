"""Write synthetic tasks in the exact anibench task format.

tasks_synth/SNNN/{spec.json, prompt.md, image.png, allowed.png, target.png, skull.png?} + tasks_synth/index.json

Every task is screened before it is kept: the reference animation (layer-exact, see check_reference.py) is
simulated in numpy and graded with src/graders.py. A seed whose reference fails is replaced by the next seed for
the same slot (seed = 1000 * slot + attempt) and the rejection is logged in index.json.

Usage: python src/synth/make_tasks.py [N] [out_dir]
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from tasks import PROMPT, SUFFIX, rotate_mask  # noqa: E402
from synth.scene import MOTIONS, build_scene  # noqa: E402
from synth.factors import compute_factors, target_masks  # noqa: E402

MIN_VISIBLE = 150  # px; a target hidden almost entirely is not a meaningful task
TIER = {"wiggle_fingers": 2, "tip_hat": 2}
POS = {1: [""], 2: ["on the left", "on the right"], 3: ["on the left", "in the middle", "on the right"]}


def describe(sc):
    ti = sc.task["char"]
    ch = sc.chars[ti]
    st = ch["style"]
    noun = {"chibi": "kid", "lanky": "tall person", "robot": "robot"}.get(st) or ch.get("species", "animal")
    who = f"the {noun}"
    n = len(sc.chars)
    if n > 1:
        who += " " + POS[n][ti]
    pos = "their" if st in ("chibi", "lanky") else "its"
    return who, pos, ch


def instruction(sc):
    who, pos, ch = describe(sc)
    m = sc.task["motion"]
    if m == "wave":
        return f"Make {who} wave {pos} raised hand, bending at the wrist."
    if m == "wiggle_fingers":
        return f"Make {who} wiggle the fingers and thumb of {pos} raised hand; the palm stays still."
    if m == "bend_elbow":
        return f"Make {who} bend {pos} raised arm further at the elbow and straighten it again; the upper arm stays still."
    if m == "raise_arm":
        return f"Make {who} raise {pos} lowered arm out to the side from the shoulder and lower it again."
    if m == "nod":
        s = f"Make {who} tilt {pos} head from side to side, pivoting at the neck"
        if "hat" in ch:
            s += f"; {pos} hat stays on {pos} head"
        return s + "."
    if m == "tip_hat":
        h = ch["hat"]
        rim = "brim" if h["kind"] in ("top", "bowler", "sun") else "rim"
        return (f"Make {who} tip {pos} hat up and back in greeting, pivoting on the {h['side']} end of the {rim} "
                f"(viewer's {h['side']}).")
    if m == "swing_earring":
        return f"Make the {ch['earring_colour']} earrings of {who} swing gently, as if in a breeze."
    if m == "wag_tail":
        kind = ch["tail"]["kind"]
        tail = "cable tail" if kind == "cable" else "tail"
        return f"Make {who} wag {pos} {tail} from its base."
    raise ValueError(m)


def allowed_region(sc):
    """Sweep of every moving set (full, un-occluded masks) about its pivot over +-2x amplitude, plus the target, dilated."""
    vis, _ = target_masks(sc)
    acc = vis.copy()
    for mv in sc.task["movers"]:
        full = np.zeros_like(vis)
        for p in mv["parts"]:
            full |= sc.full_mask(p)
        a = int(round(abs(mv["amp"]) * 2))
        for deg in range(-a, a + 1, 3):
            acc |= rotate_mask(full, mv["pivot"], deg)
        acc |= rotate_mask(full, mv["pivot"], a) | rotate_mask(full, mv["pivot"], -a) | full
    return ndimage.binary_dilation(acc, iterations=10)


def skull_mask(sc):
    """Head/hair pixels under the hat: must stay filled when the hat tips."""
    pre = f"c{sc.task['char']}_"
    hat = sc.full_mask(pre + "hat")
    under = np.zeros_like(hat)
    for n in ("head", "hair_front"):
        if any(L.name == pre + n for L in sc.layers):
            under |= sc.full_mask(pre + n)
    return under & hat


def save_mask(m, p):
    Image.fromarray((m * 255).astype(np.uint8)).save(p)


def make_spec(task_id, sc):
    m = sc.task["motion"]
    kind = "rotate_hat" if m == "tip_hat" else "rotate"
    graders = ["G1", "G2", "G3", "G4", "G5", "G6"]
    if kind == "rotate_hat":
        graders.remove("G2")  # a tipped hat is meant to come apart from the head on one side
    pivots = [[int(round(mv["pivot"][0])), int(round(mv["pivot"][1]))] for mv in sc.task["movers"]]
    amp = float(max(abs(mv["amp"]) for mv in sc.task["movers"]))
    f = compute_factors(sc)
    ch = sc.chars[sc.task["char"]]
    f.update(motion=m, n_chars=len(sc.chars), species=ch.get("species"),
             knobs={k: v for k, v in ch.get("knobs", {}).items() if k in ("occl", "prox")},
             char_scale_u=round(float(ch["u"]), 3), n_moving_parts=len(sc.task["targets"]))
    spec = dict(id=task_id, tier=TIER.get(m, 1), image=f"synth_{task_id}", width=sc.width, height=sc.height,
                instruction=instruction(sc), parts=list(sc.task["targets"]), kind=kind, amp=round(amp, 2),
                graders=graders, pivots=pivots, area_tol=0.5, blob_allow=3 if kind == "rotate_hat" else 0,
                graders_all=list(graders))
    if kind == "rotate_hat":
        spec["skull"] = True
    spec["factors"] = f
    spec["synth"] = dict(generator="synth-v1", scene_seed=int(sc.seed), motion=m,
                         movers=[dict(parts=mv["parts"], pivot=[round(mv["pivot"][0], 2), round(mv["pivot"][1], 2)],
                                      amp=round(mv["amp"], 3), phase=mv["phase"]) for mv in sc.task["movers"]])
    return spec


def write_task(task_id, seed, motion, out_root, sc=None):
    sc = sc or build_scene(seed, motion)
    d = Path(out_root) / task_id
    d.mkdir(parents=True, exist_ok=True)
    spec = make_spec(task_id, sc)
    Image.fromarray(sc.composite()).save(d / "image.png")
    vis, _ = target_masks(sc)
    save_mask(vis, d / "target.png")
    save_mask(allowed_region(sc), d / "allowed.png")
    if spec.get("skull"):
        save_mask(skull_mask(sc), d / "skull.png")
    (d / "spec.json").write_text(json.dumps(spec, indent=1))
    (d / "prompt.md").write_text(PROMPT.format(W=sc.width, H=sc.height, instruction=spec["instruction"], suffix=SUFFIX))
    return spec


def generate(n=160, out=ROOT / "tasks_synth", max_attempts=10):
    from synth.check_reference import simulate_grade
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    index, rejected = [], []
    for i in range(n):
        motion = MOTIONS[i % len(MOTIONS)]
        tid = f"S{i + 1:03d}"
        for att in range(max_attempts):
            seed = 1000 * (i + 1) + att
            sc = build_scene(seed, motion)
            spec = write_task(tid, seed, motion, out, sc=sc)
            g = simulate_grade(sc, out / tid)
            if spec["factors"]["target_area_px"] < MIN_VISIBLE:
                g = {"pass": False, "visible": {"ok": False}}
            if g["pass"]:
                break
            rejected.append(dict(id=tid, seed=seed, motion=motion, failed=[k for k, v in g.items() if k != "pass" and not v["ok"]],
                                 factors={k: spec["factors"][k] for k in ("occlusion_pct", "min_dist_px", "target_area_px", "style")},
                                 knobs=spec["factors"]["knobs"]))
            shutil.rmtree(out / tid)
        else:
            print(tid, "no passing seed", flush=True)
            continue
        spec["synth"]["attempts"] = att + 1
        (out / tid / "spec.json").write_text(json.dumps(spec, indent=1))
        index.append(spec)
        f = spec["factors"]
        print(tid, motion, f["style"], f"area={f['target_area_px']} occ={f['occlusion_pct']} chain={f['chain_length']} "
              f"dist={f['min_dist_px']} att={att + 1}", flush=True)
    (out / "index.json").write_text(json.dumps(index, indent=1))
    (out / "rejected.json").write_text(json.dumps(rejected, indent=1))
    return index, rejected


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 160
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tasks_synth"
    generate(n, out)
