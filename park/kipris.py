"""KIPRIS Plus Open API client with an on-disk cache and a monthly call counter.

Verified against real responses (2025 notebook in this project's history):
  * endpoint  patUtiModInfoSearchSevice/freeSearchInfo  (sic: "Sevice")
  * params    word, docsStart (1-based offset), docsCount, accessKey
  * response  resultCode '00' on success, TotalSearchCount, items <PatentUtilityInfo>
Everything else (other services, max docsCount per call) is NOT verified yet —
see docs/DESIGN.md §6.1 and keep notes in docs/kipris-api-notes.md when you check.

The free tier is limited by number of *calls* (1,000/month), not documents, so:
  * every response is cached (same query → no new call)
  * every real call is logged; `park quota` shows this month's usage
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

from . import normalize as N
from .schema import CANDIDATE_COLUMNS, conform

BASE_URL = "http://plus.kipris.or.kr/openapi/rest"
SEARCH_PATH = "patUtiModInfoSearchSevice/freeSearchInfo"
DEFAULT_DB = Path(".park") / "kipris_cache.sqlite"

# XML tag -> candidates.csv column
ITEM_FIELDS = {
    "ApplicationNumber": "application_no",
    "InventionName": "title",
    "Abstract": "abstract",
    "Applicant": "applicants_raw",
    "InternationalpatentclassificationNumber": "ipc",
    "ApplicationDate": "application_date",
    "OpeningDate": "publication_date",      # unverified tag name
    "PublicationDate": "publication_date",  # unverified tag name
    "RegistrationDate": "registration_date",
    "RegistrationStatus": "status",
}


class KiprisError(RuntimeError):
    pass


def load_env(path: str | Path = ".env") -> None:
    """Minimal .env reader (no dependency). Existing environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class KiprisClient:
    def __init__(self, api_key: str | None = None, db_path: str | Path = DEFAULT_DB,
                 base_url: str = BASE_URL, delay_sec: float = 0.3, session=None):
        load_env()
        self.api_key = api_key or os.environ.get("KIPRIS_API_KEY", "")
        self.base_url = base_url.rstrip("/")
        self.delay_sec = delay_sec
        self.session = session or requests.Session()
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(self.db_path)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS responses (key TEXT PRIMARY KEY, path TEXT, params TEXT,"
            " body BLOB, fetched_at TEXT)")
        self._db.execute("CREATE TABLE IF NOT EXISTS calls (ts TEXT, path TEXT, params TEXT, status INTEGER)")
        self._db.commit()
        self.network_calls = 0  # real HTTP calls made by this client instance

    # ---------- low level ----------
    @staticmethod
    def _cache_key(path: str, params: dict) -> str:
        public = {k: v for k, v in sorted(params.items()) if k != "accessKey"}
        return hashlib.sha256(f"{path}?{json.dumps(public, ensure_ascii=False)}".encode()).hexdigest()

    def is_cached(self, path: str, params: dict) -> bool:
        key = self._cache_key(path, params)
        return self._db.execute("SELECT 1 FROM responses WHERE key=?", (key,)).fetchone() is not None

    def get(self, path: str, params: dict, use_cache: bool = True) -> tuple[bytes, str]:
        """Return (body, fetched_at ISO time). Cached bodies keep their original fetch time."""
        key = self._cache_key(path, params)
        if use_cache:
            row = self._db.execute("SELECT body, fetched_at FROM responses WHERE key=?", (key,)).fetchone()
            if row:
                return row[0], row[1]
        if not self.api_key:
            raise KiprisError("KIPRIS_API_KEY is not set (put it in .env). Cached queries still work offline.")
        public = json.dumps({k: v for k, v in params.items() if k != "accessKey"}, ensure_ascii=False)
        resp = self.session.get(f"{self.base_url}/{path}", params={**params, "accessKey": self.api_key},
                                timeout=30)
        self.network_calls += 1
        now = datetime.now(timezone.utc).isoformat()
        self._db.execute("INSERT INTO calls VALUES (?,?,?,?)", (now, path, public, resp.status_code))
        self._db.commit()
        if self.delay_sec:
            time.sleep(self.delay_sec)
        if resp.status_code != 200:
            raise KiprisError(f"HTTP {resp.status_code} from {path}")
        body = resp.content
        code, msg = _result_code(body)
        if code != "00":
            raise KiprisError(f"KIPRIS resultCode={code}: {msg}")
        self._db.execute("INSERT OR REPLACE INTO responses VALUES (?,?,?,?,?)", (key, path, public, body, now))
        self._db.commit()
        return body, now

    def calls_this_month(self) -> int:
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        return self._db.execute("SELECT COUNT(*) FROM calls WHERE substr(ts,1,7)=?", (month,)).fetchone()[0]

    # ---------- search ----------
    @staticmethod
    def _search_params(word: str, start: int, count: int) -> dict:
        return {"word": word, "docsStart": str(start), "docsCount": str(count)}

    def search_page(self, word: str, start: int = 1, count: int = 100, use_cache: bool = True):
        body, fetched_at = self.get(SEARCH_PATH, self._search_params(word, start, count), use_cache=use_cache)
        total, items = parse_search(body)
        for it in items:
            it["_fetched_at"] = fetched_at
        return total, items

    def search(self, word: str, max_docs: int = 500, page_size: int = 100, use_cache: bool = True,
               budget: int | None = None, log=print):
        """Fetch up to max_docs results. `budget` caps *network* calls; cached pages are free."""
        start_calls = self.network_calls

        def affordable(start: int) -> bool:
            if budget is None or (use_cache and self.is_cached(SEARCH_PATH, self._search_params(word, start, page_size))):
                return True
            return self.network_calls - start_calls < budget

        if not affordable(1):
            log(f"[kipris] budget {budget} allows no network call and page 1 is not cached")
            return 0, []
        total, items = self.search_page(word, 1, page_size, use_cache)
        log(f"[kipris] '{word}': total {total}")
        start = 1 + page_size
        while len(items) < min(total, max_docs):
            if not affordable(start):
                log(f"[kipris] stopped at call budget {budget}; {len(items)}/{total} fetched")
                break
            _, batch = self.search_page(word, start, page_size, use_cache)
            if not batch:
                break
            items.extend(batch)
            start += page_size
        return total, items[:max_docs]


