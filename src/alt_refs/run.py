"""Render and grade every alternate style on every admitted task; build the false-fail report.

    python3 src/alt_refs/run.py render [--tasks T01,T02] [--variants easing-sine_typ,...] [--workers 2] [--force]
    python3 src/alt_refs/run.py report
    python3 src/alt_refs/run.py gifs
    python3 src/alt_refs/run.py evidence   # re-render failing runs and rewrite their evidence images

render: resumable. One JSON per (variant, task) in results/alt_refs/raw/<variant>/<task>.json; existing results
  are skipped unless --force, so a long run can be split into chunks and restarted after an interruption.
  Pages are built under out/alt_refs/ (gitignored). Graded with src/graders.py, using each task's admitted
  checks (spec.json "graders", as narrowed by validation/admission.md). For every failed check an evidence
  image (original | frame | overlay, cropped) goes to results/alt_refs/evidence/.
report: writes results/alt_refs/false_fail.{md,json} from raw/ and the hand classification in
  results/alt_refs/classification.json.
gifs: zoomed example GIFs per style in results/alt_refs/gifs/.
"""
import argparse
import json
import multiprocessing as mp
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import alt_refs  # noqa: E402

RES = ROOT / "results" / "alt_refs"
RAW = RES / "raw"
EVID = RES / "evidence"
PAGES = ROOT / "out" / "alt_refs"
CHECKS = ["G1", "G2", "G3", "G4", "G5", "G6"]
CHECK_NAMES = {"G1": "isolation", "G2": "integrity", "G3": "area", "G4": "motion", "G5": "pivot", "G6": "loop/fidelity"}
GIF_TASKS = {"easing": ["T01", "T15", "T13"], "squash_stretch": ["T03", "T16", "T17"],
             "follow_through": ["T06", "T19", "T15"], "alt_impl": ["T12", "T14", "T18"], "pivot": ["T01", "T11"]}


def admitted():
    idx = json.loads((ROOT / "tasks/index.json").read_text())
    out = []
    for s in idx:
        spec = json.loads((ROOT / "tasks" / s["id"] / "spec.json").read_text())
        if spec["graders"]:
            out.append(s["id"])
    return out


# ---- evidence ------------------------------------------------------------------------------------

def _box(mask, pad, shape):
    ys, xs = np.nonzero(mask)
    if len(xs) == 0:
        return (0, 0, shape[1], shape[0])
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(shape[1], xs.max() + pad + 1), min(shape[0], ys.max() + pad + 1))


def worst_frames(frames, task_dir):
    """Per check, the frame index where it is worst and a mask of the offending pixels (mirrors graders.py)."""
    from graders import G5_R, blobs, changed, disc, foreground, load_mask
    from scipy import ndimage
    spec = json.loads((task_dir / "spec.json").read_text())
    orig = np.array(Image.open(task_dir / "image.png").convert("RGB"))
    allowed = load_mask(task_dir, "allowed.png")
    target = load_mask(task_dir, "target.png")
    ch = [changed(f, orig) for f in frames]
    fgs = [foreground(f) for f in frames]
    fg0 = foreground(orig)
    out = {}
    out["G1"] = max(range(len(frames)), key=lambda i: (ch[i] & ~allowed).sum())
    out["G1_px"] = ch[out["G1"]] & ~allowed
    out["G2"] = max(range(len(frames)), key=lambda i: blobs(fgs[i] & allowed))
    lab, n = ndimage.label(fgs[out["G2"]] & allowed)
    sizes = ndimage.sum(np.ones_like(lab), lab, range(1, n + 1)) if n else []
    small = np.zeros_like(allowed)
    big = [k + 1 for k, s in enumerate(sizes) if s >= 60]
    if big:
        main = max(big, key=lambda k: sizes[k - 1])
        small = np.isin(lab, [k for k in big if k != main])
    out["G2_px"] = small
    area0 = (fg0 & allowed).sum()
    out["G3"] = max(range(len(frames)), key=lambda i: abs(int((fgs[i] & allowed).sum()) - int(area0)))
    out["G3_px"] = (fgs[out["G3"]] ^ fg0) & allowed
    out["G4"] = max(range(len(frames)), key=lambda i: (ch[i] & target).sum())
    out["G4_px"] = ch[out["G4"]] & target
    dm = np.zeros_like(target)
    for (x, y) in spec.get("pivots", []):
        d = disc(orig.shape, x, y, G5_R) & target
        if d.sum() >= 30:
            dm |= d
    out["G5"] = max(range(len(frames)), key=lambda i: (ch[i] & dm).sum())
    out["G5_px"] = ch[out["G5"]] & dm
    out["G5_disc"] = dm
    loopd = changed(frames[0], frames[-1])
    out["G6"] = len(frames) - 1 if loopd.mean() > ch[0].mean() else 0
    out["G6_px"] = loopd if out["G6"] else ch[0]
    return out, orig, allowed, target


