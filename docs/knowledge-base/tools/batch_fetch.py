# -*- coding: utf-8 -*-
"""Batch fetch assigned gov.cn sources, verify markers, record results."""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_source import UA, fetch, html_to_text, sha256_bytes  # noqa: E402

KB = Path(__file__).resolve().parents[1]
RAW = KB / "sources" / "raw"
TEXT = KB / "sources" / "text"
RESULTS = KB / "evidence" / "fetch_results.json"


def strip_em(s: str) -> str:
    return re.sub(r"\s+", "", s or "")


def main() -> int:
    only = sys.argv[1:] or None
    assign = json.loads((KB / "evidence" / "url_assignments.json").read_text(encoding="utf-8"))
    results = json.loads(RESULTS.read_text(encoding="utf-8")) if RESULTS.exists() else {}
    for doc_id, meta in assign.items():
        if doc_id.startswith("_"):
            continue
        if only and doc_id not in only:
            continue
        if doc_id in results and results[doc_id].get("http_status") == 200 and results[doc_id].get("markers_ok"):
            continue
        url = meta["url"]
        try:
            status, data, ctype = fetch(url)
        except Exception as exc:  # noqa: BLE001
            results[doc_id] = {"url": url, "error": str(exc)[:200]}
            print(f"{doc_id}: FETCH ERROR {exc}")
            continue
        rec: dict = {"url": url, "http_status": status, "ctype": ctype, "bytes": len(data)}
        if status == 200:
            text, title = html_to_text(data)
            (RAW / f"{doc_id}.html").write_bytes(data)
            (TEXT / f"{doc_id}.txt").write_text(text, encoding="utf-8")
            compact = strip_em(text)
            checks = {m: (strip_em(m) in compact) for m in meta.get("markers", [])}
            rec.update(
                {
                    "sha256": sha256_bytes(data),
                    "page_title": title[:100],
                    "text_chars": len(text),
                    "marker_checks": checks,
                    "markers_ok": all(checks.values()),
                }
            )
            print(f"{doc_id}: HTTP 200 {len(data)}B text={len(text)} markers={'OK' if all(checks.values()) else checks}")
        else:
            print(f"{doc_id}: HTTP {status}")
        results[doc_id] = rec
        RESULTS.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        time.sleep(2.0)
    print("saved ->", RESULTS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
