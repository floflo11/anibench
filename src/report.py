"""Aggregate grades into results tables, charts and a failure-library index.

Writes results/summary.json, results/runs.csv, results/README.md, results/charts/*.png,
results/library/<model>_<task>_<try>.gif  (legacy tables: first try of each model)

and, for the evaluation protocol (docs/protocol.md), results/protocol.json, results/protocol.md and
results/charts/protocol_pass1.png: per model x setting, pass@1 over all k samples with a task-bootstrap
95% CI, partial credit with CI, per-check failure rates, and paired-bootstrap comparisons.
"""
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

import stats  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results"
GRADERS = ["G1", "G2", "G2b", "G2c", "G3", "G4", "G5", "G6"]
GNAME = {"G1": "Isolation", "G2": "Integrity", "G2b": "Connectivity", "G2c": "Residual", "G3": "Area", "G4": "Motion",
         "G5": "Pivot", "G6": "Loop/fidelity"}
STAGE = {"G1": "isolation", "G2": "cut-out", "G2b": "cut-out", "G2c": "cut-out", "G3": "cut-out", "G4": "motion",
         "G5": "pivot", "G6": "motion"}
LABEL = {"sonnet": "Claude Sonnet 5.5", "sol": "GPT-6.1 Sol", "qwen": "Qwen 3.8 27B",
         "nemotron": "Nemotron 3.5 Super VL", "gemma": "Gemma 4 31B",
         "sonnet-cc": "Claude Sonnet 5.5 (Claude Code, Valkyrie)", "sol-codex": "GPT-6.1 Sol (Codex, Valkyrie)",
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


def setting_of(g):
    """Protocol setting of a graded run. Runs imported before the protocol have no setting field:
    Valkyrie runs used the legacy anibench/core dataset; local runs were chat single-shot + one repair turn."""
    return g.get("setting") or ("core" if g.get("source") == "valkyrie" else "chat")


EXCLUDED = ("API_ERROR", "HUMAN")  # infrastructure failures and human-labelled tasks are not scored


def protocol_rows(runs_dir=None):
    rows, excluded = [], defaultdict(int)
    for d in sorted(Path(runs_dir or ROOT / "runs").glob("*/T*/*")):
        if not d.is_dir():
            continue
        g = final_grade(d)
        if not g:
            continue
        model, setting = d.parent.parent.name, setting_of(g)
        if g["status"] in EXCLUDED or g.get("tier") not in (1, 2):
            excluded[(model, setting)] += 1
            continue
        grades = g.get("grades") or {}
        checks = {k: (None if v.get("ok") is None else bool(v["ok"]))
                  for k, v in grades.items() if k != "pass" and isinstance(v, dict)}
        rows.append(dict(model=model, setting=setting, task=d.parent.name, try_=d.name,
                         passed=g["status"] == "PASS", checks=checks or None))
    return rows, excluded


def _ci(x, pct=True):
    if x.get("mean") is None:
        return "–"
    f = 100 if pct else 1
    return f"{x['mean'] * f:.1f} [{x['lo'] * f:.1f}, {x['hi'] * f:.1f}]"


def _diff(x):
    if x.get("diff") is None:
        return "–"
    return f"{x['diff'] * 100:+.1f} [{x['lo'] * 100:+.1f}, {x['hi'] * 100:+.1f}]"


def check_order(k):
    return (k[:2], len(k), k)


def protocol_report(runs_dir=None, out=None, n_boot=stats.N_BOOT, seed=stats.SEED, chart=True):
    out = Path(out or OUT)
    rows, excluded = protocol_rows(runs_dir)
    if not rows:
        print("no protocol runs")
        return None
    groups = defaultdict(list)
    for r in rows:
        groups[(r["model"], r["setting"])].append(r)
    cells = {}
    for (m, st), rs in sorted(groups.items()):
        s = stats.summarize(rs, n_boot, seed)
        s.update(model=m, setting=st, label=LABEL.get(m, m), excluded=excluded.get((m, st), 0))
        cells[(m, st)] = s
    tp = {k: stats.task_pass1(rs) for k, rs in groups.items()}
    tc = {k: stats.task_partial(rs) for k, rs in groups.items()}

    def compare(a, b):
        p = stats.paired_bootstrap(tp[a], tp[b], n_boot, seed)
        c = stats.paired_bootstrap(tc[a], tc[b], n_boot, seed)
        p.pop("tasks"); c.pop("tasks")
        return dict(a=dict(model=a[0], setting=a[1]), b=dict(model=b[0], setting=b[1]), pass1_diff=p, partial_diff=c)

    keys = sorted(groups)
    comps = []
    for i, a in enumerate(keys):  # same setting, different models; same model, different settings
        for b in keys[i + 1:]:
            if (a[1] == b[1]) != (a[0] == b[0]):
                comps.append(compare(a, b))
    res = dict(n_boot=n_boot, seed=seed, level=stats.LEVEL, cells=list(cells.values()), comparisons=comps)
    (out / "protocol.json").write_text(json.dumps(res, indent=1))

    checks = sorted({k for c in cells.values() for k in c["checks"]}, key=check_order)
    L = ["# Results by evaluation protocol", "",
         "Generated by `src/report.py`; definitions in `docs/protocol.md`. pass@1 and partial credit are means over "
         "tasks of the per-task mean over k samples, in %, with 95% task-bootstrap CIs "
         f"({n_boot} resamples, seed {seed}). Settings `core` (legacy Valkyrie dataset) and `chat` "
         "(single-shot API + one repair turn) are pre-protocol runs.", "",
         "| Model | Setting | Tasks | k | pass@1 % [95% CI] | Partial credit % [95% CI] | No output | Excluded |",
         "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for c in cells.values():
        k = str(c["k_min"]) if c["k_min"] == c["k_max"] else f"{c['k_min']}–{c['k_max']}"
        L.append(f"| {c['label']} | {c['setting']} | {c['n_tasks']} | {k} | {_ci(c['pass1'])} | {_ci(c['partial'])} "
                 f"| {c['no_grades']}/{c['n_runs']} | {c['excluded']} |")
    L += ["", "## Failure rate per check (graded runs; runs without output excluded)", "",
          "| Model | Setting | " + " | ".join(checks) + " |", "| --- | --- |" + " --- |" * len(checks)]
    for c in cells.values():
        cs = [f"{c['checks'][k]['rate'] * 100:.0f}% ({c['checks'][k]['failed']}/{c['checks'][k]['n']})"
              if k in c["checks"] else "–" for k in checks]
        L.append(f"| {c['label']} | {c['setting']} | " + " | ".join(cs) + " |")
    L += ["", "## Paired comparisons (A − B on the tasks both ran; percentage points [95% paired-bootstrap CI])", "",
          "| A | B | Shared tasks | Δ pass@1 | P(Δ ≤ 0) | Δ partial credit |", "| --- | --- | --- | --- | --- | --- |"]
    for x in comps:
        a, b = x["a"], x["b"]
        p = x["pass1_diff"]
        ple0 = "–" if p["p_le0"] is None else f"{p['p_le0']:.3f}"
        L.append(f"| {LABEL.get(a['model'], a['model'])} · {a['setting']} | {LABEL.get(b['model'], b['model'])} · "
                 f"{b['setting']} | {p['n']} | {_diff(p)} | {ple0} | {_diff(x['partial_diff'])} |")
    if chart:
        L += ["", "![pass@1 by model and setting](charts/protocol_pass1.png)"]
    (out / "protocol.md").write_text("\n".join(L) + "\n")

    if chart:
        (out / "charts").mkdir(parents=True, exist_ok=True)
        cl = list(cells.values())
        fig, ax = plt.subplots(figsize=(7, 0.32 * len(cl) + 1.2), dpi=150)
        ys = range(len(cl))[::-1]
        for y, c in zip(ys, cl):
            p = c["pass1"]
            ax.errorbar(p["mean"] * 100, y, xerr=[[(p["mean"] - p["lo"]) * 100], [(p["hi"] - p["mean"]) * 100]],
                        fmt="o", color="#3b6fd8", ecolor="#9db7ec", capsize=3, ms=4)
        ax.set_yticks(list(ys), [f"{c['label']} · {c['setting']} (n={c['n_tasks']})" for c in cl], fontsize=7)
        ax.set_xlim(-2, 102)
        ax.set_xlabel("pass@1 (%), 95% task-bootstrap CI", fontsize=8)
        ax.spines[["top", "right"]].set_visible(False)
        ax.set_title("pass@1 by model and setting", fontsize=10, loc="left")
        fig.tight_layout()
        fig.savefig(out / "charts/protocol_pass1.png")
        plt.close(fig)
    return res


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
    all_rows = rows
    rows = [r for r in rows if r["try_"] == "1"]  # compare every model on its first try
    with open(OUT / "runs.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        w.writeheader()
        w.writerows(all_rows)

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
    protocol_report()


if __name__ == "__main__":
    main()
