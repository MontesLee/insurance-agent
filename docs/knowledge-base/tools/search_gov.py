# -*- coding: utf-8 -*-
"""Search helpers for official sources (gov.cn policy library)."""
from __future__ import annotations

import json
import sys

import requests

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def search_gov_cn(query: str, field: str = "title", n: int = 8) -> list[dict]:
    """Search 中国政府网政策文件库 (国务院文件 + 法律)."""
    url = "https://sousuo.www.gov.cn/search-gov/data"
    params = {
        "t": "zhengcelibrary",
        "q": query,
        "timetype": "timeqb",
        "mint": "",
        "maxt": "",
        "sort": "score",
        "sortType": "1",
        "searchfield": field,
        "p": 1,
        "n": n,
        "inpro": "",
        "bmfl": "",
        "dup": "",
        "orpro": "",
        "docId": "",
        "toChild": "",
    }
    r = requests.get(
        url,
        params=params,
        headers={"User-Agent": UA, "Referer": "https://sousuo.www.gov.cn/"},
        timeout=30,
    )
    r.raise_for_status()
    d = r.json()
    vo = d.get("searchVO", {}) or {}
    items = vo.get("listVO") or []
    if not items:
        for cat in (vo.get("catMap") or {}).values():
            items.extend(cat.get("listVO") or [])
    out = []
    for it in items:
        out.append(
            {
                "title": it.get("title"),
                "puborg": it.get("puborgStr") or it.get("fwdw"),
                "ptime": it.get("ptime") or it.get("pubtimeStr"),
                "url": it.get("url") or it.get("pcurl"),
                "pcode": it.get("pcode"),
            }
        )
    return out


if __name__ == "__main__":
    query = sys.argv[1]
    field = sys.argv[2] if len(sys.argv) > 2 else "title"
    for hit in search_gov_cn(query, field):
        print(json.dumps(hit, ensure_ascii=False))
