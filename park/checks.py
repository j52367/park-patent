"""Deterministic gates that keep LLM output honest.

* check_screening — every screening row is well-formed, its tech_code exists in TECH_TREE.md,
  and its evidence_quote really appears in the source text it points to.
* lint_numbers — report prose must take counts from stats.json placeholders, not type them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .schema import EVIDENCE_LEVELS, RELEVANCE_VALUES

_WS = re.compile(r"\s+")
_PLACEHOLDER = re.compile(r"\{\{\s*[^}]+\s*\}\}")
# a number followed by a count/percent unit, e.g. "1,234건", "35%", "12개사", also glued to Korean
# text ("총999건"). Only digits/commas/dots before the match are excluded (no matching mid-number).
_BARE_NUMBER = re.compile(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?\s*(?:건|%|퍼센트|개사|개 기업|개국|명)")
MIN_QUOTE_CHARS = 8


def _squash(s: str) -> str:
    return _WS.sub("", str(s))


def tech_codes(tech_tree_md: str) -> set[str]:
    """Codes are the first cell of each Markdown table row in TECH_TREE.md, written in backticks: | `A1` | ..."""
    return set(re.findall(r"^\|\s*`([^`]+)`\s*\|", tech_tree_md, flags=re.M))


def _source_text(src, location: str, fulltext: str):
    """Text the quote must come from, chosen by evidence_location. Returns (text, None) or (None, reason)."""
    loc = str(location).strip()
    if "요약" in loc or loc.lower().startswith("abstract"):
        return src["abstract"], None
    if "명칭" in loc or "제목" in loc or loc.lower().startswith("title"):
        return src["title"], None
    if "청구항" in loc or loc.lower().startswith("claim"):
        if fulltext:
            return fulltext, None
        claims = str(src.get("independent_claims", "") or "")
        if claims.strip():
            num = re.search(r"\d+", loc)
            if not num:  # "독립청구항": any independent claim
                return claims, None
            part = _claim_text(claims, int(num.group(0)))
            if part is None:
                return None, f"evidence_location '{loc}': claim {num.group(0)} is not among the imported independent claims"
            return part, None
    if "서지" in loc:
        return " ".join(str(src[c]) for c in ("title", "abstract", "applicants_raw", "ipc")), None
    if fulltext:  # 청구항 n, [0023], 명세서 … — need the full document
        return fulltext, None
    return None, f"evidence_location '{loc or '(empty)'}' needs full text (fulltext/<no>.txt) — "                  f"with abstract-only data use 요약 / 명칭 / 서지"


CLAIM_HEAD = re.compile(r"^\s*(?:【\s*)?(?:청구항\s*)?(\d{1,3})\s*(?:】|\.|\))?\s*")


def claims_by_number(claims: list[str]) -> dict[int, str]:
    """{claim number: text} from a list where each item is one whole claim ("1. …", "청구항 1 …").

    Items without a leading number are numbered by position. This avoids guessing claim
    boundaries inside running text (where "설정값 10. 이하" is not claim 10).
    """
    out: dict[int, str] = {}
    for i, c in enumerate(claims, 1):
        m = CLAIM_HEAD.match(c)
        n = int(m.group(1)) if (m and m.group(1)) else i
        out.setdefault(n, c)
    return out


def load_claims(d, application_no: str) -> dict[int, str] | None:
    """Claims of a document: details/<no>.json (one item per claim) or fulltext/<no>.txt."""
    import json as _json
    from pathlib import Path as _P

    det = _P(d) / "details" / f"{application_no}.json"
    if det.exists():
        claims = _json.loads(det.read_text(encoding="utf-8")).get("claims", [])
        if claims:
            return claims_by_number(claims)
    ft = _P(d) / "fulltext" / f"{application_no}.txt"
    if ft.exists():
        # one claim per line-start number; numbers inside sentences are not boundaries
        parts = re.split(r"(?m)^(?=\s*\d{1,3}\s*\.\s)", ft.read_text(encoding="utf-8"))
        return claims_by_number([p for p in parts if p.strip()])
    return None


def _claim_text(claims: str, n: int) -> str | None:
    """Text of claim n from a one-string field like '1. … 10. …' (None if absent).

    A claim number counts only at the start, after a line break, or after a sentence end,
    so "설정값 10. 이하" inside a claim is not taken for claim 10.
    """
    starts = [(int(m.group(1)), m.start())
              for m in re.finditer(r"(?:^|(?<=\n)|(?<=[.;:。]\s))(\d{1,3})\.\s", claims)]
    for i, (k, pos) in enumerate(starts):
        if k == n:
            end = starts[i + 1][1] if i + 1 < len(starts) else len(claims)
            return claims[pos:end]
    return None


def tech_labels(tech_tree_md: str) -> dict[str, str]:
    """code → most specific name in the row (소분류, else 중분류, else the next cell)."""
    lines = [l for l in tech_tree_md.splitlines() if l.strip().startswith("|")]
    if not lines:
        return {}
    header = [c.strip() for c in lines[0].strip().strip("|").split("|")]
    order = [header.index(h) for h in ("소분류", "중분류", "대분류") if h in header] or [1]
    out = {}
    for l in lines[1:]:
        cells = [c.strip() for c in l.strip().strip("|").split("|")]
        m = re.fullmatch(r"`([^`]+)`", cells[0]) if cells else None
        if m:
            out[m.group(1)] = next((cells[i] for i in order if i < len(cells) and cells[i]), "")
    return out


@dataclass
class CheckResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors


def check_screening(candidates: pd.DataFrame, screening: pd.DataFrame, tech_tree_md: str | None = None,
                    fulltext: dict[str, str] | None = None) -> CheckResult:
    res = CheckResult()
    screening = screening.fillna("").astype(str)  # NaN must not become the text 'nan'
    candidates = candidates.fillna("")
    by_no = candidates.set_index("application_no")
    codes = tech_codes(tech_tree_md) if tech_tree_md else None
    fulltext = fulltext or {}
    verified = unverifiable = human_no_quote = 0

    dup = screening["application_no"][screening["application_no"].duplicated()].unique()
    for no in dup:
        res.errors.append(f"{no}: screened more than once")
    missing = set(candidates["application_no"]) - set(screening["application_no"])
    if missing:
        res.warnings.append(f"{len(missing)} candidates have no screening row (e.g. {sorted(missing)[:3]})")

    for i, r in screening.iterrows():
        where = f"row {i + 2} ({r['application_no']})"
        if r["application_no"] not in by_no.index:
            res.errors.append(f"{where}: application_no not in candidates.csv")
            continue
        if r["relevance"] not in RELEVANCE_VALUES:
            res.errors.append(f"{where}: relevance '{r['relevance']}' not in {sorted(RELEVANCE_VALUES)}")
        if r["evidence_level"] not in EVIDENCE_LEVELS:
            res.errors.append(f"{where}: evidence_level '{r['evidence_level']}' not in {sorted(EVIDENCE_LEVELS)}")
        if r["relevance"] == "valid":
            if not r["tech_code"]:
                res.errors.append(f"{where}: valid but tech_code is empty")
            elif codes is not None and r["tech_code"] not in codes:
                res.errors.append(f"{where}: tech_code '{r['tech_code']}' not defined in TECH_TREE.md")
        if r["evidence_level"] == "confirmed" and not fulltext.get(r["application_no"]):
            res.errors.append(f"{where}: evidence_level=confirmed but no full text is available — use provisional")
        quote = _squash(r.get("evidence_quote", ""))
        if not quote:
            if str(r.get("screened_by", "")).startswith("human"):
                human_no_quote += 1  # imported human judgement: allowed, but reported
            elif r["relevance"] != "undecided":
                res.errors.append(f"{where}: no evidence_quote — judgements without evidence are not allowed")
            continue
        whole_title = ("명칭" in str(r.get("evidence_location", "")) and
                       quote == _squash(by_no.loc[r["application_no"]].get("title", "")))
        if len(quote) < MIN_QUOTE_CHARS and not whole_title:  # a short title quoted in full is fine
            res.errors.append(f"{where}: evidence_quote too short to be evidence (<{MIN_QUOTE_CHARS} chars)")
            continue
        haystack, why = _source_text(by_no.loc[r["application_no"]], r.get("evidence_location", ""),
                                     fulltext.get(r["application_no"], ""))
        if haystack is None:
            res.errors.append(f"{where}: {why}")
            unverifiable += 1
            continue
        if quote in _squash(haystack):
            verified += 1
        else:
            res.errors.append(f"{where}: evidence_quote not found verbatim in '{r.get('evidence_location', '')}': "
                              f"'{str(r.get('evidence_quote', ''))[:40]}…'")
            unverifiable += 1

    counts = screening["relevance"].value_counts().to_dict()
    if human_no_quote:
        res.warnings.append(f"{human_no_quote} human judgements were imported without evidence quotes")
    res.stats = {"rows": int(len(screening)), "quotes_verified": verified, "quotes_failed": unverifiable,
                 "human_without_quote": human_no_quote,
                 **{f"relevance_{k}": int(v) for k, v in counts.items()}}
    return res


# method wording that contains a number but is not a count: "1건씩", "1건마다", "100%"
_METHOD_PHRASE = re.compile(r"(?<![\d.,])1\s*건\s*(?:씩|마다)|(?<![\d.,])100\s*%")


def lint_numbers(markdown: str) -> list[str]:
    """Lines that state counts/percentages without a {{placeholder}}."""
    hits = []
    for n, line in enumerate(markdown.splitlines(), 1):
        stripped = _METHOD_PHRASE.sub("", _PLACEHOLDER.sub("", line))
        for m in _BARE_NUMBER.finditer(stripped):
            hits.append(f"line {n}: '{m.group(0)}' — use a {{{{stats...}}}} placeholder instead of a typed number")
    return hits


def load_fulltext(analysis_dir: Path) -> dict[str, str]:
    """Optional fulltext/<application_no>.txt files (Phase 2 fills these)."""
    d = analysis_dir / "fulltext"
    if not d.exists():
        return {}
    return {p.stem: p.read_text(encoding="utf-8") for p in d.glob("*.txt")}
