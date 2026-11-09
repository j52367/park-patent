"""Multi-country exports (WIPS-style headers). All test data below is fictional."""
import pandas as pd

from park import checks, ingest as ING, normalize as N, stats
from park.schema import CANDIDATE_COLUMNS, SCREENING_COLUMNS, conform

WIPS = (
    "국가코드,출원번호,출원일,발명의 명칭,요약,\"독립청구항[KR,JP,US,CN,EP,IN]\",출원인,출원인 대표명화 영문명,출원인 국적,"
    "\"상태정보[KR,JP,US,EP,CN,CA,AU]\",Current IPC All\n"
    "KR,10-2024-0000123,2024-11-28,보행 보조,요약1,1. 발목 관절에 장착되는 촉각 센서를 포함하는 시스템,가람대학교산학협력단,Garam University,KR,심사중,B25J-009/00 | A61B-005/103\n"
    "US,11/000777,2007-03-28,Example tactile sensor,abs,1. A sensor,UNIV OF EXAMPLE,UNIVERSITY OF EXAMPLE,US,등록,G01L-001/00\n"
    "US,11/000777,2007-03-28,Example tactile sensor,abs,1. A sensor,UNIV OF EXAMPLE,UNIVERSITY OF EXAMPLE,US,등록,G01L-001/00\n"
    "JP,2019-123456,2019-05-01,触覚センサ,abs,1. センサ,サンプル株式会社,SAMPLE Corporation,JP,소멸(연차료불납),G01L-005/22\n"
    "KR,10-2020-0000001,2020-01-01,그리퍼,요약2,1. 그리퍼,가람대학교 산학협력단,,KR,등록,B25J-015/00\n"
)


def _ingest(tmp_path):
    p = tmp_path / "wips.csv"
    p.write_text(WIPS, encoding="utf-8")
    df, mapping = ING.ingest(p)
    return ING.finalize([df]), mapping


def test_wips_headers_countries_and_dedupe(tmp_path):
    c, mapping = _ingest(tmp_path)
    assert mapping["상태정보[KR,JP,US,EP,CN,CA,AU]"] == "status"
    assert mapping["Current IPC All"] == "ipc" and mapping["독립청구항[KR,JP,US,CN,EP,IN]"] == "independent_claims"
    assert len(c) == 4  # the duplicated US row is merged
    by = c.set_index("application_no")
    assert "US11000777" in by.index and "JP2019123456" in by.index and "1020240000123" in by.index
    assert by.loc["JP2019123456", "status"] == "소멸" and by.loc["US11000777", "ipc_main"] == "G01L"


def test_representative_names_learned_for_rows_without_one(tmp_path):
    c, _ = _ingest(tmp_path)
    by = c.set_index("application_no")
    assert by.loc["1020240000123", "applicants"] == "Garam University"
    assert by.loc["1020200000001", "applicants"] == "Garam University"  # no rep name, learned from the other row


def test_country_stats_and_nationality(tmp_path):
    c, _ = _ingest(tmp_path)
    s = stats.compute(c, None, as_of="2026-06-01")
    assert [r["country"] for r in s["country"]] == ["KR", "US", "JP"]
    garam = next(a for a in s["applicants_top"] if a["name"] == "Garam University")
    assert garam["count"] == 2 and garam["nationality"] == "KR"


def test_claim_evidence_uses_independent_claims_and_human_imports_warn(tmp_path):
    c, _ = _ingest(tmp_path)
    tree = "| `W1` | x |\n"
    s = conform(pd.DataFrame([
        {"application_no": "1020240000123", "relevance": "valid", "tech_code": "W1", "evidence_level": "provisional",
         "evidence_location": "독립청구항", "evidence_quote": "발목 관절에 장착되는 촉각 센서"},
        {"application_no": "US11000777", "relevance": "valid", "tech_code": "W1", "evidence_level": "provisional",
         "screened_by": "human:cpu"},
    ]), SCREENING_COLUMNS)
    res = checks.check_screening(c, s, tree)
    assert res.ok, res.errors
    assert res.stats["quotes_verified"] == 1 and res.stats["human_without_quote"] == 1


def test_country_prefixed_numbers_do_not_collide():
    assert N.norm_application_no("16/123,456", "US") != N.norm_application_no("16123456", "JP")
    assert N.norm_application_no("10-2019-0012345", "KR") == "1020190012345"
    assert N.norm_country("미국") == "US" and N.norm_country("") == ""


def test_partial_representative_names_keep_every_applicant():
    raw = pd.Series(["주식회사 가나센서|재단법인가상과학기술원", "삼성전자주식회사|연세대학교 산학협력단"])
    rep = pd.Series(["|Virtual Institute of Science and Technology", "Samsung Electronics Co.,Ltd.|Yonsei University"])
    aliases, eff = ING._apply_representative_names(raw, rep, {})
    out = N.normalize_applicants(eff, aliases)
    assert out.iloc[0].split("|") == ["주식회사 가나센서", "Virtual Institute of Science and Technology"]
    assert out.iloc[1] == "Samsung Electronics Co.,Ltd.|Yonsei University"


