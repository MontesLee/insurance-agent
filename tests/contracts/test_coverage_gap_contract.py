"""CoverageGapAnalysis contract test (Phase 2: now backed by the real skill).

Runs coverage-gap-analysis engine on a realistic composite input, wraps the output through
the Canonical adapter, and validates against contracts/coverage-gap-analysis.schema.json.
Proves the contract is satisfiable by the actual skill AND that the canonical shape enforces:
independent gap judgment, current_coverage.status enum, gap_level enum, and NO risk-layer
fields (Risk != Coverage Gap).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from adapters.coverage_gap_analysis_adapter import to_canonical as coverage_gap_analysis_from_engine  # noqa: E402
from _common import validate  # noqa: E402

SKILL_SCRIPTS = os.path.join(
    REPO, ".trae", "skills", "coverage-gap-analysis", "scripts"
)
if SKILL_SCRIPTS not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS)

from coverage_gap_engine import analyze, load_rules  # noqa: E402


def _composite_input():
    return {
        "client_profile": {"client_id": "C001", "existing_protection": "社保 + 百万医疗"},
        "requirement_analysis": {
            "requirements": [
                {"requirement_id": "REQ-LIFE", "requirement_type": "life", "summary": "责任", "priority": "P0_CRITICAL", "boundary": "requirement_only"},
                {"requirement_id": "REQ-MED", "requirement_type": "medical", "summary": "医疗", "priority": "P1_HIGH", "boundary": "requirement_only"},
            ]
        },
        "risk_assessment": {
            "analysis_status": "FORMAL",
            "overall_confidence": 0.85,
            "risks": [
                {
                    "risk_id": "R4-001",
                    "risk_category": "R4",
                    "risk_name": "身故责任",
                    "priority": "P0",
                    "severity": "CRITICAL",
                    "likelihood": "MEDIUM",
                    "residual_risk": "HIGH",
                    "existing_protection": "无",
                    "coverage_assessment": {"protected_amount": 0, "unprotected_amount": 2000000, "confidence": 0.8},
                    "reasoning_evidence_refs": ["E004"],
                },
                {
                    "risk_id": "R1-001",
                    "risk_category": "R1",
                    "risk_name": "医疗",
                    "priority": "P1",
                    "severity": "HIGH",
                    "likelihood": "HIGH",
                    "residual_risk": "HIGH",
                    "existing_protection": "百万医疗已配置",
                    "coverage_assessment": {"protected_amount": 200000, "unprotected_amount": 300000, "confidence": 0.6},
                    "reasoning_evidence_refs": ["E001"],
                },
            ],
        },
    }


def run():
    data = _composite_input()
    rules = load_rules()
    payload = analyze(data["client_profile"], data["requirement_analysis"], data["risk_assessment"], rules)
    provenance = [
        {"source_type": "RISK", "source_id": g["related_risk_ids"][0], "confidence": g.get("confidence")}
        for g in payload["gaps"]
    ]
    artifact = coverage_gap_analysis_from_engine(payload, provenance=provenance)

    ok, msgs = validate(artifact, "coverage-gap-analysis.schema.json")
    if not ok:
        return ("coverage-gap-analysis", False, "; ".join(msgs))

    # extra invariants: engine output must not carry risk-layer quantities.
    forbidden = {"severity", "likelihood", "residual_risk", "risk_priority"}
    flat = str(payload)
    leaked = [k for k in forbidden if f'"{k}"' in flat]
    if leaked:
        return ("coverage-gap-analysis", False, "risk-layer keys leaked: " + ", ".join(leaked))
    return ("coverage-gap-analysis", True, f"gaps={len(payload['gaps'])} status={payload['status']}")
