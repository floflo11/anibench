"""Grader v2 vs v3, side by side, on the same rendered frames. Writes results/grader_v3.{json,md}.

    python3 src/grader_v3_report.py [--workers 2]

Same frames, two graders: every page is rendered once (frames come from the frame cache, src/framecache.py) and
graded by grader v2 (src/graders.py at commit V2_COMMIT, loaded from git) and by the current grader (v3). Each
grader gets its own admission: a check counts for a task only if that grader passes the task's reference on it.

  - Mutation suite, raster tasks: validation/<task>/<variant>/ pages (src/reference.py); detection per broken-copy
    type, raw and counting only copies whose part really comes apart (reference.oracle_split).
  - Mutation suite, synthetic sample: validation/synth/ pages (src/synth/mutations.py), same tables.
  - Valid alternate animations (src/alt_refs): failure rate per check with each grader's admitted checks; a
    failure is a false fail unless results/alt_refs/classification.json calls it a real break (class b).
  - Reference pass rate: references that pass every candidate check, before admission.
Results of v3 itself come from validation/results.json, validation/results_synth.json and results/alt_refs/raw.
"""
import argparse
import importlib.util
import json
import multiprocessing as mp
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from validate import EXPECT, SPLIT_VARIANTS  # noqa: E402

V2_COMMIT = "a898e10"
OUT = ROOT / "results"
NAMES = {"whole": "Whole image", "missed_thumb": "Missed thumb", "hole": "Hole left", "frozen": "Frozen",
         "center_pivot": "Center pivot", "no_loop": "No loop", "wrong_part": "Wrong part",
         "detach_small": "Detach small", "detach_tip": "Detach tip", "gap_seam": "Gap seam"}
CHECKS = ["G1", "G2", "G2b", "G2c", "G3", "G4", "G5", "G6"]


