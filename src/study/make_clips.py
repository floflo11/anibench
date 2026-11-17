"""Build the clips, manifest and key for the human study (E4, docs/human_study.md).

For every sampled run it writes, under <out>/rater/clips/ (ids are random, nothing names the model):
  <id>.mp4 (or .webp/.gif without ffmpeg)  the clip raters watch. Four synchronized panels:
                                           original still | animation, zoom of the original | zoom of the
                                           animation (the zoom box is the one zoom_gifs.py uses).
and, under <out>/judge_media/ (for judges that take images rather than video; raters do not need them):
  <id>_orig.png, <id>_origzoom.png         the original image at full resolution, and its zoom
  <id>_sheet.png, <id>_zoom.png            3x3 contact sheets of frames (t = 0 ... 1.92 s), full and zoomed
and two JSON files:
  rater/manifest.json  rater-facing: clip id, task, instruction, sizes, paths (relative to rater/).
                       No model, setting or grades. Ship the whole rater/ folder (manifest + clips/).
  key.json             private, next to rater/: clip id -> run, model, setting, grader results,
                       attention-check flag and the expected answer. Raters never get this file.

Five attention-check clips (reference solutions and obviously broken copies from validation/) are added
to every study; they look like any other clip in the manifest and are flagged only in the key.

python3 src/study/make_clips.py --out build/study/pilot --n 600 --seed 0          # sample from runs/
python3 src/study/make_clips.py --out build/study/x kimi/T01/1 qwen/T03/1           # given runs
python3 src/study/make_clips.py --out build/study/pilot --split 100                  # rater batches
"""
import argparse
import hashlib
import json
import os
import random
import secrets
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from study.common import DEFECTS, KEY_SCHEMA, MANIFEST_SCHEMA, QUESTION  # noqa: E402
from zoom_gifs import zbox_mask  # noqa: E402

FPS = 12            # 24 distinct frames per 2 s cycle (render.py renders 25; the last repeats t = 0)
LOOPS = 3           # cycles encoded per video, so the browser's own loop seam comes once every 6 s
SHEET_IDX = [0, 3, 6, 9, 12, 15, 18, 21, 23]
BG = (232, 232, 232)
INK = (40, 40, 40)

# Built-in attention checks: obvious passes (reference solutions) and obvious failures.
ATTENTION = [
    dict(task="T01", variant="ref", expect_pass=True, defects=[]),
    dict(task="T09", variant="ref", expect_pass=True, defects=[]),
    dict(task="T06", variant="whole", expect_pass=False, defects=["outside_moved"]),
    dict(task="T02", variant="frozen", expect_pass=False, defects=["barely_moves"]),
    dict(task="T20", variant="wrong_part", expect_pass=False, defects=["outside_moved", "barely_moves"]),
]


# ---------------------------------------------------------------- runs

def checks_of(g):
    """grade json -> {check: True/False/None} (None = not applicable), or None if the run has no grades."""
    grades = g.get("grades")
    if not grades:
        return None
    return {k: (None if v.get("ok") is None else bool(v["ok"]))
            for k, v in grades.items() if k != "pass" and isinstance(v, dict)}


def setting_of(g):
    """Same rule as report.setting_of: pre-protocol local runs are chat, Valkyrie runs are core."""
    return g.get("setting") or ("core" if g.get("source") == "valkyrie" else "chat")


def task_spec(task):
    return json.loads((ROOT / "tasks" / task / "spec.json").read_text())


def frames_source(d, stage):
    """Pre-rendered frames for a run dir, if any: frames_<stage>.npz, frames.npz or frames/*.png."""
    for p in (d / f"frames_{stage}.npz", d / "frames.npz"):
        if p.exists():
            return str(p)
    if (d / "frames").is_dir() and any((d / "frames").glob("*.png")):
        return str(d / "frames")
    return None


