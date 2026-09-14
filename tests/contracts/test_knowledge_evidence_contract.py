"""KnowledgeEvidence contract test (Phase 4: real Evidence Provider round-trip).

Instead of validating a static fixture, this runs an actual round through the shared
Evidence Provider: KnowledgeQuery -> knowledge-search engine -> KnowledgeEvidence,
then validates the result against contracts/knowledge-evidence.schema.json.

Also asserts the "Evidence != Recommendation" boundary: no decision fields may appear.
"""
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from evidence.request import build_evidence_request  # noqa: E402
from evidence.provider import provide_evidence  # noqa: E402
from _common import validate  # noqa: E402

# Decision-layer fields that must never appear in an Evidence artifact.
FORBIDDEN_KEYS = {"recommendation", "primary_recommendation", "candidate_id", "fit", "priority"}


def run():
    query = build_evidence_request(
        domain="medical",
        purpose="POLICY_FACT",
        related_artifact_ids=["GAP-R1-001"],
        requester="coverage-gap-analysis",
    )
    artifact, ok, errors = provide_evidence(query, top_k=3)
    if artifact is None:
        return ("knowledge-evidence", False, "; ".join(errors) or "provider returned no artifact")
    if not ok:
        return ("knowledge-evidence", False, "; ".join(errors))

    ok, msgs = validate(artifact, "knowledge-evidence.schema.json")
    if not ok:
        return ("knowledge-evidence", False, "; ".join(msgs))

    p = artifact["payload"]
    hits = [k for k in FORBIDDEN_KEYS if k in p] + [
        k for e in (p.get("evidence") or []) for k in FORBIDDEN_KEYS if k in e
    ]
    if hits:
        return ("knowledge-evidence", False, "decision fields leaked: " + ", ".join(sorted(set(hits))))

    return (
        "knowledge-evidence",
        True,
        f"valid; status={p.get('status')} n={len(p.get('evidence') or [])} conflict={p.get('conflict')}",
    )