def load_v2():
    src = subprocess.check_output(["git", "-C", str(ROOT), "show", f"{V2_COMMIT}:src/graders.py"])
    p = Path(tempfile.mkdtemp()) / "graders_v2.py"
    p.write_bytes(src)
    spec = importlib.util.spec_from_file_location("graders_v2", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def jobs():
    """(kind, key, page dir, task dir) for every page we compare."""
    out = []
    for name, tasks_dir, pages, results in (("raster", ROOT / "tasks", ROOT / "validation", ROOT / "validation/results.json"),
                                            ("synth", ROOT / "tasks_synth", ROOT / "validation/synth",
                                             ROOT / "validation/results_synth.json")):
        if not results.exists():
            continue
        for tid, vs in json.loads(results.read_text()).items():
            for v, g in vs.items():
                if "error" not in g:
                    out.append((name, f"{tid}/{v}", str(pages / tid / v), str(tasks_dir / tid)))
    for p in sorted((OUT / "alt_refs/raw").glob("*/*.json")):
        r = json.loads(p.read_text())
        if "error" not in r:
            out.append(("alt", f"{r['task']}/{r['variant']}", str(ROOT / "out/alt_refs" / r["variant"] / r["task"]),
                        str(ROOT / "tasks" / r["task"])))
    return out


def _worker(items, q):
    from framecache import CachedRenderer
    G2 = load_v2()
    R = CachedRenderer()
    for kind, key, page, td in items:
        spec = json.loads((Path(td) / "spec.json").read_text())
        fr, err, _ = R.render(page, td, spec["width"], spec["height"])
        if fr is None:
            q.put((kind, key, {"error": err}))
            continue
        # v2's candidate checks: the task's original checks plus G2b (v2 had no G2c)
        q.put((kind, key, G2.grade(fr, td, checks=G2.candidate_checks({"graders": [k for k in spec.get(
            "graders_all", spec["graders"]) if k != "G2c"]}))))
    R.close()


def grade_v2(workers):
    cache = OUT / "grader_v2_on_v3_frames.json"
    done = json.loads(cache.read_text()) if cache.exists() else {}
    todo = [j for j in jobs() if f"{j[0]}:{j[1]}" not in done]
    if todo:
        q = mp.Queue()
        ps = [mp.Process(target=_worker, args=(todo[i::workers], q)) for i in range(workers)]
        for p in ps:
            p.start()
        for i in range(len(todo)):
            kind, key, g = q.get()
            done[f"{kind}:{key}"] = g
            if i % 25 == 0:
                cache.write_text(json.dumps(done))
                print(i, len(todo), flush=True)
        for p in ps:
            p.join()
        cache.write_text(json.dumps(done))
    return done


def detection(res, admitted):
    """Per broken-copy type: [caught, applicable] raw and among copies that really split; and per-task refs."""
    raw = {v: [0, 0] for v in EXPECT}
    split = {v: [0, 0] for v in SPLIT_VARIANTS}
    for tid, vs in res.items():
        kept = admitted.get(tid, [])
        for v, ks in EXPECT.items():
            g = vs.get(v)
            app = [k for k in ks if k in kept]
            if not app or g is None or "error" in g:
                continue
            hit = any(not g[k]["ok"] for k in app if k in g)
            raw[v][0] += hit
            raw[v][1] += 1
            if v in split and vs[v].get("oracle", {}).get("split", True):
                split[v][0] += hit
                split[v][1] += 1
    return raw, split


def admit(res):
    """{task: checks the reference passes} (the admission rule) and the share of references passing everything."""
    adm, full = {}, 0
    for tid, vs in res.items():
        ref = vs.get("ref", {})
        adm[tid] = [k for k, x in ref.items() if k not in ("pass", "oracle") and isinstance(x, dict) and x.get("ok")]
        full += bool(ref.get("pass"))
    return adm, [full, len(res)]


def split_by(v2flat, kind):
    out = {}
    for k, g in v2flat.items():
        kd, key = k.split(":", 1)
        if kd != kind:
            continue
        tid, v = key.split("/", 1)
        out.setdefault(tid, {})[v] = g
    return out


def alt_table(v2flat):
    cls = json.loads((OUT / "alt_refs/classification.json").read_text())
    rows = {}
    v3 = {}
    for p in sorted((OUT / "alt_refs/raw").glob("*/*.json")):
        r = json.loads(p.read_text())
        if "error" not in r:
            v3[f"{r['task']}/{r['variant']}"] = r
    # admitted checks per task under each grader
    adm2, _ = admit(split_by(v2flat, "raster"))
    for name, get in (("v2", lambda key: v2flat.get(f"alt:{key}")), ("v3", lambda key: v3[key]["result"])):
        per = {k: [0, 0, 0] for k in CHECKS}  # failed, applicable, false fails
        runs = fails = ffails = 0
        for key, r in v3.items():
            tid, var = key.split("/")
            g = get(key)
            if g is None or "error" in g:
                continue
            kept = adm2.get(tid, []) if name == "v2" else r["graders"]
            runs += 1
            failed = [k for k in kept if k in g and not g[k]["ok"]]
            for k in CHECKS:
                if k in kept and k in g:
                    per[k][1] += 1
                    if k in failed:
                        per[k][0] += 1
                        per[k][2] += cls.get(f"{var}/{tid}/{k}", {}).get("class") != "b"
            fails += bool(failed)
            ffails += bool(failed) and not any(cls.get(f"{var}/{tid}/{k}", {}).get("class") == "b" for k in failed)
        rows[name] = dict(runs=runs, failed=fails, false_fail=ffails, checks=per)
    return rows


def frac(a):
    return f"{a[0]}/{a[1]}" if a[1] else "n/a"


def main(workers=2):
    v2flat = grade_v2(workers)
    out = dict(v2_commit=V2_COMMIT)
    md = ["# Grader v3 vs v2", "",
          "Generated by `python3 src/grader_v3_report.py`. Same rendered frames, two graders: v2 is `src/graders.py` "
          f"at commit `{V2_COMMIT}`, v3 is the current one. Each grader gets its own admission (a check counts for a "
          "task only if that grader passes the task's reference on it). Tasks are the current ones (T07 earrings "
          "with their chain, T10 head without the sleeve sliver, T14's hat tipped one way).", ""]
    for kind, path in (("raster", ROOT / "validation/results.json"), ("synth", ROOT / "validation/results_synth.json")):
        if not path.exists():
            continue
        r3 = json.loads(path.read_text())
        r2 = split_by(v2flat, kind)
        for tid in r3:  # oracle results are grader-independent
            for v in r3[tid]:
                if v in r2.get(tid, {}) and "oracle" in r3[tid][v]:
                    r2[tid][v]["oracle"] = r3[tid][v]["oracle"]
        a2, ref2 = admit(r2)
        a3, ref3 = admit(r3)
        d2, s2 = detection(r2, a2)
        d3, s3 = detection(r3, a3)
        out[kind] = dict(ref_pass_all=dict(v2=ref2, v3=ref3), detect=dict(v2=d2, v3=d3), split=dict(v2=s2, v3=s3),
                         admitted=dict(v2=a2, v3=a3))
        title = "Raster tasks (T01-T21)" if kind == "raster" else f"Synthetic sample ({len(r3)} tasks)"
        md += [f"## Mutation suite: {title}", "",
               f"References passing every candidate check: v2 {frac(ref2)}, v3 {frac(ref3)} "
               f"(v3 adds G2c; checks a reference fails are dropped for that task).", "",
               "| Broken copy | Intended checks | v2 caught | v3 caught | v2 caught, part really comes apart | v3 caught, part really comes apart |",
               "| --- | --- | --- | --- | --- | --- |"]
        for v, ks in EXPECT.items():
            md.append(f"| {NAMES[v]} | {'/'.join(ks)} | {frac(d2[v])} | {frac(d3[v])} | "
                      f"{frac(s2[v]) if v in s2 else '-'} | {frac(s3[v]) if v in s3 else '-'} |")
        drops = {k: [sum(k not in a2[t] for t in a2), sum(k not in a3[t] for t in a3)] for k in CHECKS}
        md += ["", "Checks dropped by admission (tasks whose reference fails them), v2 / v3: " + "; ".join(
            f"{k} {a}/{b}" for k, (a, b) in drops.items()), ""]
        out[kind]["dropped"] = drops
    if (OUT / "alt_refs/raw").exists():
        at = alt_table(v2flat)
        out["alt"] = at
        md += ["## Valid alternate animations (src/alt_refs)", "",
               f"Runs: {at['v3']['runs']}. Any check failed: v2 {at['v2']['failed']}, v3 {at['v3']['failed']}. "
               f"False fails (no failed check classified as a real break in results/alt_refs/classification.json): "
               f"v2 {at['v2']['false_fail']} ({100 * at['v2']['false_fail'] / max(1, at['v2']['runs']):.1f}%), "
               f"v3 {at['v3']['false_fail']} ({100 * at['v3']['false_fail'] / max(1, at['v3']['runs']):.1f}%).", "",
               "| Check | v2 failed / applicable | v2 false fails | v3 failed / applicable | v3 false fails |",
               "| --- | --- | --- | --- | --- |"]
        for k in CHECKS:
            a, b = at["v2"]["checks"][k], at["v3"]["checks"][k]
            md.append(f"| {k} | {a[0]}/{a[1]} | {a[2]} | {b[0]}/{b[1]} | {b[2]} |")
        md.append("")
    notes = OUT / "grader_v3_notes.md"
    if notes.exists():
        md += [notes.read_text().strip(), ""]
    (OUT / "grader_v3.json").write_text(json.dumps(out, indent=1))
    (OUT / "grader_v3.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    main(ap.parse_args().workers)