def evidence(frames, tid, variant, failed):
    task_dir = ROOT / "tasks" / tid
    wf, orig, allowed, target = worst_frames(frames, task_dir)
    EVID.mkdir(parents=True, exist_ok=True)
    paths = {}
    from scipy import ndimage
    edge = allowed ^ ndimage.binary_erosion(allowed, iterations=2)
    for k in failed:
        i = wf[k]
        px = wf[k + "_px"]
        f = frames[i]
        region = allowed | px if k in ("G1", "G6") else allowed
        box = _box(region if px.sum() == 0 or k != "G1" else (px | target), 30, orig.shape)
        if k == "G5":
            box = _box(wf["G5_disc"], 40, orig.shape)
        ov = (0.55 * f + 0.45 * 255).astype(np.uint8)
        ov[edge] = (60, 120, 255)                           # allowed-region border (blue)
        ov[px] = (230, 20, 20)                              # offending pixels (red)
        x0, y0, x1, y1 = box
        tiles = [Image.fromarray(a[y0:y1, x0:x1]) for a in (orig, f, ov)]
        w, h = tiles[0].size
        s = min(3.0, 900 / (3 * w), 420 / h)
        tiles = [t.resize((max(1, int(w * s)), max(1, int(h * s))), Image.NEAREST) for t in tiles]
        # zoom row: original | frame around the offending pixels, 4x
        zx0, zy0, zx1, zy1 = _box(px if px.any() else region, 14, orig.shape)
        zw, zh = zx1 - zx0, zy1 - zy0
        zs = min(6.0, 440 / zw, 300 / zh)
        zoom = [Image.fromarray(a[zy0:zy1, zx0:zx1]).resize((max(1, int(zw * zs)), max(1, int(zh * zs))), Image.NEAREST)
                for a in (orig, f)]
        W, H = tiles[0].size
        ZW, ZH = zoom[0].size
        sheet = Image.new("RGB", (max(3 * W + 20, 2 * ZW + 10), H + ZH + 50), "white")
        for j, t in enumerate(tiles):
            sheet.paste(t, (j * (W + 10), 22))
        for j, t in enumerate(zoom):
            sheet.paste(t, (j * (ZW + 10), H + 46))
        dr = ImageDraw.Draw(sheet)
        dr.text((4, 4), f"{variant} {tid} {k} ({CHECK_NAMES[k]}) frame {i}: original | frame | "
                        f"red = offending px, blue = allowed border", fill=(0, 0, 0))
        dr.text((4, H + 28), f"zoom x{zs:.1f} at ({zx0},{zy0})-({zx1},{zy1}): original | frame", fill=(0, 0, 0))
        p = EVID / f"{variant}__{tid}__{k}.png"
        sheet.save(p)
        paths[k] = p.relative_to(RES).as_posix()
    return paths


# ---- render + grade ------------------------------------------------------------------------------

