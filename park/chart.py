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

from .checks import _squash, claims_by_number, load_claims
from .normalize import norm_date

STATUS = {"개시", "일부", "미개시"}


def split_elements(claim: str) -> list[dict]:
    body = re.sub(r"^\s*\d+\s*\.\s*", "", claim).strip()
    preamble = ""
    # "…을 포함하는 (것을 특징으로 하는) 압력센서." — a short subject at the very end
    m = re.search(r"(?:을|를)\s*포함하는\s*(?:것을\s*특징으로\s*하는\s*)?([^;,.]{1,40}?)\s*\.?\s*$", body)
    if not m:  # "…를 포함하는, 정전용량형 압력 센서." (subject after a comma)
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
            include: list[str] | None = None, resplit: bool = False) -> Path:
    from sklearn.feature_extraction.text import TfidfVectorizer

    det = json.loads((d / "details" / f"{target}.json").read_text(encoding="utf-8"))
    claim = claims_by_number(det.get("claims", [])).get(claim_no)
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
    chosen = pool[(pool["sim_rank"] <= k) | pool["examiner_cited"] | pool["user_included"]].copy()
    chosen["art_type"] = [_art_type(d, r, cutoff) for _, r in chosen.iterrows()]

    out = d / "charts" / f"{target}_c{claim_no}"
    out.mkdir(parents=True, exist_ok=True)
    els = split_elements(claim)
    old = out / "elements.json"
    if old.exists() and not resplit:  # keep a split the user corrected by hand
        prev = json.loads(old.read_text(encoding="utf-8"))
        if prev.get("target") == target and prev.get("claim_no") == claim_no and prev.get("elements"):
            els = prev["elements"]
    (out / "elements.json").write_text(json.dumps({"target": target, "claim_no": claim_no, "claim": claim,
                                                   "priority_date": cutoff, "elements": els},
                                                  ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "ELEMENTS.md").write_text(
        f"# 대상 청구항 — {target} 청구항 {claim_no} (기준일 {cutoff})\n\n> {claim}\n\n"
        "| 구성요소 | 내용 |\n|---|---|\n" + "".join(f"| {e['id']} | {e['text']} |\n" for e in els)
        + "\n구성요소 분할이 맞는지 확인하고, 필요하면 elements.json을 고친 뒤 `park chart`를 다시 실행하세요"
          " (고친 분할은 유지됩니다. 자동 분할로 되돌리려면 --resplit).\n", encoding="utf-8")
    chosen[["application_no", "title", "applicants", "application_date", "similarity", "sim_rank",
            "examiner_cited", "art_type"]].to_csv(out / "prior_art.csv", index=False, encoding="utf-8-sig")
    return out


def _art_type(d: Path, r, cutoff: str) -> str:
    """공지 문헌 (published before the reference date, 특허법 제29조 제1항) vs earlier-filed but later-published
    application (확대된 선출원, 제29조 제3항 — only the identical invention counts) vs unknown publication date."""
    pub = norm_date(r.get("publication_date", ""))
    if not pub:
        det = d / "details" / f"{r['application_no']}.json"
        if det.exists():
            pub = norm_date(json.loads(det.read_text(encoding="utf-8")).get("publication_date", ""))
    if not pub:
        return "공개일 미상"
    return "공지" if pub < cutoff else "확대된 선출원"


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
    pa_path = out / "prior_art.csv"
    allowed = set(pd.read_csv(pa_path, dtype=str)["application_no"]) if pa_path.exists() else set()
    art_type = (dict(zip(*[pd.read_csv(pa_path, dtype=str, keep_default_na=False)[c] for c in ("application_no", "art_type")]))
                if pa_path.exists() and "art_type" in pd.read_csv(pa_path, nrows=0).columns else {})
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
    from collections import Counter

    dup = Counter((str(o.get("prior_art", "")), o.get("element", "")) for o in rows)
    bad: set[tuple] = set()

    def fail(key, msg):
        errors.append(f"{key[0]}/{key[1]}: {msg}")
        bad.add(key)

    for o in rows:
        no, el = str(o.get("prior_art", "")), o.get("element", "")
        key = (no, el)
        if dup[key] > 1:
            fail(key, "judged more than once — keep exactly one row per document and element")
            continue
        if no == meta["target"]:
            fail(key, "the target itself cannot be prior art")
            continue
        if allowed and no not in allowed:
            fail(key, "not one of the documents in prior_art.csv")
            continue
        if el not in ids:
            fail(key, "unknown element")
        if o.get("status") not in STATUS:
            fail(key, f"status '{o.get('status')}' not in {sorted(STATUS)}")
        if o.get("status") == "미개시":
            continue
        loc, quote = str(o.get("location", "")), _squash(o.get("quote", ""))
        if no not in cand.index:
            fail(key, "not a candidate")
            continue
        para = re.search(r"\[?(\d{4})\]?", loc) if ("[" in loc or "단락" in loc) else None
        if para:
            from .fulltext import quote_in_paragraph

            sp = d / "description" / f"{no}.json"
            ok = sp.exists() and len(quote) >= 6 and quote_in_paragraph(
                json.loads(sp.read_text(encoding="utf-8")), para.group(1), o.get("quote", ""))
            if not ok:
                fail(key, f"quote not found in description paragraph {para.group(1)} (±1)")
            continue
        if "청구항" in loc:
            claims = load_claims(d, no)
            m = re.search(r"\d+", loc)
            src = claims.get(int(m.group(0))) if (claims and m) else None
        elif "요약" in loc:
            src = cand.loc[no, "abstract"]
        else:
            src = f"{cand.loc[no, 'title']} {cand.loc[no, 'abstract']}"
        if src is None or len(quote) < 6 or quote not in _squash(src):
            fail(key, f"quote not found verbatim in {loc or 'the document'}")
    ok_combos = []
    for c in combos:
        docs = [str(x) for x in c.get("combination", [])]
        wrong = [x for x in docs if x == meta["target"] or (allowed and x not in allowed)]
        if wrong:
            errors.append(f"combination {'+'.join(docs)}: {', '.join(wrong)} is the target or not in prior_art.csv")
        else:
            ok_combos.append(c)
    combos = ok_combos
    # conclusions use verified rows only
    chart = pd.DataFrame([o for o in rows if (str(o.get("prior_art", "")), o.get("element", "")) not in bad])
    chart.to_csv(out / "chart.csv", index=False, encoding="utf-8-sig")
    summary = {"target": meta["target"], "claim_no": meta["claim_no"], "priority_date": meta["priority_date"],
               "elements": meta["elements"], "summaries": summaries, "combinations": combos}
    if len(chart):
        disclosed = chart[chart["status"] == "개시"].groupby("prior_art")["element"].nunique()
        full = [no for no, n in disclosed.items() if n == len(ids)]
        # novelty (제29조 제1항) needs a document published before the reference date
        summary["fully_disclosed_by"] = [no for no in full if art_type.get(no, "공지") == "공지"]
        summary["fully_disclosed_earlier_application"] = [no for no in full if art_type.get(no) == "확대된 선출원"]
        summary["fully_disclosed_unknown_date"] = [no for no in full if art_type.get(no) == "공개일 미상"]
    summary["errors"] = len(errors)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary, errors
