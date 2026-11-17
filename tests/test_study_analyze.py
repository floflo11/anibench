"""Tests for src/study/analyze.py: agreement statistics against hand-computed values, the rating loaders, and an
end-to-end run on a small synthetic study. Also checks that the judge schema and prompt use the same defect codes."""
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from study import analyze as A  # noqa: E402
from study.common import DEFECT_CODES, DEFECT_CHECKS, RATING_SCHEMA  # noqa: E402


# ---------------------------------------------------------------- statistics vs hand computation

def test_fleiss_kappa_hand_example():
    # 3 items x 3 raters, categories (broken, ok): [3,0], [0,3], [2,1]
    # P_i = 1, 1, 1/3 -> Pbar = 7/9; p = (5/9, 4/9) -> Pe = 41/81; kappa = (7/9 - 41/81) / (1 - 41/81) = 22/40
    assert A.fleiss_kappa([[3, 0], [0, 3], [2, 1]]) == pytest.approx(0.55)


def test_fleiss_kappa_wikipedia_example():
    # Fleiss (1971) style example from Wikipedia: 10 subjects, 14 raters, 5 categories, kappa = 0.210
    t = [[0, 0, 0, 0, 14], [0, 2, 6, 4, 2], [0, 0, 3, 5, 6], [0, 3, 9, 2, 0], [2, 2, 8, 1, 1],
         [7, 7, 0, 0, 0], [3, 2, 6, 3, 0], [2, 5, 3, 2, 2], [6, 5, 2, 1, 0], [0, 2, 2, 3, 7]]
    assert A.fleiss_kappa(t) == pytest.approx(0.20993, abs=1e-4)


def test_fleiss_kappa_edge_cases():
    assert A.fleiss_kappa([[3, 0], [0, 3]]) == pytest.approx(1.0)
    assert np.isnan(A.fleiss_kappa([[3, 0], [3, 0]]))           # one category only: undefined
    # items rated by fewer than 2 raters carry no agreement information and are dropped
    assert A.fleiss_kappa([[3, 0], [0, 3], [1, 0]]) == pytest.approx(1.0)


def test_krippendorff_alpha_hand_example():
    # 2 coders, 4 units: (1,1) (0,0) (1,0) (0,0). Coincidences o00=4, o11=2, o01=o10=1; n0=5, n1=3, n=8.
    # alpha = 1 - (n-1) * (o01+o10) / (2 n0 n1) = 1 - 7*2/30 = 8/15
    assert A.krippendorff_alpha([[1, 1], [0, 0], [1, 0], [0, 0]]) == pytest.approx(8 / 15)


def test_krippendorff_alpha_reference_example():
    # Krippendorff (2011), "Computing Krippendorff's Alpha-Reliability": 4 observers, 12 units, missing data,
    # nominal alpha = 0.743
    N = None
    obs = [[1, 2, 3, 3, 2, 1, 4, 1, 2, N, N, N],
           [1, 2, 3, 3, 2, 2, 4, 1, 2, 5, N, 3],
           [N, 3, 3, 3, 2, 3, 4, 2, 2, 5, 1, N],
           [1, 2, 3, 3, 2, 4, 4, 1, 2, 5, 1, N]]
    units = [list(u) for u in zip(*obs)]
    assert A.krippendorff_alpha(units) == pytest.approx(0.743, abs=5e-4)


def test_cohen_kappa_hand_example():
    # 50 items: both yes 20, A yes/B no 5, A no/B yes 10, both no 15. po = 0.7, pe = 0.5*0.6 + 0.5*0.4 = 0.5
    a = [1] * 20 + [1] * 5 + [0] * 10 + [0] * 15
    b = [1] * 20 + [0] * 5 + [1] * 10 + [0] * 15
    assert A.cohen_kappa(a, b) == pytest.approx(0.4)
    assert A.cohen_kappa([1, 0, 1, 0], [1, 0, 1, 0]) == pytest.approx(1.0)


def test_binary_metrics():
    # pred broken vs truth broken: tp=3 fp=1 fn=2 tn=4
    pred = [1, 1, 1, 1, 0, 0, 0, 0, 0, 0]
    true = [1, 1, 1, 0, 1, 1, 0, 0, 0, 0]
    m = A.binary_metrics(pred, true)
    assert (m["tp"], m["fp"], m["fn"], m["tn"]) == (3, 1, 2, 4)
    assert m["accuracy"] == pytest.approx(0.7)
    assert m["precision"] == pytest.approx(0.75) and m["recall"] == pytest.approx(0.6)
    assert m["kappa"] == pytest.approx(A.cohen_kappa(pred, true))


def test_majority():
    assert A.majority([True, True, False]) is True
    assert A.majority([False, True, False]) is False
    assert A.majority([True, False]) is None
    assert A.majority([]) is None


