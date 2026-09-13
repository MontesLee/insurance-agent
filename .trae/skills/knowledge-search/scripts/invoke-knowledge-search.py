#!/usr/bin/env python3
"""Knowledge Search 调用入口（CLI + importable API）。

读取外置 rules，构建 store（默认最小测试 KB），执行检索，
输出符合 knowledge-search-output.schema.json 的 JSON。
"""
import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rag.store import KnowledgeStore
from rag.engine import KnowledgeSearchEngine

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_KB = os.path.join(SKILL_DIR, "evals", "fixtures", "kb")
RET_RULES = os.path.join(SKILL_DIR, "resources", "config", "retrieval.rules.json")
RK_RULES = os.path.join(SKILL_DIR, "resources", "config", "ranking.rules.json")


def load_rules():
    rules = json.load(open(RET_RULES, encoding="utf-8-sig"))
    rules.update(json.load(open(RK_RULES, encoding="utf-8-sig")))
    return rules


def build_engine(kb_dir=DEFAULT_KB):
    store = KnowledgeStore()
    store.ingest_dir(kb_dir)
    return KnowledgeSearchEngine(store, load_rules())


def search(query, top_k=5, min_relevance=None, filters=None, debug=False, kb_dir=DEFAULT_KB):
    engine = build_engine(kb_dir)
    return engine.search(query, top_k=top_k, min_relevance=min_relevance,
                         filters=filters, debug=debug)


def main():
    ap = argparse.ArgumentParser(description="Knowledge Search")
    ap.add_argument("--query", required=True)
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--min-relevance", type=float, default=None)
    ap.add_argument("--kb", default=DEFAULT_KB)
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    result = search(args.query, top_k=args.top_k, min_relevance=args.min_relevance,
                    debug=args.debug, kb_dir=args.kb)
    out = result.to_dict()
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from validate_retrieval import validate_output
        validate_output(out)
    except Exception as e:  # noqa: BLE001 - validation warning must not break output
        out["_validation_warning"] = str(e)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
