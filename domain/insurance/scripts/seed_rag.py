#!/usr/bin/env python3
"""Domain Pack → 生产知识库（SQLite）种子脚本。

把 domain/insurance/references/ 经 rag.store 摄取为持久化知识库，
供 knowledge-search / evidence provider 在运行时指向。属运行产物，不计入基线。

用法：
    python seed_rag.py                  # 写到 pack.yaml: rag_seed.output_db
    python seed_rag.py --out kb/my.db  # 显式指定输出
"""
from __future__ import annotations
import argparse
import os
import sqlite3
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PACK_ROOT = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(PACK_ROOT))
sys.path.insert(0, REPO_ROOT)

import yaml  # PyYAML
from rag.store import KnowledgeStore
from build_domain_engine import ingest_pack

DEFAULT_REF = os.path.join(PACK_ROOT, "references")
DEFAULT_DB = os.path.join(PACK_ROOT, "kb", "insurance_kb.sqlite")


def load_pack():
    with open(os.path.join(PACK_ROOT, "pack.yaml"), encoding="utf-8") as f:
        return yaml.safe_load(f)


def main():
    ap = argparse.ArgumentParser(description="Seed Domain Pack corpus into a SQLite KB")
    ap.add_argument("--ref", default=DEFAULT_REF, help="references 目录")
    ap.add_argument("--out", default=None, help="输出 SQLite 路径（默认取 pack.yaml: rag_seed.output_db）")
    args = ap.parse_args()

    out = args.out or load_pack().get("rag_seed", {}).get("output_db", DEFAULT_DB)
    if not os.path.isabs(out):
        out = os.path.join(PACK_ROOT, out)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        os.remove(out)

    store = KnowledgeStore(out)
    total = ingest_pack(store, args.ref)
    store.conn.commit()

    # 与 rag/store 默认 schema 保持一致：验证计数
    n = store.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    print(f"[seed] ingested {total} chunks from {args.ref}")
    print(f"[seed] total chunks in {out}: {n}")
    print(f"[seed] done. Point knowledge-search at this DB via --kb or store path.")


if __name__ == "__main__":
    main()