def test_cluster_bootstrap_ci_contains_point_and_is_deterministic():
    rng = np.random.default_rng(1)
    clusters = np.repeat(np.arange(10), 5)
    pred = rng.random(50) < 0.5
    true = np.where(rng.random(50) < 0.8, pred, ~pred)
    a = A.metrics_with_ci(pred, true, clusters, n_boot=500, seed=0)
    b = A.metrics_with_ci(pred, true, clusters, n_boot=500, seed=0)
    assert a == b
    for k in ("accuracy", "kappa", "precision", "recall"):
        assert a[k + "_ci"][0] <= a[k] <= a[k + "_ci"][1]


# ---------------------------------------------------------------- synthetic study

CLIPS = {  # clip -> (task, pixel checks failing, attention)
    "c1": ("T01", [], False), "c2": ("T01", ["G1"], False), "c3": ("T02", ["G4"], False),
    "c4": ("T02", ["G2"], False), "c5": ("T03", [], False), "c6": ("T03", ["G1", "G6"], False),
    "a1": ("T01", [], True), "a2": ("T06", ["G1"], True),
}
# human truth per clip (pass, defects)
TRUTH = {"c1": (True, []), "c2": (False, ["outside_moved"]), "c3": (False, ["barely_moves"]),
         "c4": (True, []), "c5": (True, []), "c6": (False, ["outside_moved", "loop_jump"]),
         "a1": (True, []), "a2": (False, ["outside_moved"])}


def make_key():
    clips = {}
    for cid, (task, failing, att) in CLIPS.items():
        checks = {g: g not in failing for g in ("G1", "G2", "G3", "G4", "G5", "G6")}
        clips[cid] = dict(run=f"m/{task}/1", model="attention:x" if att else "m", setting="chat", task=task,
                          checks=checks, passed=not failing, attention=att,
                          expected=dict(**{"pass": TRUTH[cid][0]}, defects=TRUTH[cid][1]) if att else None)
    return dict(schema="anibench-study-key-v1", study_id="s", clips=clips)


def rating(cid, p, defects, conf=3):
    return dict(clip_id=cid, pass_=p, defects=defects, other_text="", confidence=conf)


def export(rater, rows, path, kind="json"):
    recs = [dict(clip_id=r["clip_id"], position=i, **{"pass": r["pass_"]}, defects=r["defects"], other_text="",
                 confidence=r["confidence"], first_shown_at="2026-11-17T00:00:00Z",
                 answered_at="2026-11-17T00:00:20Z", time_ms=20000 + i, n_visits=1, n_edits=0)
            for i, r in enumerate(rows)]
    if kind == "json":
        path.write_text(json.dumps(dict(schema=RATING_SCHEMA, study_id="s", rater_id=rater, ratings=recs)))
    else:
        cols = ["study_id", "rater_id", "clip_id", "position", "pass", "defects"] + [f"d_{c}" for c in DEFECT_CODES] + \
               ["other_text", "confidence", "first_shown_at", "answered_at", "time_ms", "n_visits", "n_edits"]
        with path.open("w", newline="") as f:
            w = csv.DictWriter(f, cols)
            w.writeheader()
            for r in recs:
                row = dict(study_id="s", rater_id=rater, clip_id=r["clip_id"], position=r["position"],
                           **{"pass": int(r["pass"])}, defects=";".join(r["defects"]), other_text="",
                           confidence=r["confidence"], first_shown_at=r["first_shown_at"],
                           answered_at=r["answered_at"], time_ms=r["time_ms"], n_visits=1, n_edits=0)
                row.update({f"d_{c}": int(c in r["defects"]) for c in DEFECT_CODES})
                w.writerow(row)
    return path


@pytest.fixture
def study(tmp_path):
    key = tmp_path / "key.json"
    key.write_text(json.dumps(make_key()))
    truth = [rating(c, *TRUTH[c]) for c in CLIPS]
    r1 = export("R1", truth, tmp_path / "r1.json")
    r2 = export("R2", truth, tmp_path / "r2.csv", kind="csv")
    flip = [rating(c, *TRUTH[c]) if c != "c4" else rating("c4", False, ["tore_split"], 1) for c in CLIPS]
    r3 = export("R3", flip, tmp_path / "r3.json")
    # inattentive rater: says pass to everything (fails attention check a2)
    lazy = [rating(c, True, []) for c in CLIPS]
    r4 = export("R4", lazy, tmp_path / "r4.json")
    perfect = export("judge:perfect", truth, tmp_path / "judge_perfect.json")
    allpass = export("judge:allpass", lazy, tmp_path / "judge_allpass.json")
    return dict(key=key, raters=[r1, r2, r3, r4], judges=[perfect, allpass], dir=tmp_path)


