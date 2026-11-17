"""Analyze the human study (E4): inter-rater agreement, the human majority label, and how well the pixel
checks and each multimodal LLM judge agree with it. See docs/human_study.md.

Inputs
  --key      key.json written by make_clips.py (grader results and attention checks per clip)
  --ratings  rater exports from tools/rater.html (.json or .csv; one file per rater)
  --judges   judge outputs in the same schema (.json export, or .jsonl with one judge_schema.json record
             per line; the judge name is the rater_id, else the file stem)
Outputs (in --out)
  results.json   every number below, with 95% cluster-bootstrap CIs
  table.tex      two booktabs tables: overall agreement with the human majority, and per defect <-> check
  confusion.png  2x2 confusion matrices (overall "broken") per evaluator
  per_clip.csv   one row per clip: human votes and majority, pixel checks, judge labels
  summary.md     a readable summary

Definitions
  "broken" is the positive class: a human or judge answered No, or the pixel grader failed the run.
  Per defect, a human/judge flags defect d if they answered No and ticked d; the pixel grader flags it if
  any check mapped to d (common.DEFECT_CHECKS) failed. Clips where no mapped check applies are skipped.
  The human majority is a strict majority of the kept raters (ties -> no label; that clip is skipped).
  "Human (one vs rest)" compares every single rating with the majority of the *other* raters on that clip,
  the usual ceiling for an automatic evaluator.
  Raters who miss more attention checks than allowed (--min-attention correct out of the attention clips
  they rated) are excluded; attention clips never enter the agreement numbers.
  CIs resample tasks (clusters of clips), as src/stats.py does for pass rates; --boot-unit clip resamples
  clips instead.

python3 src/study/analyze.py --key build/study/x/key.json --ratings ratings/*.json --judges judges/*.jsonl \\
    --out results/study
"""
import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
import stats  # noqa: E402
from study.common import DEFECT_CHECKS, DEFECT_CODES, DEFECT_LABEL  # noqa: E402

PIXEL = "pixel"
HUMAN_LOO = "human_loo"
EV_LABEL = {PIXEL: "Pixel checks", HUMAN_LOO: "Human (one vs.\\ rest)"}


# ---------------------------------------------------------------- agreement statistics

def fleiss_kappa(counts):
    """Fleiss' kappa from an items x categories count table. Items may have different numbers of raters
    (P_i uses each item's own n_i, category shares pool all ratings); items with < 2 ratings are dropped.
    With a constant number of raters this is exactly Fleiss (1971). nan if chance agreement is 1."""
    c = np.asarray(counts, float)
    n = c.sum(1)
    c, n = c[n >= 2], n[n >= 2]
    if len(c) == 0:
        return float("nan")
    P = ((c * c).sum(1) - n) / (n * (n - 1))
    p = c.sum(0) / c.sum()
    Pe = (p * p).sum()
    return float("nan") if Pe >= 1 - 1e-12 else float((P.mean() - Pe) / (1 - Pe))


def krippendorff_alpha(units):
    """Krippendorff's alpha, nominal metric. units: list of lists of values (None = missing).
    Coincidence-matrix form: alpha = 1 - (n - 1) * sum_{c != k} o_ck / sum_{c != k} n_c n_k."""
    vals = sorted({v for u in units for v in u if v is not None}, key=str)
    ix = {v: i for i, v in enumerate(vals)}
    o = np.zeros((len(vals), len(vals)))
    for u in units:
        u = [ix[v] for v in u if v is not None]
        m = len(u)
        if m < 2:
            continue
        cnt = np.bincount(u, minlength=len(vals)).astype(float)
        o += (np.outer(cnt, cnt) - np.diag(cnt)) / (m - 1)
    nc = o.sum(1)
    n = nc.sum()
    off = o.sum() - np.trace(o)
    exp = n * n - (nc * nc).sum()
    if n < 2 or exp == 0:
        return float("nan")
    return float(1 - (n - 1) * off / exp)


def cohen_kappa(a, b):
    a, b = list(a), list(b)
    cats = sorted(set(a) | set(b), key=str)
    n = len(a)
    po = sum(x == y for x, y in zip(a, b)) / n
    pe = sum((a.count(c) / n) * (b.count(c) / n) for c in cats)
    return float("nan") if pe >= 1 - 1e-12 else (po - pe) / (1 - pe)