def run_item(d, include_ungraded=False, explicit=False):
    """One run dir -> item dict, or None if there is nothing to show (or no grades, unless allowed)."""
    d = Path(d)
    for stage in ("repair", "first", None):
        gp = d / (f"grade_{stage}.json" if stage else "grade.json")
        if gp.exists() or stage is None:
            break
    g = json.loads(gp.read_text()) if gp.exists() else {}
    stage = g.get("stage") or stage or "first"
    html = next((p for p in (d / f"index_{stage}.html", d / "index.html") if p.exists()), None)
    frames = frames_source(d, stage)
    if html is None and frames is None:
        return None
    status = g.get("status", "UNGRADED")
    if status in ("API_ERROR", "NO_HTML", "RUNTIME"):
        return None
    checks = checks_of(g)
    if checks is None and not (include_ungraded or explicit):
        return None
    task = g.get("task") or d.parent.name
    model = g.get("model") or d.parent.parent.name
    try_ = str(g.get("try_") or d.name)
    spec = task_spec(task)
    return dict(run=f"{model}/{task}/{try_}", model=model, task=task, try_=try_, stage=stage,
                setting=setting_of(g), status=status, checks=checks,
                passed=(status == "PASS") if checks is not None else None,
                html=str(html) if html else None, frames=frames, dir=str(d),
                width=spec["width"], height=spec["height"], instruction=spec["instruction"], attention=False)


def discover_runs(runs_dir=None, include_ungraded=False):
    runs_dir = Path(runs_dir or ROOT / "runs")
    out = []
    for d in sorted(runs_dir.glob("*/T*/*")):
        if d.is_dir():
            it = run_item(d, include_ungraded)
            if it:
                out.append(it)
    return out


def resolve_runs(args, runs_dir=None):
    """CLI run arguments ('model/task/try' under runs_dir, or a run directory) -> items."""
    runs_dir = Path(runs_dir or ROOT / "runs")
    out = []
    for a in args:
        d = Path(a) if Path(a).is_dir() else runs_dir / a
        it = run_item(d, explicit=True)
        if it is None:
            raise SystemExit(f"{a}: no HTML or frames to show")
        out.append(it)
    return out


def attention_items():
    res_p = ROOT / "validation/results.json"
    res = json.loads(res_p.read_text()) if res_p.exists() else {}
    out = []
    for a in ATTENTION:
        d = ROOT / "validation" / a["task"] / a["variant"]
        spec = task_spec(a["task"])
        g = res.get(a["task"], {}).get(a["variant"])
        checks = checks_of({"grades": g}) if g else None
        out.append(dict(run=f"validation/{a['task']}/{a['variant']}", model="attention:" + a["variant"],
                        task=a["task"], try_="0", stage="ref", setting="attention",
                        status=("PASS" if g["pass"] else "FAIL") if g else "UNGRADED", checks=checks,
                        passed=bool(g["pass"]) if g else None, html=str(d / "index.html"), frames=None,
                        dir=str(d), width=spec["width"], height=spec["height"], instruction=spec["instruction"],
                        attention=True, variant=a["variant"],
                        expected=dict(pass_=a["expect_pass"], defects=a["defects"])))
    return out


# ---------------------------------------------------------------- sampling

def _factors(c):
    f = [("task", c["task"]), ("model", c["model"]), ("pass", c.get("passed"))]
    f += [("check:" + k, v) for k, v in sorted((c.get("checks") or {}).items()) if v is not None]
    return f


def stratified_sample(cands, n, seed=0, weights=None):
    """Pick n runs balanced across tasks, models, overall pass/fail and each check's pass/fail.

    Greedy marginal balancing: each step takes the run whose factor values are most under-represented
    so far (count of already-picked runs sharing the value, minus that factor's even share), weighted per
    factor; ties are broken by a seeded shuffle. Rare outcomes (e.g. the few passes) are therefore
    over-sampled up to an even split as far as the pool allows. Deterministic for a given seed."""
    weights = weights or {"task": 2.0, "model": 2.0, "pass": 1.5, "check": 1.0}
    pool = list(cands)
    random.Random(seed).shuffle(pool)
    if n >= len(pool):
        return pool
    levels = defaultdict(set)
    for c in pool:
        for k, v in _factors(c):
            levels[k].add(v)
    counts = Counter()
    picked = []
    for _ in range(n):
        m = len(picked)

        def score(c):
            s = 0.0
            for k, v in _factors(c):
                w = weights.get(k.split(":")[0], 1.0)
                if k.startswith("check:"):
                    w /= max(1, sum(1 for x in levels if x.startswith("check:")))
                s += w * (counts[(k, v)] - m / len(levels[k]))
            return s
        best = min(range(len(pool)), key=lambda i: score(pool[i]))
        c = pool.pop(best)
        picked.append(c)
        for kv in _factors(c):
            counts[kv] += 1
    return picked


# ---------------------------------------------------------------- composition

def zoom_box(allowed, aspect=16 / 9, pad=40):
    return zbox_mask(np.asarray(allowed, bool), aspect, pad)


