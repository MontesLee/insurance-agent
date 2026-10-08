#!/usr/bin/env python3
"""28.C-3 concept-QA retrieval probe (read-only operator tool).

Asks N concept questions through the REAL production retrieval path
(KnowledgeService -> WeKnora -> governance) and reports hit/miss with
traceable evidence. NO LLM, NO gate changes, NO writes.

HIT  = >=1 governed evidence item whose content substantively matches
       the question topic (manual review column included).
MISS = 0 evidence, or evidence unrelated/unsupportive.

Usage: python tools/qa_concept_hit_probe.py [--out tmp/obs/c3_probe.json]
Env: assembled from repo .env + tmp/hd2.* (same as the pilot server).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
if REPO not in sys.path:
    sys.path.insert(0, REPO)

QUESTIONS = [
    "百万医疗险和重疾险有什么区别？",
    "医疗险的免赔额是什么意思？",
    "保险的等待期是什么？",
    "犹豫期是什么意思？买保险后能退吗？",
    "什么是保险的现金价值？",
    "定期寿险和终身寿险有什么区别？",
    "意外险保障什么？和医疗险有什么不同？",
    "保额和保费有什么区别？",
    "什么是健康告知？不如实告知会怎样？",
    "受益人是什么意思？可以指定谁？",
]


def _setup_env() -> None:
    """Pilot-equivalent env (WeKnora + PG) — same sources as
    tmp/_serve_pilot.py; secrets never printed."""
    def priv(name):
        p = os.path.join(REPO, "tmp", name)
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    s = line.strip()
                    if s and not s.startswith("#"):
                        return s
        except OSError:
            return ""
        return ""
    os.environ.setdefault("INSURANCE_AGENT_KNOWLEDGE_PROVIDER", "weknora")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_URL",
                          "http://127.0.0.1:8080")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_API_KEY", priv("hd2.key"))
    os.environ.setdefault("AGENT_PG_PASSWORD", priv("hd2.pgpass"))
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID",
                          "54d7b757-f6e0-4c29-8de0-e40e92d8464a")
    os.environ.setdefault("INSURANCE_AGENT_WEKNORA_SEARCH_METHOD",
                          "vector_search")
    os.environ.setdefault("INSURANCE_AGENT_DATA_KEY", priv("hd2-data.key"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(
        REPO, "tmp", "obs", "c3_probe.json"))
    args = ap.parse_args()
    _setup_env()

    # strict-mode composition (the production path)
    os.environ["INSURANCE_AGENT_MODE"] = "controlled_pilot"
    from knowledge.service import default_service
    svc = default_service()

    rows = []
    for q in QUESTIONS:
        try:
            items, governed, _dec, _ctx = svc.build_evidence(q, top_k=8)
        except Exception as e:  # noqa: BLE001 — recorded, never faked
            rows.append({"question": q, "error": "%s: %s" % (
                type(e).__name__, str(e)[:100])})
            continue
        rows.append({
            "question": q,
            "evidence_count": len(items),
            "grounding_status": getattr(governed, "status", ""),
            "sources": [((it.get("source_name") or
                          it.get("document_name") or "?")[:40])
                        for it in items[:3]],
            "snippets": [ (it.get("content") or "")[:60] for it in items[:2]],
        })
    hits = sum(1 for r in rows if (r.get("evidence_count") or 0) > 0
               and r.get("grounding_status") not in
               ("insufficient_evidence", "retrieval_error"))
    total = len(rows)
    summary = {"total": total, "hits": hits, "misses": total - hits,
               "hit_rate": round(hits / total, 2) if total else 0.0,
               "note": "HIT=governed evidence>=1; substantive relevance "
                       "needs the snippets column (manual review)"}
    out = {"summary": summary, "rows": rows}
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False))
    for r in rows:
        print("%-28s ev=%-2s %s %s" % (
            r["question"][:14], r.get("evidence_count"),
            (r.get("sources") or ["-"])[0][:22],
            r.get("error", "")[:40]))
    print("written: %s" % args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
