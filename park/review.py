"""Phase 2: key-patent review on claims.

Inputs: shortlist.csv, enrich.csv, details/<no>.json (claims), IMPORTANCE.md (criteria).
Batches show each document's independent claims plus deterministic signals (forward citations with
their percentile in the shortlist, claim count, status, family size, filing year). The judge
(LLM or person) writes review/done/*.jsonl; merge() turns them into key_review.csv and checks that
every evidence quote is a verbatim part of the cited claim.

key_review.csv columns:
  application_no, importance (핵심|주목|일반), evidence_level (confirmed), evidence_location ("청구항 n"),
  evidence_quote, key_features (one line: what the claim actually protects), rationale, reviewed_by
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .checks import _squash, load_claims
from .kipris import independent_claims
from .schema import read_csv, write_csv

IMPORTANCE_VALUES = {"핵심", "주목", "일반"}
REVIEW_COLUMNS = ["application_no", "importance", "evidence_level", "evidence_location", "evidence_quote",
                  "key_features", "rationale", "reviewed_by"]


def signals(d: Path) -> pd.DataFrame:
    s = read_csv(d / "shortlist.csv")
    e = read_csv(d / "enrich.csv")
    df = s.merge(e, on="application_no", how="inner")
    fc = pd.to_numeric(df["forward_citations"], errors="coerce").fillna(0)
    # top-x% among enriched shortlist documents; omitted when too few are enriched to compare
    df["forward_top_pct"] = ((fc.rank(ascending=False, method="min") / len(df)) * 100).round(0).astype(int) \
        if len(df) >= 20 else -1
    return df


def make_batches(d: Path, size: int = 15) -> int:
    df = signals(d)
    tdir = d / "review" / "todo"
    tdir.mkdir(parents=True, exist_ok=True)
    done = set()
    for f in (d / "review" / "done").glob("*.jsonl") if (d / "review" / "done").exists() else []:
        done |= {json.loads(l)["application_no"] for l in f.read_text(encoding="utf-8").splitlines() if l.strip()}
    df = df[~df["application_no"].isin(done)]
    for old in tdir.glob("key_*.md"):
        old.unlink()
    n = 0
    for i in range(0, len(df), size):
        n += 1
        blocks = []
        for _, r in df.iloc[i:i + size].iterrows():
            det = json.loads((d / "details" / f"{r['application_no']}.json").read_text(encoding="utf-8"))
            indep = "\n".join(f"  - {c[:1200]}" for c in independent_claims(det.get("claims", []))) or "  (청구항 없음)"
            blocks.append(
                f"### {r['application_no']}\n- 명칭: {r['title']}\n- 출원인: {r['applicants']}\n"
                f"- 기술분류: {r['tech_code']} · 상태: {r['status']} ({r['register_status']}) · 출원일: {r['application_date']}\n"
                f"- 신호: 피인용 {r['forward_citations']}건"
                + (f" (압축 목록 내 상위 {int(r['forward_top_pct'])}%)" if int(r["forward_top_pct"]) >= 0 else "")
                + ", "
                f"청구항 {r['claim_count']}개 (독립항 {r['independent_claims']}), 패밀리 {r['family_size']}건\n"
                f"- 독립청구항:\n{indep}\n")
        (tdir / f"key_{n:03d}.md").write_text(f"# key_{n:03d}\n\n" + "\n".join(blocks), encoding="utf-8")
    return n


def merge(d: Path) -> tuple[pd.DataFrame, list[str]]:
    rows, errors = [], []
    files = sorted((d / "review" / "done").glob("*.jsonl"), key=lambda f: (f.stat().st_mtime, f.name))
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as e:
                    errors.append(f"{f.name}:{n}: invalid JSON ({e})")
    df = pd.DataFrame(rows).reindex(columns=REVIEW_COLUMNS).fillna("").astype(str)
    df = df.drop_duplicates("application_no", keep="last").reset_index(drop=True)
    bad: set[str] = set()

    def fail(no: str, msg: str):
        errors.append(f"{no}: {msg}")
        bad.add(no)

    for _, r in df.iterrows():
        no = r["application_no"]
        if r["importance"] not in IMPORTANCE_VALUES:
            fail(no, f"importance '{r['importance']}' not in {sorted(IMPORTANCE_VALUES)}")
        claims = load_claims(d, no)
        quote = _squash(r["evidence_quote"])
        if claims is None:
            if quote:
                fail(no, "no claims text (details/ or fulltext/) — run `park enrich`")
            continue
        if not quote:
            if r["importance"] != "일반":
                fail(no, "no evidence_quote — only '일반' may be given without a claim quote")
            continue
        m = re.search(r"\d+", r["evidence_location"])
        if not m:
            fail(no, "evidence_location must name one claim, e.g. '청구항 1'")
            continue
        part = claims.get(int(m.group(0)))
        if part is None:
            fail(no, f"{r['evidence_location']} not found among the claims")
        elif len(quote) < 8 or quote not in _squash(part):
            fail(no, f"evidence_quote not found verbatim in {r['evidence_location']}")
    # only verified judgements reach key_review.csv (and therefore the report)
    write_csv(df[~df["application_no"].isin(bad)], d / "key_review.csv")
    return df, errors