def test_load_ratings_json_and_csv_agree(study):
    a = A.load_ratings([study["raters"][0]])
    b = A.load_ratings([study["raters"][1]])
    strip = lambda rs: sorted((r["clip_id"], r["pass"], tuple(r["defects"]), r["confidence"]) for r in rs)  # noqa: E731
    assert strip(a) == strip(b)
    assert {r["rater_id"] for r in a} == {"R1"} and {r["rater_id"] for r in b} == {"R2"}


def test_load_judge_jsonl(tmp_path):
    p = tmp_path / "gpt-x.jsonl"
    p.write_text("\n".join(json.dumps(dict(clip_id=c, **{"pass": True}, defects=[], other_text="", confidence=2,
                                           reason="ok")) for c in ("c1", "c2")))
    rs = A.load_ratings([p], kind="judge")
    assert [r["rater_id"] for r in rs] == ["judge:gpt-x"] * 2 and all(r["kind"] == "judge" for r in rs)


def test_validate_judge_record():
    ok = {"clip_id": "c1", "pass": False, "defects": ["outside_moved"], "other_text": "", "confidence": 2,
          "reason": "the other child's arm moves"}
    assert A.validate_judge_record(ok) == []
    assert A.validate_judge_record({**ok, "defects": ["nope"]})
    assert A.validate_judge_record({**ok, "pass": True})            # a pass lists no defects
    assert A.validate_judge_record({**ok, "defects": []})            # a fail lists at least one
    assert A.validate_judge_record({**ok, "confidence": 5})
    assert A.validate_judge_record({k: v for k, v in ok.items() if k != "pass"})


def test_analyze_end_to_end(study):
    out = study["dir"] / "out"
    res = A.analyze(A.load_ratings(study["raters"]), A.load_ratings(study["judges"], kind="judge"),
                    json.loads(study["key"].read_text()), out, n_boot=200, seed=0, min_attention=2)
    # attention: R4 misses a2 and is excluded; the others pass both checks
    assert res["raters"]["R4"]["attention_correct"] == 1 and res["raters"]["R4"]["excluded"]
    assert not res["raters"]["R1"]["excluded"] and res["n_raters_kept"] == 3
    # attention clips are not part of the agreement analysis
    assert res["n_clips"] == 6
    # majority equals the truth (R3's flip on c4 is outvoted)
    assert res["majority"]["c4"]["pass"] is True and res["majority"]["c2"]["pass"] is False
    ev = res["evaluators"]
    # the perfect judge agrees fully; the all-pass judge has zero recall of broken clips
    assert ev["judge:perfect"]["overall"]["kappa"] == pytest.approx(1.0)
    assert ev["judge:allpass"]["overall"]["recall"] == 0.0
    # pixel checks: c4 fails G2 but humans call it fine -> one false positive, everything else right
    px = ev["pixel"]["overall"]
    assert (px["tp"], px["fp"], px["fn"], px["tn"]) == (3, 1, 0, 2)
    assert ev["pixel"]["per_defect"]["outside_moved"]["accuracy"] == pytest.approx(1.0)
    assert ev["pixel"]["per_defect"]["tore_split"]["fp"] == 1
    assert set(ev["pixel"]["per_defect"]) == set(DEFECT_CHECKS)
    # inter-rater agreement: R3 disagrees once overall
    ag = res["agreement"]["overall"]
    assert 0 < ag["fleiss_kappa"] < 1 and 0 < ag["krippendorff_alpha"] < 1
    assert "outside_moved" in res["agreement"]["per_defect"]
    assert "human_loo" in ev
    for f in ("results.json", "table.tex", "confusion.png", "per_clip.csv", "summary.md"):
        assert (out / f).exists(), f
    tex = (out / "table.tex").read_text()
    assert "\\begin{tabular}" in tex and "Pixel checks" in tex and "kappa" in tex.lower()
    assert tex.count("\\begin{tabular}") == tex.count("\\end{tabular}")


def test_cli(study):
    out = study["dir"] / "cli"
    A.main(["--key", str(study["key"]), "--ratings", *map(str, study["raters"]), "--judges",
            *map(str, study["judges"]), "--out", str(out), "--n-boot", "100"])
    assert json.loads((out / "results.json").read_text())["n_clips"] == 6


# ---------------------------------------------------------------- judge prompt and schema

def test_judge_schema_and_prompt_match_codes():
    schema = json.loads((ROOT / "src/study/judge_schema.json").read_text())
    enum = schema["properties"]["defects"]["items"]["enum"]
    assert enum == DEFECT_CODES
    assert set(schema["required"]) >= {"clip_id", "pass", "defects", "confidence"}
    prompt = (ROOT / "src/study/judge_prompt.md").read_text()
    for c in DEFECT_CODES:
        assert f"`{c}`" in prompt, c
    assert re.search(r"Did the animation do what was asked without breaking anything else\?", prompt)
    rater = (ROOT / "tools/rater.html").read_text()
    assert re.findall(r"code: '([a-z_]+)'", rater) == DEFECT_CODES
