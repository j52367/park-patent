"""Phase 2: detail/citing parsing, enrich, key review merge, SWOT. All data is fictional."""
import json

import pandas as pd

from park import review, swot
from park.cli import main
from park.enrich import enrich, shortlist
from park.kipris import parse_citing, parse_detail
from park.schema import CANDIDATE_COLUMNS, SCREENING_COLUMNS, conform, write_csv

DETAIL = """<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header><body><item>
<biblioSummaryInfoArray><biblioSummaryInfo><applicationNumber>10-2020-0000001</applicationNumber>
<claimCount>3</claimCount><inventionTitle>가상 촉각 장치</inventionTitle><registerStatus>등록</registerStatus>
<registerNumber>10-9999999</registerNumber></biblioSummaryInfo></biblioSummaryInfoArray>
<claimInfoArray>
<claimInfo><claim>1. 탄성층과 상기 탄성층 아래의 전극 어레이를 포함하는 감지 장치.</claim></claimInfo>
<claimInfo><claim>2. 제1항에 있어서, 상기 전극은 투명한 감지 장치.</claim></claimInfo>
<claimInfo><claim>3. 접촉 압력을 측정하는 단계를 포함하는 방법.</claim></claimInfo>
<claimInfo><claim>4. 삭제</claim></claimInfo>
</claimInfoArray>
<priorArtDocumentsInfoArray><priorArtDocumentsInfo><documentsNumber>KR1020100000001 A</documentsNumber>
<examinerQuotationFlag>Y</examinerQuotationFlag></priorArtDocumentsInfo></priorArtDocumentsInfoArray>
<familyInfoArray><familyInfo><familyApplicationNumber>US17000001</familyApplicationNumber></familyInfo></familyInfoArray>
<legalStatusInfoArray><legalStatusInfo><receiptDate>2020.01.01</receiptDate><documentName>출원서</documentName>
<commonCodeName>수리</commonCodeName></legalStatusInfo></legalStatusInfoArray>
</item></body></response>""".encode("utf-8")

CITING = """<response><header><resultCode></resultCode><resultMsg></resultMsg></header><body><items>
<citingInfo><StandardCitationApplicationNumber>1020200000001</StandardCitationApplicationNumber>
<ApplicationNumber>1020230000002</ApplicationNumber><CitationLiteratureTypeCodeName>선행기술조사보고서</CitationLiteratureTypeCodeName></citingInfo>
</items></body></response>""".encode("utf-8")


def test_parse_detail_and_citing():
    d = parse_detail(DETAIL)
    assert d["application_no"] == "1020200000001" and d["claim_count"] == 3
    assert [c[:2] for c in d["independent_claims"]] == ["1.", "3."]  # claim 2 depends on claim 1
    assert d["prior_art"] == [{"number": "KR1020100000001 A", "examiner": True}]
    assert len(d["family"]) == 1 and d["legal_status"][0]["document"] == "출원서"
    assert parse_citing(CITING) == [{"citing_application_no": "1020230000002", "type": "선행기술조사보고서"}]


class FakeClient:
    def __init__(self):
        self.network_calls = 0

    def detail(self, no):
        self.network_calls += 1
        d = parse_detail(DETAIL)
        d["application_no"] = no
        return d

    def citing(self, no):
        self.network_calls += 1
        return parse_citing(CITING)


def _project(tmp_path):
    d = tmp_path / "p"
    d.mkdir()
    cand = conform(pd.DataFrame([
        {"application_no": f"10202000000{i:02d}", "title": f"문헌{i}", "abstract": "요약", "status": "등록" if i % 2 else "거절",
         "applicants": "가람연구원" if i < 4 else ("나래전자" if i < 12 else "다온대학교"),
         "application_date": f"{2012 + i % 12}-01-01"} for i in range(1, 16)]), CANDIDATE_COLUMNS)
    scr = conform(pd.DataFrame([
        {"application_no": no, "relevance": "valid", "tech_code": "S1" if i % 3 else "C1", "evidence_level": "provisional"}
        for i, no in enumerate(cand["application_no"])]), SCREENING_COLUMNS)
    write_csv(cand, d / "candidates.csv")
    write_csv(scr, d / "screening.csv")
    (d / "TECH_TREE.md").write_text("| 코드 | 소분류 |\n|---|---|\n| `S1` | 센서 어레이 |\n| `C1` | 힘 제어 |\n", encoding="utf-8")
    return d, cand, scr


