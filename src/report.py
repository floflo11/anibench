"""Aggregate grades into results tables, charts and a failure-library index.

Writes results/summary.json, results/runs.csv, results/README.md, results/charts/*.png,
results/library/<model>_<task>_<try>.gif
"""
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
GRADERS = ["G1", "G2", "G3", "G4", "G5", "G6"]
GNAME = {"G1": "Isolation", "G2": "Integrity", "G3": "Area", "G4": "Motion", "G5": "Pivot", "G6": "Loop/fidelity"}
STAGE = {"G1": "isolation", "G2": "cut-out", "G3": "cut-out", "G4": "motion", "G5": "pivot", "G6": "motion"}
LABEL = {"sonnet": "Claude Sonnet 5.5", "sol": "GPT-6.1 Sol", "qwen": "Qwen 3.8 27B",
         "nemotron": "Nemotron 3.5 Super VL", "gemma": "Gemma 4 31B",
         "gemini4": "Gemini 4 Carbon", "grok": "Grok 4.7", "kimi": "Kimi K3.1 Pro", "deepseek": "DeepSeek V4 Flash Vision"}


def final_grade(d):
    """Use the repair turn's grade if there was one, else the first."""
    for stage in ("repair", "first"):
        p = d / f"grade_{stage}.json"
        if p.exists():
            g = json.loads(p.read_text())
            g["final_stage"] = stage
            g["repaired"] = stage == "repair"
            return g
    return None


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "charts").mkdir(exist_ok=True)
    lib = OUT / "library"
    lib.mkdir(exist_ok=True)
    rows = []
    for d in sorted((ROOT / "runs").glob("*/T*/*")):
        if not d.is_dir():
            continue
        g = final_grade(d)
        if not g:
            continue
        row = dict(model=d.parent.parent.name, task=d.parent.name, try_=d.name, tier=g["tier"], status=g["status"],
                   stage=g["final_stage"], cost=(g.get("usage") or {}).get("cost"),
                   out_tokens=(g.get("usage") or {}).get("completion_tokens"))
        for k in GRADERS:
            row[k] = "" if "grades" not in g or k not in g["grades"] else ("ok" if g["grades"][k]["ok"] else "FAIL")
        rows.append(row)
        gif = d / f"anim_{g['final_stage']}.gif"
        if gif.exists():
            shutil.copy(gif, lib / f"{row['model']}_{row['task']}_{row['try_']}.gif")
    if not rows:
        print("no graded runs")
        return
    with open(OUT / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    models = sorted({r["model"] for r in rows})
    summ = {}
    for m in models:
        rs = [r for r in rows if r["model"] == m and r["tier"] in (1, 2)]
        n = len(rs)
        p = sum(r["status"] == "PASS" for r in rs)
        by_tier = {}
        for t in (1, 2):
            rt = [r for r in rs if r["tier"] == t]
            by_tier[t] = dict(n=len(rt), passed=sum(r["status"] == "PASS" for r in rt))
        runtime = sum(r["status"] in ("RUNTIME", "NO_HTML", "API_ERROR") for r in rs)
        gfail = {}
        for k in GRADERS:
            applicable = [r for r in rs if r[k] in ("ok", "FAIL")]
            gfail[k] = dict(n=len(applicable), failed=sum(r[k] == "FAIL" for r in applicable))
        summ[m] = dict(label=LABEL.get(m, m), n=n, passed=p, pass_rate=round(p / n, 3) if n else None,
                       by_tier=by_tier, runtime_fail=runtime, grader_fail=gfail,
                       cost=round(sum(r["cost"] or 0 for r in rows if r["model"] == m), 3))
    (OUT / "summary.json").write_text(json.dumps(summ, indent=1))

    full_models = [m for m in models if summ[m]["n"] >= 10]  # charts only for models that ran the full set
    models = full_models or models
    # chart 1: pass rate per model and tier
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    xs = range(len(models))
    w = 0.38
    for i, t in enumerate((1, 2)):
        vals = [summ[m]["by_tier"][t]["passed"] / max(1, summ[m]["by_tier"][t]["n"]) * 100 for m in models]
        bars = ax.bar([x + (i - 0.5) * w for x in xs], vals, w, label=f"Tier {t}", color=["#3b6fd8", "#9db7ec"][i])
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center", fontsize=8)
    ax.set_xticks(list(xs), [LABEL.get(m, m) for m in models], fontsize=8)
    ax.set_ylabel("Tasks passed (%)")
    ax.set_ylim(0, 105)
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Share of animation tasks passed, by tier", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "charts/pass_rate.png")
    plt.close(fig)

    # chart 2: failure rate per grader per model
    fig, ax = plt.subplots(figsize=(7, 3.6), dpi=150)
    w = 0.8 / len(models)
    cols = ["#3b6fd8", "#e07b39", "#4a9d5b", "#8e5cc4", "#c4a23a", "#5aa3b8", "#b85a7a"]
    for i, m in enumerate(models):
        vals = [summ[m]["grader_fail"][k]["failed"] / max(1, summ[m]["grader_fail"][k]["n"]) * 100 for k in GRADERS]
        ax.bar([j + (i - (len(models) - 1) / 2) * w for j in range(len(GRADERS))], vals, w, label=LABEL.get(m, m), color=cols[i % len(cols)])
    ax.set_xticks(range(len(GRADERS)), [f"{k}\n{GNAME[k]}" for k in GRADERS], fontsize=8)
    ax.set_ylabel("Runs failing this check (%)")
    ax.spines[["top", "right"]].set_visible(False)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Where animations break: failure rate per check", fontsize=10, loc="left")
    fig.tight_layout()
    fig.savefig(OUT / "charts/failures_by_check.png")
    plt.close(fig)

    # README table
    lines = ["# Results", "", "| Model | Scored runs | Passed | Tier 1 | Tier 2 | Didn't run | Cost |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for m in models:
        s = summ[m]
        t1, t2 = s["by_tier"][1], s["by_tier"][2]
        lines.append(f"| {s['label']} | {s['n']} | {s['passed']} ({(s['pass_rate'] or 0) * 100:.0f}%) | {t1['passed']}/{t1['n']} | {t2['passed']}/{t2['n']} | {s['runtime_fail']} | ${s['cost']} |")
    lines += ["", "## Failure rate per check", "", "| Check | " + " | ".join(LABEL.get(m, m) for m in models) + " |", "| --- |" + " --- |" * len(models)]
    for k in GRADERS:
        cells = []
        for m in models:
            gf = summ[m]["grader_fail"][k]
            cells.append(f"{gf['failed']}/{gf['n']}")
        lines.append(f"| {k} {GNAME[k]} | " + " | ".join(cells) + " |")
    lines += ["", "![pass rate](charts/pass_rate.png)", "", "![failures](charts/failures_by_check.png)", "",
              "Per-run detail: `runs.csv`. Every run's animation: `library/`."]
    (OUT / "README.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summ, indent=1))


if __name__ == "__main__":
    main()
