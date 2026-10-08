# -*- coding: utf-8 -*-
"""Fetch an NFRA document by docId from its static JSON endpoint."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_source import UA, html_to_text, sha256_bytes  # noqa: E402

KB = Path(__file__).resolve().parents[1]
RAW = KB / "sources" / "raw"
TEXT = KB / "sources" / "text"
RESULTS = KB / "evidence" / "fetch_results.json"


def fetch_nfra(doc_id_label: str, nfra_doc_id: str) -> dict:
    url = (
        "https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectByDocId/"
        f"data_docId={nfra_doc_id}.json"
    )
    r = requests.get(
        url, headers={"User-Agent": UA, "Referer": "https://www.nfra.gov.cn/"}, timeout=30
    )
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data") or {}

    doc_title = (data.get("docTitle") or "").replace("\n", "")
    clob = data.get("docClob") or ""
    # strip outer html wrapper already handled by html_to_text
    text, _ = html_to_text(clob.encode("utf-8"))
    header = (
        f"标题: {doc_title}\n"
        f"发布日期: {data.get('publishDate')}\n"
        f"来源: {data.get('docSource')}\n"
        f"NFRA docId: {nfra_doc_id}\n"
        f"官方页面: https://www.nfra.gov.cn/cn/view/pages/ItemDetail.html"
        f"?docId={nfra_doc_id}&itemId=925&generaltype=0\n"
        + "-" * 40 + "\n"
    )
    full = header + text
    (TEXT / f"{doc_id_label}.txt").write_text(full, encoding="utf-8")
    raw_payload = json.dumps(payload, ensure_ascii=False)
    (RAW / f"{doc_id_label}.json").write_text(raw_payload, encoding="utf-8")

    rec = {
        "url": url,
        "official_page": header.splitlines()[3] if len(header.splitlines()) > 3 else "",
        "http_status": 200,
        "nfra_doc_id": nfra_doc_id,
        "nfra_doc_title": doc_title,
        "publish_date": data.get("publishDate"),
        "text_chars": len(full),
        "sha256": hashlib.sha256(raw_payload.encode("utf-8")).hexdigest(),
    }
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    results[doc_id_label] = rec
    RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return rec


if __name__ == "__main__":
    label, doc_id = sys.argv[1], sys.argv[2]
    print(json.dumps(fetch_nfra(label, doc_id), ensure_ascii=False, indent=1))