def _worker(jobs, q):
    from graders import grade
    from render import Renderer, prepare
    R = Renderer()
    try:
        for tid, v in jobs:
            spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
            d = PAGES / v / tid
            try:
                alt_refs.build(tid, v, d)
                prepare(d, ROOT / "tasks" / tid)
                fr, err, logs = R.render(d, spec["width"], spec["height"])
            except Exception as e:  # noqa: BLE001
                fr, err, logs = None, f"BUILD: {type(e).__name__}: {e}", []
            if fr is None:
                rec = dict(task=tid, variant=v, error=err, logs=logs[-5:])
            else:
                g = grade(fr, ROOT / "tasks" / tid)
                failed = [k for k in CHECKS if k in g and not g[k]["ok"]]
                rec = dict(task=tid, variant=v, graders=spec["graders"], result=g, failed=failed)
                if failed:
                    rec["evidence"] = evidence(fr, tid, v, failed)
            out = RAW / v / f"{tid}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(rec, indent=1))
            q.put(rec)
    finally:
        R.close()


def render_all(tasks=None, variants=None, workers=2, force=False):
    tasks = tasks or admitted()
    variants = variants or sorted(alt_refs.VARIANTS)
    jobs = [(t, v) for t in tasks for v in variants
            if alt_refs.applicable(t, v) and (force or not (RAW / v / f"{t}.json").exists())]
    print(f"{len(jobs)} jobs", flush=True)
    if not jobs:
        return
    q = mp.Queue()
    ps = [mp.Process(target=_worker, args=(jobs[i::workers], q)) for i in range(workers)]
    for p in ps:
        p.start()
    for _ in jobs:
        r = q.get()
        msg = "ERR " + r["error"] if "error" in r else ("pass" if not r["failed"] else "FAIL " + ",".join(r["failed"]))
        print(r["task"], r["variant"], msg, flush=True)
    for p in ps:
        p.join()


# ---- report --------------------------------------------------------------------------------------

def load_raw():
    recs = []
    for p in sorted(RAW.glob("*/*.json")):
        recs.append(json.loads(p.read_text()))
    return recs


def report():
    recs = load_raw()
    cls_path = RES / "classification.json"
    cls = json.loads(cls_path.read_text()) if cls_path.exists() else {}
    variants = sorted({r["variant"] for r in recs})
    tasks = sorted({r["task"] for r in recs})
    by = {(r["variant"], r["task"]): r for r in recs}

    def fails(r):
        return r.get("failed", []) if "error" not in r else ["ERR"]

    def is_valid_fail(r):
        """A run counts as a false fail if it failed and none of its failures is classified (b) style broke the rule."""
        f = fails(r)
        if not f:
            return False
        labels = [cls.get(f"{r['variant']}/{r['task']}/{k}", {}).get("class") for k in f]
        return not any(lab == "b" for lab in labels)

    summary = {"runs": len(recs), "variants": {}, "checks": {}, "tasks": {}}
    for v in variants:
        rs = [by[(v, t)] for t in tasks if (v, t) in by]
        nf = sum(bool(fails(r)) for r in rs)
        nff = sum(is_valid_fail(r) for r in rs)
        per = {}
        for k in CHECKS:
            applic = [r for r in rs if "error" not in r and k in r["graders"]]
            per[k] = dict(applicable=len(applic), failed=sum(k in r["failed"] for r in applic),
                          false_fail=sum(k in r["failed"] and cls.get(f"{v}/{r['task']}/{k}", {}).get("class") != "b"
                                         for r in applic))
        summary["variants"][v] = dict(style=alt_refs.VARIANTS[v]["style"], runs=len(rs), failed=nf, false_fail=nff,
                                      errors=sum("error" in r for r in rs), checks=per)
    for k in CHECKS:
        applic = [r for r in recs if "error" not in r and k in r["graders"]]
        summary["checks"][k] = dict(
            applicable=len(applic), failed=sum(k in r["failed"] for r in applic),
            too_strict=sum(k in r["failed"] and cls.get(f"{r['variant']}/{r['task']}/{k}", {}).get("class") == "a" for r in applic),
            real=sum(k in r["failed"] and cls.get(f"{r['variant']}/{r['task']}/{k}", {}).get("class") == "b" for r in applic),
            unclassified=sum(k in r["failed"] and f"{r['variant']}/{r['task']}/{k}" not in cls for r in applic))
    for t in tasks:
        rs = [by[(v, t)] for v in variants if (v, t) in by]
        summary["tasks"][t] = dict(runs=len(rs), failed=sum(bool(fails(r)) for r in rs),
                                   false_fail=sum(is_valid_fail(r) for r in rs))
    n = len(recs)
    nf = sum(bool(fails(r)) for r in recs)
    nff = sum(is_valid_fail(r) for r in recs)
    summary["overall"] = dict(runs=n, failed=nf, raw_fail_rate=round(nf / max(1, n), 4), false_fail=nff,
                              false_fail_rate=round(nff / max(1, n), 4))
    # the same restricted to variants whose own design is fully inside the documented valid envelope
    summary["runs_detail"] = {f"{r['variant']}/{r['task']}": dict(failed=fails(r), values={
        k: r["result"][k] for k in r.get("failed", [])}) for r in recs if fails(r)}
    (RES / "false_fail.json").write_text(json.dumps(summary, indent=1))
    (RES / "false_fail.md").write_text(render_md(summary, recs, cls, variants, tasks, by))
    print(json.dumps(summary["overall"]))
    return summary


