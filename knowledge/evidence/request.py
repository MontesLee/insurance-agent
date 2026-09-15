"""Canonical KnowledgeQuery builder (Phase 4) — the "Skill -> Evidence Request" side.

Any skill (or the orchestrator) may ask for evidence. This module turns that need into a
Canonical KnowledgeQuery artifact (contracts/knowledge-query.schema.json).

Design rules:
  * Query text is TEMPLATE-GENERATED from (domain, purpose) — see
    evidence/resources/config/evidence-request.rules.json. Callers cannot inject free text,
    so queries are deterministic and no query is invented.
  * The requesting artifact is recorded in `related_artifact_ids` (traceability),
    NOT by stuffing its prose into the query.
  * This module never decides anything — it only formulates a request.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "resources", "config", "evidence-request.rules.json")

VALID_DOMAINS = ("medical", "critical_illness", "accident", "life", "savings", "general")
VALID_PURPOSES = (
    "SOLUTION_VALIDATION",
    "PRODUCT_VALIDATION",
    "POLICY_FACT",
    "MEDICAL_FACT",
    "REGULATORY_FACT",
    "COMPARISON",
    "OTHER",
)


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_payload(artifact: Any) -> Any:
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def build_query_text(domain: str, purpose: str, rules: Optional[dict] = None) -> str:
    rules = rules or load_rules()
    domain = domain if domain in VALID_DOMAINS else "general"
    purpose = purpose if purpose in VALID_PURPOSES else "OTHER"
    base = rules["domain_query_template"][domain]
    suffix = rules["purpose_query_suffix"].get(purpose, "")
    return f"{base} {suffix}".strip()


def build_evidence_request(
    domain: str,
    purpose: str,
    query: Optional[str] = None,
    required_evidence_type: Optional[str] = None,
    related_artifact_ids: Optional[list] = None,
    requester: str = "orchestrator",
    rules: Optional[dict] = None,
) -> dict:
    """Return a canonical KnowledgeQuery envelope."""
    rules = rules or load_rules()
    domain = domain if domain in VALID_DOMAINS else "general"
    purpose = purpose if purpose in VALID_PURPOSES else "OTHER"

    from adapters.base import make_envelope

    payload = {
        "query": query or build_query_text(domain, purpose, rules),
        "domain": domain,
        "purpose": purpose,
        "required_evidence_type": required_evidence_type
        or rules["purpose_default_evidence_type"][purpose],
        "related_artifact_ids": list(related_artifact_ids or []),
    }
    provenance = [
        {"source_type": "REQUESTER", "source_id": requester, "field": "query", "confidence": None}
    ]
    for aid in payload["related_artifact_ids"]:
        provenance.append(
            {"source_type": "ARTIFACT", "source_id": aid, "field": "related_artifact_ids", "confidence": None}
        )
    return make_envelope(
        artifact_type="knowledge-query",
        skill="knowledge-search",
        legacy_skill="knowledge-search",
        payload=payload,
        provenance=provenance,
    )


def from_gap(gap: Any, purpose: Optional[str] = None, requester: str = "coverage-gap-analysis",
             rules: Optional[dict] = None) -> dict:
    """Build an Evidence Request from a single CoverageGap entry."""
    rules = rules or load_rules()
    gap = extract_payload(gap) or {}
    purpose = purpose or rules["default_purpose_by_source"]["gap"]
    ids = [gap["gap_id"]] if gap.get("gap_id") else []
    ids += list(gap.get("related_risk_ids") or [])
    return build_evidence_request(
        domain=gap.get("domain", "general"),
        purpose=purpose,
        related_artifact_ids=ids,
        requester=requester,
        rules=rules,
    )


def from_solution(solution: Any, purpose: Optional[str] = None, requester: str = "solution",
                  rules: Optional[dict] = None) -> dict:
    """Build an Evidence Request from a single SolutionPlan entry."""
    rules = rules or load_rules()
    sol = extract_payload(solution) or {}
    purpose = purpose or rules["default_purpose_by_source"]["solution"]
    ids = [sol["solution_id"]] if sol.get("solution_id") else []
    ids += list(sol.get("related_gap_ids") or [])
    return build_evidence_request(
        domain=_domain_from_solution_type(sol.get("solution_type")),
        purpose=purpose,
        related_artifact_ids=ids,
        requester=requester,
        rules=rules,
    )


def _domain_from_solution_type(solution_type: Optional[str]) -> str:
    return {
        "TERM_LIFE": "life",
        "MEDICAL": "medical",
        "CRITICAL_ILLNESS": "critical_illness",
        "ACCIDENT": "accident",
        "SAVINGS": "savings",
    }.get(solution_type or "", "general")