def _rates(tp, fp, fn, tn):
    """Vectorized metrics from confusion counts (arrays or scalars). Positive class = broken."""
    tp, fp, fn, tn = (np.asarray(x, float) for x in (tp, fp, fn, tn))
    n = tp + fp + fn + tn
    with np.errstate(invalid="ignore", divide="ignore"):
        acc = (tp + tn) / n
        prec = tp / (tp + fp)
        rec = tp / (tp + fn)
        f1 = 2 * tp / (2 * tp + fp + fn)
        pe = ((tp + fp) * (tp + fn) + (fn + tn) * (fp + tn)) / (n * n)
        kap = np.where(pe >= 1 - 1e-12, np.nan, (acc - pe) / (1 - pe))
    return dict(accuracy=acc, precision=prec, recall=rec, f1=f1, kappa=kap)


def _confusion(pred, true):
    pred, true = np.asarray(pred, bool), np.asarray(true, bool)
    return [int((pred & true).sum()), int((pred & ~true).sum()), int((~pred & true).sum()), int((~pred & ~true).sum())]


def binary_metrics(pred, true):
    """pred/true: 1 = broken. Accuracy, precision/recall/F1 of 'broken', Cohen's kappa, confusion counts."""
    tp, fp, fn, tn = _confusion(pred, true)
    r = {k: _f(v) for k, v in _rates(tp, fp, fn, tn).items()}
    return dict(n=tp + fp + fn + tn, tp=tp, fp=fp, fn=fn, tn=tn, **r)


def _f(x):
    x = float(x)
    return None if np.isnan(x) else x


def _boot_idx(n_clusters, n_boot, seed):
    return np.random.default_rng(seed).integers(0, n_clusters, size=(n_boot, n_clusters))


def _clusters(cl):
    keys = sorted(set(cl), key=str)
    m = {k: i for i, k in enumerate(keys)}
    return np.array([m[c] for c in cl], int), len(keys)


def _pct(samples, level):
    s = np.asarray(samples, float)
    s = s[~np.isnan(s)]
    if len(s) == 0:
        return None
    a = (1 - level) / 2
    lo, hi = np.percentile(s, [100 * a, 100 * (1 - a)])
    return [float(lo), float(hi)]


def metrics_with_ci(pred, true, clusters, n_boot=stats.N_BOOT, seed=stats.SEED, level=stats.LEVEL):
    """binary_metrics plus percentile CIs from a cluster bootstrap (resample clusters with replacement)."""
    m = binary_metrics(pred, true)
    if m["n"] == 0:
        return m
    ci, T = _clusters(clusters)
    pred, true = np.asarray(pred, bool), np.asarray(true, bool)
    per = np.zeros((T, 4))
    for t in range(T):
        per[t] = _confusion(pred[ci == t], true[ci == t])
    s = per[_boot_idx(T, n_boot, seed)].sum(1)
    for k, v in _rates(*s.T).items():
        m[k + "_ci"] = _pct(v, level)
    return m


def fleiss_with_ci(counts, clusters, n_boot=stats.N_BOOT, seed=stats.SEED, level=stats.LEVEL):
    c = np.asarray(counts, float)
    n = c.sum(1)
    keep = n >= 2
    c, n = c[keep], n[keep]
    cl = [x for x, k in zip(clusters, keep) if k]
    out = dict(kappa=_f(fleiss_kappa(c)), n_items=int(len(c)), kappa_ci=None)
    if len(c) == 0:
        return out
    ci, T = _clusters(cl)
    P = ((c * c).sum(1) - n) / (n * (n - 1))
    sumP = np.bincount(ci, P, T)
    nit = np.bincount(ci, minlength=T).astype(float)
    cat = np.stack([np.bincount(ci, c[:, j], T) for j in range(c.shape[1])], 1)
    idx = _boot_idx(T, n_boot, seed)
    Pbar = sumP[idx].sum(1) / nit[idx].sum(1)
    cs = cat[idx].sum(1)
    p = cs / cs.sum(1, keepdims=True)
    Pe = (p * p).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        k = np.where(Pe >= 1 - 1e-12, np.nan, (Pbar - Pe) / (1 - Pe))
    out["kappa_ci"] = _pct(k, level)
    return out


