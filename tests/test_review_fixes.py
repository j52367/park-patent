"""Regression tests for the phase-2 code review and the first end-to-end skill run. All data is fictional."""
import json

import pandas as pd

from park import chart, review, stats
from park.checks import _claim_text, claims_by_number, lint_numbers
from park.cli import main
from park.enrich import enrich
from park.fulltext import parse_spec, quote_in_paragraph
from park.kipris import _looks_like_response, independent_claims, parse_citing
from park.schema import SCREENING_COLUMNS, conform, read_csv, write_csv

from test_phase2 import SPEC_TEXT, FakeClient, _project


# ---- claims ---------------------------------------------------------------------------------

def test_number_inside_a_claim_is_not_a_claim_boundary():
    claims = ["1. 압력이 설정값 10. 이하이면 정지하는 장치.", "2. 제1항에 있어서, 센서를 더 포함하는 장치."]
    assert claims_by_number(claims)[1].endswith("정지하는 장치.")
    assert 10 not in claims_by_number(claims)
    assert _claim_text("1. 압력이 설정값 10. 이하이면 정지하는 장치.\n2. 방법.", 10) is None


def test_claim_headings_and_deleted_claims():
    claims = ["【청구항 1】 탄성층을 포함하는 장치.", "청구항 2 제1항에 있어서, 투명한 장치.", "【청구항 3】 삭제", "4) 측정 방법."]
    got = independent_claims(claims)
    assert got == ["【청구항 1】 탄성층을 포함하는 장치.", "4) 측정 방법."]
    assert sorted(claims_by_number(claims)) == [1, 2, 3, 4]


# ---- KIPRIS responses -----------------------------------------------------------------------

def test_empty_result_code_needs_a_real_response():
    assert _looks_like_response(b"<response><header/><body><items/></body></response>")
    assert not _looks_like_response(b"<html><body>service notice</body></html>")
    assert not _looks_like_response(b"not xml")


def test_citing_documents_are_counted_once():
    body = ("<response><header><resultCode></resultCode></header><body><items>"
            + "".join(f"<citingInfo><ApplicationNumber>{no}</ApplicationNumber>"
                      f"<CitationLiteratureTypeCodeName>{t}</CitationLiteratureTypeCodeName></citingInfo>"
                      for no, t in [("10-2023-0000002", "심사"), ("1020230000002", "선행기술조사"), ("1020240000003", "심사")])
            + "</items></body></response>").encode("utf-8")
    assert [c["citing_application_no"] for c in parse_citing(body)] == ["1020230000002", "1020240000003"]


# ---- description paragraphs -----------------------------------------------------------------

def test_quote_needs_the_cited_paragraph_to_exist():
    spec = parse_spec(SPEC_TEXT)
    assert quote_in_paragraph(spec, "0003", "끝.")
    assert not quote_in_paragraph(spec, "0004", "끝.")  # [0004] does not exist; [0003] is only its neighbour


# ---- coverage and audits --------------------------------------------------------------------

def _screen(rows):
    return conform(pd.DataFrame(rows), SCREENING_COLUMNS)


def test_tail_estimate_uses_its_frame_and_handles_undecided():
    cand = pd.DataFrame({"application_no": [f"N{i:03d}" for i in range(200)]})
    top = [{"application_no": f"N{i:03d}", "relevance": "valid", "screened_by": "m"} for i in range(50)]
    tail = [{"application_no": f"N{i:03d}", "relevance": r, "screened_by": "m:tail-audit"}
            for i, r in zip(range(50, 70), ["valid"] * 2 + ["undecided"] * 2 + ["noise"] * 16)]
    # the sample was drawn from N050–N149 only; N150–N199 came in later
    frame = {f"N{i:03d}" for i in range(50, 150)}
    c = stats.coverage(cand, _screen(top + tail), {1: frame})
    assert c["tail_undecided"] == 2 and c["tail_frame_left"] == 80
    assert c["tail_est_valid"] == round(2 / 18 * 80)  # undecided rows are not counted as noise
    assert c["n_unscreened_outside_frame"] == 50
    assert c["tail_est_high"] >= round(4 / 20 * 80)  # undecided may be relevant: the upper bound allows it


