"""Import Valkyrie run results (results.json) as graded runs under runs/<label>/T../<try>/grade_first.json.

python3 src/import_valkyrie.py <results.json> <label>
    legacy: anibench/core runs, written to try folder 1 (e.g. label = sonnet-cc for the Claude Code agent)
python3 src/import_valkyrie.py <results.json> <label> --setting single [--try 2]
    protocol runs (docs/protocol.md): written to try folders <setting>-<n>, n = --try, --try + 1, ...
    when a task appears more than once in the file (several attempts in one run), and the setting is
    recorded in each grade file. Import sample i of a setting with --try i, or one file holding all samples.
"""
import argparse
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ("single", "feedback", "agent")
AUDIT_KEYS = ("preview_calls", "probe_tests_visible")


def main(path, label, setting=None, start=1, runs_dir=None):
    runs_dir = Path(runs_dir) if runs_dir else ROOT / "runs"
    d = json.loads(Path(path).read_text())
    r = d.get("evaluation_results") or {}
    r = r if isinstance(r, list) else list(r.values())
    seen = defaultdict(int)
    n = 0
    for x in r:
        tid = x["task_id"].split("-")[-1].upper()
        spec = json.loads((ROOT / "tasks" / tid / "spec.json").read_text())
        rw = x.get("rewards") or {}
        grades = {k: {"ok": bool(v >= 0.5)} for k, v in rw.items() if k.startswith("G")}
        status = "PASS" if rw.get("reward", 0) >= 0.5 else ("FAIL" if grades else "RUNTIME")
        if setting is None:
            try_ = "1"
        else:
            try_ = f"{setting}-{start + seen[tid]}"
            seen[tid] += 1
        out = runs_dir / label / tid / try_
        out.mkdir(parents=True, exist_ok=True)
        g = dict(stage="first", task=tid, model=label, try_=try_, tier=spec["tier"], status=status,
                 grades=dict(grades, **{"pass": status == "PASS"}) if grades else None, source="valkyrie",
                 run_id=d.get("benchmark_id"), verifier_tail=(x.get("metadata") or {}).get("verifier_output", "")[-400:])
        if g["grades"] is None:
            del g["grades"]
        if setting is not None:
            g["setting"] = setting
            audit = {k: rw[k] for k in AUDIT_KEYS if k in rw}
            if audit:
                g["audit"] = audit
        (out / "grade_first.json").write_text(json.dumps(g, indent=1))
        n += 1
    print("imported", n, "runs as", label, "" if setting is None else f"(setting {setting})")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Import Valkyrie results.json into runs/")
    ap.add_argument("results")
    ap.add_argument("label", help="model label, e.g. sonnet-cc; the same label across settings")
    ap.add_argument("--setting", choices=SETTINGS, help="protocol setting; omit for legacy anibench/core runs")
    ap.add_argument("--try", dest="start", type=int, default=1, help="sample number of the first attempt (default 1)")
    a = ap.parse_args()
    main(a.results, a.label, a.setting, a.start)
