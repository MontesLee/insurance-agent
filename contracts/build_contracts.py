#!/usr/bin/env python3
"""Build the 9 Canonical Contracts for Insurance Agent V2 (Phase 1).

Run: python contracts/build_contracts.py
Produces contracts/*.schema.json and contracts/skill-id-map.json.

Design principle (Phase 1 — boundary only, no business-logic rewrite):
- Every Canonical Artifact is an *envelope* carrying the legacy skill output as `payload`
  plus a canonical label (skill / legacy_skill), a schema_version, a generated_at timestamp,
  and a provenance array.
- For the 6 EXISTING skills, `payload` is intentionally permissive (`{"type":"object"}`):
  their internal shape is already validated by each skill's own output schema + eval suite.
  Phase 1 only establishes the *contract boundary* (skills exchange labeled artifacts, not
  raw files / implicit fields). Deep canonical reshaping happens when each skill is rebuilt
  in later phases.
- For the 3 forward-looking skills (coverage-gap-analysis, solution-plan, knowledge-query)
  and for knowledge-evidence / product-recommendation, the `payload` is strictly defined per
  the V2 architecture spec, so future skill implementations have a concrete target.
- Risk != Coverage Gap: coverage-gap-analysis payload does NOT carry severity/likelihood;
  it references risk_id instead.
- Solution != Product: solution-plan payload forbids concrete product/insurer names
  (enforced by convention + adapter; schema keeps solution_type/objective/coverage_direction).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))

ARTIFACT_TYPES = [
    "client-profile",
    "requirement-analysis",
    "risk-assessment",
    "coverage-gap-analysis",
    "solution-plan",
    "knowledge-query",
    "knowledge-evidence",
    "product-recommendation",
    "insurance-report",
]

PROV_ITEM = {
    "type": "object",
    "required": ["source_type", "source_id", "confidence"],
    "properties": {
        "source_type": {"type": "string"},
        "source_id": {"type": "string"},
        "field": {"type": "string"},
        "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
    },
}


def envelope(artifact_type, payload_schema, description):
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": f"{artifact_type} Canonical Contract",
        "description": description,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "artifact_type",
            "skill",
            "legacy_skill",
            "schema_version",
            "generated_at",
            "payload",
            "provenance",
        ],
        "properties": {
            "artifact_type": {"type": "string", "enum": ARTIFACT_TYPES},
            "skill": {"type": "string", "minLength": 1, "description": "Canonical skill id (kebab-case)."},
            "legacy_skill": {
                "type": "string",
                "minLength": 1,
                "description": "Legacy / physical skill directory name (may be snake_case).",
            },
            "schema_version": {"type": "string", "const": "1.0"},
            "generated_at": {"type": "string", "description": "ISO-8601 timestamp."},
            "payload": payload_schema,
            "provenance": {"type": "array", "items": PROV_ITEM},
        },
    }


LOOSE_PAYLOAD = {
    "type": "object",
    "description": "Phase-1 permissive payload: legacy skill output is wrapped as-is. "
    "Internal shape is already governed by the skill's own output schema + eval suite.",
}


# ---- payload schemas for forward-looking / strictly-defined artifacts ----

COVERAGE_GAP_PAYLOAD = {
    "type": "object",
    "required": ["gaps", "status"],
    "properties": {
        "gaps": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["gap_id", "domain", "current_coverage", "gap_level"],
                "additionalProperties": False,
                "properties": {
                    "gap_id": {"type": "string"},
                    "domain": {
                        "type": "string",
                        "enum": ["medical", "critical_illness", "accident", "life", "savings", "general"],
                    },
                    "subject": {"type": "string"},
                    "related_requirement_ids": {"type": "array", "items": {"type": "string"}},
                    "related_risk_ids": {"type": "array", "items": {"type": "string"}},
                    "current_coverage": {
                        "type": "object",
                        "required": ["status"],
                        "additionalProperties": False,
                        "properties": {
                            "status": {"type": "string", "enum": ["NONE", "PARTIAL", "SUFFICIENT", "UNKNOWN"]},
                            "evidence_refs": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                    "target_coverage": {
                        "type": "object",
                        "required": ["direction"],
                        "additionalProperties": False,
                        "properties": {
                            "direction": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                    },
                    "gap_level": {
                        "type": "string",
                        "enum": ["CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"],
                    },
                    "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "evidence_refs": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
        "priorities": {"type": "array", "items": {"type": "object"}},
        "information_gaps": {"type": "array", "items": {"type": "object"}},
        "status": {
            "type": "string",
            "enum": [
                "COMPLETE",
                "PRELIMINARY",
                "NEED_MORE_INFORMATION",
                "INSUFFICIENT_INFORMATION",
                "FAILED",
            ],
        },
    },
    "description": "Independent business-judgment layer. Risk != Coverage Gap: no severity/likelihood here, "
    "only references to risk_id. Computed from existing_protection + requirements + risk.",
}

SOLUTION_PLAN_PAYLOAD = {
    "type": "object",
    "required": ["objective", "coverage_direction", "priority"],
    "properties": {
        "solution_type": {
            "type": "string",
            "description": "Strategy class, e.g. TERM_LIFE. NOT a concrete product.",
        },
        "objective": {"type": "string", "minLength": 1, "description": "解决目标."},
        "coverage_direction": {
            "type": "string",
            "minLength": 1,
            "description": "保障方向 / 额度与期限逻辑。禁止具体产品名 / 保险公司名。",
        },
        "priority": {"type": "string", "enum": ["P0", "P1", "P2", "P3"]},
        "constraints": {"type": "array", "items": {"type": "object"}},
        "trade_offs": {"type": "array", "items": {"type": "object"}},
        "rejected_directions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"direction": {"type": "string"}, "reason": {"type": "string"}},
            },
        },
        "related_gap_ids": {"type": "array", "items": {"type": "string"}},
        "status": {
            "type": "string",
            "enum": ["COMPLETE", "PRELIMINARY", "NEED_MORE_INFORMATION", "INSUFFICIENT_INFORMATION", "FAILED"],
        },
    },
    "description": "Solution STRATEGY, not product recommendation. No concrete product / insurer names.",
}

KNOWLEDGE_QUERY_PAYLOAD = {
    "type": "object",
    "required": ["query", "domain", "purpose"],
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "domain": {
            "type": "string",
            "enum": ["medical", "critical_illness", "accident", "life", "savings", "general"],
        },
        "purpose": {
            "type": "string",
            "enum": [
                "SOLUTION_VALIDATION",
                "PRODUCT_VALIDATION",
                "POLICY_FACT",
                "MEDICAL_FACT",
                "REGULATORY_FACT",
                "COMPARISON",
                "OTHER",
            ],
        },
        "required_evidence_type": {"type": "string"},
        "related_artifact_ids": {"type": "array", "items": {"type": "string"}},
    },
    "description": "Evidence Provider request. Knowledge Search is a shared provider, not a fixed workflow step.",
}

KNOWLEDGE_EVIDENCE_PAYLOAD = {
    "type": "object",
    "required": ["status", "evidence", "conflict"],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["success", "partial_evidence", "insufficient_evidence", "retrieval_error"],
        },
        "query": {"type": "string"},
        "evidence": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["evidence_id", "content", "source", "relevance", "confidence"],
                "properties": {
                    "evidence_id": {"type": "string"},
                    "content": {"type": "string"},
                    "source": {"type": "string"},
                    "source_type": {"type": "string"},
                    "relevance": {"type": ["number", "null"]},
                    "confidence": {"type": ["number", "null"], "minimum": 0, "maximum": 1},
                    "provenance": {"type": "array"},
                    "conflict": {"type": "boolean"},
                },
            },
        },
        "conflict": {"type": "boolean"},
    },
    "description": "KnowledgeEvidence != Recommendation. Knowledge Search must not carry final decisions.",
}

PRODUCT_RECOMMENDATION_PAYLOAD = {
    "type": "object",
    "required": [
        "status",
        "primary_recommendation",
        "alternatives",
        "not_recommended",
        "evidence_refs",
        "human_review_required",
    ],
    "properties": {
        "status": {
            "type": "string",
            "enum": ["COMPLETE", "INSUFFICIENT_INPUT", "NO_CANDIDATES", "INCOMPLETE_EVIDENCE"],
        },
        "primary_recommendation": {
            "type": ["object", "null"],
            "properties": {
                "candidate_id": {"type": "string"},
                "fit": {"type": "string"},
                "reason_codes": {"type": "array", "items": {"type": "string"}},
                "provenance": {"type": "array"},
            },
        },
        "alternatives": {"type": "array", "items": {"type": "object"}},
        "not_recommended": {"type": "array", "items": {"type": "object"}},
        "tradeoffs": {"type": "array"},
        "uncertainties": {"type": "array"},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
        "human_review_required": {"type": "boolean"},
    },
    "description": "Phase-1 output mirrors legacy recommendation output. The V2 INPUT contract changes in "
    "Phase 5: consumes RequirementAnalysis + RiskAssessment + CoverageGapAnalysis + SolutionPlan + KnowledgeEvidence "
    "instead of the phantom candidate_solutions.",
}


SCHEMAS = {
    "client-profile.schema.json": envelope(
        "client-profile",
        LOOSE_PAYLOAD,
        "Canonical client fact source. Origin: client-intake (CanonicalClientState). Downstream must not modify facts.",
    ),
    "requirement-analysis.schema.json": envelope(
        "requirement-analysis",
        LOOSE_PAYLOAD,
        "Client needs analysis. Origin: requirement_analysis. Note: its legacy coverage_gaps field is a "
        "requirement-level gap hint, NOT the final CoverageGap Artifact.",
    ),
    "risk-assessment.schema.json": envelope(
        "risk-assessment",
        LOOSE_PAYLOAD,
        "Risk identification. Origin: risk-analysis. Legacy coverage_assessment is an auxiliary risk-level coverage "
        "judgment, NOT the final CoverageGap Artifact (owned by coverage-gap-analysis).",
    ),
    "coverage-gap-analysis.schema.json": envelope(
        "coverage-gap-analysis",
        COVERAGE_GAP_PAYLOAD,
        "Independent gap judgment from existing_protection + requirements + risk. Skill not yet implemented (Phase 2).",
    ),
    "solution-plan.schema.json": envelope(
        "solution-plan",
        SOLUTION_PLAN_PAYLOAD,
        "Solution STRATEGY layer (Gap -> Solution). No concrete product / insurer names. Skill not yet implemented.",
    ),
    "knowledge-query.schema.json": envelope(
        "knowledge-query",
        KNOWLEDGE_QUERY_PAYLOAD,
        "Evidence Provider request shape. Knowledge Search is invoked on demand by any skill, not a fixed workflow step.",
    ),
    "knowledge-evidence.schema.json": envelope(
        "knowledge-evidence",
        KNOWLEDGE_EVIDENCE_PAYLOAD,
        "Evidence returned by Knowledge Search. Evidence != Recommendation.",
    ),
    "product-recommendation.schema.json": envelope(
        "product-recommendation",
        PRODUCT_RECOMMENDATION_PAYLOAD,
        "Product candidate recommendation. Legacy name: recommendation. V2 input contract finalized in Phase 5.",
    ),
    "insurance-report.schema.json": envelope(
        "insurance-report",
        LOOSE_PAYLOAD,
        "Final collected/normalized/rendered report. Origin: report-generation. Owns NO business judgment — "
        "only collect / normalize / render / validate.",
    ),
}

SKILL_ID_MAP = {
    "description": "Canonical skill id -> legacy physical skill name. Phase 1 does NOT rename directories; "
    "the map decouples canonical ids from legacy snake_case dirs.",
    "canonical_to_legacy": {
        "client-intake": "client-intake",
        "requirement-analysis": "requirement_analysis",
        "risk-analysis": "risk-analysis",
        "coverage-gap-analysis": None,
        "solution": None,
        "knowledge-search": "knowledge-search",
        "product-recommendation": "recommendation",
        "report-generation": "report-generation",
    },
}


def main():
    for name, schema in SCHEMAS.items():
        path = os.path.join(HERE, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(schema, f, ensure_ascii=False, indent=2)
    with open(os.path.join(HERE, "skill-id-map.json"), "w", encoding="utf-8") as f:
        json.dump(SKILL_ID_MAP, f, ensure_ascii=False, indent=2)
    summary = "\n".join(f"  - {n}" for n in SCHEMAS) + "\n  - skill-id-map.json"
    with open(os.path.join(HERE, "_build_log.txt"), "w", encoding="utf-8") as f:
        f.write("built:\n" + summary + "\n")
    print("BUILT:\n" + summary)


if __name__ == "__main__":
    main()
