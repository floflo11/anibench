"""Statistics for the anibench evaluation protocol (docs/protocol.md).

A *run* is one sample of one model on one task in one setting:
    dict(task="T01", passed=bool, checks={"G1": True, "G2": False, "G5": None, ...} or None)
`checks` maps check name -> True (passed) / False (failed) / None (not applicable). A missing key also
means not applicable. `checks=None` means the page produced no gradable frames (no HTML, runtime error).

Every estimate is a mean over tasks of a per-task value, and every CI resamples tasks (not samples):
the task set is the main source of variance, and the k samples of a task are averaged first.
"""
from collections import defaultdict
from math import comb

import numpy as np

N_BOOT = 10_000
SEED = 0
LEVEL = 0.95


def pass_at_k(n, c, k=1):
    """Unbiased pass@k from n samples with c correct (Chen et al. 2021): 1 - C(n-c, k) / C(n, k).
    For k=1 this is c/n."""
    if n < 1 or not 0 <= c <= n or not 1 <= k <= n:
        raise ValueError(f"need n >= 1, 0 <= c <= n, 1 <= k <= n (got n={n}, c={c}, k={k})")
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def partial_credit(checks):
    """Share of applicable checks passed in one run. Not-applicable checks (None/absent) are ignored;
    a run with no gradable output scores 0."""
    vals = [bool(v) for v in (checks or {}).values() if v is not None]
    return sum(vals) / len(vals) if vals else 0.0


def _by_task(runs):
    d = defaultdict(list)
    for r in runs:
        d[r["task"]].append(r)
    return d


def task_pass_at_k(runs, k=1):
    """task -> unbiased pass@k from that task's samples."""
    return {t: pass_at_k(len(rs), sum(bool(r["passed"]) for r in rs), k) for t, rs in _by_task(runs).items()}


def task_pass1(runs):
    return task_pass_at_k(runs, 1)


def task_partial(runs):
    """task -> mean partial credit over that task's samples."""
    return {t: sum(partial_credit(r.get("checks")) for r in rs) / len(rs) for t, rs in _by_task(runs).items()}


def check_failure_rates(runs):
    """check -> dict(n=runs where the check was graded, failed, rate). Runs without grades are excluded
    (they are counted separately as no_grades by summarize)."""
    n, failed = defaultdict(int), defaultdict(int)
    for r in runs:
        for k, v in (r.get("checks") or {}).items():
            if v is None:
                continue
            n[k] += 1
            failed[k] += not v
    return {k: dict(n=n[k], failed=failed[k], rate=failed[k] / n[k]) for k in sorted(n)}


def _percentile_ci(vals, n_boot, seed, level):
    vals = np.asarray(vals, dtype=float)
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(vals), size=(n_boot, len(vals)))
    means = vals[idx].mean(axis=1)
    a = (1 - level) / 2
    lo, hi = np.percentile(means, [100 * a, 100 * (1 - a)])
    return means, float(lo), float(hi)


def bootstrap_ci(values, n_boot=N_BOOT, seed=SEED, level=LEVEL):
    """Percentile bootstrap CI of the mean of per-task values (list, or dict task -> value)."""
    vals = list(values.values()) if isinstance(values, dict) else list(values)
    if not vals:
        return dict(mean=None, lo=None, hi=None, n=0)
    _, lo, hi = _percentile_ci(vals, n_boot, seed, level)
    return dict(mean=float(np.mean(vals)), lo=lo, hi=hi, n=len(vals))


def paired_bootstrap(a, b, n_boot=N_BOOT, seed=SEED, level=LEVEL):
    """CI for mean(a) - mean(b) over the tasks both have (dicts task -> per-task value).
    Each resample draws tasks once and takes the difference on the same tasks.
    p_le0 = share of resamples where a is not better than b (a one-sided bootstrap p-value)."""
    tasks = sorted(set(a) & set(b))
    if not tasks:
        return dict(diff=None, lo=None, hi=None, p_le0=None, n=0, tasks=[])
    d = [a[t] - b[t] for t in tasks]
    means, lo, hi = _percentile_ci(d, n_boot, seed, level)
    return dict(diff=float(np.mean(d)), lo=lo, hi=hi, p_le0=float((means <= 0).mean()), n=len(tasks), tasks=tasks)


def summarize(runs, n_boot=N_BOOT, seed=SEED, level=LEVEL):
    """pass@1 and partial credit with task-bootstrap CIs, per-check failure rates, sample counts."""
    ks = [len(rs) for rs in _by_task(runs).values()]
    return dict(
        n_tasks=len(ks), n_runs=len(runs), k_min=min(ks, default=0), k_max=max(ks, default=0),
        pass1=bootstrap_ci(task_pass1(runs), n_boot, seed, level),
        partial=bootstrap_ci(task_partial(runs), n_boot, seed, level),
        checks=check_failure_rates(runs),
        no_grades=sum(not r.get("checks") for r in runs),
    )