def test_shortlist_keeps_focal_and_codes(tmp_path):
    _, cand, scr = _project(tmp_path)
    s = shortlist(cand, scr, None, ["가람연구원"], n=6, per_code=1)
    assert set(s[s["reason"] == "focal"]["applicants"]) == {"가람연구원"}
    assert set(s["tech_code"]) == {"S1", "C1"} and len(s) == 6  # every code is represented


def test_enrich_respects_budget_and_writes_claims(tmp_path):
    d, cand, _ = _project(tmp_path)
    nos = cand["application_no"].head(3).tolist()
    c = FakeClient()
    df = enrich(c, nos, d, budget=4, log=lambda *_: None)  # 2 calls per document
    assert len(df) == 2 and c.network_calls == 4
    assert (d / "fulltext" / f"{nos[0]}.txt").read_text(encoding="utf-8").startswith("1. 탄성층")
    df = enrich(c, nos, d, budget=4, log=lambda *_: None)  # cached docs cost nothing
    assert len(df) == 3 and c.network_calls == 6
    assert df.iloc[0]["forward_citations"] == 1 and df.iloc[0]["family_size"] == 1


def test_review_merge_verifies_quotes_against_the_named_claim(tmp_path):
    d, cand, scr = _project(tmp_path)
    nos = cand["application_no"].head(2).tolist()
    enrich(FakeClient(), nos, d, log=lambda *_: None)
    out = d / "review" / "done"
    out.mkdir(parents=True)
    good = {"application_no": nos[0], "importance": "핵심", "evidence_level": "confirmed", "evidence_location": "청구항 1",
            "evidence_quote": "탄성층 아래의 전극 어레이를 포함하는", "key_features": "x", "rationale": "y", "reviewed_by": "t"}
    wrong = {**good, "application_no": nos[1], "evidence_location": "청구항 3"}  # quote is from claim 1
    (out / "key_001.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in (good, wrong)), encoding="utf-8")
    df, errors = review.merge(d)
    assert len(df) == 2 and len(errors) == 1 and nos[1] in errors[0]


def test_swot_hints_and_report_section(tmp_path):
    d, cand, scr = _project(tmp_path)
    s = swot.compute(cand, scr, "가람연구원", ["나래전자", "다온대학교"], as_of="2025-12-31", window=3)
    focal = s["applicants"][0]
    assert focal["name"] == "가람연구원" and focal["n"] == 3 and sum(focal["by_code"].values()) == 3
    assert any(t["competitor"] == "나래전자" for t in s["hints"]["T"])
    kr = pd.DataFrame({"application_no": [cand["application_no"].iloc[1]], "importance": ["핵심"]})  # an S1 doc; focal has 2 in S1
    s2 = swot.compute(cand, scr, "가람연구원", ["나래전자"], as_of="2025-12-31", window=3, key_review=kr)
    assert any(h["focal_key"] == 1 for h in s2["hints"]["S"])  # a key patent makes the code a strength candidate
    assert main(["map", str(d), "--as-of", "2025-12-31"]) == 0
    assert main(["swot", str(d), "--focal", "가람연구원", "--vs", "나래전자,다온대학교", "--as-of", "2025-12-31"]) == 0
    (d / "SWOT.md").write_text("## 강점\n- {{swot.applicants.0.name}}의 유효특허는 {{swot.applicants.0.n}}건입니다.\n",
                               encoding="utf-8")
    assert main(["report", str(d), "--strict"]) == 0
    html = (d / "REPORT.html").read_text(encoding="utf-8")
    assert "SWOT · 특허 전략" in html and "가람연구원의 유효특허는 3건입니다" in html
