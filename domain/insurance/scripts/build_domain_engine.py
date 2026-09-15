#!/usr/bin/env python3
"""Domain Pack 引擎装配（thin consumer over rag + knowledge-search rules）.

把 domain/insurance/references/ 当作权威生产语料，构建 KnowledgeSearchEngine。
本脚本只读消费 knowledge-search 的 rules，不修改任何 Skill。

用法（作为库）：
    from build_domain_engine import build_domain_engine
    engine = build_domain_engine()           # 用 references/ 默认语料
    engine = build_domain_engine(kb_dir=...)  # 指定语料目录

用法（CLI）：
    python build_domain_engine.py --query "重疾险 等待期" --top-k 3
"""
from __future__ import annotations
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.dirname(HERE)                      # domain/insurance
REPO_ROOT = os.path.dirname(os.path.dirname(PACK_ROOT))  # parents[3] from script
sys.path.insert(0, REPO_ROOT)

from knowledge.rag.store import KnowledgeStore, chunk_markdown       # noqa: E402
from knowledge.rag.engine import KnowledgeSearchEngine              # noqa: E402

KS_SKILL = os.path.join(REPO_ROOT, ".trae", "skills", "knowledge-search")
RET_RULES = os.path.join(KS_SKILL, "resources", "config", "retrieval.rules.json")
RK_RULES = os.path.join(KS_SKILL, "resources", "config", "ranking.rules.json")
DEFAULT_KB = os.path.join(PACK_ROOT, "references")

_MARKER_RE = __import__("re").compile(r"<!--\s*domain-pack:\s*(.*?)\s*-->")
_KV_RE = __import__("re").compile(r"(\w+)=(\S+)")


def parse_marker(text: str) -> dict:
    """解析 references 文件头的 domain-pack 标记（version/effective_date/source_level/code）。"""
    m = _MARKER_RE.search(text)
    if not m:
        return {}
    return dict(_KV_RE.findall(m.group(1)))


def ingest_pack(store, ref_dir: str) -> int:
    """按 Domain Pack 标记中的 code 作为权威 product_type 摄取语料（覆盖文件名前缀启发式）。"""
    total = 0
    for fn in sorted(os.listdir(ref_dir)):
        if not fn.lower().endswith((".md", ".txt")):
            continue
        path = os.path.join(ref_dir, fn)
        text = open(path, encoding="utf-8-sig").read()
        meta = parse_marker(text)
        doc_id = os.path.splitext(fn)[0]
        chunks = chunk_markdown(
            text, doc_id, doc_id,
            source_type="internal",
            source_level=meta.get("source_level", "B"),
            product_type=meta.get("code", ""),
            topic=meta.get("code", ""),
        )
        store.add_chunks(chunks)
        total += len(chunks)
    return total


def load_rules() -> dict:
    rules = json.load(open(RET_RULES, encoding="utf-8-sig"))
    rules.update(json.load(open(RK_RULES, encoding="utf-8-sig")))
    return rules


def build_domain_engine(kb_dir: str = DEFAULT_KB):
    """Build a KnowledgeSearchEngine over the Domain Pack corpus (default: references/)."""
    store = KnowledgeStore()
    ingest_pack(store, kb_dir)
    return KnowledgeSearchEngine(store, load_rules())


def search(query, top_k=5, min_relevance=None, filters=None, debug=False, kb_dir=DEFAULT_KB):
    engine = build_domain_engine(kb_dir)
    return engine.search(query, top_k=top_k, min_relevance=min_relevance,
                         filters=filters, debug=debug)


def main():
    ap = argparse.ArgumentParser(description="Domain Pack engine (insurance)")
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--product-type", default=None, help="可选过滤：medical/critical/...")
    ap.add_argument("--kb", default=DEFAULT_KB)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    filters = {"product_type": args.product_type} if args.product_type else None
    result = search(args.query, top_k=args.top_k, filters=filters,
                    debug=args.debug, kb_dir=args.kb)
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