def _pct(a, b):
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "n/a"


def render_md(S, recs, cls, variants, tasks, by):
    o = S["overall"]
    L = ["# Alternate valid animations: false-fail analysis", "",
         "Generated by `python3 src/alt_refs/run.py report` from `results/alt_refs/raw/` and the hand "
         "classification in `results/alt_refs/classification.json`. What counts as valid is defined in "
         "[docs/alt_refs.md](../../docs/alt_refs.md).", "",
         f"**Runs:** {o['runs']} (style variants x admitted tasks, each graded with the task's admitted checks). "
         f"**Raw fail rate:** {_pct(o['failed'], o['runs'])}. "
         f"**False-fail rate** (failed, and no failed check is classified as a real rule break): "
         f"{_pct(o['false_fail'], o['runs'])}.", "",
         "## Per variant", "",
         "| Variant | Style | Runs | Failed | False fails | " + " | ".join(f"{k} fail" for k in CHECKS) + " |",
         "| --- | --- | --- | --- | --- |" + " --- |" * len(CHECKS)]
    for v in variants:
        s = S["variants"][v]
        cells = []
        for k in CHECKS:
            c = s["checks"][k]
            cells.append(f"{c['failed']}/{c['applicable']}" if c["applicable"] else "-")
        L.append(f"| {v} | {s['style']} | {s['runs']} | {s['failed']} | {s['false_fail']} | " + " | ".join(cells) + " |")
    L += ["", "## Per check", "",
          "| Check | Applicable runs | Failed | (a) too strict | (b) real break | Unclassified |",
          "| --- | --- | --- | --- | --- | --- |"]
    for k in CHECKS:
        c = S["checks"][k]
        L.append(f"| {k} {CHECK_NAMES[k]} | {c['applicable']} | {c['failed']} | {c['too_strict']} | {c['real']} | {c['unclassified']} |")
    L += ["", "## Per task", "", "| Task | Runs | Failed | False fails | Failing variants (checks) |", "| --- | --- | --- | --- | --- |"]
    for t in tasks:
        s = S["tasks"][t]
        fl = [f"{v} ({','.join(by[(v, t)].get('failed', ['ERR']))})" for v in variants
              if (v, t) in by and (by[(v, t)].get("failed") or "error" in by[(v, t)])]
        L.append(f"| {t} | {s['runs']} | {s['failed']} | {s['false_fail']} | {'; '.join(fl) or '-'} |")
    L += ["", "## Every failure, classified", "",
          "(a) = grader too strict: a valid animation by any reasonable human judgment. "
          "(b) = the style really broke the rule. Evidence: original | failing frame | overlay (red = offending "
          "pixels, blue = border of the allowed region).", "",
          "| Run | Check | Value | Class | Reason | Evidence |", "| --- | --- | --- | --- | --- | --- |"]
    for r in sorted(recs, key=lambda r: (r["task"], r["variant"])):
        if "error" in r:
            L.append(f"| {r['variant']} / {r['task']} | ERR | {r['error'][:80]} | | | |")
            continue
        for k in r["failed"]:
            key = f"{r['variant']}/{r['task']}/{k}"
            c = cls.get(key, {})
            val = {kk: vv for kk, vv in r["result"][k].items() if kk != "ok"}
            ev = r.get("evidence", {}).get(k)
            L.append(f"| {r['variant']} / {r['task']} | {k} | {json.dumps(val)} | {c.get('class', '?')} | "
                     f"{c.get('reason', '')} | {f'[png]({ev})' if ev else ''} |")
    notes = RES / "notes.md"
    if notes.exists():
        L += ["", notes.read_text().strip()]
    return "\n".join(L) + "\n"


