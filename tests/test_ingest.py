from park import ingest as ING


def test_legacy_notebook_format(tmp_path):
    p = tmp_path / "patents_raw.csv"
    p.write_text(
        "application_no,application_date,title,ipc_raw,ipc_major,applicant,abstract,registration_status\n"
        "1020167010147,20140821,뉴럴 방법,G06N 3/04|G06N 3/08,G06N,퀄컴 인코포레이티드,요약문,등록\n",
        encoding="utf-8-sig")
    df, mapping = ING.ingest(p, as_of="2025-05-01")
    r = df.iloc[0]
    assert r["application_no"] == "1020167010147"
    assert r["application_date"] == "2014-08-21"
    assert r["ipc_main"] == "G06N" and r["status"] == "등록" and r["status_as_of"] == "2025-05-01"
    assert mapping["ipc_raw"] == "ipc"


def test_korean_headers_with_title_rows_and_cp949(tmp_path):
    p = tmp_path / "kipris_export.csv"
    text = ("검색결과 목록\n다운로드일 2025-06-30\n"
            "번호,출원번호,발명의 명칭,출원인,출원일자,IPC,요약,법적상태\n"
            "1,10-2019-0012345,배터리 SOC 추정,가람에너지(주);한빛대학교 산학협력단,2019.03.02,G01R 31/367,요약,출원취하\n")
    p.write_bytes(text.encode("cp949"))
    df, mapping = ING.ingest(p)
    r = df.iloc[0]
    assert r["application_no"] == "1020190012345"
    assert r["applicants_raw"] == "가람에너지(주)|한빛대학교 산학협력단"
    assert r["application_date"] == "2019-03-02"
    assert r["status"] == "취하"  # terminal state wins over '출원'


def test_finalize_dedupes_across_files(tmp_path):
    a = tmp_path / "a.csv"
    a.write_text("출원번호,발명의명칭,출원인\n1020190012345,제목,가람에너지(주)\n", encoding="utf-8")
    b = tmp_path / "b.csv"
    b.write_text("출원번호,발명의명칭,출원인,등록일자\n1020190012345,,가람에너지 주식회사,20210101\n", encoding="utf-8")
    out = ING.finalize([ING.ingest(a)[0], ING.ingest(b)[0]])
    assert len(out) == 1
    assert out.iloc[0]["title"] == "제목" and out.iloc[0]["registration_date"] == "2021-01-01"


def test_missing_application_column_is_an_error(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("foo,bar\n1,2\n", encoding="utf-8")
    try:
        ING.ingest(p)
    except ValueError as e:
        assert "application-number" in str(e)
    else:
        raise AssertionError("expected ValueError")
