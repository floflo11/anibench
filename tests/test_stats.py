"""Tests for src/stats.py, checked against small hand-computed examples."""
import itertools
import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import stats  # noqa: E402


# ---------- pass@k ----------

def brute_pass_at_k(n, c, k):
    """Fraction of all k-subsets of n samples (c correct) that contain at least one correct sample."""
    samples = [1] * c + [0] * (n - c)
    subsets = list(itertools.combinations(range(n), k))
    return sum(any(samples[i] for i in s) for s in subsets) / len(subsets)


def test_pass_at_1_is_fraction_correct():
    assert stats.pass_at_k(3, 0, 1) == 0.0
    assert stats.pass_at_k(3, 1, 1) == pytest.approx(1 / 3)
    assert stats.pass_at_k(3, 3, 1) == 1.0
    assert stats.pass_at_k(5, 2, 1) == pytest.approx(0.4)


@pytest.mark.parametrize("n,c,k", [(3, 1, 2), (5, 2, 3), (4, 1, 4), (6, 3, 2), (5, 0, 2), (5, 5, 3)])
def test_pass_at_k_matches_brute_force(n, c, k):
    assert stats.pass_at_k(n, c, k) == pytest.approx(brute_pass_at_k(n, c, k))


def test_pass_at_k_hand_value():
    # n=4, c=1, k=2: 1 - C(3,2)/C(4,2) = 1 - 3/6 = 0.5
    assert stats.pass_at_k(4, 1, 2) == pytest.approx(0.5)


def test_pass_at_k_rejects_bad_input():
    with pytest.raises(ValueError):
        stats.pass_at_k(2, 3, 1)
    with pytest.raises(ValueError):
        stats.pass_at_k(2, 1, 3)
    with pytest.raises(ValueError):
        stats.pass_at_k(0, 0, 1)


# ---------- per-run partial credit ----------

def test_partial_credit_ignores_not_applicable_checks():
    # 2 of 3 applicable checks pass; G5 is null (not applicable), G6 absent
    checks = {"G1": True, "G2": False, "G3": True, "G4": None}
    assert stats.partial_credit(checks) == pytest.approx(2 / 3)


def test_partial_credit_all_and_none():
    assert stats.partial_credit({"G1": True, "G2": True}) == 1.0
    assert stats.partial_credit({"G1": False, "G2": False}) == 0.0


def test_partial_credit_no_grades_is_zero():
    # a page that did not run gets no credit
    assert stats.partial_credit(None) == 0.0
    assert stats.partial_credit({}) == 0.0
    assert stats.partial_credit({"G1": None}) == 0.0


# ---------- per-task aggregation ----------

RUNS = [
    # task A: k=3, 2 passes; partial 1, 1, 0.5
    dict(task="A", passed=True, checks={"G1": True, "G2": True}),
    dict(task="A", passed=True, checks={"G1": True, "G2": True}),
    dict(task="A", passed=False, checks={"G1": True, "G2": False}),
    # task B: k=2, 0 passes; one runtime failure (no checks), one with 1/3 checks
    dict(task="B", passed=False, checks=None),
    dict(task="B", passed=False, checks={"G1": False, "G2": True, "G3": False, "G5": None}),
]


def test_task_pass1():
    t = stats.task_pass1(RUNS)
    assert t == {"A": pytest.approx(2 / 3), "B": 0.0}


def test_task_partial():
    t = stats.task_partial(RUNS)
    assert t["A"] == pytest.approx((1 + 1 + 0.5) / 3)
    assert t["B"] == pytest.approx((0 + 1 / 3) / 2)


def test_check_failure_rates_count_only_applicable_graded_runs():
    f = stats.check_failure_rates(RUNS)
    # G1 graded in 4 runs (A x3, B second), fails once
    assert f["G1"] == dict(n=4, failed=1, rate=pytest.approx(0.25))
    # G2 graded in 4 runs, fails once (A third)
    assert f["G2"] == dict(n=4, failed=1, rate=pytest.approx(0.25))
    # G3 graded once, failed
    assert f["G3"] == dict(n=1, failed=1, rate=1.0)
    # G5 is null everywhere -> not applicable, not reported
    assert "G5" not in f


# ---------- bootstrap ----------

