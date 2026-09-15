"""Controlled Evidence loop (Phase 4): Skill -> Evidence Request -> Knowledge Search -> Skill.

This is the shape the user asked for in review item 3:

                   ┌→ Knowledge Search
                   │
    Risk ─→ Gap ─→ Solution
                   │
                   └→ Knowledge Search
                            ↓
                    Product Recommendation

i.e. Knowledge Search is a shared Evidence Provider reachable from ANY skill at ANY point,
not "step 6" of a fixed pipeline.

Hard rules enforced here:
  * The loop NEVER mutates the requesting artifact. The caller receives evidence separately
    and decides what to do with it. (`source_unchanged` is asserted by deep comparison.)
  * The loop never decides. It returns KnowledgeEvidence only.
  * Abstention is propagated honestly: insufficient_evidence stays insufficient_evidence.
"""
from __future__ import annotations

import copy
from typing import Any, Optional

from . import request as _request
from . import provider as _provider

DEFAULT_REQUESTER = {
    "gap": "coverage-gap-analysis",
    "solution": "solution",
    "risk": "risk-analysis",
    "text": "orchestrator",
}


def _build_request(source_artifact: Any, source_kind: str, purpose: Optional[str],
                   requester: Optional[str], rules: Optional[dict]):
    rules = rules or _request.load_rules()
    requester = requester or DEFAULT_REQUESTER.get(source_kind, "orchestrator")
    if source_kind == "gap":
        return _request.from_gap(source_artifact, purpose=purpose, requester=requester, rules=rules)
    if source_kind == "solution":
        return _request.from_solution(source_artifact, purpose=purpose, requester=requester, rules=rules)
    if source_kind == "text":
        payload = _request.extract_payload(source_artifact) or {}
        return _request.build_evidence_request(
            domain=payload.get("domain", "general"),
            purpose=purpose or payload.get("purpose", "OTHER"),
            query=payload.get("query"),
            related_artifact_ids=payload.get("related_artifact_ids"),
            requester=requester,
            rules=rules,
        )
    raise ValueError(f"unknown source_kind: {source_kind!r}")


def request_evidence(
    source_artifact: Any,
    source_kind: str = "solution",
    purpose: Optional[str] = None,
    requester: Optional[str] = None,
    top_k: Optional[int] = None,
    engine: Any = None,
    kb_dir: Optional[str] = None,
    rules: Optional[dict] = None,
    do_validate: bool = True,
) -> dict:
    """Run one Evidence round. Returns an EvidenceRound dict (see module docstring)."""
    before = copy.deepcopy(source_artifact)

    query_artifact = _build_request(source_artifact, source_kind, purpose, requester, rules)
    evidence_artifact, ok, errors = _provider.provide_evidence(
        query_artifact,
        top_k=top_k,
        engine=engine,
        kb_dir=kb_dir,
        do_validate=do_validate,
    )

    return {
        "requester": requester or DEFAULT_REQUESTER.get(source_kind, "orchestrator"),
        "source_kind": source_kind,
        "purpose": _request.extract_payload(query_artifact).get("purpose"),
        "request": query_artifact,
        "evidence": evidence_artifact,
        "ok": ok,
        "errors": list(errors),
        "source_unchanged": before == source_artifact,
    }


def request_evidence_batch(
    sources: list,
    source_kind: str = "solution",
    purpose: Optional[str] = None,
    **kwargs,
) -> list:
    """Run one Evidence round per source artifact (each is independent)."""
    return [request_evidence(s, source_kind=source_kind, purpose=purpose, **kwargs) for s in sources]
