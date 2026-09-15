"""Structure Integrity Test — repository architecture invariants.

Verifies the directory contract documented in docs/repository-structure.md.
This is an architecture-level test: it checks the invariants that other
tests, scripts and the orchestrator rely on — NOT a hardcoded inventory
of every file in the repository.

Exit 0 = all invariants hold.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))  # tests/structure -> repo root

CHECKS = []


def _check(name, ok):
    CHECKS.append((name, bool(ok)))


def _repo(*parts):
    return os.path.join(REPO, *parts)


def main():
    # 1-11: directories that must exist -----------------------------------
    for rel in (
        "runtime",
        os.path.join("runtime", "state"),
        os.path.join("knowledge", "rag"),
        os.path.join("knowledge", "evidence"),
        os.path.join(".trae", "skills"),
        "contracts",
        "catalog",
        "tests",
        "test-cases",
        "evals",
        "docs",
    ):
        _check(f"exists: {rel}", os.path.isdir(_repo(rel)))

    # 12-16: legacy locations that must be gone ----------------------------
    for rel in (
        "workflow",
        "state",
        "rag",
        "evidence",
        os.path.join("scripts", "run-regression.ps1"),
    ):
        _check(f"gone:   {rel}", not os.path.exists(_repo(rel)))

    # 17-18: frozen / versioned anchors ------------------------------------
    _check("frozen: .trae/skills/requirement_analysis",
           os.path.isdir(_repo(".trae", "skills", "requirement_analysis")))
    _check("catalog: product-catalog.v0.1.json",
           os.path.isfile(_repo("catalog", "product-catalog.v0.1.json")))

    # 19-21: entrypoints ----------------------------------------------------
    _check("entrypoint: runtime/orchestrator.py",
           os.path.isfile(_repo("runtime", "orchestrator.py")))
    _check("workflow-def: runtime/insurance-analysis.yaml",
           os.path.isfile(_repo("runtime", "insurance-analysis.yaml")))
    _check("entrypoint: demo.py", os.path.isfile(_repo("demo.py")))

    failures = [(n, ok) for n, ok in CHECKS if not ok]
    for name, ok in CHECKS:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    total = len(CHECKS)
    print(f"STRUCTURE INTEGRITY: {total - len(failures)}/{total} PASS")
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
