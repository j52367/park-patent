"""Bring patent lists from other sources into candidates.csv.

Supported inputs (CSV or Excel):
  * PARK's own candidates.csv
  * the column layout of the original KIPRIS notebook (application_no, ipc_raw, applicant, ...)
  * spreadsheets downloaded from the KIPRIS website or other DBs, matched by Korean/English
    header synonyms. The synonym list is a best guess — please send a PR if your export
    uses headers that are not recognised (run with --show-mapping to see what matched).
"""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

from . import normalize as N
from .schema import CANDIDATE_COLUMNS, conform

# target column -> accepted header spellings (compared after removing spaces/brackets, lowercase)
HEADER_SYNONYMS: dict[str, list[str]] = {
    "application_no": ["application_no", "applicationnumber", "출원번호", "applno", "appno"],
    "country": ["country", "국가코드", "국가", "발행국", "countrycode", "출원국가"],
    "independent_claims": ["independent_claims", "독립청구항", "대표청구항", "청구항", "claims"],
    "title": ["title", "inventionname", "발명의명칭", "발명의명칭한글", "명칭", "발명명칭"],
    "abstract": ["abstract", "요약", "요약서", "초록"],
    "applicants_raw": ["applicants_raw", "applicants", "applicant", "출원인", "출원인명", "권리자"],
    "ipc": ["ipc", "ipc_raw", "internationalpatentclassificationnumber", "ipc분류", "국제특허분류", "ipc코드",
            "currentipcall", "ipcall", "ipc전체", "originalipcall"],
    "application_date": ["application_date", "applicationdate", "출원일", "출원일자"],
    "publication_date": ["publication_date", "openingdate", "publicationdate", "공개일", "공개일자"],
    "registration_date": ["registration_date", "registrationdate", "등록일", "등록일자"],
    "status": ["status", "registration_status", "registrationstatus", "법적상태", "등록상태", "상태", "상태정보", "행정처분"],
    # representative applicant names from commercial DBs (WIPS '출원인 대표명화'): preferred display names
    "applicant_country": ["applicant_country", "출원인국적", "출원인국가"],
    "applicants_rep": ["applicants_rep", "출원인대표명화영문명", "출원인대표명화", "대표출원인", "대표출원인명"],
    "status_as_of": ["status_as_of"],
    "source": ["source"],
}

# Checked in order: terminal states first, so '출원취하' becomes 취하 rather than 공개.
STATUS_MAP = [
    ("무효", "무효"), ("invalidated", "무효"),
    ("소멸", "소멸"), ("expired", "소멸"), ("lapsed", "소멸"),
    ("거절", "거절"), ("rejected", "거절"), ("refused", "거절"),
    ("취하", "취하"), ("withdrawn", "취하"),
    ("포기", "포기"), ("abandoned", "포기"),
    ("등록", "등록"), ("granted", "등록"), ("registered", "등록"), ("active", "등록"),
    ("공개", "공개"), ("published", "공개"), ("pending", "공개"), ("심사중", "공개"), ("출원", "공개"),
]


def _key(header: str) -> str:
    """'상태정보[KR,JP,US]' → '상태정보', 'Current IPC All' → 'currentipcall'."""
    h = re.sub(r"\[[^\]]*\]", "", str(header))
    return re.sub(r"[\s()_\-/.]", "", h).lower()


def map_headers(columns) -> dict[str, str]:
    """Return {source_header: target_column} for the headers we recognise.

    Exact PARK column names win over synonyms, so re-importing PARK's own candidates.csv
    (which has both 'applicants' and 'applicants_raw') maps applicants_raw → applicants_raw.
    """
    columns = list(columns)
    mapping: dict[str, str] = {}
    used: set[str] = set()
    for col in columns:  # pass 1: exact target names
        k = _key(col)
        for target in HEADER_SYNONYMS:
            if k == _key(target) and target not in used:
                mapping[col] = target
                used.add(target)
    lookup = {}
    for target, names in HEADER_SYNONYMS.items():
        for n in names:
            lookup.setdefault(_key(n), target)
    for col in columns:  # pass 2: synonyms
        if col in mapping:
            continue
        target = lookup.get(_key(col))
        if target and target not in used:
            mapping[col] = target
            used.add(target)
    return mapping


def _read_any(path: Path) -> pd.DataFrame:
    """Read CSV/Excel as strings, skipping title rows above the real header (common in DB exports)."""
    if path.suffix.lower() in {".xlsx", ".xls"}:
        raw = pd.read_excel(path, header=None, dtype=str)
    else:
        data = path.read_bytes()
        for enc in ("utf-8-sig", "cp949"):
            try:
                text = data.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise ValueError(f"cannot decode {path} as UTF-8 or CP949")
        # csv module, not pandas: exports often start with title rows that have fewer fields
        rows = list(csv.reader(io.StringIO(text)))
        width = max((len(r) for r in rows), default=0)
        raw = pd.DataFrame([r + [""] * (width - len(r)) for r in rows], dtype=str)
    raw = raw.fillna("")
    app_keys = {_key(n) for n in HEADER_SYNONYMS["application_no"]}
    header_row = 0
    for i in range(min(15, len(raw))):
        if any(_key(v) in app_keys for v in raw.iloc[i].tolist()):
            header_row = i
            break
    df = raw.iloc[header_row + 1:].copy()
    df.columns = [str(c).strip() for c in raw.iloc[header_row].tolist()]
    return df.reset_index(drop=True)