def majority(labels):
    """Strict majority of booleans; None on a tie or no labels."""
    labels = list(labels)
    y = sum(bool(x) for x in labels)
    if not labels or 2 * y == len(labels):
        return None
    return 2 * y > len(labels)


# ---------------------------------------------------------------- loading

def _norm(rec, rater_id, kind):
    p = rec.get("pass")
    if isinstance(p, str):
        p = p.strip().lower() in ("1", "true", "yes", "pass")
    defects = rec.get("defects") or []
    if isinstance(defects, str):
        defects = [d for d in defects.split(";") if d]
    if not defects and any(f"d_{c}" in rec for c in DEFECT_CODES):
        defects = [c for c in DEFECT_CODES if str(rec.get(f"d_{c}", "0")).strip() in ("1", "true", "True")]
    conf = rec.get("confidence")
    tm = rec.get("time_ms")
    rid = rec.get("rater_id") or rater_id
    if kind == "judge" and not str(rid).startswith("judge:"):
        rid = "judge:" + str(rid)
    return dict(rater_id=str(rid), kind=kind, clip_id=str(rec["clip_id"]), **{"pass": None if p is None else bool(p)},
                defects=[c for c in DEFECT_CODES if c in set(defects)], other_text=rec.get("other_text") or "",
                confidence=int(conf) if conf not in (None, "") else None,
                time_ms=float(tm) if tm not in (None, "") else None)


def load_ratings(paths, kind=None):
    """Rater exports (.json/.csv from tools/rater.html) or judge outputs (.json in the same schema, or .jsonl
    records) -> list of normalized ratings. kind: 'human' | 'judge' | None (judge iff rater_id starts with
    'judge:' or the document says rater_kind = 'judge')."""
    out = []
    for p in map(Path, paths):
        if p.suffix == ".csv":
            with p.open(newline="") as f:
                rows = list(csv.DictReader(f))
            recs, rid, k = rows, p.stem, None
        elif p.suffix == ".jsonl":
            recs = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
            rid, k = p.stem, None
        else:
            doc = json.loads(p.read_text())
            if isinstance(doc, dict):
                recs, rid, k = doc.get("ratings", []), doc.get("rater_id") or p.stem, doc.get("rater_kind")
            else:
                recs, rid, k = doc, p.stem, None
        for r in recs:
            r_id = r.get("rater_id") or rid
            kk = kind or k or ("judge" if str(r_id).startswith("judge:") else "human")
            out.append(_norm(r, r_id, kk))
    return out


def validate_judge_record(rec):
    """Check one judge output against src/study/judge_schema.json (without a jsonschema dependency).
    Returns a list of problems (empty = valid)."""
    errs = []
    if not isinstance(rec, dict):
        return ["not an object"]
    for k in ("clip_id", "pass", "defects", "confidence"):
        if k not in rec:
            errs.append(f"missing {k}")
    if errs:
        return errs
    if not isinstance(rec["clip_id"], str):
        errs.append("clip_id must be a string")
    if not isinstance(rec["pass"], bool):
        errs.append("pass must be true or false")
    d = rec["defects"]
    if not isinstance(d, list) or any(x not in DEFECT_CODES for x in d) or len(set(d)) != len(d):
        errs.append(f"defects must be a list of distinct codes from {DEFECT_CODES}")
    elif rec["pass"] is True and d:
        errs.append("pass = true must have no defects")
    elif rec["pass"] is False and not d:
        errs.append("pass = false needs at least one defect")
    elif "other" in d and not str(rec.get("other_text") or "").strip():
        errs.append("defect 'other' needs other_text")
    if rec["confidence"] not in (1, 2, 3) or isinstance(rec["confidence"], bool):
        errs.append("confidence must be 1, 2 or 3")
    extra = set(rec) - {"clip_id", "pass", "defects", "other_text", "confidence", "reason"}
    if extra:
        errs.append(f"unexpected fields {sorted(extra)}")
    return errs


# ---------------------------------------------------------------- analysis

def _broken(r, code=None):
    """A rating's 'broken' label overall, or for one defect."""
    if code is None:
        return not r["pass"]
    return (not r["pass"]) and code in r["defects"]


