"""Pre-ranking: order candidates by similarity to the technology classification table.

Screening thousands of candidates with an LLM is slow and costly, so PARK screens in rank
order and stops when batches stop yielding relevant documents (checked by sampling the tail
with `park audit-sample --tail`). Ranking never removes a document; it only decides the order.

Method (dependency-free, deterministic): character 2–3-gram TF-IDF, which works for Korean
without a morphological analyser. Each TECH_TREE row becomes a profile (names, definition,
'포함' terms); the document score is its best cosine similarity to any profile, minus a penalty
when it is closer to the row's '제외' text than to its profile.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import pandas as pd

_CLEAN = re.compile(r"[^0-9a-z가-힣]+")


def _grams(text: str, ns=(2, 3)) -> Counter:
    s = _CLEAN.sub(" ", str(text).lower())
    out: Counter = Counter()
    for word in s.split():
        if len(word) == 1:
            continue
        for n in ns:
            for i in range(len(word) - n + 1):
                out[word[i:i + n]] += 1
    return out


def tech_profiles(tech_tree_md: str) -> dict[str, tuple[str, str]]:
    """code → (positive text, exclusion text) from the TECH_TREE table."""
    lines = [l for l in tech_tree_md.splitlines() if l.strip().startswith("|")]
    if not lines:
        return {}
    header = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    excl = header.index("제외") if "제외" in header else None
    out = {}
    for l in lines[1:]:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        m = re.fullmatch(r"`([^`]+)`", cells[0]) if cells else None
        if not m:
            continue
        pos = " ".join(c for i, c in enumerate(cells[1:], 1) if i != excl and not re.fullmatch(r"[\d\-①-⑳]+", c))
        neg = cells[excl] if excl is not None and excl < len(cells) else ""
        out[m.group(1)] = (pos, neg)
    return out


def doc_text(row) -> str:
    # title counts twice: it is the most deliberate summary of the invention
    return " ".join([str(row.get("title", ""))] * 2 + [str(row.get("abstract", "")),
                                                        str(row.get("independent_claims", ""))])


def rank(candidates: pd.DataFrame, tech_tree_md: str, extra_terms: str = "") -> pd.DataFrame:
    profiles = tech_profiles(tech_tree_md)
    if not profiles:
        raise ValueError("TECH_TREE.md has no rows with `code` cells — cannot rank")
    docs = [_grams(doc_text(r)) for _, r in candidates.iterrows()]
    n = len(docs)
    df: Counter = Counter()
    for d in docs:
        df.update(d.keys())
    idf = {g: math.log((n + 1) / (c + 1)) + 1 for g, c in df.items()}

    def vec(counter: Counter) -> dict[str, float]:
        v = {g: (1 + math.log(c)) * idf.get(g, math.log(n + 1) + 1) for g, c in counter.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        return {g: x / norm for g, x in v.items()}

    pos_vecs = {k: vec(_grams(p + " " + extra_terms)) for k, (p, _) in profiles.items()}
    neg_vecs = {k: vec(_grams(ng)) for k, (_, ng) in profiles.items() if ng.strip()}

    rows = []
    for (_, r), d in zip(candidates.iterrows(), docs):
        v = vec(d)
        best_code, best = "", 0.0
        for k, pv in pos_vecs.items():
            s = sum(x * pv.get(g, 0.0) for g, x in v.items())
            if s > best:
                best_code, best = k, s
        penalty = 0.0
        if best_code in neg_vecs:
            neg = sum(x * neg_vecs[best_code].get(g, 0.0) for g, x in v.items())
            penalty = max(0.0, neg - best) * 0.5
        rows.append({"application_no": r["application_no"], "rank_score": round(best - penalty, 5),
                     "rank_code": best_code})
    out = pd.DataFrame(rows).sort_values("rank_score", ascending=False, kind="stable").reset_index(drop=True)
    out["rank"] = range(1, len(out) + 1)
    return out
