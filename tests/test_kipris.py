import pytest

from park.kipris import KiprisClient, KiprisError, items_to_candidates, parse_search

XML = """<?xml version="1.0" encoding="UTF-8"?>
<response><header><resultCode>00</resultCode><resultMsg>NORMAL SERVICE.</resultMsg></header>
<body><items>
<PatentUtilityInfo>
  <ApplicationNumber>1020190012345</ApplicationNumber>
  <InventionName>배터리 SOC 추정 방법</InventionName>
  <Abstract>셀 전압을 측정한다.</Abstract>
  <Applicant>가람에너지(주)|한빛대학교 산학협력단</Applicant>
  <InternationalpatentclassificationNumber>G01R 31/367|H01M 10/48</InternationalpatentclassificationNumber>
  <ApplicationDate>20190302</ApplicationDate>
  <RegistrationDate>20210101</RegistrationDate>
  <RegistrationStatus>등록</RegistrationStatus>
</PatentUtilityInfo>
</items><TotalSearchCount>1</TotalSearchCount></body></response>""".encode("utf-8")


class FakeResp:
    def __init__(self, body, status=200):
        self.content, self.status_code = body, status


class FakeSession:
    def __init__(self, body):
        self.body, self.calls = body, []

    def get(self, url, params, timeout):
        self.calls.append(params)
        return FakeResp(self.body)


def test_parse_search():
    total, items = parse_search(XML)
    assert total == 1 and items[0]["title"] == "배터리 SOC 추정 방법"
    df = items_to_candidates(items, "2025-06-30")
    r = df.iloc[0]
    assert r["ipc_main"] == "G01R" and r["status"] == "등록" and r["registration_date"] == "2021-01-01"


def test_cache_prevents_second_call_and_counts_quota(tmp_path):
    s = FakeSession(XML)
    c = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    c.search_page("IPC=[G01R]")
    c.search_page("IPC=[G01R]")
    assert len(s.calls) == 1
    assert c.calls_this_month() == 1
    assert s.calls[0]["accessKey"] == "k"


def test_cache_key_ignores_access_key():
    a = KiprisClient._cache_key("p", {"word": "x", "accessKey": "1"})
    b = KiprisClient._cache_key("p", {"word": "x", "accessKey": "2"})
    assert a == b


def test_no_key_uncached_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("KIPRIS_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    c = KiprisClient(api_key="", db_path=tmp_path / "c.sqlite", session=FakeSession(XML), delay_sec=0)
    with pytest.raises(KiprisError):
        c.search_page("IPC=[G01R]")


def test_error_result_code_not_cached(tmp_path):
    bad = b"<response><header><resultCode>10</resultCode><resultMsg>bad key</resultMsg></header></response>"
    s = FakeSession(bad)
    c = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    for _ in range(2):
        with pytest.raises(KiprisError, match="bad key"):
            c.search_page("x")
    assert len(s.calls) == 2  # errors are retried, not served from cache


def _page_xml(total, n, offset):
    items = "".join(
        f"<PatentUtilityInfo><ApplicationNumber>10201900{offset + i:05d}</ApplicationNumber>"
        f"<InventionName>t</InventionName></PatentUtilityInfo>" for i in range(n))
    return (f"<response><header><resultCode>00</resultCode></header><body><items>{items}</items>"
            f"<TotalSearchCount>{total}</TotalSearchCount></body></response>").encode()


class PagedSession:
    def __init__(self, total):
        self.total, self.calls = total, []

    def get(self, url, params, timeout):
        self.calls.append(params)
        start, count = int(params["docsStart"]), int(params["docsCount"])
        return FakeResp(_page_xml(self.total, max(0, min(count, self.total - start + 1)), start))


def test_budget_counts_only_network_calls(tmp_path):
    s = PagedSession(total=30)
    c = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    total, items = c.search("q", max_docs=30, page_size=10, budget=2, log=lambda *_: None)
    assert total == 30 and len(items) == 20 and len(s.calls) == 2
    # pages 1-2 are cached now, so budget 1 is enough to get page 3
    c2 = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    total, items = c2.search("q", max_docs=30, page_size=10, budget=1, log=lambda *_: None)
    assert len(items) == 30 and len(s.calls) == 3
    # budget 0 with nothing cached makes no call at all
    c3 = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    assert c3.search("other", budget=0, log=lambda *_: None) == (0, []) and len(s.calls) == 3


def test_cached_items_keep_original_fetch_date(tmp_path):
    s = FakeSession(XML)
    c = KiprisClient(api_key="k", db_path=tmp_path / "c.sqlite", session=s, delay_sec=0)
    c.search_page("q")
    c._db.execute("UPDATE responses SET fetched_at='2020-03-04T00:00:00+00:00'")
    c._db.commit()
    _, items = c.search_page("q")
    assert items_to_candidates(items).iloc[0]["status_as_of"] == "2020-03-04"
