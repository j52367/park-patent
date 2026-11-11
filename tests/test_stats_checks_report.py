import json

import pandas as pd

from park import checks, report, stats
from park.cli import main
from park.schema import CANDIDATE_COLUMNS, SCREENING_COLUMNS, conform, read_csv


def _cand(rows):
    return conform(pd.DataFrame(rows), CANDIDATE_COLUMNS)


def test_unpublished_window_and_full_counting():
    c = _cand([
        {"application_no": "1", "application_date": "2020-05-01", "applicants": "A|B", "ipc_main": "G06N", "status": "등록"},
        {"application_no": "2", "application_date": "2024-02-01", "applicants": "A", "ipc_main": "G06N", "status": "공개"},
    ])
    s = stats.compute(c, None, as_of="2025-06-30")
    assert s["meta"]["unpublished_cutoff"] == "2023-12-30"
    flags = {r["year"]: r["incomplete"] for r in s["yearly"]}
    assert flags[2020] is False and flags[2024] is True
    assert flags[2023] is False  # only 1 day of 2023 falls inside the window (< INCOMPLETE_MIN_DAYS)
    top = {a["name"]: a["count"] for a in s["applicants_top"]}
    assert top == {"A": 2, "B": 1}
    assert s["meta"]["basis"].startswith("all-candidates")


def test_months_before_end_of_month():
    from datetime import date
    assert stats._months_before(date(2025, 8, 31), 18) == date(2024, 2, 29)


TREE = "| 코드 | 대분류 |\n|---|---|\n| `A1` | x |\n"


def _screen(rows):
    return conform(pd.DataFrame(rows), SCREENING_COLUMNS)


def _row(**kw):
    base = {"application_no": "1", "relevance": "valid", "tech_code": "A1", "evidence_level": "provisional",
            "evidence_location": "요약", "evidence_quote": "셀 전압을  측정하여 추정"}
    return _screen([{**base, **kw}])


def _errs(c, s, fulltext=None):
    return " ".join(checks.check_screening(c, s, TREE, fulltext).errors)


def test_check_screening_catches_fake_quotes_and_bad_codes():
    c = _cand([{"application_no": "1", "title": "배터리 SOC 추정 장치", "abstract": "셀 전압을 측정하여 추정한다."}])
    assert checks.check_screening(c, _row(), TREE).ok  # whitespace differences are tolerated
    errs = _errs(c, _row(tech_code="Z9", evidence_level="confirmed", evidence_quote="셀 전류를 측정하여 추정"))
    assert "Z9" in errs and "confirmed" in errs and "not found verbatim" in errs


def test_evidence_check_cannot_be_bypassed():
    c = _cand([{"application_no": "1", "title": "배터리 SOC 추정 장치", "abstract": "셀 전압을 측정하여 추정한다."}])
    assert "no evidence_quote" in _errs(c, _row(evidence_quote="   "))       # whitespace-only quote
    assert "too short" in _errs(c, _row(evidence_quote="셀"))                # trivially matching quote
    assert "not found verbatim" in _errs(c, _row(evidence_location="명칭"))  # quote is from the abstract
    assert "needs full text" in _errs(c, _row(evidence_location="청구항 1"))  # no full text available
    full = {"1": "청구항 1. 셀 전압을 측정하여 추정하는 방법"}
    assert checks.check_screening(c, _row(evidence_location="청구항 1", evidence_level="confirmed"), TREE, full).ok


def test_empty_screening_counts_zero_not_everything():
    c = _cand([{"application_no": "1", "application_date": "2020-01-01", "applicants": "A"}])
    s = stats.compute(c, _screen([]), as_of="2025-01-01")
    assert s["meta"]["basis"] == "valid" and s["meta"]["n_counted"] == 0
    assert s["meta"]["application_date_min"] == "" and s["yearly"] == []