def test_noise_audit_rates():
    rows = [{"application_no": f"V{i}", "relevance": "valid", "screened_by": "m"} for i in range(40)]
    rows += [{"application_no": f"Z{i}", "relevance": "noise", "screened_by": "m"} for i in range(10)]
    rows += [{"application_no": "Z0", "relevance": "valid", "screened_by": "m:noise-audit"}]
    rows += [{"application_no": f"Z{i}", "relevance": "noise", "screened_by": "m:noise-audit"} for i in range(1, 10)]
    scr = _screen(rows).drop_duplicates("application_no", keep="last")
    c = stats.coverage(pd.DataFrame({"application_no": scr["application_no"]}), scr)
    assert c["noise_audit_n"] == 10 and c["noise_audit_flipped"] == 1 and c["noise_audit_census"]
    assert c["noise_miss_rate"] == 0.1
    assert c["est_fnr"] == round(1 / 41, 4) == c["est_fnr_low"] == c["est_fnr_high"]  # a census has no sampling range


def test_audit_sample_writes_frame_and_noise_batch(tmp_path):
    d = tmp_path / "p"
    assert main(["demo", "--out", str(d)]) == 0
    assert main(["audit-sample", str(d), "--unscreened", "--n", "10"]) == 0
    frame = (d / "screening" / "tail_frame_r1.txt").read_text(encoding="utf-8").split()
    assert len(frame) == len(read_csv(d / "candidates.csv")) - len(read_csv(d / "screening.csv"))
    assert main(["audit-sample", str(d), "--n", "3"]) == 0
    assert (d / "screening" / "todo" / "noise_audit.md").exists()


def test_incomplete_year_needs_a_month_inside_the_window():
    cand = pd.DataFrame({"application_no": ["A", "B"], "application_date": ["2022-05-01", "2023-05-01"],
                         "applicants": ["가", "나"], "ipc_main": ["", ""], "status": ["", ""], "status_as_of": ["", ""]})
    one_day = {r["year"]: r["incomplete"] for r in stats.compute(cand, as_of="2025-06-30")["yearly"]}
    assert one_day == {2022: False, 2023: False}  # cutoff 2023-12-30: only 1 day of 2023 is inside the window
    two_months = {  # cutoff 2023-11-01: two months of 2023 are inside
       r["year"]: r["incomplete"] for r in stats.compute(cand, as_of="2025-05-01")["yearly"]}
    assert two_months[2023] is True


def test_lint_allows_method_wording():
    assert lint_numbers("문헌을 1건씩 확인했고, 인용문은 100% 대조했다.") == []
    assert lint_numbers("유효특허는 48건이다.") != []


# ---- latest judgement wins ------------------------------------------------------------------

def test_a_later_noise_judgement_removes_a_document(tmp_path):
    from park import swot
    from park.enrich import shortlist
    d, cand, scr = _project(tmp_path)
    no = cand["application_no"].iloc[0]
    scr2 = pd.concat([scr, _screen([{"application_no": no, "relevance": "noise"}])], ignore_index=True)
    assert no not in set(shortlist(cand, scr2, None, ["가람연구원"], n=15)["application_no"])
    assert swot.compute(cand, scr2, "가람연구원", [], as_of="2025-12-31")["applicants"][0]["n"] == 2


# ---- enrich ---------------------------------------------------------------------------------

def test_cached_detail_restores_claims_text(tmp_path):
    d, cand, _ = _project(tmp_path)
    no = cand["application_no"].iloc[0]
    enrich(FakeClient(), [no], d, log=lambda *_: None)
    (d / "fulltext" / f"{no}.txt").unlink()
    c = FakeClient()
    enrich(c, [no], d, log=lambda *_: None)
    assert c.network_calls == 0 and (d / "fulltext" / f"{no}.txt").exists()


# ---- key review -----------------------------------------------------------------------------

def _review_rows(d, rows):
    out = d / "review" / "done"
    out.mkdir(parents=True, exist_ok=True)
    (out / "key_001.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")


