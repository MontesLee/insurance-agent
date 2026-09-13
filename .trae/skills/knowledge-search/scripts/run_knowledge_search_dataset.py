#!/usr/bin/env python3
"""Knowledge Search 全量 Eval 回归。

单一真源：evals/cases/dataset-manifest.json（自然用例）
         + 代码内合成用例（source / conflict / metadata / abstention）。
运行：python scripts/run-knowledge-search-dataset.py
run_all() -> list[(name, ok, detail)]；main() 打印并 exit(0/1)。
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from rag.store import KnowledgeStore
from rag.engine import KnowledgeSearchEngine
from rag.models import Chunk

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_DIR = os.path.join(SKILL_DIR, "evals", "fixtures", "kb")
MANIFEST = os.path.join(SKILL_DIR, "evals", "cases", "dataset-manifest.json")


def load_rules():
    r = json.load(open(os.path.join(SKILL_DIR, "resources", "config", "retrieval.rules.json"), encoding="utf-8-sig"))
    r.update(json.load(open(os.path.join(SKILL_DIR, "resources", "config", "ranking.rules.json"), encoding="utf-8-sig")))
    return r


def build_engine(kb_dir=KB_DIR):
    s = KnowledgeStore()
    s.ingest_dir(kb_dir)
    return KnowledgeSearchEngine(s, load_rules())


def _case_conflict():
    s = KnowledgeStore()
    s.add_chunks([
        Chunk("A", "docA", "文档A", "百万医疗险等待期为 30 天，等待期内出险一般不予赔付。", "等待期", "official", "S", "medical"),
        Chunk("B", "docB", "文档B", "百万医疗险等待期为 90 天，等待期内出险一般不予赔付。", "等待期", "official", "S", "medical"),
    ])
    e = KnowledgeSearchEngine(s, load_rules())
    r = e.search("百万医疗险等待期", top_k=5)
    ok = r.conflict and any("30" in c.content for c in r.results) and any("90" in c.content for c in r.results)
    return ok, f"conflict={r.conflict} n={len(r.results)}"


def _case_source_priority():
    s = KnowledgeStore()
    s.add_chunks([
        Chunk("S1", "dS", "官方文件", "百万医疗险是报销型保险，凭医疗费用票据按约定比例报销。", "定义", "official", "S", "medical"),
        Chunk("D1", "dD", "自媒体", "百万医疗险是报销型保险，凭医疗费用票据按约定比例报销。", "定义", "internal", "D", "medical"),
    ])
    e = KnowledgeSearchEngine(s, load_rules())
    r = e.search("百万医疗险是什么", top_k=5)
    order = [c.chunk_id for c in r.results]
    ok = order.index("S1") < order.index("D1")
    return ok, f"order={order}"


def _case_metadata_filter():
    s = KnowledgeStore()
    s.add_chunks([
        Chunk("M1", "dM", "医疗文档", "百万医疗险为报销型，解决大额医疗费用。", "定义", "internal", "B", "medical"),
        Chunk("L1", "dL", "寿险文档", "寿险以身故或全残为给付条件。", "定义", "internal", "B", "life"),
    ])
    e = KnowledgeSearchEngine(s, load_rules())
    r = e.search("百万医疗险报销型", top_k=5, filters={"product_type": "medical"})
    ok = len(r.results) >= 1 and all(c.chunk_id.startswith("M") for c in r.results)
    return ok, f"returned={[c.chunk_id for c in r.results]}"


def _case_abstention():
    s = KnowledgeStore()  # empty store
    e = KnowledgeSearchEngine(s, load_rules())
    r = e.search("百万医疗险和重疾险区别", top_k=5)
    ok = r.status == "insufficient_evidence" and len(r.results) == 0
    return ok, f"status={r.status} n={len(r.results)}"


def run_all():
    engine = build_engine()
    manifest = json.load(open(MANIFEST, encoding="utf-8-sig"))
    out = []
    for c in manifest["cases"]:
        r = engine.search(c["query"], top_k=5)
        cands = set(r.retrieval_metadata.get("candidate_chunk_ids", []))
        exp = c.get("expect_in_candidates", [])
        recall_ok = all(g in cands for g in exp)
        status_ok = (r.status == c.get("expect_status"))
        top_ok = True
        if "expect_top" in c and r.results:
            top_ok = r.results[0].chunk_id in c["expect_top"]
        ok = recall_ok and status_ok and top_ok
        detail = (f"status={r.status} recall={'OK' if recall_ok else 'MISS=' + str(set(exp) - cands)}"
                  f" top={'OK' if top_ok else r.results[0].chunk_id if r.results else 'none'}")
        out.append((c["id"], ok, detail))
    out.append(("conflict_detection", *_case_conflict()))
    out.append(("source_priority", *_case_source_priority()))
    out.append(("metadata_filter", *_case_metadata_filter()))
    out.append(("abstention", *_case_abstention()))
    return out


def main():
    results = run_all()
    fails = [n for n, ok, _ in results if not ok]
    for n, ok, det in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {n}: {det}")
    print(f"\nDATASET RESULT: {'ALL GREEN' if not fails else 'PROBLEMS ' + str(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