def test_reimport_preserves_status_and_observation_date(tmp_path):
    from park import ingest as ING
    from park.schema import write_csv

    first = _cand([{"application_no": "1020190012345", "title": "t", "applicants_raw": "가람에너지(주)",
                    "applicants": "가람에너지(주)", "status": "등록", "status_as_of": "2025-01-01",
                    "source": "kipris-api"}])
    p = tmp_path / "candidates.csv"
    write_csv(first, p)
    again, mapping = ING.ingest(p)  # PARK's own file has both applicants and applicants_raw
    assert mapping["applicants_raw"] == "applicants_raw" and again.iloc[0]["source"] == "kipris-api"
    older = tmp_path / "old.csv"
    older.write_text("출원번호,발명의명칭,법적상태\n1020190012345,t,공개\n", encoding="utf-8")
    titles_only = tmp_path / "t.csv"
    titles_only.write_text("출원번호,발명의명칭\n1020190012345,새 제목\n", encoding="utf-8")
    merged = ING.finalize([again, ING.ingest(older, as_of="2020-01-01")[0], ING.ingest(titles_only)[0]])
    r = merged.iloc[0]
    assert r["status"] == "등록" and r["status_as_of"] == "2025-01-01"  # older snapshot / missing status lose
    assert r["title"] == "새 제목"


def test_lint_numbers_and_placeholders():
    md = "유효특허는 {{meta.n_counted}}건이다.\n상위 3개사가 45%를 차지한다.\n2019년부터 늘었다."
    hits = checks.lint_numbers(md)
    assert len(hits) == 2 and "3개사" in hits[0] and "45%" in hits[1]  # '2019년' is not a count
    text, missing = report.fill_placeholders("{{meta.n}}건 {{top.0.share|pct}} {{nope.x}}",
                                             {"meta": {"n": 1234}, "top": [{"share": 0.3251}]})
    assert text.startswith("1,234건 32.5%") and missing == ["nope.x"]


def test_md_to_html_escapes():
    html = report.md_to_html("# 제목\n<script>x</script> **굵게**\n\n| a | b |\n|---|---|\n| 1 | 2 |")
    assert "<script>" not in html and "<b>굵게</b>" in html and "<table>" in html


def test_demo_end_to_end(tmp_path):
    out = tmp_path / "demo"
    assert main(["demo", "--out", str(out)]) == 0
    s = json.loads((out / "map" / "stats.json").read_text(encoding="utf-8"))
    assert s["meta"]["basis"] == "valid" and s["meta"]["n_applicants"] == 9
    html = (out / "REPORT.html").read_text(encoding="utf-8")
    assert "⟦" not in html and "법률 의견이 아닙니다" in html


def test_batches_merge_and_audit(tmp_path):
    d = tmp_path / "p"
    assert main(["demo", "--out", str(d)]) == 0
    (d / "screening.csv").unlink()
    assert main(["batches", str(d), "--size", "200"]) == 0
    todo = sorted((d / "screening" / "todo").glob("batch_*.md"))
    assert len(todo) == 3  # 534 docs / 200
    cand = read_csv(d / "candidates.csv")
    done = d / "screening" / "done"
    done.mkdir(parents=True)
    with (done / "batch_001.jsonl").open("w", encoding="utf-8") as f:
        for _, r in cand.head(5).iterrows():
            f.write(json.dumps({"application_no": r["application_no"], "relevance": "noise",
                                "evidence_level": "provisional", "evidence_location": "요약",
                                "evidence_quote": r["abstract"][:20], "screened_by": "test"}, ensure_ascii=False) + "\n")
    rc = main(["merge-screening", str(d)])
    assert rc == 0  # warnings about unscreened rows are not errors
    assert len(read_csv(d / "screening.csv")) == 5
    assert main(["batches", str(d), "--size", "400"]) == 2  # same prefix would overwrite earlier results
    main(["batches", str(d), "--size", "400", "--prefix", "r2"])  # screened docs are not offered again
    todo = sorted((d / "screening" / "todo").glob("r2_*.md"))
    assert [p.name for p in todo] == ["r2_001.md", "r2_002.md"]
    assert "129건" in todo[1].read_text(encoding="utf-8")  # 529 = 400 + 129
    main(["audit-sample", str(d), "--n", "3"])
    assert "노이즈 5건 중 무작위 3건" in (d / "AUDIT_SAMPLE.md").read_text(encoding="utf-8")


