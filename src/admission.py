"""Apply the admission rule to validation results.

A check counts for a task only if the reference animation passes it there.
Writes validation/admission.json + validation/admission.md and updates tasks/<id>/spec.json["graders"].
Also reports which broken copies each task's checks caught.

    python3 src/admission.py                                  # raster tasks (tasks/, validation/results.json)
    python3 src/admission.py --results validation/results_synth.json --tasks-dir tasks_synth \\
        --name admission_synth --no-write-specs                # synthetic sample: report only
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from graders import candidate_checks  # noqa: E402
from validate import EXPECT, SPLIT_VARIANTS  # noqa: E402

NAMES = {"whole": "Whole image", "missed_thumb": "Missed thumb", "hole": "Hole left", "frozen": "Frozen",
         "center_pivot": "Center pivot", "no_loop": "No loop", "wrong_part": "Wrong part",
         "detach_small": "Detach small", "detach_tip": "Detach tip", "gap_seam": "Gap seam"}


def admit(res, tasks_dir, write_specs=True):
    """{task: (kept, dropped, cells)} and the totals, from a results dict."""
    adm, rows = {}, []
    caught_tot = {v: [0, 0] for v in EXPECT}
    split_tot = {v: [0, 0] for v in SPLIT_VARIANTS}  # caught / applicable among copies that really split
    by_check = {v: {} for v in EXPECT}               # which kept intended check fired, per copy type
    for tid in sorted(res):
        spec_p = Path(tasks_dir) / tid / "spec.json"
        spec = json.loads(spec_p.read_text())
        orig = candidate_checks(spec)
        ref = res[tid].get("ref", {})
        if "error" in ref:
            kept, dropped = [], orig
        else:
            kept = [k for k in orig if k in ref and ref[k]["ok"]]
            dropped = [k for k in orig if k not in kept]
        cells = []
        for v, ks in EXPECT.items():
            g = res[tid].get(v)
            app = [k for k in ks if k in kept]
            if not app or g is None or "error" in g:
                cells.append("n/a")
                continue
            fired = [k for k in app if k in g and not g[k]["ok"]]
            hit = bool(fired)
            for k in fired:
                by_check[v][k] = by_check[v].get(k, 0) + 1
            caught_tot[v][0] += hit
            caught_tot[v][1] += 1
            split = g.get("oracle", {}).get("split", True)
            if v in split_tot and split:
                split_tot[v][0] += hit
                split_tot[v][1] += 1
            cells.append("caught" if hit else ("missed" if split else "missed (no split)"))
        adm[tid] = dict(kept=kept, dropped=dropped)
        if write_specs:
            spec["graders_all"] = orig
            spec["graders"] = kept
            spec_p.write_text(json.dumps(spec, indent=1))
        rows.append((tid, kept, dropped, cells))
    return adm, rows, caught_tot, split_tot, by_check


def main(results=ROOT / "validation/results.json", tasks_dir=ROOT / "tasks", name="admission", write_specs=True):
    res = json.loads(Path(results).read_text())
    adm, rows, caught_tot, split_tot, by_check = admit(res, tasks_dir, write_specs)
    md = ["# Grader validation", "",
          "Each scored task has a reference animation (correct) and up to 10 broken copies. A check counts for a task "
          "only if the reference passes it. A broken copy is *caught* if any of its intended checks fails on it; "
          "*n/a* means none of its intended checks was kept for the task (or the copy does not apply to the task kind). "
          "Intended checks: " + "; ".join(f"{NAMES[v]} {'/'.join(ks)}" for v, ks in EXPECT.items()) + ". "
          "*missed (no split)*: the part never actually comes apart in that copy (oracle_split draws the part "
          "alone, frame by frame, and counts its pieces), e.g. a tip left behind that the moving part slides past "
          "while still touching it; no connectivity check (G2, G2b) can see those, only G2c (a piece left behind "
          "while the fitted part moves on).", "",
          "| Task | Checks kept | Dropped (reference failed) | " + " | ".join(NAMES[v] for v in EXPECT) + " |",
          "| --- | --- | --- |" + " --- |" * len(EXPECT)]
    for tid, kept, dropped, cells in rows:
        md.append(f"| {tid} | {', '.join(kept)} | {', '.join(dropped) or '-'} | " + " | ".join(cells) + " |")
    md += ["", "**Broken copies caught (where an intended check applies):** " + "; ".join(
        f"{NAMES[v]} {c}/{n}" for v, (c, n) in caught_tot.items()),
           "", "**Detachment copies caught, counting only copies where the part really comes apart:** " + "; ".join(
        f"{NAMES[v]} {c}/{n}" for v, (c, n) in split_tot.items()),
           "", "**Which intended check fired (a copy can trip several):** " + "; ".join(
        f"{NAMES[v]} " + ", ".join(f"{k} {n}" for k, n in sorted(c.items())) for v, c in by_check.items() if c)]
    out = Path(results).parent
    (out / f"{name}.json").write_text(json.dumps(dict(tasks=adm, caught=caught_tot, caught_split_only=split_tot,
                                                       fired=by_check), indent=1))
    (out / f"{name}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "validation/results.json"))
    ap.add_argument("--tasks-dir", default=str(ROOT / "tasks"))
    ap.add_argument("--name", default="admission", help="output name: <results dir>/<name>.{md,json}")
    ap.add_argument("--no-write-specs", action="store_true", help="report only; leave spec.json untouched")
    a = ap.parse_args()
    main(a.results, a.tasks_dir, a.name, not a.no_write_specs)