def _result_code(body: bytes) -> tuple[str, str]:
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return "parse-error", str(e)
    return (root.findtext(".//resultCode", "") or "").strip(), (root.findtext(".//resultMsg", "") or "").strip()


def parse_search(body: bytes) -> tuple[int, list[dict]]:
    root = ET.fromstring(body)
    total = int((root.findtext(".//TotalSearchCount", "0") or "0").strip() or 0)
    items = []
    for el in root.iter("PatentUtilityInfo"):
        raw = {child.tag: (child.text or "").strip() for child in el}
        row = {}
        for tag, col in ITEM_FIELDS.items():
            if raw.get(tag) and not row.get(col):
                row[col] = raw[tag]
        row["_raw"] = raw
        items.append(row)
    return total, items


def items_to_candidates(items: list[dict], as_of: str = ""):
    """Turn parsed items into a candidates frame (not yet de-duplicated / applicant-normalised).

    status_as_of is the date the response was actually fetched (cached responses keep their date);
    `as_of` is only a fallback for items without a fetch time.
    """
    import pandas as pd
    from .ingest import norm_status

    rows = []
    for it in items:
        ipc, main = N.norm_ipc(it.get("ipc", ""))
        rows.append({
            "application_no": N.norm_application_no(it.get("application_no", "")),
            "country": "KR",
            "title": it.get("title", ""),
            "abstract": it.get("abstract", ""),
            "applicants_raw": "|".join(N.split_multi(it.get("applicants_raw", ""))),
            "ipc": ipc,
            "ipc_main": main,
            "application_date": N.norm_date(it.get("application_date")),
            "publication_date": N.norm_date(it.get("publication_date")),
            "registration_date": N.norm_date(it.get("registration_date")),
            "status": norm_status(it.get("status", "")),
            "status_as_of": N.norm_date((it.get("_fetched_at") or as_of)[:10]),
            "source": "kipris-api",
        })
    return conform(pd.DataFrame(rows, columns=[c for c in CANDIDATE_COLUMNS if c != "schema_version"]),
                   CANDIDATE_COLUMNS)
