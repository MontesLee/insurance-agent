"""Insurance knowledge governance package — Phase 14.3.

Provider-independent validation layer between the KnowledgeProvider
boundary and evidence. This package must never import a concrete
provider implementation (mock/weknora) — only the shared hit surface;
enforced by tests/runtime/test_p14_governance.py (G12).
"""
from .model import (AUTHORITY_LEVELS, LICENSE_STATUSES,
                    JURISDICTION_NATIONAL, STATUS_CURRENT, STATUS_EXPIRED,
                    STATUS_FUTURE, STATUS_UNKNOWN, GovernanceDecision,
                    QueryContext, RegistryError)
from .registry import SourceRegistry
from .governance import (build_evidence_item, expected_version_id,
                         govern_search_result, validate_hit)
from .provenance import (decision_evidence_refs,
                         is_no_evidence_required, scan_chain_of_thought,
                         validate_decision_provenance, validate_provenance)

__all__ = [
    "SourceRegistry", "QueryContext", "GovernanceDecision", "RegistryError",
    "validate_hit", "govern_search_result", "build_evidence_item",
    "expected_version_id",
    "AUTHORITY_LEVELS", "LICENSE_STATUSES", "JURISDICTION_NATIONAL",
    "STATUS_CURRENT", "STATUS_EXPIRED", "STATUS_FUTURE", "STATUS_UNKNOWN",
    "validate_provenance", "validate_decision_provenance",
    "decision_evidence_refs", "is_no_evidence_required",
    "scan_chain_of_thought",
]
