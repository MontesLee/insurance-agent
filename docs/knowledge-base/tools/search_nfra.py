# -*- coding: utf-8 -*-
"""NFRA site search via cbircweb/solr/totalStaSerch."""
from __future__ import annotations

import json
import sys

import requests

from fetch_source import UA


def search_nfra(keywords: str, page: int = 1, size: int = 10) -> dict:
    url = "https://www.nfra.gov.cn/cbircweb/solr/totalStaSerch"
    body = {
        "serchType": "1",
        "keyWords": keywords,
        "pageSize": str(size),
        "pageNo": page,
        "type": "",
        "title": keywords,
        "itemName": "",
        "mainType": "",
    }
    r = requests.post(
        url,
        json=body,
        headers={"User-Agent": UA, "Referer": "https://www.nfra.gov.cn/", "Accept": "application/json"},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


if __name__ == "__main__":
    data = search_nfra(sys.argv[1])
    inner = data.get("data") or data
    rows = inner.get("lists") or inner.get("rows") or []
    print("total:", inner.get("total"))
    for row in rows:
        import re

        title = re.sub(r"<[^>]+>", "", row.get("docSubtitle") or row.get("docTitle") or "")
        print(
            json.dumps(
                {
                    "docId": row.get("docId"),
                    "title": title.replace("\n", " ")[:70],
                    "date": (row.get("publishDate") or "")[:10],
                    "itemName": row.get("itemName"),
                    "documentno": row.get("documentno"),
                },
                ensure_ascii=False,
            )
        )
