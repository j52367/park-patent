"""Learned ranking: train on the screening judgements made so far, rank everything else.

This is the "continuous active learning" loop used in e-discovery: screen → learn → re-rank →
screen the top → repeat, and check what is left with a random tail sample. In our experiment
(docs/experiments/2026-11-09_ranking.md) a logistic regression on character 2–3-gram TF-IDF beat
multilingual embedding models on a random tail sample (AP 0.80 vs 0.47 for similarity ranking),
on CPU in seconds. Needs scikit-learn (`pip install park-patent[learn]`).

Probabilities from this model are NOT calibrated (labels come from the top of earlier rankings,
so the model over-estimates how much is left). Use it for ordering only; estimate the remainder
with `park audit-sample`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

MIN_PER_CLASS = 20


def _text(df: pd.DataFrame) -> pd.Series:
    cl = df["independent_claims"] if "independent_claims" in df else ""
    return df["title"] + " " + df["title"] + " " + df["abstract"] + " " + cl


def learn_rank(candidates: pd.DataFrame, screening: pd.DataFrame, folds: int = 5, seed: int = 0):
    """Return (rank frame, evaluation dict). Labelled docs get out-of-fold scores."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import average_precision_score, roc_auc_score
        from sklearn.model_selection import StratifiedKFold
    except ImportError as e:  # pragma: no cover - depends on the environment
        raise ImportError("park rank --learn needs scikit-learn: pip install 'park-patent[learn]'") from e

    lab = screening[screening["relevance"].isin(["valid", "noise"])]
    lab = lab.drop_duplicates("application_no", keep="last")
    lab = lab[lab["application_no"].isin(set(candidates["application_no"]))]
    y = (lab["relevance"] == "valid").astype(int).to_numpy()
    if min(y.sum(), len(y) - y.sum()) < MIN_PER_CLASS:
        raise ValueError(f"--learn needs at least {MIN_PER_CLASS} valid and {MIN_PER_CLASS} noise judgements "
                         f"(have {int(y.sum())} valid, {int(len(y) - y.sum())} noise) — rank by similarity first")

    cand = candidates.reset_index(drop=True)
    X = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=2, sublinear_tf=True) \
        .fit_transform(_text(cand))
    pos = pd.Series(np.arange(len(cand)), index=cand["application_no"])
    li = pos.reindex(lab["application_no"]).to_numpy()

    def model():
        return LogisticRegression(max_iter=3000, C=4.0)

    oof = np.zeros(len(y))
    k = min(folds, int(y.sum()), int(len(y) - y.sum()))
    for tr, te in StratifiedKFold(k, shuffle=True, random_state=seed).split(li, y):
        oof[te] = model().fit(X[li[tr]], y[tr]).predict_proba(X[li[te]])[:, 1]
    scores = model().fit(X[li], y).predict_proba(X)[:, 1]
    scores[li] = oof  # a labelled doc is never scored by a model that saw its label

    tail = lab["screened_by"].astype(str).str.contains("tail-audit").to_numpy() \
        if "screened_by" in lab else np.zeros(len(y), bool)

    def m(mask):
        if mask.sum() == 0 or len(set(y[mask])) < 2:
            return None
        return {"auc": round(float(roc_auc_score(y[mask], oof[mask])), 4),
                "ap": round(float(average_precision_score(y[mask], oof[mask])), 4), "n": int(mask.sum())}

    evaluation = {"method": "learn: char 2-3gram tf-idf + logistic regression", "labelled": int(len(y)),
                  "valid": int(y.sum()), "cv_folds": k, "cv_all": m(np.ones(len(y), bool)), "cv_tail": m(tail)}
    out = pd.DataFrame({"application_no": cand["application_no"], "rank_score": np.round(scores, 5),
                        "labelled": cand["application_no"].isin(set(lab["application_no"]))})
    out = out.sort_values("rank_score", ascending=False, kind="stable").reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    out["method"] = "learn"
    return out, evaluation
