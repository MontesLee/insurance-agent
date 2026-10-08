# -*- coding: utf-8 -*-
"""Crawl NFRA 政策规章规范性文件 index (itemId=928) for current-status verification."""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

from fetch_source import UA

KB = Path(__file__).resolve().parents[1]
OUT = KB / "evidence" / "nfra_rules_index.json"

BASE = (
    "https://www.nfra.gov.cn/cn/static/data/DocInfo/SelectDocByItemIdAndChild/"
    "data_itemId=928,pageIndex={page},pageSize=18.json"
)


def main() -> None:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Referer": "https://www.nfra.gov.cn/"})
    rows: list[dict] = []
    page = 1
    total = None
    while True:
        r = s.get(BASE.format(page=page), timeout=25)
        r.raise_for_status()
        d = r.json()["data"]
        total = d["total"]
        batch = d["rows"]
        if not batch:
            break
        rows.extend(batch)
        print(f"page {page}: +{len(batch)} (total {total})", flush=True)
        if len(rows) >= total:
            break
        page += 1
        time.sleep(0.8)
    OUT.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    print(f"saved {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()
