"""Experiment: does an embedding model rank candidates better than PARK's char n-gram TF-IDF?

Usage (GPU box):
    python experiments/embed_rank.py analysis/<project> --models BAAI/bge-m3 intfloat/multilingual-e5-large

Inputs in the analysis dir: candidates.csv, screening.csv (labels), rank.csv (TF-IDF scores), TECH_TREE.md.
Outputs: <dir>/embed_eval/results.json, <dir>/embed_eval/scores_<model>.csv, cached embeddings (.npy).

Two families of scores are compared:
  * zero-shot: cosine similarity between each document and the TECH_TREE row profiles (max over rows)
  * supervised probe: logistic regression on the embeddings, trained on screening labels with
    5-fold cross-validation (out-of-fold scores) — what an active-learning loop could reach
Metrics: ROC-AUC and average precision on (a) every labelled doc and (b) only the random tail samples,
which were not selected by any ranking and are therefore the fairer test.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import StratifiedKFold

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from park.rank import tech_profiles  # noqa: E402

PREFIX = {  # instruction prefixes some models expect
    "intfloat/multilingual-e5-large": ("query: ", "passage: "),
    "intfloat/multilingual-e5-base": ("query: ", "passage: "),
}


def doc_text(r) -> str:
    return f"{r['title']}. {r['abstract']}"


def metrics(y, s):
    if len(set(y)) < 2:
        return {"auc": None, "ap": None, "n": int(len(y))}
    return {"auc": round(float(roc_auc_score(y, s)), 4), "ap": round(float(average_precision_score(y, s)), 4),
            "n": int(len(y)), "pos": int(sum(y))}


def evaluate(name, scores: pd.Series, lab: pd.DataFrame, n_total: int) -> dict:
    s = scores.reindex(lab["application_no"]).to_numpy()
    tail = lab["tail"].to_numpy()
    y = lab["y"].to_numpy()
    order = scores.sort_values(ascending=False)
    rank = pd.Series(np.arange(1, len(order) + 1), index=order.index)
    vr = rank.reindex(lab.loc[lab.y == 1, "application_no"])
    return {"method": name, "all": metrics(y, s), "tail": metrics(y[tail], s[tail]),
            "known_valid_in_top1000": int((vr <= 1000).sum()), "known_valid_in_top2000": int((vr <= 2000).sum()),
            "known_valid": int(len(vr)), "n_candidates": n_total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir")
    ap.add_argument("--models", nargs="+", default=["BAAI/bge-m3", "intfloat/multilingual-e5-large"])
    ap.add_argument("--batch", type=int, default=64)
    ap.add_argument("--max-len", type=int, default=512)
    a = ap.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer

    d = Path(a.dir)
    out = d / "embed_eval"
    out.mkdir(exist_ok=True)
    cand = pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False)
    scr = pd.read_csv(d / "screening.csv", dtype=str, keep_default_na=False)
    lab = scr[scr["relevance"].isin(["valid", "noise"])].copy()
    lab["y"] = (lab["relevance"] == "valid").astype(int)
    lab["tail"] = lab["screened_by"].str.contains("tail-audit")
    lab = lab[lab["application_no"].isin(set(cand["application_no"]))].reset_index(drop=True)
    print(f"candidates {len(cand)} | labelled {len(lab)} (valid {lab["y"].sum()}) | tail {lab["tail"].sum()}")

    results = []
    tfidf = pd.read_csv(d / "rank.csv", dtype={"application_no": str}).set_index("application_no")["rank_score"]
    results.append(evaluate("tfidf-char-ngram (current)", tfidf, lab, len(cand)))

    profiles = tech_profiles((d / "TECH_TREE.md").read_text(encoding="utf-8"))
    prof_text = [p for p, _ in profiles.values()]
    texts = [doc_text(r) for _, r in cand.iterrows()]
    ids = cand["application_no"].tolist()
    pos_index = {k: i for i, k in enumerate(ids)}
    lab_idx = np.array([pos_index[x] for x in lab["application_no"]])

    for model_name in a.models:
        t0 = time.time()
        safe = model_name.replace("/", "__")
        cache = out / f"emb_{safe}.npy"
        q_pre, p_pre = PREFIX.get(model_name, ("", ""))
        try:
            model = SentenceTransformer(model_name, device="cuda", model_kwargs={"torch_dtype": torch.float16})
        except Exception as e:  # model missing or incompatible: report and continue
            print(f"[skip] {model_name}: {e}")
            results.append({"method": model_name, "error": str(e)[:200]})
            continue
        model.max_seq_length = a.max_len
        if cache.exists():
            emb = np.load(cache)
        else:
            emb = model.encode([p_pre + t for t in texts], batch_size=a.batch, normalize_embeddings=True,
                               show_progress_bar=False, convert_to_numpy=True)
            np.save(cache, emb)
        q = model.encode([q_pre + t for t in prof_text], normalize_embeddings=True, convert_to_numpy=True)
        zs = pd.Series((emb @ q.T).max(axis=1), index=ids)
        results.append(evaluate(f"{model_name} zero-shot", zs, lab, len(cand)))

        # supervised probe: out-of-fold scores for labelled docs, full-fit scores for the rest
        X, y = emb[lab_idx], lab["y"].to_numpy()
        oof = np.zeros(len(y))
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=0).split(X, y):
            clf = LogisticRegression(max_iter=2000, C=1.0).fit(X[tr], y[tr])
            oof[te] = clf.predict_proba(X[te])[:, 1]
        full = LogisticRegression(max_iter=2000, C=1.0).fit(X, y).predict_proba(emb)[:, 1]
        sup = pd.Series(full, index=ids)
        sup.loc[lab["application_no"].tolist()] = oof  # never score a labelled doc with a model trained on it
        results.append(evaluate(f"{model_name} supervised probe (5-fold)", sup, lab, len(cand)))
        unl = ~cand["application_no"].isin(set(lab["application_no"]))
        results[-1]["expected_valid_among_unlabelled"] = round(float(sup[unl.to_numpy()].sum()), 1)
        pd.DataFrame({"application_no": ids, "zero_shot": zs.values, "probe": sup.values}).to_csv(
            out / f"scores_{safe}.csv", index=False)
        results[-1]["seconds"] = round(time.time() - t0, 1)
        del model
        torch.cuda.empty_cache()

    (out / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n{'method':52s} {'AUC all':>8s} {'AP all':>7s} {'AUC tail':>9s} {'AP tail':>8s} {'top1k':>6s} {'top2k':>6s}")
    for r in results:
        if "error" in r:
            print(f"{r['method']:52s}  error")
            continue
        print(f"{r['method']:52s} {r['all']['auc']:8.3f} {r['all']['ap']:7.3f} {r['tail']['auc']:9.3f} "
              f"{r['tail']['ap']:8.3f} {r['known_valid_in_top1000']:6d} {r['known_valid_in_top2000']:6d}")


if __name__ == "__main__":
    main()
