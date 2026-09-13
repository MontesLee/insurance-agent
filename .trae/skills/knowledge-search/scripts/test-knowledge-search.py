#!/usr/bin/env python3
"""Knowledge Search 单测（7 个 Eval 维度；零依赖，pytest 非必需）。

运行：python scripts/test-knowledge-search.py  → exit 0 全绿 / 1 有 FAIL。
覆盖：recall / precision（top 相关占比）/ ranking / source / abstention / conflict / metadata filter。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# scripts -> knowledge-search -> skills -> .trae -> insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_knowledge_search_dataset as ds


def main():
    results = ds.run_all()
    fails = []
    for n, ok, det in results:
        print(f"[{'PASS' if ok else 'FAIL'}] {n}: {det}")
        if not ok:
            fails.append(n)
    print(f"\nTEST RESULT: {'ALL GREEN' if not fails else 'PROBLEMS ' + str(fails)}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