def test_review_keeps_only_verified_rows(tmp_path):
    d, cand, _ = _project(tmp_path)
    a, b, c = cand["application_no"].iloc[:3]
    enrich(FakeClient(), [a, b, c], d, log=lambda *_: None)
    base = {"importance": "핵심", "evidence_level": "confirmed", "key_features": "x", "rationale": "y", "reviewed_by": "t"}
    _review_rows(d, [
        {**base, "application_no": a, "evidence_location": "청구항 1", "evidence_quote": "탄성층 아래의 전극 어레이를"},
        {**base, "application_no": b, "evidence_location": "", "evidence_quote": "탄성층 아래의 전극 어레이를"},  # no claim number
        {**base, "application_no": c, "evidence_location": "", "evidence_quote": ""},  # 핵심 without a quote
    ])
    df, errors = review.merge(d)
    assert len(errors) == 2
    assert list(read_csv(d / "key_review.csv")["application_no"]) == [a]


def test_forward_percentile_needs_enough_documents(tmp_path):
    d, cand, scr = _project(tmp_path)
    nos = cand["application_no"].head(3).tolist()
    write_csv(enrich(FakeClient(), nos, d, log=lambda *_: None), d / "enrich.csv")
    pd.DataFrame({"application_no": nos, "title": "t", "applicants": "a", "tech_code": "S1", "status": "등록",
                  "application_date": "2020-01-01", "reason": "top"}) \
        .to_csv(d / "shortlist.csv", index=False, encoding="utf-8-sig")
    assert (review.signals(d)["forward_top_pct"] == -1).all()
    review.make_batches(d)
    assert "상위" not in (d / "review" / "todo" / "key_001.md").read_text(encoding="utf-8")


# ---- claim chart ----------------------------------------------------------------------------

def test_chart_rejects_duplicates_and_outside_documents_and_keeps_edits(tmp_path):
    d, cand, _ = _project(tmp_path)
    target, earlier, outside = cand["application_no"].iloc[-1], cand["application_no"].iloc[0], cand["application_no"].iloc[1]
    enrich(FakeClient(), [target, earlier, outside], d, log=lambda *_: None)
    out = chart.prepare(d, target, 1, k=1, examiner_apps=[earlier])
    allowed = set(pd.read_csv(out / "prior_art.csv", dtype=str)["application_no"])
    outside = next(n for n in cand["application_no"] if n not in allowed and n != target)
    assert "art_type" in pd.read_csv(out / "prior_art.csv").columns

    meta = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    meta["elements"] = [{"id": "E0", "text": "감지 장치"}, {"id": "E1", "text": "탄성층"}, {"id": "E2", "text": "전극 어레이"}]  # hand-corrected
    (out / "elements.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    chart.prepare(d, target, 1, k=1, examiner_apps=[earlier])
    assert len(json.loads((out / "elements.json").read_text(encoding="utf-8"))["elements"]) == 3
    chart.prepare(d, target, 1, k=1, examiner_apps=[earlier], resplit=True)
    assert len(json.loads((out / "elements.json").read_text(encoding="utf-8"))["elements"]) == 2  # back to the automatic split

    meta = json.loads((out / "elements.json").read_text(encoding="utf-8"))
    rows = [{"prior_art": earlier, "element": e["id"], "status": "개시", "location": "청구항 1",
             "quote": "탄성층과 상기 탄성층 아래의"} for e in meta["elements"]]
    rows.append(dict(rows[0]))  # the same document × element twice
    rows.append({"prior_art": outside, "element": "E0", "status": "개시", "location": "청구항 1", "quote": "탄성층과 상기 탄성층"})
    rows.append({"prior_art": target, "element": "E1", "status": "개시", "location": "청구항 1", "quote": "탄성층과 상기 탄성층"})
    rows.append({"combination": [earlier, target], "covers": {}, "motivation": "m", "weakness": "w"})
    (out / "done.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    summary, errors = chart.merge(d, out)
    assert any("more than once" in e for e in errors) and any("prior_art.csv" in e for e in errors)
    assert any("target itself" in e for e in errors) and summary["combinations"] == []
    written = pd.read_csv(out / "chart.csv", dtype=str)
    assert outside not in set(written["prior_art"]) and not ((written["element"] == "E0").any())
    assert summary["fully_disclosed_by"] == []  # E0 failed, so no document discloses every element
