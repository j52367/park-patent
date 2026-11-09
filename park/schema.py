"""File schemas shared by the CLI tools and the skills.

Every analysis artifact is a plain file under ``analysis/<project>/`` so that skills
(Markdown, run by an LLM) and tools (Python, deterministic) can hand work to each other.
Columns listed here are the contract; extra columns are allowed and preserved.
"""

from __future__ import annotations

import pandas as pd

SCHEMA_VERSION = "1"

# candidates.csv — one row per application (published and granted docs merged)
CANDIDATE_COLUMNS = [
    "application_no",     # KR: 13 digits; other countries: country code + digits (e.g. US16123456)
    "country",            # KR, US, JP, CN, EP, WO ... (empty = unknown)
    "title",
    "abstract",
    "independent_claims", # independent claim text when the source provides it (evidence location 독립청구항)
    "applicants",         # normalized names, "|"-separated
    "applicants_raw",     # as received, "|"-separated
    "ipc",                # all IPC codes, "|"-separated
    "ipc_main",           # first IPC subclass, e.g. G06N
    "application_date",   # YYYY-MM-DD
    "publication_date",   # YYYY-MM-DD or empty
    "registration_date",  # YYYY-MM-DD or empty
    "status",             # see STATUSES
    "status_as_of",       # date the status was observed (YYYY-MM-DD) or empty
    "source",             # kipris-api | csv:<file> | synthetic
    "schema_version",
]

STATUSES = ["공개", "등록", "소멸", "거절", "취하", "포기", "무효", "unknown"]

# screening.csv — written by the relevance-screening skill (LLM), checked by tools
SCREENING_COLUMNS = [
    "application_no",
    "relevance",          # noise | valid | undecided
    "tech_code",          # code from TECH_TREE.md (empty when noise)
    "evidence_level",     # provisional (abstract/bibliographic only) | confirmed (full text)
    "evidence_location",  # e.g. "요약", "청구항 1", "[0023]"
    "evidence_quote",     # verbatim text copied from the source document
    "rationale",
    "screened_by",        # model or person
    "schema_version",
]

RELEVANCE_VALUES = {"noise", "valid", "undecided"}
EVIDENCE_LEVELS = {"provisional", "confirmed"}


def empty_candidates() -> pd.DataFrame:
    return pd.DataFrame(columns=CANDIDATE_COLUMNS)


def conform(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Add missing contract columns (empty), put them first, keep extras after."""
    df = df.copy()
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df["schema_version"] = SCHEMA_VERSION
    extras = [c for c in df.columns if c not in columns]
    return df[columns + extras]


def read_csv(path) -> pd.DataFrame:
    """Read a PARK csv with every column as string (application numbers must not become ints)."""
    return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def write_csv(df: pd.DataFrame, path) -> None:
    # utf-8-sig so Excel on Korean Windows opens it without mojibake
    df.to_csv(path, index=False, encoding="utf-8-sig")
