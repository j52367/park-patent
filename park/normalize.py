"""Deterministic clean-up: dates, application numbers, applicant names, IPC, de-duplication."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pandas as pd

# Korean legal forms: may be glued to the name and appear before or after it.
_KO_FORMS = ["유한책임회사", "주식회사", "유한회사", "재단법인", "사단법인"]
# Foreign legal forms (Latin and Korean transliterations), compared after punctuation is turned
# into spaces. Only stripped as a trailing *separate word*, so '에이지테크' or 'magna' stay intact.
_FOREIGN_FORMS = [
    "인코포레이티드", "인크", "코포레이션", "컴퍼니", "리미티드", "엘엘씨", "게엠베하", "악티엔게젤샤프트",
    "엘티디", "에스에이", "에이지", "비브이", "비 브이",
    "incorporated", "inc", "corporation", "corp", "company", "co", "limited", "ltd", "llc",
    "gmbh", "ag", "sa", "s a", "bv", "b v", "plc", "kk",
]
_SPACE_RE = re.compile(r"\s+")


def norm_date(value) -> str:
    """Accept 20190131, 2019-01-31, 2019.01.31, 2019/01/31 → 2019-01-31. Empty when unparseable."""
    if value is None:
        return ""
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "nat"}:
        return ""
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 8:
        y, m, d = digits[:4], digits[4:6], digits[6:8]
        if 1900 <= int(y) <= 2100 and 1 <= int(m) <= 12 and 1 <= int(d) <= 31:
            return f"{y}-{m}-{d}"
    return ""


def norm_application_no(value, country: str = "") -> str:
    """'10-2019-0012345' / 1020190012345.0 → '1020190012345' (KR or unknown country).

    Other countries get their code as a prefix so numbers from different offices never collide:
    ('16/123,456', 'US') → 'US16123456'.
    """
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    c = norm_country(country)
    if c == "WO":
        # PCT/KR2020/000001 — the receiving office is part of the identity
        m = re.search(r"PCT/?([A-Z]{2})/?(\d{2,4})/?(\d+)", s.upper())
        if m:
            year = m.group(2) if len(m.group(2)) == 4 else "20" + m.group(2)
            return f"WO{m.group(1)}{year}{int(m.group(3)):06d}"
    if c in {"CN", "EP"}:
        # check digit after the last dot (CN 202010123456.7, EP 18806395.1) is dropped so the
        # same application written with or without it gets one key
        s = re.sub(r"\.[0-9X]$", "", s, flags=re.I)
    digits = re.sub(r"\D", "", s)
    if digits and c and c != "KR":
        return c + digits
    return digits


def infer_country(application_no: str) -> str:
    """KR application numbers are 13 digits: 10- patent, 20- utility model."""
    return "KR" if re.fullmatch(r"(10|20)\d{11}", application_no or "") else ""


_COUNTRY_ALIASES = {"한국": "KR", "대한민국": "KR", "미국": "US", "일본": "JP", "중국": "CN", "유럽": "EP",
                    "pct": "WO", "wipo": "WO", "대만": "TW"}


def norm_country(value) -> str:
    s = str(value or "").strip()
    if not s or s.lower() in {"nan", "none"}:
        return ""
    if s in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[s]
    if s.lower() in _COUNTRY_ALIASES:
        return _COUNTRY_ALIASES[s.lower()]
    m = re.match(r"[A-Za-z]{2}", s)
    return m.group(0).upper() if m else ""


_ANYWHERE_TOKENS = ["(주)", "㈜", "(유)", "(재)", "(사)"]
_SEP_RE = re.compile(r"[\s,.·]+")


def applicant_key(name: str) -> str:
    """Matching key for one applicant name.

    '삼성전자주식회사', '삼성전자 주식회사', '주식회사 삼성전자', '삼성전자(주)' → '삼성전자'
    'Acme Co., Ltd.', 'Acme Co. Ltd', 'ACME CORP' → 'acme'
    '에이지테크(주)' → '에이지테크' (a transliterated form inside a name is not stripped)
    Different companies can still collide (e.g. a Korean and a US company with the same name),
    which is why merges are listed in applicant_merges.csv for review.
    """
    s = name.lower()
    for tok in _ANYWHERE_TOKENS:
        s = s.replace(tok, " ")
    s = _SEP_RE.sub(" ", s).strip()
    changed = True
    while changed and s:
        changed = False
        for tok in _KO_FORMS:
            if s.endswith(tok) and len(s) > len(tok):
                s, changed = s[: -len(tok)].strip(), True
            elif s.startswith(tok) and len(s) > len(tok):
                s, changed = s[len(tok):].strip(), True
        for tok in _FOREIGN_FORMS:
            if s.endswith(" " + tok) and len(s) > len(tok) + 1:
                s, changed = s[: -len(tok) - 1].strip(), True
    return re.sub(r"[\s\-]+", "", s)


EXACT_PREFIX = "="


def load_aliases(path: str | Path | None) -> dict[str, str]:
    """aliases.csv with columns alias,canonical[,match] (user-editable).

    match=key (default): every spelling with the same matching key → canonical (use to MERGE).
    match=exact: only this exact spelling → canonical (use to SPLIT two companies that share a key,
    e.g. '(주)디티에스' vs '디티에스, 인코포레이티드').
    Returned dict uses applicant_key(alias) for key matches and '=' + spelling for exact matches.
    """
    if not path or not Path(path).exists():
        return {}
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    match = df["match"] if "match" in df.columns else [""] * len(df)
    out = {}
    for a, c, m in zip(df["alias"], df["canonical"], match):
        if not a or not c:
            continue
        if m.strip().lower() == "exact":
            out[EXACT_PREFIX + _SPACE_RE.sub(" ", a.strip())] = c.strip()
        else:
            out[applicant_key(a)] = c.strip()
    return out


def split_multi(value: str) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[|;\n]", str(value))
    return [p.strip() for p in parts if p.strip()]


def normalize_applicants(raw_series: pd.Series, aliases: dict[str, str] | None = None) -> pd.Series:
    """Map every spelling variant to one display name.

    The display name for a key is the user alias if given, else the most frequent raw spelling.
    """
    aliases = aliases or {}
    spellings = applicant_spellings(raw_series, aliases)
    display = {key: aliases.get(key) or counter.most_common(1)[0][0] for key, counter in spellings.items()}

    def convert(raw: str) -> str:
        out: list[str] = []
        for name in split_multi(raw):
            name = _SPACE_RE.sub(" ", name)
            disp = aliases.get(EXACT_PREFIX + name) or display[applicant_key(name)]
            if disp not in out:
                out.append(disp)
        return "|".join(out)

    return raw_series.map(convert)


def applicant_spellings(raw_series: pd.Series, aliases: dict[str, str] | None = None) -> dict[str, Counter]:
    """matching key → Counter of raw spellings (exact-alias spellings excluded)."""
    aliases = aliases or {}
    spellings: dict[str, Counter] = {}
    for raw in raw_series:
        for name in split_multi(raw):
            name = _SPACE_RE.sub(" ", name)
            if EXACT_PREFIX + name in aliases:
                continue
            spellings.setdefault(applicant_key(name), Counter())[name] += 1
    return spellings


def merge_report(raw_series: pd.Series, aliases: dict[str, str] | None = None) -> pd.DataFrame:
    """Keys that merged more than one spelling — review these for wrong merges."""
    rows = []
    for key, counter in applicant_spellings(raw_series, aliases).items():
        if len(counter) > 1:
            rows.append({"display": (aliases or {}).get(key) or counter.most_common(1)[0][0],
                         "spellings": " / ".join(f"{s} ({n})" for s, n in counter.most_common()),
                         "total": sum(counter.values())})
    return pd.DataFrame(rows, columns=["display", "spellings", "total"]).sort_values("total", ascending=False)


def norm_ipc(value) -> tuple[str, str]:
    """Return (all codes '|'-joined, main subclass like 'G06N')."""
    codes = []
    for code in split_multi(value):
        code = _SPACE_RE.sub(" ", code).strip()
        if code and code not in codes:
            codes.append(code)
    main = ""
    if codes:
        m = re.match(r"[A-H]\d{2}[A-Z]", codes[0].replace(" ", "").upper())
        main = m.group(0) if m else ""
    return "|".join(codes), main


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """One row per application number.

    * ordinary fields: the last non-empty value wins (a later file fills blanks, never erases)
    * status + status_as_of travel together: the pair with the latest observation date wins,
      so importing an older snapshot cannot roll a 등록 back to 공개; 'unknown' never overrides
    """
    if df.empty:
        return df
    df = df.replace({None: ""}).fillna("").astype(str)
    if not df["application_no"].duplicated().any():
        return df.reset_index(drop=True)
    has_status = "status" in df.columns
    out = []
    for _, g in df.groupby("application_no", sort=False):
        row = {c: next((v for v in reversed(g[c].tolist()) if v.strip()), "") for c in g.columns}
        if has_status:
            known = g[(g["status"] != "") & (g["status"] != "unknown")]
            if len(known):
                as_of = known["status_as_of"] if "status_as_of" in known else pd.Series([""] * len(known))
                # stable sort keeps file order among equal dates, so the later file wins ties
                best = known.assign(_k=as_of.values).sort_values("_k", kind="stable").iloc[-1]
                row["status"] = best["status"]
                if "status_as_of" in g.columns:
                    row["status_as_of"] = best["status_as_of"]
            else:
                row["status"] = "unknown" if (g["status"] == "unknown").any() else ""
        out.append(row)
    return pd.DataFrame(out, columns=df.columns)
