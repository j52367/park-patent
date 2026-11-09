"""Patent-based SWOT inputs for a focal applicant compared with chosen competitors.

Everything here is counted from the valid set (and key_review.csv / enrich.csv when present), so
the SWOT text written by a person or LLM can cite numbers through {{swot...}} placeholders.
Patent data can support S/W (what the focal applicant holds or lacks) and patent-side O/T (where
the field grows, where competitors lead); market and business facts must come from the user.

swot_stats.json:
  meta: as_of, recent window, focal, competitors
  codes: per technology code — total, recent, previous, growth, top applicant and its share
  applicants: focal first, then competitors — n, share, alive_rate, recent/previous, by_code,
              key/notable counts, mean forward citations over their shortlisted documents
  hints: deterministic candidates for S, W, O, T (each with the numbers behind it)
"""

from __future__ import annotations

from collections import Counter
from datetime import date

import pandas as pd

from .normalize import split_multi
from .stats import UNPUBLISHED_MONTHS, _months_before


def compute(candidates: pd.DataFrame, screening: pd.DataFrame, focal: str, competitors: list[str],
            as_of: str = "", window: int = 5, key_review: pd.DataFrame | None = None,
            enrich: pd.DataFrame | None = None, tech_labels: dict | None = None) -> dict:
    valid = screening[screening["relevance"] == "valid"][["application_no", "tech_code"]]
    pop = candidates.merge(valid, on="application_no", how="inner")
    pop["year"] = pd.to_datetime(pop["application_date"], errors="coerce").dt.year
    as_of_d = date.fromisoformat(as_of) if as_of else date.today()
    last_full = _months_before(as_of_d, UNPUBLISHED_MONTHS).year - 1  # last year not hit by the publication lag
    recent = (last_full - window + 1, last_full)
    previous = (recent[0] - window, recent[0] - 1)

    def in_range(y, r):
        return (y >= r[0]) & (y <= r[1])

    codes = sorted(c for c in pop["tech_code"].unique() if c)
    code_rows = []
    for c in codes:
        g = pop[pop["tech_code"] == c]
        cnt = Counter(n for v in g["applicants"] for n in split_multi(v))
        top, top_n = (cnt.most_common(1)[0] if cnt else ("", 0))
        rec, prev = int(in_range(g["year"], recent).sum()), int(in_range(g["year"], previous).sum())
        code_rows.append({"code": c, "label": (tech_labels or {}).get(c, ""), "total": int(len(g)),
                          "recent": rec, "previous": prev, "growth": round(rec / prev, 2) if prev else None,
                          "top_applicant": top, "top_share": round(top_n / len(g), 3) if len(g) else 0})

    kr = key_review.set_index("application_no")["importance"] if key_review is not None and len(key_review) else None
    fc = (pd.to_numeric(enrich.set_index("application_no")["forward_citations"], errors="coerce")
          if enrich is not None and len(enrich) else None)

    def applicant_rows(name):
        mine = pop[pop["applicants"].map(lambda v: name in split_multi(v))]
        by_code = mine["tech_code"].value_counts().to_dict()
        row = {"name": name, "n": int(len(mine)), "share": round(len(mine) / len(pop), 4) if len(pop) else 0,
               "alive_rate": round(float((mine["status"] == "등록").mean()), 3) if len(mine) else 0,
               "recent": int(in_range(mine["year"], recent).sum()), "previous": int(in_range(mine["year"], previous).sum()),
               "by_code": {c: int(by_code.get(c, 0)) for c in codes}}
        if kr is not None:
            imp = kr.reindex(mine["application_no"]).dropna()
            row["key"] = int((imp == "핵심").sum())
            row["notable"] = int((imp == "주목").sum())
            row["key_codes"] = mine[mine["application_no"].isin(imp[imp == "핵심"].index)]["tech_code"].value_counts().to_dict()
        if fc is not None:
            f = fc.reindex(mine["application_no"]).dropna()
            row["shortlisted"] = int(len(f))
            row["forward_citations_mean"] = round(float(f.mean()), 2) if len(f) else None
        return row

    apps = [applicant_rows(focal)] + [applicant_rows(c) for c in competitors]
    focal_row = apps[0]
    code_by = {r["code"]: r for r in code_rows}
    overall = focal_row["share"]

    hints = {"S": [], "W": [], "O": [], "T": []}
    for c in codes:
        n_f = focal_row["by_code"][c]
        tot = code_by[c]["total"]
        share = n_f / tot if tot else 0
        grow = code_by[c]["growth"]
        focal_key = focal_row.get("key_codes", {}).get(c, 0)
        leads = code_by[c]["top_applicant"] == focal
        if (n_f >= 3 and share >= max(1.5 * overall, 0.05)) or (leads and n_f >= 3) or (focal_key >= 1 and n_f >= 2):
            hints["S"].append({"code": c, "focal": n_f, "code_total": tot, "focal_share_in_code": round(share, 3),
                               "focal_key": focal_key, "focal_leads_code": leads})
        if grow is not None and grow >= 1.2 and n_f <= 1:
            hints["W"].append({"code": c, "focal": n_f, "code_recent": code_by[c]["recent"], "growth": grow})
        if grow is not None and grow >= 1.2 and code_by[c]["top_share"] < 0.25:
            hints["O"].append({"code": c, "growth": grow, "top_share": code_by[c]["top_share"],
                               "code_recent": code_by[c]["recent"]})
        for comp in apps[1:]:
            k = comp.get("key_codes", {}).get(c, 0)
            if comp["by_code"][c] >= max(2 * max(n_f, 1), 5) or k >= 2:
                hints["T"].append({"code": c, "competitor": comp["name"], "competitor_n": comp["by_code"][c],
                                   "competitor_key": k, "focal": n_f})
    return {"meta": {"as_of": as_of_d.isoformat(), "recent": f"{recent[0]}–{recent[1]}",
                     "previous": f"{previous[0]}–{previous[1]}", "focal": focal, "competitors": competitors,
                     "n_valid": int(len(pop)),
                     "note": "평균 피인용은 압축 목록에 든 문헌만으로 계산 (전체가 아님)"},
            "codes": code_rows, "applicants": apps, "hints": hints}