def _font(size=15):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # Pillow < 10.1
        return ImageFont.load_default()


def _label(draw, xy, text):
    draw.text(xy, text, fill=INK, font=_font())


def compose(frames, original, box, panel_w=600):
    """Four synchronized panels per frame: [original | animation] over [zoom original | zoom animation].
    frames: (N, H, W, 3) uint8 with frame N-1 = frame 0 (t = 2 s); returns N-1 PIL images."""
    original = np.asarray(original)[..., :3]
    H, W = original.shape[:2]
    pw, ph = panel_w, round(H * panel_w / W)
    bw, bh = box[2] - box[0], box[3] - box[1]
    zh = round(panel_w * bh / bw)
    bar, gap, vgap = 22, 16, 6
    CW = 2 * pw + gap
    CH = bar + ph + vgap + bar + zh
    CH += CH % 2
    full = lambda a: Image.fromarray(a).resize((pw, ph), Image.LANCZOS)  # noqa: E731
    zoom = lambda a: Image.fromarray(a).crop(box).resize((pw, zh), Image.LANCZOS)  # noqa: E731
    base = Image.new("RGB", (CW, CH), BG)
    d = ImageDraw.Draw(base)
    y2 = bar + ph + vgap
    _label(d, (4, 3), "Original image (still)")
    _label(d, (pw + gap + 4, 3), "Animation")
    _label(d, (4, y2 + 3), "Zoom: original")
    _label(d, (pw + gap + 4, y2 + 3), "Zoom: animation")
    base.paste(full(original), (0, bar))
    base.paste(zoom(original), (0, y2 + bar))
    out = []
    for f in frames[:-1]:
        if f.shape[:2] != (H, W):
            f = np.asarray(Image.fromarray(f).resize((W, H)))
        im = base.copy()
        im.paste(full(f), (pw + gap, bar))
        im.paste(zoom(f), (pw + gap, y2 + bar))
        out.append(im)
    return out