# --- regressions from the Codex multi-country review (docs/reviews/2026-11-09_codex_multicountry.md) ---

def test_check_digits_and_pct_numbers():
    assert N.norm_application_no("202010123456.7", "CN") == N.norm_application_no("202010123456", "CN")
    assert N.norm_application_no("18806395.1", "EP") == N.norm_application_no("18806395", "EP")
    kr = N.norm_application_no("PCT/KR2020/000001", "WO")
    us = N.norm_application_no("PCT/US2020/000001", "WO")
    assert kr != us and kr == "WOKR2020000001"


def test_kr_inferred_and_unknown_country_bucket(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("출원번호,국가코드,출원일,출원인\n20-2020-0000001,,2020-01-01,A\n11/1,US,2020-02-01,B\nABC123,,2020-03-01,C\n",
                 encoding="utf-8")
    c = ING.finalize([ING.ingest(p)[0]])
    assert dict(zip(c["application_no"], c["country"]))["2020200000001"] == "KR"
    s = stats.compute(c, None, as_of="2025-01-01")
    assert sum(r["count"] for r in s["country"]) == len(c)  # nothing silently dropped
    assert any(r["country"] == "미상" for r in s["country"])


def test_conflicting_representative_names_are_not_learned_and_exact_alias_wins():
    raw = pd.Series(["ACME Ltd", "ACME Inc", "ACME Inc", "디티에스, 인코포레이티드"])
    rep = pd.Series(["ACME Korea", "ACME USA", "", "DTS"])
    aliases, eff = ING._apply_representative_names(raw, rep, {N.EXACT_PREFIX + "디티에스, 인코포레이티드": "DTS(미국)"})
    out = N.normalize_applicants(eff, aliases)
    assert out.iloc[2] != "ACME Korea"  # no guess from a conflicting key
    assert out.iloc[3] == "DTS(미국)"
    assert ING.rep_conflicts(raw, rep) == [("acme", ["ACME Korea", "ACME USA"])]


def test_nationality_not_guessed_for_co_applicants():
    c = conform(pd.DataFrame([{"application_no": "1", "applicants": "A|B", "applicant_country": "KR",
                               "application_date": "2020-01-01"}]), CANDIDATE_COLUMNS)
    s = stats.compute(c, None, as_of="2025-01-01")
    assert all(a["nationality"] == "" for a in s["applicants_top"])


def test_duplicate_screening_rows_do_not_double_count():
    c = conform(pd.DataFrame([{"application_no": "US1", "country": "US", "application_date": "2020-01-01",
                               "applicants": "A"}]), CANDIDATE_COLUMNS)
    sc = conform(pd.DataFrame([{"application_no": "US1", "relevance": "valid", "tech_code": "T1"}] * 2),
                 SCREENING_COLUMNS)
    s = stats.compute(c, sc, as_of="2025-01-01")
    assert s["meta"]["n_counted"] == 1 and s["country_by_tech"]["values"] == [[1]]


def test_claim_number_must_exist_and_human_confirmed_is_an_error():
    c = conform(pd.DataFrame([{"application_no": "1", "title": "t", "abstract": "a",
                               "independent_claims": "1. 촉각 센서를 포함하는 로봇 핸드. 10. 미끄럼을 감지하는 제어 방법."}]),
                CANDIDATE_COLUMNS)
    tree = "| `A1` | x |\n"
    row = {"application_no": "1", "relevance": "valid", "tech_code": "A1", "evidence_level": "provisional",
           "evidence_quote": "촉각 센서를 포함하는 로봇 핸드"}
    ok = conform(pd.DataFrame([{**row, "evidence_location": "청구항 1"}]), SCREENING_COLUMNS)
    assert checks.check_screening(c, ok, tree).ok
    wrong_claim = conform(pd.DataFrame([{**row, "evidence_location": "청구항 10"}]), SCREENING_COLUMNS)
    assert "not found verbatim" in " ".join(checks.check_screening(c, wrong_claim, tree).errors)
    missing = conform(pd.DataFrame([{**row, "evidence_location": "청구항 99"}]), SCREENING_COLUMNS)
    assert "claim 99 is not among" in " ".join(checks.check_screening(c, missing, tree).errors)
    human = conform(pd.DataFrame([{"application_no": "1", "relevance": "valid", "tech_code": "A1",
                                   "evidence_level": "confirmed", "screened_by": "human:x"}]), SCREENING_COLUMNS)
    assert "confirmed" in " ".join(checks.check_screening(c, human, tree).errors)


def test_tech_label_falls_back_per_row():
    md = "| 코드 | 대분류 | 중분류 | 소분류 |\n|---|---|---|---|\n| `A1` | 센서 | 촉각 | |\n| `A2` | 센서 | 촉각 | 어레이 |\n"
    assert checks.tech_labels(md) == {"A1": "촉각", "A2": "어레이"}