# ---- gifs ----------------------------------------------------------------------------------------

def gifs(per_style=None):
    sys.path.insert(0, str(ROOT / "src"))
    from render import Renderer, prepare
    from zoom_gifs import zbox
    out = RES / "gifs"
    out.mkdir(parents=True, exist_ok=True)
    picks = per_style or {s: GIF_TASKS[s] for s in GIF_TASKS}
    first = {s: [v for v in sorted(alt_refs.VARIANTS) if alt_refs.VARIANTS[v]["style"] == s] for s in picks}
    R = Renderer()
    try:
        for style, tids in picks.items():
            for j, tid in enumerate(tids):
                vs = [v for v in first[style] if alt_refs.applicable(tid, v)]
                v = vs[j % len(vs)]
                spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
                d = PAGES / v / tid
                alt_refs.build(tid, v, d)
                prepare(d, ROOT / "tasks" / tid)
                fr, err, _ = R.render(d, spec["width"], spec["height"])
                if fr is None:
                    print("ERR", v, tid, err)
                    continue
                box = zbox(tid)
                w = 480
                h = int(w * (box[3] - box[1]) / (box[2] - box[0]))
                ims = [Image.fromarray(f).crop(box).resize((w, h), Image.LANCZOS) for f in fr[:-1]]
                p = out / f"{v}__{tid}.gif"
                ims[0].save(p, save_all=True, append_images=ims[1:], duration=int(2000 / len(ims)), loop=0, optimize=True)
                print(p.relative_to(ROOT))
    finally:
        R.close()


def redo_evidence():
    """Re-render every failing run and rewrite its evidence images (pages are rebuilt deterministically)."""
    from render import Renderer, prepare
    R = Renderer()
    try:
        for r in load_raw():
            if not r.get("failed"):
                continue
            tid, v = r["task"], r["variant"]
            spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
            d = PAGES / v / tid
            alt_refs.build(tid, v, d)
            prepare(d, ROOT / "tasks" / tid)
            fr, err, _ = R.render(d, spec["width"], spec["height"])
            if fr is not None:
                r["evidence"] = evidence(fr, tid, v, r["failed"])
                (RAW / v / f"{tid}.json").write_text(json.dumps(r, indent=1))
                print(v, tid, r["failed"])
    finally:
        R.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["render", "report", "gifs", "evidence"])
    ap.add_argument("--tasks")
    ap.add_argument("--variants")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.cmd == "render":
        render_all(a.tasks.split(",") if a.tasks else None, a.variants.split(",") if a.variants else None,
                   a.workers, a.force)
    elif a.cmd == "report":
        report()
    elif a.cmd == "evidence":
        redo_evidence()
    else:
        gifs()
