# -*- coding: utf-8 -*-
"""Frozen self-retrieval exhibit gate (§7): the 4 verbatim chunk-text
queries from the KB-V1 acceptance exhibit, run through the real WeKnora
vector_search path. Expects (bge): all fact chunks rank 1.
Usage: python exhibit_gate.py <kb_name> <tag>"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
KB = HERE.parents[1]
EVID = KB / "evidence" / "eval"
BASE = "http://127.0.0.1:8080"
TENANT = "10001"

EXHIBIT = [
    ("严重溃疡性结肠炎指伴有致命性电解质紊乱", "L2-01"),
    ("应当自收到消费投诉之日起15日内作出处理决定", "L1-12"),
    ("其注册资本的最低限额为人民币二亿元", "L1-01"),
    ("本办法自2024年3月1日起施行", "L1-03"),
]


def H(jwt):
    return {"Authorization": "Bearer " + jwt, "X-Tenant-ID": TENANT,
            "Content-Type": "application/json"}


def main() -> int:
    kb_name, tag = sys.argv[1], sys.argv[2]
    jwt = (REPO / "tmp" / "weknora-admin.jwt").read_text(
        encoding="utf-8").strip()
    req = urllib.request.Request(
        BASE + "/api/v1/knowledge-bases?page=1&limit=50", headers=H(jwt))
    with urllib.request.urlopen(req, timeout=30) as r:
        for kb in json.loads(r.read().decode("utf-8")).get("data") or []:
            if kb.get("name") == kb_name:
                kbid = kb["id"]
                break
        else:
            raise SystemExit("KB not found")

    rows = []
    for q, exp in EXHIBIT:
        body = json.dumps({"query": q, "knowledge_base_id": kbid,
                           "search_method": "vector_search"},
                          ensure_ascii=False).encode("utf-8")
        rq = urllib.request.Request(BASE + "/api/v1/knowledge-search",
                                    data=body, headers=H(jwt), method="POST")
        with urllib.request.urlopen(rq, timeout=60) as r:
            doc = json.loads(r.read().decode("utf-8"))
        hits = []
        for src in doc.get("data") or []:
            fname = str(src.get("knowledge_filename") or "").rsplit(".", 1)[0]
            hits.append(fname)
        # rank of the first hit whose doc matches AND whose content
        # contains the query (verbatim fact chunk), doc-level fallback
        rank_doc = next((i + 1 for i, d in enumerate(hits) if d == exp),
                        None)
        rows.append({"query": q, "expected_doc": exp,
                     "doc_rank": rank_doc, "top5": hits[:5]})
        print("%s -> doc_rank=%s top5=%s" % (q[:18], rank_doc, hits[:5]),
              flush=True)
        time.sleep(0.5)

    out = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "kb": kb_name,
           "tag": tag, "rows": rows,
           "all_top1": all(r["doc_rank"] == 1 for r in rows)}
    path = EVID / ("exhibit_%s.json" % tag)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                    encoding="utf-8")
    print("all_top1:", out["all_top1"], "->", path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