def pixel_label(info, code=None):
    """Grader 'broken' label for a clip overall, or for one defect via its mapped checks (None = n/a)."""
    if code is None:
        return None if info.get("passed") is None else not info["passed"]
    vals = [(info.get("checks") or {}).get(g) for g in DEFECT_CHECKS[code]]
    vals = [v for v in vals if v is not None]
    return None if not vals else not all(vals)


def attention_report(humans, key, min_attention):
    att = {c: v for c, v in key["clips"].items() if v.get("attention") and v.get("expected")}
    by = defaultdict(list)
    for r in humans:
        by[r["rater_id"]].append(r)
    rep = {}
    for rid, rs in sorted(by.items()):
        a = [r for r in rs if r["clip_id"] in att]
        ok = sum(r["pass"] == att[r["clip_id"]]["expected"]["pass"] for r in a)
        allowed_miss = max(0, len(att) - min_attention)
        times = [r["time_ms"] for r in rs if r["time_ms"] is not None]
        main = [r for r in rs if r["clip_id"] not in att]
        rep[rid] = dict(n_rated=len(rs), attention_n=len(a), attention_correct=ok,
                        excluded=bool(att) and (len(a) - ok) > allowed_miss,
                        median_s_per_clip=float(np.median(times)) / 1000 if times else None,
                        pass_rate=float(np.mean([r["pass"] for r in main])) if main else None,
                        mean_confidence=float(np.mean([r["confidence"] for r in main if r["confidence"]]))
                        if main else None)
    return rep


