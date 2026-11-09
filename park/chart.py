"""Claim charts (phase 2): one target claim against the closest earlier documents.

Modes (docs/DESIGN.md §5.3):
  novelty   — every element of the claim against ONE prior-art document at a time
  inventive — the same chart, plus combinations (primary + secondary documents) for missing elements
Infringement / design-around charts (product vs claims) need a product description from the user
and are not automated here.

Flow:
  prepare() → charts/<target>_c<n>/{elements.json, ELEMENTS.md, prior_art.csv, todo.md}
     elements: the claim split at ';' (Korean claims list elements that way) + the preamble subject
     prior art: candidates filed before the target's priority date, ranked by char-n-gram TF-IDF
                similarity to the claim; examiner-cited documents are marked (and always included)
  judge (LLM or person) → charts/<...>/done.jsonl
  merge() → chart.csv / summary.json, every quote verified in the cited document's text
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from .checks import _claim_text, _squash
from .normalize import norm_date

STATUS = {"개시", "일부", "미개시"}


def split_elements(claim: str) -> list[dict]:
    body = re.sub(r"^\s*\d+\s*\.\s*", "", claim).strip()
    preamble = ""
    # "…을 포함하는 (것을 특징으로 하는) 촉각센서." — a short subject at the very end
    m = re.search(r"(?:을|를)\s*포함하는\s*(?:것을\s*특징으로\s*하는\s*)?([^;,.]{1,40}?)\s*\.?\s*$", body)
    if not m:  # "…를 포함하는, 탄성 촉각 센서." (subject after a comma)
        m = re.search(r"(?<=하는|되는|있는),\s*([^;,.]{1,30}?)\s*\.?\s*$", body)
    if m:
        preamble = m.group(1).strip()
        body = body[:m.start()].strip()
    parts = [p.strip() for p in re.split(r";\s*(?:및\s*)?|,\s*및\s+", body) if p.strip()]
    els = [{"id": f"E{i}", "text": p} for i, p in enumerate(parts, 1)]
    if preamble:
        els.insert(0, {"id": "E0", "text": preamble, "preamble": True})
    return els


def _doc_text(r, fulltext: Path) -> str:
    ft = fulltext / f"{r['application_no']}.txt"
    claims = ft.read_text(encoding="utf-8") if ft.exists() else ""
    return f"{r['title']} {r['abstract']} {claims}"


def prepare(d: Path, target: str, claim_no: int = 1, k: int = 8, examiner_apps: list[str] | None = None,
            include: list[str] | None = None) -> Path:
    from sklearn.feature_extraction.text import TfidfVectorizer

    det = json.loads((d / "details" / f"{target}.json").read_text(encoding="utf-8"))
    claims = "\n".join(det.get("claims", []))
    claim = _claim_text(claims, claim_no)
    if not claim:
        raise ValueError(f"claim {claim_no} not found for {target}")
    pri = sorted(norm_date(p.get("date")) for p in det.get("priority", []) if p.get("date"))
    cand = pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False)
    tgt = cand[cand["application_no"] == target]
    cutoff = pri[0] if pri else (tgt["application_date"].iloc[0] if len(tgt) else "")
    pool = cand[(cand["application_no"] != target) & (cand["application_date"] < cutoff)].reset_index(drop=True)
    ft = d / "fulltext"
    texts = [_doc_text(r, ft) for _, r in pool.iterrows()]
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), min_df=1, sublinear_tf=True).fit(texts + [claim])
    sim = (vec.transform(texts) @ vec.transform([claim]).T).toarray().ravel()
    pool = pool.assign(similarity=sim.round(4)).sort_values("similarity", ascending=False).reset_index(drop=True)
    pool["sim_rank"] = range(1, len(pool) + 1)
    examiner = set(examiner_apps or [])
    pool["examiner_cited"] = pool["application_no"].isin(examiner)
    pool["user_included"] = pool["application_no"].isin(set(include or []))
    chosen = pool[(pool["sim_rank"] <= k) | pool["examiner_cited"] | pool["user_included"]]

    out = d / "charts" / f"{target}_c{claim_no}"
    out.mkdir(parents=True, exist_ok=True)
    els = split_elements(claim)
    (out / "elements.json").write_text(json.dumps({"target": target, "claim_no": claim_no, "claim": claim,
                                                   "priority_date": cutoff, "elements": els},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "ELEMENTS.md").write_text(
        f"# 대상 청구항 — {target} 청구항 {claim_no} (기준일 {cutoff})\n\n> {claim}\n\n"
        "| 구성요소 | 내용 |\n|---|---|\n" + "".join(f"| {e['id']} | {e['text']} |\n" for e in els)
        + "\n구성요소 분할이 맞는지 확인하고, 필요하면 elements.json을 고친 뒤 다시 배치를 만드세요.\n", encoding="utf-8")
    chosen[["application_no", "title", "applicants", "application_date", "similarity", "sim_rank",
            "examiner_cited"]].to_csv(out / "prior_art.csv", index=False, encoding="utf-8-sig")
    return out


def relevant_paragraphs(spec: dict, elements: list[dict], per_element: int = 4, limit: int = 7000) -> list[tuple[str, str]]:
    """Description paragraphs most similar to any claim element (char n-gram TF-IDF), in document order."""
    from sklearn.feature_extraction.text import TfidfVectorizer

    paras = [(k, v) for k, v in spec.get("paragraphs", {}).items() if len(v) > 30]
    if not paras:
        return []
    vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True)
    X = vec.fit_transform([v for _, v in paras] + [e["text"] for e in elements])
    P, E = X[:len(paras)], X[len(paras):]
    sim = (P @ E.T).toarray()
    keep = set()
    for j in range(sim.shape[1]):
        keep.update(sim[:, j].argsort()[::-1][:per_element].tolist())
    chosen, size = [], 0
    for i in sorted(keep, key=lambda i: paras[i][0]):
        if size + len(paras[i][1]) > limit:
            break
        chosen.append(paras[i])
        size += len(paras[i][1])
    return chosen


def make_todo(d: Path, out: Path) -> None:
    meta = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    pa = pd.read_csv(out / "prior_art.csv", dtype=str, keep_default_na=False)
    cand = pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False).set_index("application_no")
    blocks = []
    for _, r in pa.iterrows():
        no = r["application_no"]
        ft = d / "fulltext" / f"{no}.txt"
        claims = ft.read_text(encoding="utf-8") if ft.exists() else "(청구항 없음 — 요약만 대조)"
        desc = ""
        sp = d / "description" / f"{no}.json"
        if sp.exists():
            spec = json.loads(sp.read_text(encoding="utf-8"))
            paras = relevant_paragraphs(spec, meta["elements"])
            desc = "- 명세서 발췌 (구성요소와 관련된 단락):\n" + "\n".join(f"  [{k}] {v}" for k, v in paras) + "\n"
        blocks.append(f"### {no}\n- 명칭: {cand.loc[no, 'title']}\n- 출원일: {cand.loc[no, 'application_date']}"
                      f" · 유사도 순위 {r['sim_rank']}" + (" · **심사관 인용**" if r["examiner_cited"] == "True" else "")
                      + f"\n- 요약: {cand.loc[no, 'abstract']}\n- 청구항:\n{claims[:6000]}\n{desc}")
    els = "\n".join(f"- {e['id']}: {e['text']}" for e in meta["elements"])
    (out / "todo.md").write_text(
        f"# 청구항 대비 — {meta['target']} 청구항 {meta['claim_no']} (기준일 {meta['priority_date']})\n\n"
        f"## 대상 청구항\n{meta['claim']}\n\n## 구성요소\n{els}\n\n## 선행문헌 후보\n\n" + "\n".join(blocks), encoding="utf-8")


def merge(d: Path, out: Path) -> tuple[dict, list[str]]:
    meta = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    ids = {e["id"] for e in meta["elements"]}
    cand = pd.read_csv(d / "candidates.csv", dtype=str, keep_default_na=False).set_index("application_no")
    rows, summaries, combos, errors = [], [], [], []
    for line in (out / "done.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        o = json.loads(line)
        if "combination" in o:
            combos.append(o)
            continue
        if "summary" in o:
            summaries.append(o)
            continue
        rows.append(o)
    for o in rows:
        no, el = str(o.get("prior_art", "")), o.get("element", "")
        where = f"{no}/{el}"
        if el not in ids:
            errors.append(f"{where}: unknown element")
        if o.get("status") not in STATUS:
            errors.append(f"{where}: status '{o.get('status')}' not in {sorted(STATUS)}")
        if o.get("status") == "미개시":
            continue
        loc, quote = str(o.get("location", "")), _squash(o.get("quote", ""))
        if no not in cand.index:
            errors.append(f"{where}: not a candidate")
            continue
        para = re.search(r"\[?(\d{4})\]?", loc) if ("[" in loc or "단락" in loc) else None
        if para:
            from .fulltext import quote_in_paragraph

            sp = d / "description" / f"{no}.json"
            ok = sp.exists() and len(quote) >= 6 and quote_in_paragraph(
                json.loads(sp.read_text(encoding="utf-8")), para.group(1), o.get("quote", ""))
            if not ok:
                errors.append(f"{where}: quote not found in description paragraph {para.group(1)} (±1)")
            continue
        if "청구항" in loc:
            ft = d / "fulltext" / f"{no}.txt"
            m = re.search(r"\d+", loc)
            src = _claim_text(ft.read_text(encoding="utf-8"), int(m.group(0))) if (ft.exists() and m) else None
        elif "요약" in loc:
            src = cand.loc[no, "abstract"]
        else:
            src = f"{cand.loc[no, 'title']} {cand.loc[no, 'abstract']}"
        if src is None or len(quote) < 6 or quote not in _squash(src):
            errors.append(f"{where}: quote not found verbatim in {loc or 'the document'}")
    chart = pd.DataFrame(rows)
    chart.to_csv(out / "chart.csv", index=False, encoding="utf-8-sig")
    summary = {"target": meta["target"], "claim_no": meta["claim_no"], "priority_date": meta["priority_date"],
               "elements": meta["elements"], "summaries": summaries, "combinations": combos}
    if len(chart):
        disclosed = chart[chart["status"] == "개시"].groupby("prior_art")["element"].nunique()
        summary["fully_disclosed_by"] = [no for no, n in disclosed.items() if n == len(ids)]
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary, errors
