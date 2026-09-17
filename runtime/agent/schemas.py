"""Agent schemas (Phase 2.6) — JSON Schema for tool inputs.

The decision channel is a NATIVE tool call (spec §10/§14): the model must call
`agent_decide` with one of {ask_user, call_tool, finish}. Tool arguments are
validated with jsonschema BEFORE execution; invalid output costs one of the two
bounded retries (§34) — never executed blind.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# the decision tool (always present in the tool list)
# --------------------------------------------------------------------------- #
AGENT_DECIDE = {
    "name": "agent_decide",
    "description": "Report your decision for this step. Always set `intent` on the FIRST decision of a turn.",
    "parameters": {
        "type": "object",
        "required": ["action"],
        "properties": {
            "intent": {
                "type": "string",
                "enum": ["GENERAL_KNOWLEDGE", "GENERAL_GUIDANCE", "CLIENT_ADVISORY",
                         "PRODUCT_LOOKUP", "TASK_EXECUTION"],
                "description": "User's top-level intent this turn",
            },
            "action": {"type": "string", "enum": ["ask_user", "call_tool", "finish"]},
            "reason": {"type": "string", "maxLength": 200,
                       "description": "Short decision rationale — NOT chain-of-thought"},
            "message": {"type": "string", "maxLength": 1200,
                        "description": "User-facing message (ask_user / finish)"},
            "required_fields": {"type": "array", "maxItems": 8, "items": {"type": "string"},
                                "description": "Missing facts to ask for (ask_user)"},
            "tool": {"type": "string",
                     "description": "Tool to call (call_tool) — must be a known tool name"},
            "arguments": {"type": "object",
                          "description": "Tool arguments (call_tool)"},
        },
        "additionalProperties": False,
    },
}

# --------------------------------------------------------------------------- #
# client fact extraction (dialogue-skill tools) — minimal, provenance-safe
# --------------------------------------------------------------------------- #
_FIELD = {
    "type": "object",
    "properties": {
        "value": {"type": ["string", "number", "null"]},
        "status": {"type": "string", "enum": ["KNOWN", "UNKNOWN", "ESTIMATED", "ASSUMED"]},
        "source": {"type": "string"},
        "confidence": {"type": ["string", "number", "null"]},
    },
}

RECORD_CLIENT_PROFILE = {
    "name": "record_client_profile",
    "description": (
        "Store the client facts you have extracted from the conversation into the "
        "canonical ClientProfile (the client-intake dialogue skill's role). Only "
        "include facts the user actually stated; mark the rest UNKNOWN."),
    "parameters": {
        "type": "object",
        "properties": {
            "family_profile": {"type": "object"},
            "financial_profile": {"type": "object"},
            "existing_protection": {"type": "object"},
            "notes_for_unknown": {"type": "array", "items": {"type": "string"},
                                  "description": "Fields the user has not provided yet"},
        },
    },
}

RECORD_REQUIREMENT_ANALYSIS = {
    "name": "record_requirement_analysis",
    "description": (
        "Store the requirement analysis derived from what the user said "
        "(the requirement-analysis dialogue skill's role). Requirements must map "
        "to the user's stated concerns — never invent needs."),
    "parameters": {
        "type": "object",
        "required": ["requirements"],
        "properties": {
            "requirements": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["requirement_id", "requirement_type", "summary", "priority"],
                    "properties": {
                        "requirement_id": {"type": "string"},
                        "requirement_type": {"type": "string",
                                             "enum": ["medical", "critical_illness",
                                                      "accident", "death",
                                                      "savings", "other"]},
                        "summary": {"type": "string", "maxLength": 120},
                        "priority": {"type": "string",
                                     "enum": ["P1_HIGH", "P2_MEDIUM", "P3_LOW"]},
                        "reason": {"type": "string", "maxLength": 300},
                    },
                },
            },
        },
    },
}

RECORD_RISK_ASSESSMENT = {
    "name": "record_risk_assessment",
    "description": (
        "Store the risk assessment derived from the user's stated situation "
        "(the risk-analysis dialogue skill's role). Base severity/likelihood on "
        "stated facts only."),
    "parameters": {
        "type": "object",
        "required": ["risks"],
        "properties": {
            "overall_confidence": {"type": "number"},
            "risks": {
                "type": "array", "minItems": 1,
                "items": {
                    "type": "object",
                    "required": ["risk_id", "risk_category", "risk_name", "priority"],
                    "properties": {
                        "risk_id": {"type": "string"},
                        "risk_category": {"type": "string",
                                          "enum": ["R1_medical", "R2_critical_illness",
                                                   "R3_accident", "R4_death",
                                                   "R5_savings"]},
                        "risk_name": {"type": "string", "maxLength": 80},
                        "priority": {"type": "string",
                                     "enum": ["P0_CRITICAL", "P1_HIGH", "P2_MEDIUM", "P3_LOW"]},
                        "severity": {"type": "string"},
                        "likelihood": {"type": "string"},
                        "reason": {"type": "string", "maxLength": 300},
                    },
                },
            },
        },
    },
}

# --------------------------------------------------------------------------- #
# downstream deterministic stage runners — arguments are empty; the runtime
# assembles stage inputs from CaseState exactly like the workflow does
# --------------------------------------------------------------------------- #
def _stage_runner(name: str, description: str) -> dict:
    return {"name": name, "description": description,
            "parameters": {"type": "object", "properties": {}}}

RUN_COVERAGE_GAP = _stage_runner(
    "coverage_gap_analysis", "Run the deterministic coverage-gap engine over the "
    "stored client facts / requirements / risks.")
RUN_SOLUTION = _stage_runner(
    "solution", "Run the deterministic solution engine over the coverage gaps.")
RUN_PRODUCT_CANDIDATES = _stage_runner(
    "product_candidate_provider", "Filter the DEMO product catalog for admissible "
    "candidates (includes the knowledge-search evidence round-trip).")
RUN_RECOMMENDATION = _stage_runner(
    "recommendation", "Run the deterministic recommendation engine.")
RUN_REPORT = _stage_runner(
    "report_generation", "Generate the final insurance analysis report artifact.")

KNOWLEDGE_SEARCH = {
    "name": "knowledge_search",
    "description": ("Search the insurance knowledge base (RAG evidence provider). "
                    "Returns evidence chunks with document ids — cite them; say the "
                    "catalog/KB has no answer when it doesn't."),
    "parameters": {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string", "maxLength": 200}},
    },
}

CHECK_CATALOG_PRODUCT = {
    "name": "check_catalog_product",
    "description": ("Check whether a product exists in the DEMO product catalog. "
                    "NEVER describe a product to the user without checking it here "
                    "first."),
    "parameters": {
        "type": "object",
        "required": ["query"],
        "properties": {"query": {"type": "string", "maxLength": 120,
                                 "description": "Product id or name to look up"}},
    },
}

DIALOGUE_TOOLS = [RECORD_CLIENT_PROFILE, RECORD_REQUIREMENT_ANALYSIS,
                  RECORD_RISK_ASSESSMENT]
STAGE_TOOLS = [RUN_COVERAGE_GAP, RUN_SOLUTION, RUN_PRODUCT_CANDIDATES,
               RUN_RECOMMENDATION, RUN_REPORT]
QA_TOOLS = [KNOWLEDGE_SEARCH, CHECK_CATALOG_PRODUCT]