def test_map_rerun_removes_stale_charts(tmp_path):
    d = tmp_path / "p"
    main(["demo", "--out", str(d)])
    assert (d / "map" / "tech_by_year.svg").exists()
    (d / "screening.csv").write_text(",".join(SCREENING_COLUMNS) + "\n", encoding="utf-8")
    main(["map", str(d), "--as-of", "2025-06-30"])
    assert not (d / "map" / "tech_by_year.svg").exists()
    assert not (d / "map" / "yearly.svg").exists()  # 0 valid docs → no trend chart either


def test_missing_candidates_is_a_clean_error(tmp_path, capsys):
    assert main(["check", str(tmp_path)]) == 2
    assert "run `park search` or `park ingest` first" in capsys.readouterr().err


def test_rank_orders_by_tech_tree_similarity_and_batches_respect_top(tmp_path):
    from park.rank import rank
    tree = ("| 코드 | 소분류 | 정의 | 포함 | 제외 |\n|---|---|---|---|---|\n"
            "| `S1` | 촉각 센서 어레이 | 접촉 압력 분포를 측정 | 촉각 어레이, 압력분포 센서 | 터치스크린 |\n")
    c = _cand([
        {"application_no": "1", "title": "커피 머신", "abstract": "원두를 분쇄하여 커피를 추출한다."},
        {"application_no": "2", "title": "촉각 센서 어레이", "abstract": "압력 분포를 측정하는 촉각 어레이 센서."},
        {"application_no": "3", "title": "터치스크린 패널", "abstract": "터치스크린의 접촉 좌표를 검출한다."},
    ])
    r = rank(c, tree)
    assert r.iloc[0]["application_no"] == "2" and r.iloc[0]["rank_code"] == "S1"
    assert list(r["rank"]) == [1, 2, 3]
    d = tmp_path / "p"
    d.mkdir()
    from park.schema import write_csv
    write_csv(c, d / "candidates.csv")
    (d / "TECH_TREE.md").write_text(tree, encoding="utf-8")
    assert main(["rank", str(d)]) == 0
    assert main(["batches", str(d), "--top", "1", "--size", "10"]) == 0
    body = (d / "screening" / "todo" / "batch_001.md").read_text(encoding="utf-8")
    assert "### 2" in body and "### 1\n" not in body
    assert main(["audit-sample", str(d), "--below-rank", "1", "--n", "5"]) == 0
    tail = (d / "screening" / "todo" / "tail_audit.md").read_text(encoding="utf-8")
    assert "### 2" not in tail and "미선별 2건" in tail


def test_coverage_estimates_valid_docs_left_below_the_cut():
    c = _cand([{"application_no": str(i), "application_date": "2020-01-01", "applicants": "A"} for i in range(100)])
    rows = [{"application_no": str(i), "relevance": "valid", "tech_code": "A1", "screened_by": "codex"} for i in range(10)]
    rows += [{"application_no": str(10 + i), "relevance": "valid" if i < 5 else "noise", "tech_code": "A1",
              "screened_by": "codex:tail-audit"} for i in range(10)]
    s = stats.compute(c, _screen(rows), as_of="2025-01-01")["meta"]
    assert s["n_screened"] == 20 and s["n_unscreened"] == 80
    assert s["tail_valid"] == 5 and s["tail_est_valid"] == 40
    assert s["tail_est_low"] < 40 < s["tail_est_high"]
    full = stats.compute(c, _screen(rows), as_of="2025-01-01")["meta"]
    assert full["n_counted"] == 15 and full["est_recall"] == round(15 / (15 + 40), 4)
    assert full["est_recall_low"] < full["est_recall"] < full["est_recall_high"]