def contact_sheet(images, labels, cols=3, pad=6):
    w, h = images[0].size
    rows = -(-len(images) // cols)
    sheet = Image.new("RGB", (cols * (w + pad) + pad, rows * (h + 20 + pad) + pad), BG)
    d = ImageDraw.Draw(sheet)
    for i, (im, lab) in enumerate(zip(images, labels)):
        x, y = pad + (i % cols) * (w + pad), pad + (i // cols) * (h + 20 + pad)
        _label(d, (x + 2, y + 2), lab)
        sheet.paste(im, (x, y + 20))
    return sheet


def have_ffmpeg():
    return shutil.which("ffmpeg") is not None


def write_clip(frames, stem, fmt="auto", fps=FPS, loops=LOOPS):
    """Write PIL frames as a looping clip. mp4 (H.264, crf 12, `loops` cycles) needs ffmpeg; webp is
    lossless animated WebP (Pillow); gif is the last resort (palette, dithering)."""
    stem = Path(stem)
    if fmt == "auto":
        fmt = "mp4" if have_ffmpeg() else "webp"
    if fmt == "mp4":
        p = stem.with_suffix(".mp4")
        W, H = frames[0].size
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", "12",
               "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(p)]
        data = b"".join(np.asarray(f.convert("RGB")).tobytes() for f in frames) * loops
        subprocess.run(cmd, input=data, check=True)
        return p
    p = stem.with_suffix("." + fmt)
    kw = dict(save_all=True, append_images=frames[1:], duration=round(1000 / fps), loop=0)
    if fmt == "webp":
        kw.update(lossless=True, method=4)
    else:
        kw.update(optimize=True)
    frames[0].save(p, **kw)
    return p


# ---------------------------------------------------------------- frames

class RenderFrames:
    """item -> frames (N, H, W, 3). Loads pre-rendered frames if the item has them, else renders the HTML
    with src/render.py (same Chrome and flags as the grader)."""

    def __init__(self):
        self.R = None

    def __call__(self, item):
        src = item.get("frames")
        if src:
            p = Path(src)
            if p.suffix == ".npz":
                z = np.load(p)
                return z[z.files[0]]
            return np.stack([np.asarray(Image.open(f).convert("RGB")) for f in sorted(p.glob("*.png"))])
        from render import Renderer, prepare
        if self.R is None:
            self.R = Renderer()
        html = Path(item["html"])
        if item.get("variant"):
            # attention check: rebuild the reference/broken variant (its PNG layers are gitignored) under build/
            from reference import build_variant
            page = ROOT / "build/attention" / item["task"] / item["variant"]
            if not (page / "base.png").exists():
                build_variant(task_spec(item["task"]), item["variant"], page)
        elif html.name == "index.html":
            page = html.parent
        else:  # runs/<model>/<task>/<try>/index_<stage>.html -> page_<stage>/ (gitignored), as grade_runs.py
            page = html.parent / f"page_{item['stage']}"
            page.mkdir(exist_ok=True)
            (page / "index.html").write_text(html.read_text())
        prepare(page, ROOT / "tasks" / item["task"])
        fr, err, _ = self.R.render(page, item["width"], item["height"])
        if fr is None:
            raise RuntimeError(f"{item['run']}: {err}")
        return fr

    def close(self):
        if self.R:
            self.R.close()
            self.R = None


# ---------------------------------------------------------------- study

def clip_id(salt, run):
    return "c" + hashlib.sha256(f"{salt}|{run}".encode()).hexdigest()[:8]


def build_clip(item, cid, clips_dir, frames, fmt="auto", panel_w=600, media_dir=None):
    """Write the rater clip to clips_dir and the judge images to media_dir (default: clips_dir).
    Returns the manifest entry; paths are relative to clips_dir's parent (the rater/ folder)."""
    media_dir = media_dir or clips_dir
    media_dir.mkdir(parents=True, exist_ok=True)
    original = np.asarray(Image.open(ROOT / "tasks" / item["task"] / "image.png").convert("RGB"))
    allowed = np.asarray(Image.open(ROOT / "tasks" / item["task"] / "allowed.png")) > 127
    box = zoom_box(allowed)
    comp = compose(frames, original, box, panel_w)
    video = write_clip(comp, clips_dir / cid, fmt)
    n = len(frames) - 1
    idx = [i for i in SHEET_IDX if i < n]
    labs = [f"t = {2 * i / n:.2f} s" for i in idx]
    sw = 400
    sh = round(item["height"] * sw / item["width"])
    zh = round(sw * (box[3] - box[1]) / (box[2] - box[0]))
    p = {k: media_dir / f"{cid}_{k}.png" for k in ("orig", "origzoom", "sheet", "zoom")}
    Image.fromarray(original).save(p["orig"])
    Image.fromarray(original).crop(box).resize((sw, zh), Image.LANCZOS).save(p["origzoom"])
    contact_sheet([Image.fromarray(frames[i]).resize((sw, sh), Image.LANCZOS) for i in idx], labs).save(p["sheet"])
    contact_sheet([Image.fromarray(frames[i]).crop(box).resize((sw, zh), Image.LANCZOS) for i in idx], labs) \
        .save(p["zoom"])
    base = clips_dir.parent
    rel = lambda q: os.path.relpath(q, base).replace(os.sep, "/")  # noqa: E731
    return dict(clip_id=cid, task=item["task"], instruction=item["instruction"],
                width=item["width"], height=item["height"], box=list(map(int, box)),
                video=rel(video), still=rel(p["orig"]), still_zoom=rel(p["origzoom"]),
                sheet_full=rel(p["sheet"]), sheet_zoom=rel(p["zoom"]),
                fps=FPS, n_frames=n, loops=LOOPS if video.suffix == ".mp4" else 1,
                sheet_times=[round(2 * i / n, 3) for i in idx])


def build_study(runs, out, n=None, seed=0, salt=None, attention=True, frames_fn=None, fmt="auto",
                panel_w=600, study_id=None, log=print):
    """Sample n of `runs` (all if n is None), add the attention checks, write clips + manifest + key."""
    out = Path(out)
    rater_dir = out / "rater"
    clips_dir = rater_dir / "clips"
    clips_dir.mkdir(parents=True, exist_ok=True)
    salt = salt or secrets.token_hex(8)
    chosen = stratified_sample(runs, n, seed) if n is not None else list(runs)
    items = chosen + (attention_items() if attention else [])
    own = frames_fn is None
    frames_fn = frames_fn or RenderFrames()
    entries, key = [], {}
    try:
        for it in items:
            cid = clip_id(salt, it["run"])
            assert cid not in key, f"clip id collision for {it['run']}"
            try:
                fr = frames_fn(it)
            except Exception as e:  # noqa: BLE001
                if it["attention"]:
                    raise RuntimeError(f"attention check {it['run']} could not be rendered: {e}") from e
                log(f"skip {it['run']}: {e}")
                continue
            entries.append(build_clip(it, cid, clips_dir, fr, fmt, panel_w, out / "judge_media"))
            exp = it.get("expected")
            key[cid] = dict(run=it["run"], model=it["model"], setting=it["setting"], task=it["task"],
                            try_=it["try_"], stage=it["stage"], status=it["status"], checks=it["checks"],
                            passed=it["passed"], attention=it["attention"],
                            expected=dict(**{"pass": exp["pass_"]}, defects=exp["defects"]) if exp else None)
            log(f"{cid} {it['run']}")
    finally:
        if own:
            frames_fn.close()
    entries.sort(key=lambda e: e["clip_id"])
    study_id = study_id or f"anibench-e4-s{seed}-{hashlib.sha256(salt.encode()).hexdigest()[:6]}"
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest = dict(schema=MANIFEST_SCHEMA, study_id=study_id, created=now, question=QUESTION,
                    defects=[dict(code=c, label=lab) for c, lab, _ in DEFECTS], clips=entries)
    keyd = dict(schema=KEY_SCHEMA, study_id=study_id, created=now, seed=seed, salt=salt, n_requested=n,
                clips=key)
    (rater_dir / "manifest.json").write_text(json.dumps(manifest, indent=1))
    (out / "key.json").write_text(json.dumps(keyd, indent=1))
    return manifest, keyd


def split_study(out, batch_size, seed=0):
    """Split a built study into rater batches: <out>/batches/bNN/ with its own manifest.json (a subset of the
    clips plus every attention clip) and clips/ (hard links, or copies across file systems). Clips are dealt
    out in a seeded random order, so every batch mixes tasks and models. Returns the batch directories."""
    out = Path(out)
    man = json.loads((out / "rater/manifest.json").read_text())
    key = json.loads((out / "key.json").read_text())["clips"]
    att = [c for c in man["clips"] if key[c["clip_id"]]["attention"]]
    main_ = [c for c in man["clips"] if not key[c["clip_id"]]["attention"]]
    random.Random(seed).shuffle(main_)
    dirs = []
    for b, i in enumerate(range(0, len(main_), batch_size)):
        d = out / "batches" / f"b{b + 1:02d}"
        (d / "clips").mkdir(parents=True, exist_ok=True)
        clips = sorted(main_[i:i + batch_size] + att, key=lambda c: c["clip_id"])
        for c in clips:
            src, dst = out / "rater" / c["video"], d / c["video"]
            if not dst.exists():
                try:
                    os.link(src, dst)
                except OSError:
                    shutil.copy(src, dst)
        m = dict(man, study_id=f"{man['study_id']}-b{b + 1:02d}", parent_study_id=man["study_id"],
                 clips=[{k: v for k, v in c.items() if not str(v).startswith("../")} for c in clips])
        (d / "manifest.json").write_text(json.dumps(m, indent=1))
        dirs.append(d)
    return dirs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="*", help="model/task/try under --runs-dir, or run directories (default: all)")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, default=None, help="stratified sample size (default: all runs)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--salt", default=None, help="clip-id salt (default: random, recorded in key.json)")
    ap.add_argument("--fmt", default="auto", choices=["auto", "mp4", "webp", "gif"])
    ap.add_argument("--panel", type=int, default=600, help="panel width in px")
    ap.add_argument("--no-attention", action="store_true")
    ap.add_argument("--include-ungraded", action="store_true")
    ap.add_argument("--study-id", default=None)
    ap.add_argument("--split", type=int, default=None, metavar="SIZE",
                    help="only split an already built --out study into rater batches of SIZE clips (+ attention)")
    a = ap.parse_args(argv)
    if a.split:
        for d in split_study(a.out, a.split, a.seed):
            print(d, len(json.loads((d / "manifest.json").read_text())["clips"]), "clips")
        return
    runs = resolve_runs(a.runs, a.runs_dir) if a.runs else discover_runs(a.runs_dir, a.include_ungraded)
    print(f"{len(runs)} candidate runs")
    man, key = build_study(runs, a.out, a.n, a.seed, a.salt, not a.no_attention, fmt=a.fmt, panel_w=a.panel,
                           study_id=a.study_id)
    print(f"wrote {len(man['clips'])} clips to {a.out}/rater (study {man['study_id']}); "
          f"give raters only the rater/ folder, keep {a.out}/key.json")


if __name__ == "__main__":
    main()
