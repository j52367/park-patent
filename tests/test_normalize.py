import pandas as pd

from park import normalize as N


def test_applicant_key_merges_entity_variants():
    keys = {N.applicant_key(n) for n in ["삼성전자주식회사", "삼성전자 주식회사", "주식회사 삼성전자", "삼성전자(주)", "㈜삼성전자"]}
    assert keys == {"삼성전자"}


def test_applicant_key_latin_suffix_and_inner_text_kept():
    assert N.applicant_key("Example Power Corp.") == N.applicant_key("Example Power Corporation")
    assert N.applicant_key("Magna International") == "magnainternational"  # 'ag' inside a word survives
    assert N.applicant_key("Siemens AG") == "siemens"


def test_normalize_applicants_uses_most_common_spelling_and_aliases():
    s = pd.Series(["가람에너지(주)", "가람에너지(주)", "가람에너지 주식회사|한빛대학교 산학협력단"])
    out = N.normalize_applicants(s)
    assert list(out) == ["가람에너지(주)", "가람에너지(주)", "가람에너지(주)|한빛대학교 산학협력단"]
    out = N.normalize_applicants(s, {N.applicant_key("가람에너지"): "가람에너지"})
    assert out.iloc[0] == "가람에너지"


def test_dates_numbers_ipc():
    assert N.norm_date("20190131") == "2019-01-31"
    assert N.norm_date("2019.01.31") == "2019-01-31"
    assert N.norm_date("") == "" and N.norm_date("nan") == ""
    assert N.norm_application_no("10-2019-0012345") == "1020190012345"
    assert N.norm_application_no(1020190012345.0) == "1020190012345"
    assert N.norm_ipc("G06N 3/04|G06N 3/08|G06N 3/04") == ("G06N 3/04|G06N 3/08", "G06N")
    assert N.norm_ipc("") == ("", "")


def test_dedupe_fills_blanks_from_later_rows():
    df = pd.DataFrame([
        {"application_no": "1", "title": "a", "registration_date": ""},
        {"application_no": "1", "title": "", "registration_date": "2020-01-01"},
        {"application_no": "2", "title": "b", "registration_date": ""},
    ])
    out = N.dedupe(df).set_index("application_no")
    assert len(out) == 2
    assert out.loc["1", "title"] == "a" and out.loc["1", "registration_date"] == "2020-01-01"


def test_exact_alias_splits_companies_sharing_a_key(tmp_path):
    p = tmp_path / "aliases.csv"
    p.write_text('alias,canonical,match\n"디티에스, 인코포레이티드","DTS, Inc. (미국)",exact\n', encoding="utf-8")
    aliases = N.load_aliases(p)
    s = pd.Series(["(주)디티에스", "디티에스, 인코포레이티드", "주식회사 디티에스"])
    assert list(N.normalize_applicants(s, aliases)) == ["(주)디티에스", "DTS, Inc. (미국)", "(주)디티에스"]
    rep = N.merge_report(s, aliases)
    assert len(rep) == 1 and "인코포레이티드" not in rep.iloc[0]["spellings"]


def test_korean_inc_transliteration():
    assert N.applicant_key("마이크론 테크놀로지, 인크.") == N.applicant_key("마이크론 테크놀로지, 인크")
