"""Agent Registry — Specialist Agent definitions with capability boundaries.

Each agent is a TRUSTED, hand-curated definition declaring:
  - which task_types it may execute
  - which tools it may use
  - its specialist system prompt

Agents are EXECUTORS, not controllers (§27). They cannot:
  - skip tasks, mark themselves PASS, bypass eval
  - modify dependencies, checkpoints, or harness state
  - access tools outside their declared boundary
"""
from __future__ import annotations

AGENT_REGISTRY: dict = {
    "insurance_analyst": {
        "agent_id": "insurance_analyst",
        "name": "Insurance Analyst",
        "description": "分析客户保险需求、风险、保障缺口和方案策略",
        "allowed_task_types": [
            "client_profile",
            "requirement_analysis",
            "risk_analysis",
            "coverage_gap",
            "solution",
        ],
        "allowed_tools": [
            "record_client_profile",
            "record_requirement_analysis",
            "record_risk_assessment",
            "coverage_gap_analysis",
            "solution",
        ],
        "system_prompt": """You are an Insurance Analysis Agent.
You are responsible for insurance analysis tasks: client profiling, requirement
analysis, risk assessment, coverage gap analysis, and solution design.

You may:
- analyze client requirements and risks
- identify coverage gaps
- formulate strategy-level solutions

You may not:
- recommend specific products
- invent catalog products
- bypass evaluation
- modify task or project state
- access product recommendation tools""",
    },
    "knowledge_specialist": {
        "agent_id": "knowledge_specialist",
        "name": "Knowledge Specialist",
        "description": "检索保险知识库并提供证据",
        "allowed_task_types": [
            "knowledge_search",
        ],
        "allowed_tools": [
            "knowledge_search",
        ],
        "system_prompt": """You are a Knowledge Specialist Agent.
You are responsible for retrieving evidence from the insurance knowledge base.

You may:
- search the knowledge base for relevant evidence
- provide sourced answers with document references

You may not:
- invent facts not in the knowledge base
- bypass evidence provenance
- access analysis or product tools""",
    },
    "product_specialist": {
        "agent_id": "product_specialist",
        "name": "Product Specialist",
        "description": "筛选候选产品并形成推荐结论",
        "allowed_task_types": [
            "product_candidates",
            "recommendation",
        ],
        "allowed_tools": [
            "product_candidate_provider",
            "recommendation",
            "check_catalog_product",
        ],
        "system_prompt": """You are a Product Specialist Agent.
You are responsible for catalog-backed product tasks: candidate filtering
and recommendation.

You may:
- retrieve product candidates from the catalog
- compare catalog-backed products
- produce recommendation artifacts

You may not:
- invent products not in the catalog
- alter catalog data
- bypass the product trust boundary
- access risk analysis or requirement tools""",
    },
    "report_specialist": {
        "agent_id": "report_specialist",
        "name": "Report Specialist",
        "description": "生成最终保险需求分析报告",
        "allowed_task_types": [
            "report_generation",
        ],
        "allowed_tools": [
            "report_generation",
        ],
        "system_prompt": """You are a Report Specialist Agent.
You are responsible for generating the final insurance analysis report.

You may:
- synthesize upstream artifacts into a structured report
- reference evidence and provenance

You may not:
- invent analysis conclusions not backed by upstream artifacts
- modify upstream artifacts
- access analysis or product tools""",
    },
}

# deterministic task_type → agent_id assignment (§5: NOT LLM-decided)
TASK_AGENT_MAP: dict = {}
for _agent_id, _def in AGENT_REGISTRY.items():
    for _tt in _def["allowed_task_types"]:
        TASK_AGENT_MAP[_tt] = _agent_id

# --------------------------------------------------------------------------- #
# Communication Policy (Phase 6.2 §11): who may send messages to whom.
# Derived from the workflow's data-flow: analysis → knowledge/evidence →
# product selection → reporting. Reverse/diagonal communication is denied.
# --------------------------------------------------------------------------- #
COMMUNICATION_POLICY: dict = {
    "insurance_analyst": {
        "knowledge_specialist",   # analyst may request evidence
        "product_specialist",    # analyst hands off to product selection
    },
    "knowledge_specialist": {
        "insurance_analyst",     # evidence flows back to analysis
    },
    "product_specialist": {
        "report_specialist",     # product results feed the report
        "insurance_analyst",     # product specialist may request analysis review
    },
    "report_specialist": {
        "insurance_analyst",     # report specialist may flag analysis gaps
    },
}


def allowed_message_targets(agent_id: str) -> set:
    """Which agents this agent may send messages to."""
    return COMMUNICATION_POLICY.get(agent_id, set())


def can_communicate(sender: str, target: str) -> bool:
    """Check communication policy: sender → target allowed?"""
    return target in COMMUNICATION_POLICY.get(sender, set())


def get(agent_id: str):
    return AGENT_REGISTRY.get(agent_id)


def agent_for_task(task_type: str):
    """Deterministic assignment: task_type → agent_id."""
    return TASK_AGENT_MAP.get(task_type)


def is_valid_agent(agent_id: str) -> bool:
    return agent_id in AGENT_REGISTRY


def can_execute(agent_id: str, task_type: str) -> bool:
    d = AGENT_REGISTRY.get(agent_id)
    return bool(d) and task_type in d.get("allowed_task_types", [])


def allowed_tools(agent_id: str) -> list:
    d = AGENT_REGISTRY.get(agent_id)
    return (d or {}).get("allowed_tools", [])


def validate_assignment(task_type: str, agent_id: str) -> tuple:
    """Validate that agent_id may execute task_type. Returns (ok, error)."""
    if not is_valid_agent(agent_id):
        return False, "unknown agent %r (not in Agent Registry)" % agent_id
    if not can_execute(agent_id, task_type):
        return False, "agent %r is not allowed to execute task_type %r" % (agent_id, task_type)
    return True, None
