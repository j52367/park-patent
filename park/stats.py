"""Patent-map statistics. All numbers in a report must come from here (see `park check-report`).

Counting rules (docs/DESIGN.md §5.2):
  * one row per application number (dedupe happens at ingest)
  * co-applicants: full counting — each applicant gets 1 for a shared application
  * the last ~18 months before `as_of` are marked incomplete (many applications are not yet published)
  * the growth-stage chart is a reference indicator only
"""

from __future__ import annotations

from collections import Counter
from datetime import date

import pandas as pd

from .normalize import split_multi

UNPUBLISHED_MONTHS = 18
COUNTRY_ORDER = ["KR", "US", "JP", "CN", "EP", "WO"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson interval for a proportion k/n."""
    if n == 0:
        return 0.0, 0.0
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return max(0.0, centre - half), min(1.0, centre + half)


def coverage(candidates: pd.DataFrame, screening: pd.DataFrame | None) -> dict:
    """How much of the candidate set was screened, and what the tail sample says about the rest.

    Tail-audit rows (screened_by contains 'tail-audit') are a random sample of documents below the
    screening cut; their valid share, scaled to the documents still unscreened, estimates how many
    relevant documents the counts in this report do not include.
    """
    if screening is None or screening.empty:
        return {"n_screened": 0, "n_unscreened": int(len(candidates))}
    screened = set(screening["application_no"])
    n_uns = int((~candidates["application_no"].isin(screened)).sum())
    out = {"n_screened": int(len(screened & set(candidates["application_no"]))), "n_unscreened": n_uns}
    tail = screening[screening["screened_by"].astype(str).str.contains("tail-audit")] \
        if "screened_by" in screening else screening.iloc[0:0]
    if len(tail):
        # only the latest round describes the documents that are still unscreened
        rounds = tail["screened_by"].astype(str).str.extract(r"tail-audit(?:-r(\d+))?")[0].fillna("1").astype(int)
        tail = tail[rounds == rounds.max()]
        out["tail_round"] = int(rounds.max())
    if len(tail):
        k, n = int((tail["relevance"] == "valid").sum()), int(len(tail))
        lo, hi = wilson(k, n)
        # the sample was drawn from (unscreened + sample) documents
        frame = n_uns + n
        out.update({"tail_sample": n, "tail_valid": k,
                    "tail_est_valid": round(k / n * n_uns), "tail_est_low": round(lo * n_uns),
                    "tail_est_high": round(hi * n_uns), "tail_frame": frame})
    return out


def _first(seq) -> str:
    return seq[0] if seq else ""


def _months_before(d: date, months: int) -> date:
    import calendar

    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def population(candidates: pd.DataFrame, screening: pd.DataFrame | None):
    """Rows to count: screened-valid applications if a screening exists, else every candidate."""
    if screening is not None:  # an existing but empty screening means 0 valid docs, not "count everything"
        if screening.empty:
            screening = pd.DataFrame(columns=["application_no", "relevance", "tech_code"])
        # the last judgement per application wins (same rule as merge-screening) — never count twice
        screening = screening.drop_duplicates(subset="application_no", keep="last")
        valid = screening[screening["relevance"] == "valid"][["application_no", "tech_code"]]
        pop = candidates.merge(valid, on="application_no", how="inner", validate="one_to_one")
        return pop, "valid"
    pop = candidates.copy()
    pop["tech_code"] = ""
    return pop, "all-candidates (unscreened)"


def compute(candidates: pd.DataFrame, screening: pd.DataFrame | None = None, as_of: str = "",
            top_n: int = 15, growth_period: int = 2) -> dict:
    pop, basis = population(candidates, screening)
    as_of_d = date.fromisoformat(as_of) if as_of else date.today()
    cutoff = _months_before(as_of_d, UNPUBLISHED_MONTHS)

    years = pd.to_datetime(pop["application_date"], errors="coerce").dt.year
    pop = pop.assign(year=years)
    dated = pop.dropna(subset=["year"])
    dated = dated.assign(year=dated["year"].astype(int))

    yearly = []
    if not dated.empty:
        counts = dated["year"].value_counts()
        for y in range(int(dated["year"].min()), int(dated["year"].max()) + 1):
            yearly.append({
                "year": y,
                "count": int(counts.get(y, 0)),
                # any part of the year falls inside the unpublished window
                "incomplete": date(y, 12, 31) > cutoff,
            })

    app_counter: Counter = Counter()
    app_nat: dict[str, Counter] = {}
    nat_col = pop["applicant_country"] if "applicant_country" in pop else pd.Series([""] * len(pop), index=pop.index)
    for names, nats in zip(pop["applicants"], nat_col):
        names, nats = split_multi(names), split_multi(nats)
        for i, n in enumerate(names):
            app_counter[n] += 1
            nat = nats[i] if len(nats) == len(names) else ""  # never guess for co-applicants
            if nat:
                app_nat.setdefault(n, Counter())[nat] += 1
    n_pop = len(pop)
    applicants_top = [
        {"name": n, "count": c, "share": round(c / n_pop, 4) if n_pop else 0,
         "nationality": app_nat[n].most_common(1)[0][0] if n in app_nat else ""}
        for n, c in app_counter.most_common(top_n)
    ]

    ipc_counts = pop["ipc_main"].replace("", "미상").value_counts().head(top_n)
    status_counts = pop["status"].replace("", "unknown").value_counts()

    result = {
        "meta": {
            "basis": basis,
            "n_candidates": int(len(candidates)),
            "n_counted": int(n_pop),
            "n_undated": int(len(pop) - len(dated)),
            "application_date_min": _first(sorted(d for d in pop["application_date"] if d)),
            "application_date_max": _first(sorted((d for d in pop["application_date"] if d), reverse=True)),
            # when the legal status was observed; "" = unknown for every counted doc
            "status_as_of_min": _first(sorted(d for d in pop["status_as_of"] if d)),
            "status_as_of_max": _first(sorted((d for d in pop["status_as_of"] if d), reverse=True)),
            "n_status_as_of_unknown": int((pop["status_as_of"] == "").sum()),
            "as_of": as_of_d.isoformat(),
            "unpublished_cutoff": cutoff.isoformat(),
            "n_applicants": len(app_counter),
            "counting": "full counting (each co-applicant +1)",
            **coverage(candidates, screening),
        },
        "yearly": yearly,
        "applicants_top": applicants_top,
        "ipc_main": [{"code": k, "count": int(v)} for k, v in ipc_counts.items()],
        "status": [{"status": k, "count": int(v)} for k, v in status_counts.items()],
        "growth": _growth(dated, growth_period, cutoff),
    }

    countries = [c for c in pop["country"].value_counts().index if c] if "country" in pop else []
    if countries and (pop["country"] == "").any():
        pop = pop.assign(country=pop["country"].replace("", "미상"))
        dated = dated.assign(country=dated["country"].replace("", "미상"))
        countries.append("미상")
    if countries:
        order = [c for c in COUNTRY_ORDER if c in countries] + sorted(c for c in countries if c not in COUNTRY_ORDER)
        result["country"] = [{"country": c, "count": int((pop["country"] == c).sum())} for c in order]
        yrs = [r["year"] for r in yearly]
        cy = dated.groupby(["country", "year"]).size()
        result["country_by_year"] = {"countries": order, "years": yrs,
                                     "values": [[int(cy.get((c, y), 0)) for y in yrs] for c in order]}

    if basis == "valid" and (pop["tech_code"] != "").any():
        codes = sorted(c for c in pop["tech_code"].unique() if c)
        yrs = [r["year"] for r in yearly]
        tech_year = dated.groupby(["tech_code", "year"]).size()
        result["tech_by_year"] = {
            "codes": codes, "years": yrs,
            "values": [[int(tech_year.get((c, y), 0)) for y in yrs] for c in codes],
        }
        top_names = [a["name"] for a in applicants_top[:10]]
        mat = {n: Counter() for n in top_names}
        for names, code in zip(pop["applicants"], pop["tech_code"]):
            for n in split_multi(names):
                if n in mat:
                    mat[n][code] += 1
        if countries:
            ct = pop.groupby(["country", "tech_code"]).size()
            result["country_by_tech"] = {"countries": result["country_by_year"]["countries"], "codes": codes,
                                         "values": [[int(ct.get((c, k), 0)) for k in codes]
                                                    for c in result["country_by_year"]["countries"]]}
        result["applicant_by_tech"] = {
            "applicants": top_names, "codes": codes,
            "values": [[mat[n][c] for c in codes] for n in top_names],
        }
    return result


def _growth(dated: pd.DataFrame, period: int, cutoff: date) -> list[dict]:
    """(number of applicants, number of applications) per period — the classic 'technology life cycle' plot."""
    if dated.empty:
        return []
    y0, y1 = int(dated["year"].min()), int(dated["year"].max())
    out = []
    for start in range(y0, y1 + 1, period):
        end = min(start + period - 1, y1)
        part = dated[(dated["year"] >= start) & (dated["year"] <= end)]
        names = set()
        for v in part["applicants"]:
            names.update(split_multi(v))
        out.append({
            "period": f"{start}" if start == end else f"{start}–{end}",
            "applications": int(len(part)),
            "applicants": len(names),
            "incomplete": date(end, 12, 31) > cutoff,
        })
    return out
