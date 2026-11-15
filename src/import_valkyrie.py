"""Import Valkyrie run results (results.json) as graded runs under runs/<label>/T../1/grade_first.json.

python3 src/import_valkyrie.py <results.json> <label>     e.g. label = sonnet-cc (Claude Code agent)
"""
import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def main(path, label):
    d = json.loads(Path(path).read_text())
    r = d.get("evaluation_results") or {}
    r = r if isinstance(r, list) else list(r.values())
    n = 0
    for x in r:
        tid = x["task_id"].split("-")[-1].upper()
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        rw = x.get("rewards") or {}
        grades = {k: {"ok": bool(v >= 0.5)} for k, v in rw.items() if k.startswith("G")}
        status = "PASS" if rw.get("reward", 0) >= 0.5 else ("FAIL" if grades else "RUNTIME")
        out = ROOT / "runs" / label / tid / "1"
        out.mkdir(parents=True, exist_ok=True)
        g = dict(stage="first", task=tid, model=label, try_="1", tier=spec["tier"], status=status,
                 grades=dict(grades, **{"pass": status == "PASS"}) if grades else None, source="valkyrie",
                 run_id=d.get("benchmark_id"), verifier_tail=(x.get("metadata") or {}).get("verifier_output", "")[-400:])
        if g["grades"] is None:
            del g["grades"]
        (out / "grade_first.json").write_text(json.dumps(g, indent=1))
        n += 1
    print("imported", n, "runs as", label)

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
