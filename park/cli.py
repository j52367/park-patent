"""`park` command line — the deterministic half of PARK. Skills call these commands."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import __version__
from . import charts, checks, ingest as ING, report, stats
from .schema import CANDIDATE_COLUMNS, SCREENING_COLUMNS, conform, read_csv, write_csv

TECH_TREE_TEMPLATE = """# 기술 분류표 — <과제명>

코드는 반드시 백틱으로 감싸 첫 칸에 적습니다 (`park check`가 이 칸을 읽습니다).

| 코드 | 대분류 | 중분류 | 정의 | 포함 | 제외 |
|---|---|---|---|---|---|
| `A1` | | | | | |
"""

SEARCH_LOG_TEMPLATE = """# 검색 기록

- **데이터베이스**:
- **국가**:
- **기간**:
- **검색 시각**:

## 검색식과 결과
"""


def _append_log(d: Path, text: str) -> None:
    p = d / "SEARCH_LOG.md"
    if not p.exists():
        p.write_text(SEARCH_LOG_TEMPLATE, encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write("\n" + text.rstrip() + "\n")


class UserError(Exception):
    """A problem the user can fix; printed without a traceback."""


def _load(d: Path):
    if not (d / "candidates.csv").exists():
        raise UserError(f"{d / 'candidates.csv'} not found — run `park search` or `park ingest` first")
    cand = read_csv(d / "candidates.csv")
    sp = d / "screening.csv"
    screen = read_csv(sp) if sp.exists() else None
    return cand, screen


def _merge_candidates(d: Path, new_frames, aliases):
    from .normalize import load_aliases, merge_report

    frames = list(new_frames)
    if (d / "candidates.csv").exists():
        frames.insert(0, read_csv(d / "candidates.csv"))
    cand = ING.finalize(frames, aliases)
    rep = merge_report(cand["applicants_raw"], load_aliases(aliases))
    write_csv(rep, d / "applicant_merges.csv")
    if len(rep):
        print(f"{len(rep)} applicant names merged from several spellings -> review {d / 'applicant_merges.csv'}")
    return cand


# ---------------- commands ----------------
def cmd_init(a):
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    for name, body in (("TECH_TREE.md", TECH_TREE_TEMPLATE), ("SEARCH_LOG.md", SEARCH_LOG_TEMPLATE)):
        if not (d / name).exists():
            (d / name).write_text(body, encoding="utf-8")
    print(f"initialised {d}")


def cmd_ingest(a):
    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    frames, lines = [], []
    for f in a.files:
        df, mapping = ING.ingest(f, as_of=a.as_of, aliases_path=a.aliases)
        frames.append(df)
        lines.append(f"- CSV 반입 `{Path(f).name}`: {len(df):,}행 · 인식한 열 {mapping}")
        if a.show_mapping:
            print(f"{f}: {mapping}")
    before = len(read_csv(d / "candidates.csv")) if (d / "candidates.csv").exists() else 0
    cand = _merge_candidates(d, frames, a.aliases)
    write_csv(cand, d / "candidates.csv")
    _append_log(d, f"### {datetime.now():%Y-%m-%d %H:%M} 반입\n" + "\n".join(lines)
                + f"\n- candidates.csv: {before:,} → {len(cand):,}건 (중복 제거 후)")
    print(f"candidates.csv: {before} -> {len(cand)} rows")


def cmd_search(a):
    from .kipris import KiprisClient, KiprisError, items_to_candidates

    d = Path(a.out)
    d.mkdir(parents=True, exist_ok=True)
    client = KiprisClient(db_path=a.cache)
    used_before = client.calls_this_month()
    if a.count_only:
        try:
            total, _ = client.search_page(a.word, 1, 1)
        except KiprisError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        used = client.calls_this_month() - used_before
        _append_log(d, f"### {datetime.now():%Y-%m-%d %H:%M} 건수 확인\n- 검색식: `{a.word}` → 전체 {total:,}건 (호출 {used}회)")
        print(f"total={total} new_calls={used} (count only, candidates.csv unchanged)")
        return 0
    try:
        total, items = client.search(a.word, max_docs=a.max, page_size=a.page_size, budget=a.budget)
    except KiprisError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    new = items_to_candidates(items)
    before = len(read_csv(d / "candidates.csv")) if (d / "candidates.csv").exists() else 0
    cand = _merge_candidates(d, [new], a.aliases)
    write_csv(cand, d / "candidates.csv")
    used = client.calls_this_month() - used_before
    _append_log(d, f"### {datetime.now():%Y-%m-%d %H:%M} KIPRIS 검색\n- 검색식: `{a.word}`\n"
                   f"- 전체 {total:,}건 중 {len(items):,}건 수집 (상한 {a.max:,}) · 실제 API 호출 {used}회\n"
                   f"- candidates.csv: {before:,} → {len(cand):,}건 (중복 제거 후)")
    print(f"total={total} fetched={len(items)} new_calls={used} candidates={len(cand)}")
    if total > len(items):
        print(f"note: {total - len(items)} results not fetched (raise --max if needed)")


def cmd_quota(a):
    from .kipris import KiprisClient
    import os

    c = KiprisClient(db_path=a.cache)
    limit = int(os.environ.get("KIPRIS_MONTHLY_LIMIT", "1000"))
    used = c.calls_this_month()
    print(f"KIPRIS calls this month: {used} / {limit}  (remaining {max(limit - used, 0)})")


def _short(name: str, n: int) -> str:
    return name if len(name) <= n else name[: n - 1] + "…"


def cmd_map(a):
    d = Path(a.dir)
    cand, screen = _load(d)
    as_of = a.as_of or max([v for v in cand["status_as_of"] if v], default="") or date.today().isoformat()
    frames = {}
    for f in (d / "screening").glob("tail_frame_r*.txt") if (d / "screening").exists() else []:
        frames[int(re.search(r"r(\d+)", f.stem).group(1))] = set(f.read_text(encoding="utf-8").split())
    s = stats.compute(cand, screen, as_of=as_of, top_n=a.top, frames=frames)
    tt = d / "TECH_TREE.md"
    if tt.exists():
        s["tech_labels"] = checks.tech_labels(tt.read_text(encoding="utf-8"))
    m = d / "map"
    m.mkdir(exist_ok=True)
    (m / "stats.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    svgs = {
        "yearly.svg": charts.bar_by_year(s["yearly"], "연도별 출원"),
        "applicants.svg": charts.hbar([(_short(r["name"], 28) + (f" ({r['nationality']})" if r.get("nationality") else ""),
                                        r["count"]) for r in s["applicants_top"]], "주요 출원인", max_label=40),
        "ipc.svg": charts.hbar([(r["code"], r["count"]) for r in s["ipc_main"]], "IPC 분포"),
        "growth.svg": charts.growth_path(s["growth"], "기술 성장 단계"),
    }
    if len(s.get("country", [])) > 1:
        svgs["country.svg"] = charts.hbar([(r["country"], r["count"]) for r in s["country"]], "국가별 출원")
        t = s["country_by_year"]
        svgs["country_by_year.svg"] = charts.heatmap(t["countries"], t["years"], t["values"], "국가 × 연도")
        if "country_by_tech" in s:
            t = s["country_by_tech"]
            svgs["country_by_tech.svg"] = charts.heatmap(t["countries"], t["codes"], t["values"], "국가 × 기술 분류")
    if "tech_by_year" in s:
        t = s["tech_by_year"]
        svgs["tech_by_year.svg"] = charts.heatmap(t["codes"], t["years"], t["values"], "기술 분류 × 연도")
        t = s["applicant_by_tech"]
        svgs["applicant_by_tech.svg"] = charts.heatmap(t["applicants"], t["codes"], t["values"], "출원인 × 기술 분류")
    # remove charts from earlier runs so the report can never show a stale one
    for old in ("yearly.svg", "applicants.svg", "ipc.svg", "growth.svg", "tech_by_year.svg", "applicant_by_tech.svg",
                "country.svg", "country_by_year.svg", "country_by_tech.svg"):
        (m / old).unlink(missing_ok=True)
    for name, svg in svgs.items():
        if svg:
            (m / name).write_text(svg, encoding="utf-8")
    meta = s["meta"]
    print(f"counted {meta['n_counted']} of {meta['n_candidates']} ({meta['basis']}); as_of {meta['as_of']}; "
          f"unpublished after {meta['unpublished_cutoff']} -> {m}")


def _doc_block(r) -> str:
    claims = str(r.get("independent_claims", "") or "").strip()
    return (f"### {r['application_no']}\n- 명칭: {r['title']}\n- 출원인: {r['applicants']}\n"
            f"- IPC: {r['ipc']}\n- 출원일: {r['application_date']} · 상태: {r['status']}\n- 요약: {r['abstract']}\n"
            + (f"- 독립청구항: {claims[:1500]}\n" if claims else ""))


def _ranked(d: Path, cand):
    """Candidates in rank order when rank.csv exists (unranked ones last), else file order."""
    rp = d / "rank.csv"
    if not rp.exists():
        return cand
    r = read_csv(rp)[["application_no", "rank"]]
    out = cand.merge(r, on="application_no", how="left")
    out["_r"] = pd.to_numeric(out["rank"], errors="coerce").fillna(10 ** 9)
    return out.sort_values("_r", kind="stable").drop(columns=["_r"])


def cmd_batches(a):
    """Split unscreened candidates into Markdown batches for the screening skill (or subagents)."""
    d = Path(a.dir)
    cand, screen = _load(d)
    done = set()
    jdir = d / "screening" / "done"
    if jdir.exists():
        for f in jdir.glob("*.jsonl"):
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    done.add(str(json.loads(line).get("application_no", "")))
    if screen is not None:
        done |= set(screen["application_no"])
    cand = _ranked(d, cand)
    if a.recheck_codes:
        # re-judge documents already judged valid under codes whose definition changed
        if screen is None:
            raise UserError("--recheck-codes needs screening.csv")
        codes = {c.strip() for c in a.recheck_codes.split(",") if c.strip()}
        ids = set(screen[(screen["relevance"] == "valid") & screen["tech_code"].isin(codes)]["application_no"])
        todo = cand[cand["application_no"].isin(ids)]
    else:
        if (a.top or a.next) and "rank" not in cand.columns:
            raise UserError("--top/--next need rank.csv — run `park rank` first")
        if a.top:
            cand = cand[pd.to_numeric(cand["rank"], errors="coerce") <= a.top]
        todo = cand[~cand["application_no"].isin(done)]
        if a.next:
            todo = todo.head(a.next)
        if (a.top or a.next) and len(todo):
            print(f"lowest rank included: {int(pd.to_numeric(todo['rank']).max())} "
                  "(use it as --below-rank for the next tail sample)")
    prefix = a.prefix
    if (d / "screening" / "done").exists() and any((d / "screening" / "done").glob(f"{prefix}_*.jsonl")) and not a.force:
        raise UserError(f"screening/done already has {prefix}_*.jsonl — use a new --prefix (e.g. r2) so results are not overwritten")
    tdir = d / "screening" / "todo"
    tdir.mkdir(parents=True, exist_ok=True)
    for old in tdir.glob(f"{prefix}_*.md"):
        old.unlink()
    n = 0
    for i in range(0, len(todo), a.size):
        n += 1
        part = todo.iloc[i:i + a.size]
        body = f"# {prefix}_{n:03d} — {len(part)}건\n\n" + "\n".join(_doc_block(r) for _, r in part.iterrows())
        (tdir / f"{prefix}_{n:03d}.md").write_text(body, encoding="utf-8")
    what = "to re-check" if a.recheck_codes else "unscreened"
    print(f"{len(todo)} {what} of {len(cand)} -> {n} batches {prefix}_###.md in {tdir}")


def cmd_merge_screening(a):
    """Merge screening/done/*.jsonl (one JSON object per line, SCREENING_COLUMNS keys) into screening.csv."""
    import pandas as pd

    d = Path(a.dir)
    rows = []
    # newer files win: a re-check written later overrides the first judgement whatever its name
    files = sorted((d / "screening" / "done").glob("*.jsonl"), key=lambda f: (f.stat().st_mtime, f.name))
    for f in files:
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  ERROR {f.name}:{n}: invalid JSON ({e})")
                continue
            obj["application_no"] = str(obj.get("application_no", ""))
            rows.append(obj)
    new = conform(pd.DataFrame(rows), SCREENING_COLUMNS).astype(str).replace({"nan": "", "None": ""})
    if (d / "screening.csv").exists():
        old = read_csv(d / "screening.csv")
        new = pd.concat([old, new], ignore_index=True)
    # a document drawn into a tail sample stays part of that sample after it is re-judged
    tags = {}
    for no, by in zip(new["application_no"], new["screened_by"]):
        m = re.search(r"tail-audit(?:-r\d+)?", str(by))
        if m:
            tags.setdefault(no, m.group(0))
    # last judgement for an application wins (re-screening overrides)
    new = new.drop_duplicates(subset="application_no", keep="last").copy()
    new["screened_by"] = [b if ("tail-audit" in str(b) or n not in tags) else f"{b}:{tags[n]}"
                          for n, b in zip(new["application_no"], new["screened_by"])]
    write_csv(conform(new, SCREENING_COLUMNS), d / "screening.csv")
    print(f"screening.csv: {len(new)} rows")
    return cmd_check(argparse.Namespace(dir=a.dir, max_errors=30))


def cmd_audit_sample(a):
    """Random sample of noise-labelled docs for an independent second look (false-negative check)."""
    d = Path(a.dir)
    cand, screen = _load(d)
    if a.unscreened or a.below_rank:
        screened = set(screen["application_no"]) if screen is not None else set()
        rest = cand[~cand["application_no"].isin(screened)]
        if a.below_rank:
            rest = _ranked(d, rest)
            rest = rest[pd.to_numeric(rest["rank"], errors="coerce").fillna(10 ** 9) > a.below_rank]
        k = min(a.n, len(rest))
        sample = rest.sample(n=k, random_state=a.seed) if k else rest
        tdir = d / "screening" / "todo"
        tdir.mkdir(parents=True, exist_ok=True)
        tag = "tail-audit" if a.round <= 1 else f"tail-audit-r{a.round}"
        name = "tail_audit" if a.round <= 1 else f"tail_audit_r{a.round}"
        body = (f"# {name} — 미선별 {len(rest)}건 중 무작위 {k}건 (seed {a.seed})\n\n"
                f"다른 배치와 똑같이 판정하세요. screened_by 뒤에 ':{tag}'를 붙입니다.\n"
                f"추정 미선별 유효 건수 = (이 표본의 유효 수 / {k}) × {len(rest)}\n\n"
                + "\n".join(_doc_block(r) for _, r in sample.iterrows()))
        (tdir / f"{name}.md").write_text(body, encoding="utf-8")
        # remember which documents the sample describes, so the estimate is applied to this frame only
        (d / "screening" / f"tail_frame_r{max(a.round, 1)}.txt").write_text(
            "\n".join(rest["application_no"]), encoding="utf-8")
        print(f"wrote {tdir / (name + '.md')} ({k} of {len(rest)} unscreened docs)")
        return 0
    if screen is None:
        print("no screening.csv yet")
        return 1
    noise = screen[screen["relevance"] == "noise"]
    n_valid = int((screen["relevance"] == "valid").sum())
    k = min(a.n, len(noise))
    sample = noise.sample(n=k, random_state=a.seed) if k else noise
    rows = cand[cand["application_no"].isin(sample["application_no"])]
    tdir = d / "screening" / "todo"
    tdir.mkdir(parents=True, exist_ok=True)
    census = k == len(noise)
    body = (f"# noise_audit — 노이즈 {len(noise)}건 중 {'전수' if census else '무작위'} {k}건 (seed {a.seed})\n\n"
            "앞선 판정을 보지 말고 TECH_TREE.md만 기준으로 다시 판단하세요. 다른 배치와 같은 형식으로 "
            "screening/done/noise_audit.jsonl에 쓰고, screened_by 뒤에 ':noise-audit'를 붙입니다.\n"
            "병합 후 `park map`이 노이즈 누락률과 추정 거짓음성률을 계산합니다.\n\n"
            "- 노이즈 누락률 r = 유효로 뒤집힌 수 / 표본 수\n"
            f"- 추정 누락 건수 = r × {len(noise)} (노이즈 전체)\n"
            f"- 추정 거짓음성률 = 추정 누락 건수 / ({n_valid} + 추정 누락 건수)  ← 유효 판정 {n_valid}건 기준\n\n"
            + "\n".join(_doc_block(r) for _, r in rows.iterrows()))
    (tdir / "noise_audit.md").write_text(body, encoding="utf-8")
    (d / "AUDIT_SAMPLE.md").write_text(body, encoding="utf-8")  # kept for older instructions
    print(f"wrote {tdir / 'noise_audit.md'} ({k} of {len(noise)} noise docs{', census' if census else ''})")


def cmd_rank(a):
    from . import rank as R

    d = Path(a.dir)
    cand, screen = _load(d)
    if a.learn:
        from .learn import learn_rank

        if screen is None:
            raise UserError("--learn needs screening.csv (judge some batches first)")
        r, ev = learn_rank(cand, screen)
        write_csv(r, d / "rank.csv")
        (d / "rank_eval.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
        cv, tail = ev["cv_all"], ev["cv_tail"]
        print(f"learned from {ev['labelled']} judgements ({ev['valid']} valid); cross-validated AUC {cv['auc']}, "
              f"AP {cv['ap']}" + (f"; on tail samples AUC {tail['auc']}, AP {tail['ap']}" if tail else ""))
        print(f"ranked {len(r)} candidates -> {d / 'rank.csv'} (scores order documents; they are not calibrated)")
        return 0
    tt = d / "TECH_TREE.md"
    if not tt.exists():
        raise UserError(f"{tt} not found — rank needs the technology classification table")
    r = R.rank(cand, tt.read_text(encoding="utf-8"), a.terms)
    r["method"] = "similarity"
    write_csv(r, d / "rank.csv")
    print(f"ranked {len(r)} candidates -> {d / 'rank.csv'} (top score {r['rank_score'].iloc[0]:.3f})")


def cmd_shortlist(a):
    from .enrich import shortlist

    d = Path(a.dir)
    cand, screen = _load(d)
    if screen is None:
        raise UserError("shortlist needs screening.csv")
    rank = read_csv(d / "rank.csv") if (d / "rank.csv").exists() else None
    s = shortlist(cand, screen, rank, [f for f in (a.focal or "").split(",")], n=a.n, per_code=a.per_code)
    write_csv(s, d / "shortlist.csv")
    print(f"shortlist.csv: {len(s)} documents " + str(s["reason"].str.split("-").str[0].value_counts().to_dict()))


def cmd_enrich(a):
    from .enrich import enrich
    from .kipris import KiprisClient, KiprisError

    d = Path(a.dir)
    src = d / a.source
    if not src.exists():
        raise UserError(f"{src} not found — run `park shortlist` first (or pass --source)")
    numbers = read_csv(src)["application_no"].tolist()
    client = KiprisClient(db_path=a.cache)
    try:
        df = enrich(client, numbers, d, budget=a.budget)
    except KiprisError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    write_csv(df, d / "enrich.csv")
    print(f"enrich.csv: {len(df)} of {len(numbers)} documents · new API calls {client.network_calls} · "
          f"with claims {int((df['claim_count'].astype(int) > 0).sum()) if len(df) else 0}")


def cmd_review_batches(a):
    from . import review

    d = Path(a.dir)
    for f in ("shortlist.csv", "enrich.csv"):
        if not (d / f).exists():
            raise UserError(f"{d / f} not found — run `park shortlist` and `park enrich` first")
    n = review.make_batches(d, a.size)
    print(f"{n} key-review batches in {d / 'review' / 'todo'}")


def cmd_merge_review(a):
    from . import review

    d = Path(a.dir)
    df, errors = review.merge(d)
    print(f"key_review.csv: {len(df)} rows {df['importance'].value_counts().to_dict() if len(df) else {}}")
    for e in errors[:30]:
        print(f"  ERROR: {e}")
    print("OK" if not errors else f"FAILED ({len(errors)} errors)")
    return 1 if errors else 0


def cmd_swot(a):
    from . import swot

    d = Path(a.dir)
    cand, screen = _load(d)
    if screen is None:
        raise UserError("swot needs screening.csv")
    kr = read_csv(d / "key_review.csv") if (d / "key_review.csv").exists() else None
    en = read_csv(d / "enrich.csv") if (d / "enrich.csv").exists() else None
    tt = d / "TECH_TREE.md"
    labels = checks.tech_labels(tt.read_text(encoding="utf-8")) if tt.exists() else {}
    as_of = a.as_of or max([v for v in cand["status_as_of"] if v], default="") or date.today().isoformat()
    s = swot.compute(cand, screen, a.focal, [c.strip() for c in a.vs.split(",") if c.strip()], as_of=as_of,
                     window=a.window, key_review=kr, enrich=en, tech_labels=labels)
    (d / "swot_stats.json").write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding="utf-8")
    apps = s["applicants"]
    codes = [r["code"] for r in s["codes"]]
    m = d / "map"
    m.mkdir(exist_ok=True)
    (m / "swot_matrix.svg").write_text(charts.heatmap([_short(x["name"], 18) for x in apps], codes,
                                                      [[x["by_code"][c] for c in codes] for x in apps],
                                                      "초점 출원인과 경쟁 출원인 × 기술 분류"), encoding="utf-8")
    h = s["hints"]
    print(f"swot_stats.json: focal {a.focal} ({apps[0]['n']} valid) vs {len(apps) - 1} competitors · "
          f"hints S{len(h['S'])} W{len(h['W'])} O{len(h['O'])} T{len(h['T'])}")


def _resolve_examiner(client, d: Path, target: str) -> list[str]:
    """KR publication numbers cited by the examiner → application numbers (1 cached search call each)."""
    det = json.loads((d / "details" / f"{target}.json").read_text(encoding="utf-8"))
    apps = []
    for p in det.get("prior_art", []):
        num = re.sub(r"\D", "", p.get("number", ""))
        if not p.get("number", "").upper().startswith("KR") or len(num) != 13:
            continue
        _, items = client.search_page(num, 1, 5)
        for it in items:
            pubs = {re.sub(r"\D", "", str(v)) for k, v in it.get("_raw", {}).items()
                    if "Number" in k and "Application" not in k}  # publication/registration numbers only
            if num in pubs:
                apps.append(it["application_no"])
                break
    return apps


def cmd_chart(a):
    from . import chart
    from .enrich import enrich
    from .kipris import KiprisClient

    d = Path(a.dir)
    client = KiprisClient(db_path=a.cache)
    if not (d / "details" / f"{a.target}.json").exists():
        enrich(client, [a.target], d, budget=2)
    examiner = _resolve_examiner(client, d, a.target) if a.examiner else []
    out = chart.prepare(d, a.target, a.claim, k=a.k, examiner_apps=examiner,
                        include=[x.strip() for x in a.include.split(",") if x.strip()], resplit=a.resplit)
    pa = read_csv(out / "prior_art.csv")
    missing = [n for n in pa["application_no"] if not (d / "fulltext" / f"{n}.txt").exists()]
    if missing and a.fetch_claims:
        enrich(client, missing, d, budget=a.budget)
    n_spec = 0
    if a.fulltext:
        from . import fulltext

        for no in pa["application_no"]:
            if fulltext.fetch(client, no, d) is not None:
                n_spec += 1
    chart.make_todo(d, out)
    hit = pa[pa["examiner_cited"] == "True"]
    print(f"{out}: {len(pa)} prior-art documents ({len(missing)} fetched claims"
          + (f", {n_spec} specifications" if a.fulltext else "") + f") · API calls {client.network_calls}")
    for _, r in hit.iterrows():
        print(f"  examiner-cited {r['application_no']} ranked {r['sim_rank']} by similarity")


def cmd_merge_chart(a):
    from . import chart

    d = Path(a.dir)
    out = d / "charts" / f"{a.target}_c{a.claim}"
    summary, errors = chart.merge(d, out)
    print(f"{out / 'chart.csv'}: fully disclosed by {summary.get('fully_disclosed_by', [])} · "
          f"{len(summary['combinations'])} combinations")
    for e in errors[:30]:
        print(f"  ERROR: {e}")
    print("OK" if not errors else f"FAILED ({len(errors)} errors)")
    return 1 if errors else 0


def cmd_check(a):
    d = Path(a.dir)
    cand, screen = _load(d)
    failed = False
    if screen is not None:
        screen = conform(screen, SCREENING_COLUMNS)
        tt = d / "TECH_TREE.md"
        res = checks.check_screening(cand, screen, tt.read_text(encoding="utf-8") if tt.exists() else None,
                                     checks.load_fulltext(d))
        print(f"screening: {res.stats}")
        for w in res.warnings:
            print(f"  warning: {w}")
        for e in res.errors[: a.max_errors]:
            print(f"  ERROR: {e}")
        if len(res.errors) > a.max_errors:
            print(f"  ... {len(res.errors) - a.max_errors} more errors")
        failed |= not res.ok
    else:
        print("screening: none yet")
    notes = d / "REPORT_NOTES.md"
    if notes.exists():
        hits = checks.lint_numbers(notes.read_text(encoding="utf-8"))
        for h in hits:
            print(f"  REPORT_NOTES {h}")
        failed |= bool(hits)
    print("OK" if not failed else "FAILED")
    return 1 if failed else 0


def cmd_report(a):
    out, problems = report.build(a.dir, a.title)
    for p in problems:
        print(f"  problem: {p}")
    print(f"wrote {out}")
    return 1 if (problems and a.strict) else 0


def _skills_source() -> Path | None:
    """Skills shipped in the wheel (park/skills) or, in a git checkout, the repo's skills/ folder."""
    for cand in (Path(__file__).resolve().parent / "skills", Path(__file__).resolve().parent.parent / "skills"):
        if cand.is_dir() and any(cand.glob("*/SKILL.md")):
            return cand
    try:
        from importlib.resources import files

        p = Path(str(files("park.skills")))
        if any(p.glob("*/SKILL.md")):
            return p
    except (ModuleNotFoundError, TypeError):
        pass
    return None