def test_bootstrap_constant_values_have_zero_width():
    r = stats.bootstrap_ci([0.5, 0.5, 0.5, 0.5])
    assert r["mean"] == 0.5 and r["lo"] == 0.5 and r["hi"] == 0.5 and r["n"] == 4


def test_bootstrap_two_tasks_hand_computed():
    # Resampling 2 tasks from {0, 1}: mean is 0 (p=.25), .5 (p=.5), 1 (p=.25).
    # The 2.5th percentile is 0 and the 97.5th is 1.
    r = stats.bootstrap_ci([0.0, 1.0], n_boot=10000, seed=0)
    assert r["mean"] == 0.5
    assert r["lo"] == 0.0 and r["hi"] == 1.0


def test_bootstrap_ci_brackets_mean_and_is_seeded():
    vals = [0, 0, 1, 1, 1, 0, 1, 0.5, 0.25, 1]
    a = stats.bootstrap_ci(vals, seed=7)
    b = stats.bootstrap_ci(vals, seed=7)
    assert a == b
    assert a["lo"] <= a["mean"] <= a["hi"]
    assert a["mean"] == pytest.approx(sum(vals) / len(vals))
    # normal-approx sanity: half-width close to 1.96 * sd / sqrt(n)
    m = sum(vals) / len(vals)
    sd = math.sqrt(sum((v - m) ** 2 for v in vals) / len(vals))
    half = (a["hi"] - a["lo"]) / 2
    assert half == pytest.approx(1.96 * sd / math.sqrt(len(vals)), rel=0.25)


def test_bootstrap_accepts_dict_and_resamples_tasks():
    # dict input (task -> per-task value) is the normal call path
    r = stats.bootstrap_ci({"A": 1.0, "B": 0.0, "C": 1.0})
    assert r["mean"] == pytest.approx(2 / 3) and r["n"] == 3


def test_bootstrap_empty():
    r = stats.bootstrap_ci([])
    assert r["n"] == 0 and r["mean"] is None and r["lo"] is None and r["hi"] is None


# ---------- paired bootstrap ----------

def test_paired_identical_models_zero_difference():
    a = {"A": 1.0, "B": 0.0, "C": 0.5}
    r = stats.paired_bootstrap(a, dict(a))
    assert r["diff"] == 0 and r["lo"] == 0 and r["hi"] == 0 and r["n"] == 3


def test_paired_uses_only_shared_tasks():
    a = {"A": 1.0, "B": 1.0, "C": 1.0, "D": 1.0}
    b = {"A": 0.0, "B": 0.0, "X": 1.0}
    r = stats.paired_bootstrap(a, b)
    assert r["n"] == 2 and r["tasks"] == ["A", "B"]
    assert r["diff"] == 1.0 and r["lo"] == 1.0 and r["hi"] == 1.0


def test_paired_bootstrap_hand_computed():
    # per-task differences a-b = [1, 0]: same distribution as the 2-task bootstrap above
    a = {"A": 1.0, "B": 0.5}
    b = {"A": 0.0, "B": 0.5}
    r = stats.paired_bootstrap(a, b, seed=0)
    assert r["diff"] == 0.5 and r["lo"] == 0.0 and r["hi"] == 1.0
    # share of resamples where a is not better than b: P(both draws are task B) = 1/4
    assert r["p_le0"] == pytest.approx(0.25, abs=0.02)


def test_paired_is_tighter_than_unpaired_when_tasks_vary():
    # tasks differ a lot in difficulty, but a beats b by exactly 0.1 on every task
    a = {f"t{i}": min(1.0, i / 10 + 0.1) for i in range(10)}
    b = {f"t{i}": i / 10 for i in range(10)}
    r = stats.paired_bootstrap(a, b)
    assert r["lo"] == pytest.approx(0.1) and r["hi"] == pytest.approx(0.1)


# ---------- summary ----------

def test_summarize():
    s = stats.summarize(RUNS, n_boot=2000, seed=0)
    assert s["n_tasks"] == 2 and s["n_runs"] == 5
    assert s["k_min"] == 2 and s["k_max"] == 3
    assert s["pass1"]["mean"] == pytest.approx((2 / 3 + 0) / 2)
    assert s["partial"]["mean"] == pytest.approx(((2.5 / 3) + (1 / 6)) / 2)
    assert s["no_grades"] == 1
    assert s["checks"]["G3"]["failed"] == 1