def analyze(humans, judges, key, out, n_boot=stats.N_BOOT, seed=stats.SEED, level=stats.LEVEL, min_attention=4,
            boot_unit="task"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    kc = key["clips"]
    raters = attention_report(humans, key, min_attention)
    kept = {r for r, v in raters.items() if not v["excluded"]}
    main_ids = sorted(c for c, v in kc.items() if not v.get("attention"))
    unknown = sorted({r["clip_id"] for r in humans + judges} - set(kc))
    H = defaultdict(dict)                                  # clip -> rater -> rating
    for r in humans:
        if r["rater_id"] in kept and r["clip_id"] in kc and not kc[r["clip_id"]].get("attention") and r["pass"] is not None:
            H[r["clip_id"]][r["rater_id"]] = r
    clips = [c for c in main_ids if H[c]]
    cluster = {c: (kc[c]["task"] if boot_unit == "task" else c) for c in clips}
    bk = dict(n_boot=n_boot, seed=seed, level=level)

    # majority labels
    maj = {}
    for c in clips:
        rs = list(H[c].values())
        maj[c] = {"pass": (lambda m: None if m is None else not m)(majority(_broken(r) for r in rs)),
                  "n": len(rs), **{d: majority(_broken(r, d) for r in rs) for d in DEFECT_CODES}}

    # inter-rater agreement
    def agreement(code):
        cnt = [[sum(_broken(r, code) for r in H[c].values()), sum(not _broken(r, code) for r in H[c].values())]
               for c in clips]
        f = fleiss_with_ci(cnt, [cluster[c] for c in clips], **bk)
        units = [[_broken(r, code) for r in H[c].values()] for c in clips]
        prev = [m for m in (maj[c][code] if code else (None if maj[c]["pass"] is None else not maj[c]["pass"])
                            for c in clips) if m is not None]
        return dict(fleiss_kappa=f["kappa"], fleiss_kappa_ci=f["kappa_ci"], krippendorff_alpha=_f(krippendorff_alpha(units)),
                    n_items=f["n_items"], prevalence=float(np.mean(prev)) if prev else None)
    agree = dict(overall=agreement(None), per_defect={d: agreement(d) for d in DEFECT_CODES})

    def truth(c, code):
        return (None if maj[c]["pass"] is None else not maj[c]["pass"]) if code is None else maj[c][code]

    def compare(get_pred, codes):
        res = {}
        for code in codes:
            rows = [(get_pred(c, code), truth(c, code), cluster[c]) for c in clips]
            rows = [r for r in rows if r[0] is not None and r[1] is not None]
            if not rows:
                res[code or "overall"] = dict(n=0)
                continue
            p, t, cl = zip(*rows)
            res[code or "overall"] = metrics_with_ci(p, t, cl, **bk)
        return dict(overall=res.pop("overall"), per_defect=res)

    evaluators = {}
    evaluators[PIXEL] = compare(lambda c, code: pixel_label(kc[c], code), [None, *DEFECT_CHECKS])
    J = defaultdict(dict)
    for r in judges:
        if r["clip_id"] in kc and r["pass"] is not None:
            J[r["rater_id"]][r["clip_id"]] = r
    for jid in sorted(J):
        evaluators[jid] = compare(lambda c, code, jid=jid: _broken(J[jid][c], code) if c in J[jid] else None,
                                  [None, *DEFECT_CODES])
        evaluators[jid]["coverage"] = sum(c in J[jid] for c in clips) / max(1, len(clips))
    # one human vs the majority of the others
    loo = {}
    for code in [None, *DEFECT_CODES]:
        rows = []
        for c in clips:
            for rid, r in H[c].items():
                m = majority(_broken(o, code) for o2, o in H[c].items() if o2 != rid)
                if m is not None:
                    rows.append((_broken(r, code), m, cluster[c]))
        loo[code or "overall"] = metrics_with_ci(*zip(*rows), **bk) if rows else dict(n=0)
    evaluators[HUMAN_LOO] = dict(overall=loo.pop("overall"), per_defect=loo)

    res = dict(study_id=key.get("study_id"), n_clips=len(clips), n_ratings=sum(len(H[c]) for c in clips),
               n_raters_kept=len(kept), n_raters_excluded=len(raters) - len(kept), min_attention=min_attention,
               boot_unit=boot_unit, n_boot=n_boot, seed=seed, level=level, unknown_clips=unknown,
               ties_overall=sum(maj[c]["pass"] is None for c in clips), raters=raters, agreement=agree,
               majority=maj, evaluators=evaluators)
    (out / "results.json").write_text(json.dumps(res, indent=1))
    write_per_clip(out / "per_clip.csv", clips, kc, H, maj, J)
    (out / "table.tex").write_text(latex_tables(res))
    confusion_png(res, out / "confusion.png")
    (out / "summary.md").write_text(summary_md(res))
    return res


# ---------------------------------------------------------------- outputs

def write_per_clip(path, clips, kc, H, maj, J):
    cols = ["clip_id", "task", "model", "setting", "n_raters", "human_pass_votes", "majority_pass",
            *[f"maj_{d}" for d in DEFECT_CODES], "pixel_pass", *[f"pixel_{d}" for d in DEFECT_CHECKS],
            *[f"{j}_pass" for j in sorted(J)]]
    with Path(path).open("w", newline="") as f:
        w = csv.DictWriter(f, cols)
        w.writeheader()
        for c in clips:
            info = kc[c]
            row = dict(clip_id=c, task=info["task"], model=info.get("model"), setting=info.get("setting"),
                       n_raters=len(H[c]), human_pass_votes=sum(r["pass"] for r in H[c].values()),
                       majority_pass=maj[c]["pass"], pixel_pass=info.get("passed"))
            row.update({f"maj_{d}": maj[c][d] for d in DEFECT_CODES})
            row.update({f"pixel_{d}": pixel_label(info, d) for d in DEFECT_CHECKS})
            row.update({f"{j}_pass": (J[j][c]["pass"] if c in J[j] else None) for j in sorted(J)})
            w.writerow(row)


def _tex(s):
    return str(s).replace("\\", "\\textbackslash{}").replace("_", "\\_").replace("&", "\\&").replace("%", "\\%") \
        .replace("#", "\\#")


def _cell(m, k):
    v = m.get(k)
    if v is None:
        return "--"
    ci = m.get(k + "_ci")
    return f"{v:.2f}" + (f" {{\\scriptsize[{ci[0]:.2f}, {ci[1]:.2f}]}}" if ci else "")


def _ev_names(res):
    ev = res["evaluators"]
    return [HUMAN_LOO, PIXEL] + sorted(k for k in ev if k not in (HUMAN_LOO, PIXEL))


def _ev_label(k):
    return EV_LABEL.get(k) or _tex(k.removeprefix("judge:"))


def latex_tables(res):
    ev = res["evaluators"]
    pct = int(round(res["level"] * 100))
    unit = "tasks" if res["boot_unit"] == "task" else "clips"
    L = [f"% anibench human study (E4), study {_tex(res['study_id'])}: {res['n_clips']} clips, "
         f"{res['n_ratings']} ratings from {res['n_raters_kept']} raters. Generated by src/study/analyze.py.",
         f"% Brackets: {pct}\\% bootstrap CIs over {unit} ({res['n_boot']} resamples, seed {res['seed']}).",
         "% Table 1: agreement with the human majority on whether the clip is broken.",
         "\\begin{tabular}{lrrrrr}", "\\toprule",
         "Evaluator & $n$ & Accuracy & Precision & Recall & Cohen's $\\kappa$ \\\\", "\\midrule"]
    for k in _ev_names(res):
        m = ev[k]["overall"]
        if not m.get("n"):
            continue
        L.append(f"{_ev_label(k)} & {m['n']} & {_cell(m, 'accuracy')} & {_cell(m, 'precision')} & "
                 f"{_cell(m, 'recall')} & {_cell(m, 'kappa')} \\\\")
    ag = res["agreement"]["overall"]
    alpha = "--" if ag["krippendorff_alpha"] is None else f"{ag['krippendorff_alpha']:.2f}"
    prev = "--" if ag["prevalence"] is None else f"{100 * ag['prevalence']:.0f}\\%"
    L += ["\\midrule",
          f"\\multicolumn{{6}}{{l}}{{\\footnotesize Inter-rater: Fleiss' $\\kappa$ = {_cell(ag, 'fleiss_kappa')}, "
          f"Krippendorff's $\\alpha$ = {alpha}; clips the majority calls broken: {prev}}} \\\\",
          "\\bottomrule", "\\end{tabular}", ""]
    names = _ev_names(res)
    L += ["% Table 2: per defect. Inter-rater Fleiss' kappa, then Cohen's kappa of each evaluator against the human",
          "% majority for that defect (pixel: the mapped checks).",
          "\\begin{tabular}{ll" + "r" * (2 + len(names)) + "}", "\\toprule",
          "Defect & Check & Prev. & Fleiss' $\\kappa$ & " + " & ".join(_ev_label(k) for k in names) + " \\\\",
          "\\midrule"]
    for d in DEFECT_CODES:
        a = res["agreement"]["per_defect"][d]
        cells = []
        for k in names:
            m = ev[k]["per_defect"].get(d)
            cells.append(_cell(m, "kappa") if m and m.get("n") else "--")
        prev = "--" if a["prevalence"] is None else f"{a['prevalence']:.0%}".replace("%", "\\%")
        L.append(f"{_tex(DEFECT_LABEL[d])} & {'/'.join(DEFECT_CHECKS.get(d, [])) or '--'} & {prev} & "
                 f"{_cell(a, 'fleiss_kappa')} & " + " & ".join(cells) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}", ""]
    return "\n".join(L)


def confusion_png(res, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    names = [k for k in _ev_names(res) if res["evaluators"][k]["overall"].get("n")]
    if not names:
        names = [PIXEL]
    fig, axes = plt.subplots(1, len(names), figsize=(2.6 * len(names), 2.9), squeeze=False)
    for ax, k in zip(axes[0], names):
        m = res["evaluators"][k]["overall"]
        M = np.array([[m.get("tp", 0), m.get("fn", 0)], [m.get("fp", 0), m.get("tn", 0)]], float)
        ax.imshow(M, cmap="Blues", vmin=0, vmax=max(1, M.max()))
        for i in range(2):
            for j in range(2):
                ax.text(j, i, int(M[i, j]), ha="center", va="center", fontsize=12,
                        color="white" if M[i, j] > 0.6 * M.max() else "#1d1d1f")
        ax.set_xticks([0, 1], ["broken", "ok"])
        ax.set_yticks([0, 1], ["broken", "ok"])
        ax.set_xlabel("evaluator", fontsize=9)
        ax.set_ylabel("human majority", fontsize=9)
        kap = m.get("kappa")
        lab = EV_LABEL.get(k, k.removeprefix("judge:")).replace("\\", "").replace("~", " ")
        ax.set_title(f"{lab}\n" + (f"κ = {kap:.2f}" if kap is not None else "κ n/a"), fontsize=9)
        for s in ax.spines.values():
            s.set_visible(False)
        ax.tick_params(length=0, labelsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def summary_md(res):
    ev = res["evaluators"]
    f2 = lambda v: "--" if v is None else f"{v:.2f}"  # noqa: E731
    ci = lambda m, k: f2(m.get(k)) + (f" [{m[k + '_ci'][0]:.2f}, {m[k + '_ci'][1]:.2f}]" if m.get(k + "_ci") else "")  # noqa: E731
    L = [f"# Human study analysis: {res['study_id']}", "",
         f"{res['n_clips']} clips, {res['n_ratings']} ratings, {res['n_raters_kept']} raters kept, "
         f"{res['n_raters_excluded']} excluded by attention checks (need {res['min_attention']} correct). "
         f"Ties in the overall majority: {res['ties_overall']}. CIs: {int(res['level'] * 100)}% bootstrap over "
         f"{res['boot_unit']}s, {res['n_boot']} resamples.", "",
         "## Raters", "", "| rater | rated | attention | median s/clip | pass rate | excluded |", "|---|---|---|---|---|---|"]
    for r, v in res["raters"].items():
        L.append(f"| {r} | {v['n_rated']} | {v['attention_correct']}/{v['attention_n']} | "
                 f"{f2(v['median_s_per_clip'])} | {f2(v['pass_rate'])} | {'yes' if v['excluded'] else ''} |")
    ag = res["agreement"]
    L += ["", "## Inter-rater agreement", "", "| | Fleiss' kappa | Krippendorff's alpha | items | prevalence |",
          "|---|---|---|---|---|",
          f"| overall (broken) | {ci(ag['overall'], 'fleiss_kappa')} | {f2(ag['overall']['krippendorff_alpha'])} | "
          f"{ag['overall']['n_items']} | {f2(ag['overall']['prevalence'])} |"]
    for d in DEFECT_CODES:
        a = ag["per_defect"][d]
        L.append(f"| {d} | {ci(a, 'fleiss_kappa')} | {f2(a['krippendorff_alpha'])} | {a['n_items']} | {f2(a['prevalence'])} |")
    L += ["", "## Agreement with the human majority (overall: broken or not)", "",
          "| evaluator | n | accuracy | precision | recall | kappa |", "|---|---|---|---|---|---|"]
    for k in _ev_names(res):
        m = ev[k]["overall"]
        if m.get("n"):
            L.append(f"| {EV_LABEL.get(k, k).replace(chr(92), '')} | {m['n']} | {ci(m, 'accuracy')} | "
                     f"{ci(m, 'precision')} | {ci(m, 'recall')} | {ci(m, 'kappa')} |")
    L += ["", "## Per defect (Cohen's kappa vs the human majority for that defect)", "",
          "| defect | checks | " + " | ".join(EV_LABEL.get(k, k).replace(chr(92), "") for k in _ev_names(res)) + " |",
          "|---|---|" + "---|" * len(_ev_names(res))]
    for d in DEFECT_CODES:
        cells = []
        for k in _ev_names(res):
            m = ev[k]["per_defect"].get(d)
            cells.append(f"{ci(m, 'kappa')} (n={m['n']})" if m and m.get("n") else "--")
        L.append(f"| {d} | {'/'.join(DEFECT_CHECKS.get(d, [])) or '--'} | " + " | ".join(cells) + " |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--key", required=True)
    ap.add_argument("--ratings", nargs="+", required=True)
    ap.add_argument("--judges", nargs="*", default=[])
    ap.add_argument("--out", required=True)
    ap.add_argument("--n-boot", type=int, default=stats.N_BOOT)
    ap.add_argument("--seed", type=int, default=stats.SEED)
    ap.add_argument("--min-attention", type=int, default=4, help="attention checks a rater must get right (of 5)")
    ap.add_argument("--boot-unit", choices=["task", "clip"], default="task")
    a = ap.parse_args(argv)
    key = json.loads(Path(a.key).read_text())
    res = analyze(load_ratings(a.ratings, kind="human"), load_ratings(a.judges, kind="judge"), key, a.out,
                  a.n_boot, a.seed, min_attention=a.min_attention, boot_unit=a.boot_unit)
    print(f"{res['n_clips']} clips, {res['n_ratings']} ratings; wrote {a.out}/results.json, table.tex, confusion.png")


if __name__ == "__main__":
    main()
