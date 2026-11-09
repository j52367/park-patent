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
    assert flags[2020] is False and flags[2023] is True and flags[2024] is True
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
    main(["batches", str(d), "--size", "400"])  # screened docs are not offered again
    todo = sorted((d / "screening" / "todo").glob("batch_*.md"))
    assert [p.name for p in todo] == ["batch_001.md", "batch_002.md"]
    assert "129건" in todo[1].read_text(encoding="utf-8")  # 529 = 400 + 129
    main(["audit-sample", str(d), "--n", "3"])
    assert "3건 / 노이즈 5건" in (d / "AUDIT_SAMPLE.md").read_text(encoding="utf-8")


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
