"""Evidence layer dataset runner (V2 Phase 4).

For each case in cases/manifest.json:
  1. load the source artifact (a solution entry / a gap entry / a free-text request)
  2. run ONE controlled Evidence round (Skill -> Evidence Request -> Knowledge Search -> Evidence)
  3. validate the KnowledgeQuery and the KnowledgeEvidence against their Canonical Contracts
  4. assert the per-case checks (domain / purpose / traceability / abstention / conflict /
     no-mutation / evidence presence)

Exit 0 = all cases pass; 1 = any failure. Results are also written to
tests/evidence/_evidence_dataset_log.txt (PowerShell redirection mangles UTF-16).
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from evidence import request as request_mod  # noqa: E402
from evidence import provider as provider_mod  # noqa: E402
from evidence import loop as loop_mod  # noqa: E402

CASES_DIR = os.path.join(HERE, "cases")
LOG_PATH = os.path.join(HERE, "_evidence_dataset_log.txt")


class _FakeResult:
    def __init__(self, d):
        self._d = d

    def to_dict(self):
        return self._d


class FakeConflictEngine:
    """Engine stub emitting a conflicting result set (for conflict-propagation tests)."""

    def search(self, query, top_k=None):
        return _FakeResult(
            {
                "query": query,
                "status": "success",
                "conflict": True,
                "results": [
                    {
                        "chunk_id": "FAKE-A",
                        "document_id": "DOC-A",
                        "document_name": "source-A",
                        "source_type": "kb",
                        "source_level": "A",
                        "section": "s1",
                        "content": "证据 A 的说法",
                        "score": 0.81,
                    },
                    {
                        "chunk_id": "FAKE-B",
                        "document_id": "DOC-B",
                        "document_name": "source-B",
                        "source_type": "kb",
                        "source_level": "B",
                        "section": "s2",
                        "content": "证据 B 的相反说法",
                        "score": 0.79,
                    },
                ],
                "retrieval_metadata": {"candidate_count": 2, "returned_count": 2},
            }
        )


def check_case(case: dict) -> tuple:
    source_kind = case["source_kind"]
    fixture_path = os.path.join(CASES_DIR, case["fixture"])
    with open(fixture_path, encoding="utf-8") as f:
        source = json.load(f)

    engine = FakeConflictEngine() if case.get("engine") == "fake_conflict" else None
    round_result = loop_mod.request_evidence(
        source, source_kind=source_kind, purpose=case.get("purpose"), engine=engine
    )

    fails = []
    c = case.get("checks", {})
    q = round_result["request"]
    qp = q["payload"] if q else {}
    ev = round_result["evidence"]
    ep = ev["payload"] if ev else {}

    if not round_result["ok"]:
        fails.append("round not ok: " + "; ".join(round_result["errors"]))

    if c.get("require_query_valid"):
        ok, errs = provider_mod.validate(q, provider_mod.QUERY_SCHEMA)
        if not ok:
            fails.append("QUERY_INVALID: " + "; ".join(errs))

    if "expected_domain" in c and qp.get("domain") != c["expected_domain"]:
        fails.append(f"domain={qp.get('domain')} != expected {c['expected_domain']}")
    if "expected_purpose" in c and qp.get("purpose") != c["expected_purpose"]:
        fails.append(f"purpose={qp.get('purpose')} != expected {c['expected_purpose']}")
    for aid in c.get("expect_related_contains", []):
        if aid not in (qp.get("related_artifact_ids") or []):
            fails.append(f"related_artifact_ids missing {aid}")
    if "expected_status" in c and ep.get("status") != c["expected_status"]:
        fails.append(f"evidence status={ep.get('status')} != expected {c['expected_status']}")

    n_ev = len(ep.get("evidence") or [])
    if c.get("require_evidence") and n_ev == 0:
        fails.append("evidence expected but empty")
    if c.get("deny_evidence") and n_ev > 0:
        fails.append(f"evidence must be empty on abstention, got {n_ev}")
    if "expected_conflict" in c and bool(ep.get("conflict")) != bool(c["expected_conflict"]):
        fails.append(f"conflict={ep.get('conflict')} != expected {c['expected_conflict']}")
    if c.get("expected_conflict"):
        for e in ep.get("evidence") or []:
            if not e.get("conflict"):
                fails.append(f"evidence {e.get('evidence_id')} did not inherit conflict=True")
    if c.get("source_unchanged") and not round_result["source_unchanged"]:
        fails.append("source artifact was mutated by the evidence loop")

    return (len(fails) == 0, fails, round_result)


def main():
    with open(os.path.join(CASES_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    lines = [f"EVIDENCE DATASET: {len(manifest['cases'])} cases", ""]
    all_ok = True
    for case in manifest["cases"]:
        ok, fails, r = check_case(case)
        qp = r["request"]["payload"] if r["request"] else {}
        ep = r["evidence"]["payload"] if r["evidence"] else {}
        tag = "PASS" if ok else "FAIL"
        if not ok:
            all_ok = False
        lines.append(f"[{tag}] {case['case_id']} | {case.get('intent','')}")
        lines.append(
            f"        query='{qp.get('query','')}' domain={qp.get('domain')} purpose={qp.get('purpose')}"
        )
        lines.append(
            f"        evidence status={ep.get('status')} n={len(ep.get('evidence') or [])} conflict={ep.get('conflict')}"
        )
        for d in fails:
            lines.append(f"    - {d}")
    lines.append("")
    lines.append("RESULT: " + ("ALL GREEN" if all_ok else "FAILURES PRESENT"))

    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