def test_recheck_newest_wins_and_tail_rounds(tmp_path):
    import os
    import time
    d = tmp_path / "p"
    assert main(["demo", "--out", str(d)]) == 0
    (d / "screening.csv").unlink()
    cand = read_csv(d / "candidates.csv")
    done = d / "screening" / "done"
    done.mkdir(parents=True)
    a, b = cand.iloc[0], cand.iloc[1]

    def row(r, rel, code, by):
        return json.dumps({"application_no": r["application_no"], "relevance": rel, "tech_code": code,
                           "evidence_level": "provisional", "evidence_location": "요약",
                           "evidence_quote": r["abstract"][:20], "screened_by": by}, ensure_ascii=False) + "\n"

    (done / "zz_first.jsonl").write_text(row(a, "valid", "A1", "m") + row(b, "valid", "A1", "m:tail-audit"), encoding="utf-8")
    main(["merge-screening", str(d)])
    assert main(["batches", str(d), "--recheck-codes", "A1", "--prefix", "recheck"]) == 0
    assert "2건" in (d / "screening" / "todo" / "recheck_001.md").read_text(encoding="utf-8")
    time.sleep(0.05)
    f = done / "aa_recheck.jsonl"  # alphabetically first, but written later → must win
    f.write_text(row(a, "noise", "", "m2") + row(b, "noise", "", "m2"), encoding="utf-8")
    os.utime(f, None)
    main(["merge-screening", str(d)])
    s = read_csv(d / "screening.csv").set_index("application_no")
    assert s.loc[a["application_no"], "relevance"] == "noise"
    assert s.loc[b["application_no"], "screened_by"].endswith(":tail-audit")  # still part of the sample
    # a later round replaces the earlier one for estimates
    rows = [{"application_no": str(i), "relevance": "valid", "tech_code": "A1", "screened_by": "x:tail-audit"} for i in range(4)]
    rows += [{"application_no": str(10 + i), "relevance": "noise", "tech_code": "", "screened_by": "x:tail-audit-r2"} for i in range(4)]
    c = _cand([{"application_no": str(i), "application_date": "2020-01-01", "applicants": "A"} for i in range(30)])
    m = stats.compute(c, _screen(rows), as_of="2025-01-01")["meta"]
    assert m["tail_round"] == 2 and m["tail_valid"] == 0 and m["tail_sample"] == 4


def test_learned_rank_puts_unscreened_relevant_docs_first(tmp_path):
    d = tmp_path / "p"
    assert main(["demo", "--out", str(d)]) == 0  # 534 synthetic docs with ground-truth screening
    truth = read_csv(d / "screening.csv")
    # keep only half of the judgements, as if screening were half done
    half = truth.sample(frac=0.5, random_state=1)
    from park.schema import write_csv
    write_csv(half, d / "screening.csv")
    assert main(["rank", str(d), "--learn"]) == 0
    r = read_csv(d / "rank.csv")
    ev = json.loads((d / "rank_eval.json").read_text(encoding="utf-8"))
    assert ev["cv_all"]["auc"] > 0.9 and r["method"].iloc[0] == "learn"
    unl = r[r["labelled"] == "False"].merge(truth[["application_no", "relevance"]], on="application_no")
    top = unl.head(len(unl) // 2)
    assert (top["relevance"] == "valid").mean() > (unl["relevance"] == "valid").mean()  # better than random
    assert main(["batches", str(d), "--next", "30", "--prefix", "r2", "--size", "10"]) == 0
    assert len(list((d / "screening" / "todo").glob("r2_*.md"))) == 3


def test_learned_rank_needs_enough_judgements(tmp_path, capsys):
    d = tmp_path / "p"
    main(["demo", "--out", str(d)])
    from park.schema import write_csv
    write_csv(read_csv(d / "screening.csv").head(10), d / "screening.csv")
    assert main(["rank", str(d), "--learn"]) == 2
    assert "needs at least" in capsys.readouterr().err
