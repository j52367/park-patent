"""Specification full text from KIPRIS publication/grant PDFs.

KIPRIS (`getAnnFullTextInfoSearch` = granted, `getPubFullTextInfoSearch` = published) returns a link
to the gazette PDF. We keep the PDF under pdf/<no>.pdf and write description/<no>.json:
  {"source": "ann"|"pub", "paragraphs": {"0001": "...", ...}, "text": "<cleaned full text>"}

Paragraph numbers in KIPO PDFs sit in the page margin, so text extraction places "[0012]" a little
before or after the sentence it labels. Paragraph text is therefore approximate; quote checks look at
the cited paragraph and its neighbours (paragraph_window).

Needs PyMuPDF (`pip install park-patent[fulltext]`); falls back to pypdf if present.
PDFs are files from an external service — parse them, never execute anything from them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import requests

from .checks import _squash
from .kipris import NEW_BASE_URL

FULLTEXT_OPS = {"ann": "patUtiModInfoSearchSevice/getAnnFullTextInfoSearch",
                "pub": "patUtiModInfoSearchSevice/getPubFullTextInfoSearch"}
_HEADER = re.compile(r"^\s*(등록특허|공개특허|공고특허|등록실용신안|공개실용신안)\s*\d{2}-\d+\s*$")
_MARK = re.compile(r"\[(\d{4})\]")


def pdf_text(path: Path) -> str:
    try:
        import fitz  # PyMuPDF

        with fitz.open(path) as doc:
            return "\n".join(p.get_text() for p in doc)
    except ImportError:
        from pypdf import PdfReader

        return "\n".join(p.extract_text() or "" for p in PdfReader(str(path)).pages)


def parse_spec(text: str) -> dict:
    lines = [l for l in text.splitlines() if not _HEADER.match(l)]
    clean = "\n".join(lines)
    parts = _MARK.split(clean)
    paragraphs = {}
    # parts = [before, "0001", text1, "0002", text2, ...]
    for i in range(1, len(parts) - 1, 2):
        paragraphs.setdefault(parts[i], re.sub(r"\s+", " ", parts[i + 1]).strip())
    return {"paragraphs": paragraphs, "text": re.sub(r"[ \t]+", " ", clean)}


def paragraph_window(spec: dict, number: str, radius: int = 1) -> str:
    """Text of paragraph `number` and its neighbours, markers removed (for quote checks)."""
    try:
        n = int(number)
    except ValueError:
        return ""
    keys = [f"{k:04d}" for k in range(n - radius, n + radius + 1)]
    return " ".join(spec["paragraphs"].get(k, "") for k in keys)


def quote_in_paragraph(spec: dict, number: str, quote: str) -> bool:
    q = _squash(quote)
    return bool(q) and q in _squash(paragraph_window(spec, number))


def fetch(client, application_no: str, out_dir: Path, prefer: str = "ann") -> dict | None:
    """Download (once) and parse the specification. Returns the parsed dict or None if unavailable."""
    desc_dir, pdf_dir = out_dir / "description", out_dir / "pdf"
    desc_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    target = desc_dir / f"{application_no}.json"
    if target.exists():
        return json.loads(target.read_text(encoding="utf-8"))
    import xml.etree.ElementTree as ET

    for kind in ([prefer, "pub"] if prefer == "ann" else ["pub", "ann"]):
        pdf = pdf_dir / f"{application_no}_{kind}.pdf"
        if not pdf.exists():
            try:
                body, _ = client.get(FULLTEXT_OPS[kind], {"applicationNumber": application_no},
                                     base=NEW_BASE_URL, key_param="ServiceKey")
            except Exception:
                continue
            url = (ET.fromstring(body).findtext(".//path") or "").strip()
            if not url:
                continue
            resp = requests.get(url, timeout=60)
            if resp.status_code != 200 or not resp.content.startswith(b"%PDF"):
                continue
            pdf.write_bytes(resp.content)
        spec = parse_spec(pdf_text(pdf))
        if not spec["paragraphs"]:
            continue
        spec["source"] = kind
        target.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
        return spec
    return None
