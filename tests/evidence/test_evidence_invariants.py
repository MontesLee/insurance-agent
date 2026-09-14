"""Evidence layer architecture invariants (V2 Phase 4) — NEGATIVE assertions.

  * Evidence != Recommendation -> the evidence payload must not carry decision fields.
  * Abstention honesty         -> insufficient_evidence must mean an EMPTY evidence list.
  * No free-text injection     -> query text is a pure function of (domain, purpose);
                                  two different callers in the same domain get the SAME query.
  * Read-only loop             -> the requesting artifact is never mutated.
  * Traceability               -> the requesting artifact id appears in related_artifact_ids.

Writes tests/evidence/_evidence_invariants_log.txt; exits non-zero on failure.
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
from evidence import loop as loop_mod  # noqa: E402

CASES_DIR = os.path.join(HERE, "cases")
LOG_PATH = os.path.join(HERE, "_evidence_invariants_log.txt")

# Decision-layer fields that MUST NOT appear in an Evidence artifact.
FORBIDDEN_KEYS = {
    "recommendation",
    "primary_recommendation",
    "candidate_id",
    "candidates",
    "fit",
    "priority",
    "severity",
    "likelihood",
    "residual_risk",
    "gap_level",
}


def _walk_keys(obj, path=""):
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN_KEYS:
                hits.append(f"{path}.{k}")
            hits.extend(_walk_keys(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits.extend(_walk_keys(v, f"{path}[{i}]"))
    return hits


def run():
    with open(os.path.join(CASES_DIR, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)

    lines = []
    all_ok = True

    for case in manifest["cases"]:
        with open(os.path.join(CASES_DIR, case["fixture"]), encoding="utf-8") as f:
            source = json.load(f)
        r = loop_mod.request_evidence(source, source_kind=case["source_kind"])
        fails = []
        ep = (r["evidence"] or {}).get("payload", {}) or {}
        qp = (r["request"] or {}).get("payload", {}) or {}

        # Invariant 1: Evidence != Recommendation.
        hits = _walk_keys(r["evidence"] or {})
        if hits:
            fails.append("decision fields leaked into evidence: " + ", ".join(hits))

        # Invariant 2: abstention honesty.
        if ep.get("status") == "insufficient_evidence" and (ep.get("evidence") or []):
            fails.append("insufficient_evidence but evidence list is not empty")

        # Invariant 3: every evidence item carries the contract-required fields.
        for e in ep.get("evidence") or []:
            missing = [k for k in ("evidence_id", "content", "source", "relevance", "confidence") if k not in e]
            if missing:
                fails.append(f"evidence {e.get('evidence_id')} missing {missing}")

        # Invariant 4: read-only loop.
        if not r["source_unchanged"]:
            fails.append("source artifact was mutated")

        # Invariant 5: canonical labels.
        if (r["evidence"] or {}).get("artifact_type") != "knowledge-evidence":
            fails.append("evidence artifact_type != knowledge-evidence")
        if (r["request"] or {}).get("artifact_type") != "knowledge-query":
            fails.append("request artifact_type != knowledge-query")

        # Invariant 6: traceability back to the requesting artifact.
        src_id = source.get("solution_id") or source.get("gap_id")
        if src_id and src_id not in (qp.get("related_artifact_ids") or []):
            fails.append(f"request does not reference source id {src_id}")

        tag = "PASS" if not fails else "FAIL"
        if fails:
            all_ok = False
        lines.append(f"[{tag}] {case['case_id']}")
        for d in fails:
            lines.append(f"    - {d}")

    # Invariant 7: query is a pure function of (domain, purpose) — no free-text injection.
    a = request_mod.from_gap({"gap_id": "GAP-A", "domain": "medical"}, purpose="POLICY_FACT")
    b = request_mod.from_gap({"gap_id": "GAP-B", "domain": "medical"}, purpose="POLICY_FACT")
    c = request_mod.from_gap({"gap_id": "GAP-A", "domain": "medical"}, purpose="COMPARISON")
    qa, qb, qc = a["payload"]["query"], b["payload"]["query"], c["payload"]["query"]
    det_fails = []
    if qa != qb:
        det_fails.append(f"same (domain,purpose) produced different queries: '{qa}' vs '{qb}'")
    if qa == qc:
        det_fails.append("different purpose produced the same query")
    tag = "PASS" if not det_fails else "FAIL"
    if det_fails:
        all_ok = False
    lines.append(f"[{tag}] query-determinism")
    lines.append(f"        POLICY_FACT='{qa}' | COMPARISON='{qc}'")
    for d in det_fails:
        lines.append(f"    - {d}")

    lines.append("")
    lines.append("RESULT: " + ("ALL GREEN" if all_ok else "FAILURES PRESENT"))
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(run())
