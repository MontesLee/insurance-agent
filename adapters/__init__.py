"""Adapter layer (Phase 1 of Insurance Agent V2).

Each adapter converts an EXISTING skill's legacy output into its Canonical Contract
artifact (envelope + payload + provenance). Adapters contain NO business logic — they
only wrap/relabel/normalize. Business logic lives in the skills and is not modified here.
"""
from .base import make_envelope, build_provenance
from .client_intake_adapter import to_canonical as client_profile_from_intake
from .requirement_analysis_adapter import to_canonical as requirement_analysis_from_legacy
from .risk_analysis_adapter import to_canonical as risk_assessment_from_legacy
from .knowledge_search_adapter import to_canonical as knowledge_evidence_from_search
from .recommendation_adapter import to_canonical as product_recommendation_from_legacy
from .report_generation_adapter import to_canonical as insurance_report_from_legacy
from .coverage_gap_analysis_adapter import to_canonical as coverage_gap_analysis_from_engine
from .solution_adapter import to_canonical as solution_plan_from_engine

__all__ = [
    "make_envelope",
    "build_provenance",
    "client_profile_from_intake",
    "requirement_analysis_from_legacy",
    "risk_assessment_from_legacy",
    "knowledge_evidence_from_search",
    "product_recommendation_from_legacy",
    "insurance_report_from_legacy",
    "coverage_gap_analysis_from_engine",
    "solution_plan_from_engine",
]