def norm_status(value: str) -> str:
    s = str(value).strip().lower()
    if not s:
        return "unknown"
    for k, v in STATUS_MAP:
        if k in s:
            return v
    return "unknown"


def ingest(path: str | Path, as_of: str = "", aliases_path: str | Path | None = None,
           source: str | None = None) -> tuple[pd.DataFrame, dict[str, str]]:
    """Read one file and return (candidates dataframe, header mapping used)."""
    path = Path(path)
    df = _read_any(path)
    mapping = map_headers(df.columns)
    if "application_no" not in mapping.values():
        raise ValueError(f"{path.name}: no application-number column found. Headers: {list(df.columns)}")
    # select first, then rename: unmapped columns can never collide with target names
    out = df[list(mapping)].rename(columns=mapping).copy()

    out["country"] = out["country"].map(N.norm_country) if "country" in out else ""
    if "applicant_country" in out:
        out["applicant_country"] = out["applicant_country"].map(
            lambda v: "|".join(N.norm_country(x) for x in N.split_multi(v)))
    out["application_no"] = [N.norm_application_no(a, c) for a, c in zip(out["application_no"], out["country"])]
    # country missing: infer KR from the 13-digit KR format so mixed files still add up per country
    out["country"] = [c or N.infer_country(a) for a, c in zip(out["application_no"], out["country"])]
    out = out[out["application_no"].str.len() > 0]
    for col in ("application_date", "publication_date", "registration_date"):
        if col in out:
            out[col] = out[col].map(N.norm_date)
    if "ipc" in out:
        pairs = out["ipc"].map(N.norm_ipc)
        out["ipc"] = pairs.map(lambda p: p[0])
        out["ipc_main"] = pairs.map(lambda p: p[1])
    # a missing status stays empty so it cannot overwrite a known status when files are merged
    out["status"] = out["status"].map(lambda v: norm_status(v) if str(v).strip() else "") if "status" in out else ""
    if as_of:
        out["status_as_of"] = N.norm_date(as_of)
    elif "status_as_of" in out:
        out["status_as_of"] = out["status_as_of"].map(N.norm_date)
    else:
        out["status_as_of"] = ""
    if "applicants_raw" in out:
        out["applicants_raw"] = out["applicants_raw"].map(lambda v: "|".join(N.split_multi(v)))
    if "applicants_rep" in out:
        # keep empty slots: '| Example Institute' means "no representative name for applicant 1"
        out["applicants_rep"] = out["applicants_rep"].map(
            lambda v: "|".join(x.strip() for x in str(v).split("|")) if str(v).strip() else "")
    default_source = source or f"csv:{path.name}"
    if "source" in out:
        out["source"] = out["source"].map(lambda v: v if str(v).strip() else default_source)
    else:
        out["source"] = default_source
    out = conform(out, CANDIDATE_COLUMNS)
    return out, mapping


def finalize(frames: list[pd.DataFrame], aliases_path=None) -> pd.DataFrame:
    """Merge several ingested frames: de-duplicate and normalise applicant names across all of them."""
    df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=CANDIDATE_COLUMNS)
    df = N.dedupe(df)
    if "status" in df:
        df["status"] = df["status"].replace("", "unknown")
    aliases = N.load_aliases(aliases_path)
    if "applicants_rep" in df.columns:
        aliases, effective = _apply_representative_names(df["applicants_raw"], df["applicants_rep"], aliases)
        df["applicants"] = N.normalize_applicants(effective, aliases)
    else:
        df["applicants"] = N.normalize_applicants(df["applicants_raw"], aliases)
    return conform(df, CANDIDATE_COLUMNS)


def _rep_slots(rep: str) -> list[str]:
    return [x.strip() for x in str(rep).split("|")] if str(rep).strip() else []


def _apply_representative_names(raw: pd.Series, rep: pd.Series, aliases: dict[str, str]):
    """Use DB representative names position by position.

    * learns raw→representative pairs wherever the two lists line up, so rows without a
      representative name get the same display name (user aliases still win)
    * an empty slot keeps that applicant's own name; a length mismatch keeps all raw names
    Returns (aliases, effective names series).
    """
    seen = _rep_pairs(raw, rep)
    # a raw key seen with two different representative names (two companies sharing a key) is not learned
    learned = {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}
    merged = {**learned, **aliases}

    def explicit(name: str) -> bool:  # the user's exact alias beats the DB's representative name
        return N.EXACT_PREFIX + " ".join(name.split()) in aliases

    effective = []
    for r_val, p_val in zip(raw, rep):
        r, p = N.split_multi(r_val), _rep_slots(p_val)
        if len(r) == len(p):
            effective.append("|".join(rn if (explicit(rn) or not pn) else pn for rn, pn in zip(r, p)))
        else:
            effective.append("|".join(r))
    return merged, pd.Series(effective, index=raw.index)


def _rep_pairs(raw: pd.Series, rep: pd.Series) -> dict[str, set[str]]:
    seen: dict[str, set[str]] = {}
    for r_val, p_val in zip(raw, rep):
        r, p = N.split_multi(r_val), _rep_slots(p_val)
        if len(r) == len(p):
            for rn, pn in zip(r, p):
                if pn:
                    seen.setdefault(N.applicant_key(rn), set()).add(pn)
    return seen


def rep_conflicts(raw: pd.Series, rep: pd.Series) -> list[tuple[str, list[str]]]:
    """Raw applicant keys the DB mapped to more than one representative name (not auto-learned)."""
    return [(k, sorted(v)) for k, v in _rep_pairs(raw, rep).items() if len(v) > 1]