def cmd_install_skills(a):
    """Copy skills/ (each skill + shared-references) into a Claude Code skills directory."""
    import shutil

    src = _skills_source()
    if src is None:
        print("skills folder not found (neither in the installed package nor next to it)", file=sys.stderr)
        return 2
    dest = Path.home() / ".claude" / "skills" if a.user else Path(a.project) / ".claude" / "skills"
    dest.mkdir(parents=True, exist_ok=True)
    for item in sorted(src.iterdir()):
        if item.is_dir():
            target = dest / item.name
            if target.exists():
                if not a.force:
                    print(f"skip {target} (exists; use --force to overwrite)")
                    continue
                shutil.rmtree(target)
            shutil.copytree(item, target)
            print(f"installed {target}")
    return 0


def cmd_demo(a):
    from . import demo

    d = demo.write_project(a.out)
    print(f"[1/4] synthetic project -> {d}")
    cmd_map(argparse.Namespace(dir=str(d), as_of=demo.AS_OF, top=10))
    print("[2/4] map done")
    rc = cmd_check(argparse.Namespace(dir=str(d), max_errors=20))
    print("[3/4] checks", "passed" if rc == 0 else "FAILED")
    out, problems = report.build(d, "배터리 관리 시스템(BMS) 특허 동향 — 합성 데모")
    for p in problems:
        print(f"  problem: {p}")
    print(f"[4/4] report -> {out}")
    return 1 if (rc or problems) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="park", description="PARK — Patent Analysis Research Kit (deterministic tools)")
    p.add_argument("--version", action="version", version=f"park {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="create an analysis directory with templates")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("ingest", help="import CSV/Excel patent lists into candidates.csv")
    s.add_argument("files", nargs="+")
    s.add_argument("--out", required=True, help="analysis directory")
    s.add_argument("--as-of", default="", help="date the status column was observed (YYYY-MM-DD)")
    s.add_argument("--aliases", default=None, help="aliases.csv (alias,canonical) for applicant names")
    s.add_argument("--show-mapping", action="store_true")
    s.set_defaults(fn=cmd_ingest)

    s = sub.add_parser("search", help="KIPRIS Plus search into candidates.csv (cached, call-counted)")
    s.add_argument("--word", required=True, help="KIPRIS free-search expression, e.g. 'IPC=[G06N] * AD=[20190101~20191231]'")
    s.add_argument("--out", required=True)
    s.add_argument("--max", type=int, default=500)
    s.add_argument("--page-size", type=int, default=100)
    s.add_argument("--budget", type=int, default=None, help="max API calls for this search")
    s.add_argument("--count-only", action="store_true", help="1 call: report the total hit count, write nothing")
    s.add_argument("--aliases", default=None)
    s.add_argument("--cache", default=".park/kipris_cache.sqlite")
    s.set_defaults(fn=cmd_search)

    s = sub.add_parser("quota", help="KIPRIS calls used this month")
    s.add_argument("--cache", default=".park/kipris_cache.sqlite")
    s.set_defaults(fn=cmd_quota)

    s = sub.add_parser("map", help="compute stats.json and SVG charts")
    s.add_argument("dir")
    s.add_argument("--as-of", default="")
    s.add_argument("--top", type=int, default=15)
    s.set_defaults(fn=cmd_map)

    s = sub.add_parser("batches", help="split unscreened candidates into Markdown batches")
    s.add_argument("dir")
    s.add_argument("--size", type=int, default=40)
    s.add_argument("--top", type=int, default=0, help="only candidates ranked within the top N (needs rank.csv)")
    s.add_argument("--next", type=int, default=0, help="the next N unscreened candidates in rank order (needs rank.csv)")
    s.add_argument("--prefix", default="batch", help="batch file prefix; use a new one per screening round (r2, recheck...)")
    s.add_argument("--recheck-codes", default="", help="re-judge docs already valid under these codes, e.g. C1,W1,W2")
    s.add_argument("--force", action="store_true", help="allow a prefix that already has results")
    s.set_defaults(fn=cmd_batches)

    s = sub.add_parser("merge-screening", help="merge screening/done/*.jsonl into screening.csv and check it")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_merge_screening)

    s = sub.add_parser("shortlist", help="pick valid documents for phase-2 review (focal applicant + per-code best + score)")
    s.add_argument("dir")
    s.add_argument("--n", type=int, default=300)
    s.add_argument("--per-code", type=int, default=12)
    s.add_argument("--focal", default="", help="comma-separated applicant display names to include in full")
    s.set_defaults(fn=cmd_shortlist)

    s = sub.add_parser("enrich", help="fetch claims, cited prior art, legal status and forward citations (2 calls/doc)")
    s.add_argument("dir")
    s.add_argument("--source", default="shortlist.csv")
    s.add_argument("--budget", type=int, default=None, help="max new API calls")
    s.add_argument("--cache", default=".park/kipris_cache.sqlite")
    s.set_defaults(fn=cmd_enrich)

    s = sub.add_parser("review-batches", help="batches of shortlisted docs with independent claims + signals")
    s.add_argument("dir")
    s.add_argument("--size", type=int, default=15)
    s.set_defaults(fn=cmd_review_batches)

    s = sub.add_parser("merge-review", help="merge review/done/*.jsonl into key_review.csv and verify claim quotes")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_merge_review)

    s = sub.add_parser("swot", help="patent-based SWOT inputs for a focal applicant vs competitors (swot_stats.json)")
    s.add_argument("dir")
    s.add_argument("--focal", required=True, help="applicant display name as in the report")
    s.add_argument("--vs", default="", help="comma-separated competitor display names")
    s.add_argument("--window", type=int, default=5, help="years per comparison window (recent vs previous)")
    s.add_argument("--as-of", default="")
    s.set_defaults(fn=cmd_swot)

    s = sub.add_parser("chart", help="claim chart: split a claim into elements and pick the closest earlier documents")
    s.add_argument("dir")
    s.add_argument("--target", required=True, help="application number of the claim to chart")
    s.add_argument("--claim", type=int, default=1)
    s.add_argument("--k", type=int, default=8, help="most similar earlier documents to chart")
    s.add_argument("--examiner", action="store_true", help="also include KR documents the examiner cited (search calls)")
    s.add_argument("--include", default="", help="comma-separated application numbers to chart in any case")
    s.add_argument("--resplit", action="store_true", help="discard a hand-edited elements.json and split the claim again")
    s.add_argument("--fetch-claims", action="store_true", help="fetch claims of prior-art documents (2 calls each)")
    s.add_argument("--fulltext", action="store_true",
                   help="download specification PDFs and add the most relevant paragraphs (1-2 calls + 1 download each)")
    s.add_argument("--budget", type=int, default=40)
    s.add_argument("--cache", default=".park/kipris_cache.sqlite")
    s.set_defaults(fn=cmd_chart)

    s = sub.add_parser("merge-chart", help="verify chart quotes and summarise (charts/<target>_c<n>/done.jsonl)")
    s.add_argument("dir")
    s.add_argument("--target", required=True)
    s.add_argument("--claim", type=int, default=1)
    s.set_defaults(fn=cmd_merge_chart)

    s = sub.add_parser("rank", help="pre-rank candidates by similarity to TECH_TREE.md (screen in this order)")
    s.add_argument("dir")
    s.add_argument("--terms", default="", help="extra keywords that describe the target technology")
    s.add_argument("--learn", action="store_true",
                   help="rank by a model trained on screening.csv judgements (needs scikit-learn)")
    s.set_defaults(fn=cmd_rank)

    s = sub.add_parser("audit-sample", help="sample noise-labelled docs for a false-negative re-check")
    s.add_argument("dir")
    s.add_argument("--n", type=int, default=30)
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--unscreened", action="store_true",
                   help="sample docs never screened (e.g. below the --top cut) to estimate what the cut missed")
    s.add_argument("--below-rank", type=int, default=0, help="with rank.csv: sample only unscreened docs ranked below N")
    s.add_argument("--round", type=int, default=1, help="tail sample round; only the latest round is used for estimates")
    s.set_defaults(fn=cmd_audit_sample)

    s = sub.add_parser("check", help="validate screening evidence and report numbers")
    s.add_argument("dir")
    s.add_argument("--max-errors", type=int, default=30)
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("report", help="build REPORT.html")
    s.add_argument("dir")
    s.add_argument("--title", default=None)
    s.add_argument("--strict", action="store_true", help="exit 1 if placeholders or typed numbers are found")
    s.set_defaults(fn=cmd_report)

    s = sub.add_parser("install-skills", help="copy PARK skills into .claude/skills")
    g = s.add_mutually_exclusive_group()
    g.add_argument("--user", action="store_true", help="~/.claude/skills (all projects)")
    g.add_argument("--project", default=".", help="<project>/.claude/skills (default: current dir)")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_install_skills)

    s = sub.add_parser("demo", help="synthetic end-to-end demo (no API key needed)")
    s.add_argument("--out", default="analysis/demo")
    s.set_defaults(fn=cmd_demo)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args) or 0
    except (UserError, FileNotFoundError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
