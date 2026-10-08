# -*- coding: utf-8 -*-
"""KB-V1 source acquisition helper.

Fetches an official page (or PDF), stores the raw bytes and an
extracted plain-text projection, and prints a verification record
(url / http status / sha256 / byte count / title-line hits).

Usage:
  python docs/knowledge-base/tools/fetch_source.py <doc_id> <url> [--pdf]

Read-only towards runtime; writes only under docs/knowledge-base/.
"""
from __future__ import annotations

import hashlib
import html as html_mod
import io
import re
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "sources" / "raw"
TEXT_DIR = ROOT / "sources" / "text"

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fetch(url: str) -> tuple[int, bytes, str]:
    headers = {
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/pdf,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    }
    r = requests.get(url, headers=headers, timeout=40, verify=True)
    return r.status_code, r.content, r.headers.get("Content-Type", "")


def html_to_text(data: bytes) -> tuple[str, str]:
    """Decode HTML bytes and return (text, title). Best-effort, no deps."""
    # try utf-8 then gbk
    text_body = None
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            text_body = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text_body is None:
        text_body = data.decode("utf-8", errors="replace")

    m = re.search(r"<title[^>]*>(.*?)</title>", text_body, re.S | re.I)
    title = html_mod.unescape(m.group(1)).strip() if m else ""

    # drop script/style
    text_body = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", text_body)
    # block tags -> newline
    text_body = re.sub(r"(?i)</?(p|div|br|tr|li|h[1-6]|table)[^>]*>", "\n", text_body)
    text_body = re.sub(r"(?i)<td[^>]*>", "\t", text_body)
    text_body = re.sub(r"<[^>]+>", "", text_body)
    text_body = html_mod.unescape(text_body)
    text_body = re.sub(r"[ \t　]+", " ", text_body)
    text_body = re.sub(r"\n\s*\n+", "\n", text_body)
    return text_body.strip(), title


def pdf_to_text(data: bytes) -> tuple[str, str]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return "", ""
    try:
        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n".join(pages), ""
    except Exception as exc:  # noqa: BLE001
        return f"[pdf extract failed: {exc}]", ""


def main() -> int:
    doc_id = sys.argv[1]
    url = sys.argv[2]
    is_pdf = "--pdf" in sys.argv[3:]

    status, data, ctype = fetch(url)
    if status != 200:
        print(f"RESULT: HTTP {status} ctype={ctype} bytes={len(data)}")
        return 1

    raw_ext = ".pdf" if (is_pdf or "pdf" in ctype.lower()) else ".html"
    raw_path = RAW_DIR / f"{doc_id}{raw_ext}"
    raw_path.write_bytes(data)

    if raw_ext == ".pdf":
        text, title = pdf_to_text(data)
    else:
        text, title = html_to_text(data)

    text_path = TEXT_DIR / f"{doc_id}.txt"
    text_path.write_text(text, encoding="utf-8")

    print(f"RESULT: HTTP {status}")
    print(f"  url: {url}")
    print(f"  ctype: {ctype}")
    print(f"  bytes: {len(data)}")
    print(f"  sha256: {sha256_bytes(data)}")
    print(f"  title: {title[:120]}")
    print(f"  text_chars: {len(text)}")
    print(f"  raw: {raw_path.name}")
    head = text[:400].replace("\n", " | ")
    print(f"  head: {head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
