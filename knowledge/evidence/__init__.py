"""Evidence layer (V2 Phase 4) — shared Evidence Provider.

Knowledge Search is NOT a fixed workflow step. It is a shared provider reachable from any
skill via a controlled loop:

    Skill --(Evidence Request: KnowledgeQuery)--> Knowledge Search --> KnowledgeEvidence --> Skill

Modules:
    evidence.request   build a canonical KnowledgeQuery from a solution / gap / free text
    evidence.provider  KnowledgeQuery -> knowledge-search engine -> canonical KnowledgeEvidence
    evidence.loop      one controlled round (asserts the caller's artifact is never mutated)

Nothing here decides anything: Evidence != Recommendation.
"""
from . import request, provider, loop
from .request import build_evidence_request, from_gap, from_solution, build_query_text, load_rules
from .provider import provide_evidence, build_engine, validate
from .loop import request_evidence, request_evidence_batch

__all__ = [
    "request",
    "provider",
    "loop",
    "build_evidence_request",
    "from_gap",
    "from_solution",
    "build_query_text",
    "load_rules",
    "provide_evidence",
    "build_engine",
    "validate",
    "request_evidence",
    "request_evidence_batch",
]
