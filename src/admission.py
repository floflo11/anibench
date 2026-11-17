"""Apply the admission rule to validation results.

A check counts for a task only if the reference animation passes it there.
Writes validation/admission.json + validation/admission.md and updates tasks/<id>/spec.json["graders"].
Also reports which broken copies each task's checks caught.
"""
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


def main():
    res = json.loads((ROOT / "validation/results.json").read_text())
    adm = {}
    md = ["# Grader validation", "",
          "Each scored task has a reference animation (correct) and up to 10 broken copies. A check counts for a task "
          "only if the reference passes it. A broken copy is *caught* if any of its intended checks fails on it; "
          "*n/a* means none of its intended checks was kept for the task (or the copy does not apply to the task kind). "
          "Intended checks: " + "; ".join(f"{NAMES[v]} {'/'.join(ks)}" for v, ks in EXPECT.items()) + ". "
          "*missed (no split)*: the part never actually comes apart in that copy (reference.oracle_split draws the part "
          "alone, frame by frame, and counts its pieces), e.g. a tip left behind that the moving part slides past "
          "while still touching it; no connectivity check can see those.", "",
          "| Task | Checks kept | Dropped (reference failed) | " + " | ".join(NAMES[v] for v in EXPECT) + " |",
          "| --- | --- | --- |" + " --- |" * len(EXPECT)]
    caught_tot = {v: [0, 0] for v in EXPECT}
    split_tot = {v: [0, 0] for v in SPLIT_VARIANTS}  # caught / applicable among copies that really split
    for tid in sorted(res):
        spec_p = ROOT / "tasks" / tid / "spec.json"
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
            hit = any(not g[k]["ok"] for k in app if k in g)
            caught_tot[v][0] += hit
            caught_tot[v][1] += 1
            split = g.get("oracle", {}).get("split", True)
            if v in split_tot and split:
                split_tot[v][0] += hit
                split_tot[v][1] += 1
            cells.append("caught" if hit else ("missed" if split else "missed (no split)"))
        adm[tid] = dict(kept=kept, dropped=dropped)
        spec["graders_all"] = orig
        spec["graders"] = kept
        spec_p.write_text(json.dumps(spec, indent=1))
        md.append(f"| {tid} | {', '.join(kept)} | {', '.join(dropped) or '-'} | " + " | ".join(cells) + " |")
    md += ["", "**Broken copies caught (where an intended check applies):** " + "; ".join(
        f"{NAMES[v]} {c}/{n}" for v, (c, n) in caught_tot.items()),
           "", "**Detachment copies caught, counting only copies where the part really comes apart:** " + "; ".join(
        f"{NAMES[v]} {c}/{n}" for v, (c, n) in split_tot.items())]
    (ROOT / "validation/admission.json").write_text(json.dumps(dict(tasks=adm, caught=caught_tot, caught_split_only=split_tot), indent=1))
    (ROOT / "validation/admission.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
