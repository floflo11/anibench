"""Simulated rater and judge exports for dry runs of the analysis (NOT data: every file says fake=true).

Each simulated rater starts from the pixel grader's verdict (the key) and adds noise: with probability `flip`
the overall answer is flipped; on a "No" it ticks the defects mapped to the failing checks, dropping each with
probability `drop` and adding a random extra with probability `extra`. Attention clips are answered correctly
unless the rater is `--lazy` (answers Yes to everything). Times are log-normal around 25 s per clip.

python3 src/study/fake_ratings.py --key build/study/dry/key.json --out build/study/dry/fake --raters 3 --judges 1
"""
import argparse
import json
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from study.common import DEFECT_CHECKS, DEFECT_CODES, RATING_SCHEMA  # noqa: E402


def simulate(key, rater_id, seed, flip=0.1, drop=0.2, extra=0.05, lazy=False, judge=False):
    rng = random.Random(seed)
    ids = sorted(key["clips"])
    rng.shuffle(ids)
    t = datetime(2026, 11, 20, 15, 0, tzinfo=timezone.utc)
    out = []
    for i, cid in enumerate(ids):
        info = key["clips"][cid]
        if info.get("attention") and info.get("expected"):
            p, defects = info["expected"]["pass"], list(info["expected"]["defects"])
        else:
            p = bool(info.get("passed"))
            failing = {g for g, ok in (info.get("checks") or {}).items() if ok is False}
            defects = [d for d, gs in DEFECT_CHECKS.items() if failing & set(gs) and rng.random() > drop]
            if rng.random() < flip:
                p = not p
                defects = [] if p else [rng.choice(DEFECT_CODES[:-1])]
        if lazy:
            p, defects = True, []
        if not p:
            if rng.random() < extra:
                defects.append(rng.choice(DEFECT_CODES[:-1]))
            defects = [d for d in DEFECT_CODES if d in set(defects)] or [rng.choice(DEFECT_CODES[:-1])]
        else:
            defects = []
        secs = min(120.0, rng.lognormvariate(3.2, 0.4))
        shown = t
        t += timedelta(seconds=secs + rng.uniform(0.5, 2))
        out.append(dict(clip_id=cid, position=i, **{"pass": p}, defects=defects, other_text="",
                        confidence=rng.choice([2, 3, 3]) if not judge else 2, first_shown_at=shown.isoformat(),
                        answered_at=(shown + timedelta(seconds=secs)).isoformat(), time_ms=round(secs * 1000),
                        n_visits=1, n_edits=0, **({"reason": "simulated"} if judge else {})))
    return dict(schema=RATING_SCHEMA, fake=True, study_id=key["study_id"], rater_id=rater_id,
                rater_kind="judge" if judge else "human", ratings=out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--raters", type=int, default=3)
    ap.add_argument("--lazy", type=int, default=0, help="extra inattentive raters (fail attention checks)")
    ap.add_argument("--judges", type=int, default=1)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args(argv)
    key = json.loads(Path(a.key).read_text())
    out = Path(a.out)
    (out / "ratings").mkdir(parents=True, exist_ok=True)
    (out / "judges").mkdir(parents=True, exist_ok=True)
    for i in range(a.raters + a.lazy):
        rid = f"FAKE-R{i + 1}"
        doc = simulate(key, rid, a.seed * 100 + i, lazy=i >= a.raters)
        (out / "ratings" / f"{rid}.json").write_text(json.dumps(doc, indent=1))
    for j in range(a.judges):
        jid = f"judge:fake-judge-{j + 1}"
        doc = simulate(key, jid, a.seed * 100 + 50 + j, flip=0.25, drop=0.4, extra=0.15, judge=True)
        (out / "judges" / f"fake-judge-{j + 1}.json").write_text(json.dumps(doc, indent=1))
    print(f"wrote {a.raters + a.lazy} fake rater exports and {a.judges} fake judge files to {out}")


if __name__ == "__main__":
    main()
