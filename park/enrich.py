"""Phase 2 inputs: pick the documents worth a close look, then fetch their claims and citations.

shortlist() — deterministic, explained pre-selection from the valid set (the API budget rarely
allows fetching details for every valid document):
  * every valid document of the focal applicant(s) (the subject of the strategy work)
  * the best `per_code` documents of every technology code (so no area is left out)
  * the rest by score = status weight × relevance score (learned rank score if present)
enrich() — per document: bibliography detail (claims, priority, cited prior art, legal status,
family, R&D) + Korean forward citations. Writes details/<no>.json, fulltext/<no>.txt (claims, so
evidence can be 'confirmed'), and enrich.csv (one row of signals per document).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .kipris import independent_claims
from .normalize import split_multi

STATUS_WEIGHT = {"등록": 1.0, "공개": 0.8, "소멸": 0.6, "거절": 0.3, "취하": 0.3, "포기": 0.3, "무효": 0.3}


def shortlist(candidates: pd.DataFrame, screening: pd.DataFrame, rank: pd.DataFrame | None,
              focal: list[str], n: int = 300, per_code: int = 12) -> pd.DataFrame:
    valid = screening[screening["relevance"] == "valid"][["application_no", "tech_code"]]
    df = candidates.merge(valid, on="application_no", how="inner")
    if rank is not None and "rank_score" in rank:
        df = df.merge(rank[["application_no", "rank_score"]], on="application_no", how="left")
        df["relevance_score"] = pd.to_numeric(df["rank_score"], errors="coerce").fillna(0.5)
    else:
        df["relevance_score"] = 0.5
    df["status_weight"] = df["status"].map(STATUS_WEIGHT).fillna(0.5)
    df["score"] = (df["status_weight"] * df["relevance_score"]).round(5)
    df = df.sort_values("score", ascending=False, kind="stable")

    picked: dict[str, str] = {}
    focal_set = {f.strip() for f in focal if f.strip()}
    for _, r in df.iterrows():
        if focal_set & set(split_multi(r["applicants"])):
            picked.setdefault(r["application_no"], "focal")
    for code, g in df.groupby("tech_code", sort=True):
        for no in g["application_no"].head(per_code):
            picked.setdefault(no, f"top-{code}")
    for no in df["application_no"]:
        if len(picked) >= n:
            break
        picked.setdefault(no, "score")
    out = df[df["application_no"].isin(picked)].copy()
    out["reason"] = out["application_no"].map(picked)
    return out[["application_no", "title", "applicants", "tech_code", "status", "application_date",
                "relevance_score", "status_weight", "score", "reason"]].reset_index(drop=True)


def enrich(client, numbers: list[str], out_dir: Path, budget: int | None = None, log=print) -> pd.DataFrame:
    """Fetch detail + citing for each number (cached; at most `budget` new network calls)."""
    det_dir, ft_dir = out_dir / "details", out_dir / "fulltext"
    det_dir.mkdir(parents=True, exist_ok=True)
    ft_dir.mkdir(parents=True, exist_ok=True)
    start = client.network_calls
    rows, stopped = [], False
    for i, no in enumerate(numbers, 1):
        path = det_dir / f"{no}.json"
        if path.exists():
            d = json.loads(path.read_text(encoding="utf-8"))
            d["independent_claims"] = independent_claims(d.get("claims", []))  # rules may have improved
        else:
            if budget is not None and client.network_calls - start + 2 > budget:
                log(f"[enrich] call budget {budget} reached after {i - 1} documents")
                stopped = True
                break
            d = client.detail(no)
            d["citing"] = client.citing(no)
            path.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
            if d["claims"]:
                (ft_dir / f"{no}.txt").write_text("\n".join(d["claims"]), encoding="utf-8")
        rows.append({
            "application_no": no,
            "claim_count": d.get("claim_count", 0),
            "independent_claims": len(d.get("independent_claims", [])),
            "forward_citations": len(d.get("citing", [])),
            "backward_citations": len(d.get("prior_art", [])),
            "examiner_citations": sum(1 for p in d.get("prior_art", []) if p.get("examiner")),
            "family_size": len(d.get("family", [])),
            "register_status": d.get("register_status", ""),
            "rnd": "|".join(sorted({r.get("rndDepartmentName", "") for r in d.get("rnd", []) if r.get("rndDepartmentName")})),
            "fetched_at": d.get("fetched_at", ""),
        })
        if i % 50 == 0:
            log(f"[enrich] {i}/{len(numbers)} (new calls {client.network_calls - start})")
    df = pd.DataFrame(rows)
    if stopped:
        log("[enrich] re-run later (or with a larger --budget) to continue; fetched documents are kept")
    return df
