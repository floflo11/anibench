"""End-to-end: Valkyrie results.json -> import_valkyrie (with settings) -> report.protocol_report."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
import import_valkyrie  # noqa: E402
import report  # noqa: E402


def result(task, reward, checks, **extra):
    rw = {"reward": reward, **{k: float(v) for k, v in checks.items()}, **extra}
    return {"task_id": f"anibench-{task.lower()}", "rewards": rw, "metadata": {"verifier_output": "x"}}


def write(tmp, name, entries):
    p = tmp / name
    p.write_text(json.dumps({"benchmark_id": "run-" + name, "evaluation_results": entries}))
    return p


@pytest.fixture
def runs(tmp_path):
    rd = tmp_path / "runs"
    ok = dict(G1=1, G3=1, G4=1, G6=1)
    # model m, setting single: T01 k=2 (1 pass), T13 k=2 (0 pass, one with no output)
    f1 = write(tmp_path, "s1.json", [result("T01", 1.0, dict(G1=1, G2=1, G3=1, G4=1, G5=1, G6=1)),
                                    result("T13", 0.0, dict(ok, G1=0))])
    f2 = write(tmp_path, "s2.json", [result("T01", 0.0, dict(G1=0, G2=1, G3=1, G4=1, G5=1, G6=1)),
                                    result("T13", 0.0, {})])
    import_valkyrie.main(f1, "m", "single", 1, rd)
    import_valkyrie.main(f2, "m", "single", 2, rd)
    # model m, setting feedback: both samples in one file; records preview calls
    f3 = write(tmp_path, "f.json", [result("T01", 1.0, dict(G1=1, G2=1, G3=1, G4=1, G5=1, G6=1), preview_calls=1.0),
                                   result("T01", 1.0, dict(G1=1, G2=1, G3=1, G4=1, G5=1, G6=1), preview_calls=1.0),
                                   result("T13", 1.0, ok, preview_calls=1.0, probe_tests_visible=0.0),
                                   result("T13", 0.0, dict(ok, G4=0), preview_calls=2.0)])
    import_valkyrie.main(f3, "m", "feedback", 1, rd)
    # model n, setting single, T01 only; and a legacy (no setting) import
    import_valkyrie.main(write(tmp_path, "n.json", [result("T01", 0.0, dict(G1=0, G2=0, G3=1, G4=1, G5=1, G6=1))]),
                         "n", "single", 1, rd)
    import_valkyrie.main(write(tmp_path, "legacy.json", [result("T01", 1.0, dict(G1=1, G2=1, G3=1, G4=1, G5=1, G6=1))]),
                         "n", None, 1, rd)
    return rd


def test_import_layout(runs):
    assert sorted(p.name for p in (runs / "m/T01").iterdir()) == ["feedback-1", "feedback-2", "single-1", "single-2"]
    g = json.loads((runs / "m/T13/feedback-2/grade_first.json").read_text())
    assert g["setting"] == "feedback" and g["audit"] == {"preview_calls": 2.0} and g["status"] == "FAIL"
    legacy = json.loads((runs / "n/T01/1/grade_first.json").read_text())
    assert "setting" not in legacy and legacy["status"] == "PASS"
    assert json.loads((runs / "m/T13/single-2/grade_first.json").read_text())["status"] == "RUNTIME"


def test_protocol_report(runs, tmp_path):
    out = tmp_path / "results"
    out.mkdir()
    res = report.protocol_report(runs, out, n_boot=500, seed=0, chart=False)
    cells = {(c["model"], c["setting"]): c for c in res["cells"]}
    assert set(cells) == {("m", "single"), ("m", "feedback"), ("n", "single"), ("n", "core")}
    ms = cells[("m", "single")]
    assert ms["n_tasks"] == 2 and ms["k_min"] == ms["k_max"] == 2 and ms["no_grades"] == 1
    assert ms["pass1"]["mean"] == pytest.approx((0.5 + 0) / 2)
    # T01: (1 + 5/6) / 2; T13: (3/4 + 0) / 2
    assert ms["partial"]["mean"] == pytest.approx(((1 + 5 / 6) / 2 + (0.75 + 0) / 2) / 2)
    assert ms["checks"]["G1"] == dict(n=3, failed=2, rate=pytest.approx(2 / 3))
    mf = cells[("m", "feedback")]
    assert mf["pass1"]["mean"] == pytest.approx((1 + 0.5) / 2)
    # comparisons: same model across settings, or same setting across models; never both different
    pairs = {((c["a"]["model"], c["a"]["setting"]), (c["b"]["model"], c["b"]["setting"])): c for c in res["comparisons"]}
    assert (("m", "feedback"), ("m", "single")) in pairs
    assert (("m", "single"), ("n", "single")) in pairs
    assert (("m", "feedback"), ("n", "single")) not in pairs
    c = pairs[(("m", "single"), ("n", "single"))]
    assert c["pass1_diff"]["n"] == 1 and c["pass1_diff"]["diff"] == pytest.approx(0.5)
    md = (out / "protocol.md").read_text()
    assert "| m | feedback | 2 | 2 | 75.0 [" in md
    assert json.loads((out / "protocol.json").read_text())["n_boot"] == 500
