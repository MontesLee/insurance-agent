"""Task Type Registry — the TRUSTED catalogue the Planner may choose from.

Every entry is hand-curated: stage_id / produced artifacts / required inputs /
required eval all map to capabilities that ALREADY exist and have passed
deterministic regression. The Planner cannot invent a task_type outside this
registry (Graph Validation rejects it — fail-closed, §7/§23).
"""
from __future__ import annotations

# task_type → full definition
TASK_REGISTRY: dict = {
    "client_profile": {
        "task_type": "client_profile",
        "stage_id": "client-intake",
        "executor": "provided",          # dialogue-driven (seeded or agent-extracted)
        "description": "收集并结构化客户基础信息",
        "required_inputs": [],           # entry point — no upstream artifact
        "produced_artifacts": ["client-profile"],
        "required_eval": ["client_profile_eval"],
    },
    "requirement_analysis": {
        "task_type": "requirement_analysis",
        "stage_id": "requirement-analysis",
        "executor": "provided",
        "description": "分析客户保险需求",
        "required_inputs": ["client-profile"],
        "produced_artifacts": ["requirement-analysis"],
        "required_eval": ["requirement_analysis_eval"],
    },
    "risk_analysis": {
        "task_type": "risk_analysis",
        "stage_id": "risk-analysis",
        "executor": "provided",
        "description": "识别和评估客户风险",
        "required_inputs": ["client-profile", "requirement-analysis"],
        "produced_artifacts": ["risk-assessment"],
        "required_eval": ["risk_analysis_eval"],
    },
    "coverage_gap": {
        "task_type": "coverage_gap",
        "stage_id": "coverage-gap-analysis",
        "executor": "python",
        "description": "分析保障缺口",
        "required_inputs": ["client-profile", "requirement-analysis", "risk-assessment"],
        "produced_artifacts": ["coverage-gap-analysis"],
        "required_eval": ["coverage_gap_eval"],
    },
    "solution": {
        "task_type": "solution",
        "stage_id": "solution",
        "executor": "python",
        "description": "设计保障方案",
        "required_inputs": ["coverage-gap-analysis", "requirement-analysis", "risk-assessment"],
        "produced_artifacts": ["solution-plan"],
        "required_eval": ["solution_eval"],
    },
    "knowledge_search": {
        "task_type": "knowledge_search",
        "stage_id": "product-candidate-provider",  # service round-trip
        "executor": "service",
        "description": "检索保险知识库获取证据",
        "required_inputs": ["solution-plan"],
        "produced_artifacts": ["knowledge-evidence"],
        "required_eval": ["knowledge_evidence_eval"],
    },
    "product_candidates": {
        "task_type": "product_candidates",
        "stage_id": "product-candidate-provider",
        "executor": "python",
        "description": "筛选候选产品",
        "required_inputs": ["client-profile", "coverage-gap-analysis", "solution-plan"],
        "produced_artifacts": ["product-candidates"],
        "required_eval": ["product_candidates_eval"],
    },
    "recommendation": {
        "task_type": "recommendation",
        "stage_id": "product-recommendation",
        "executor": "python",
        "description": "形成产品推荐结论",
        "required_inputs": ["requirement-analysis", "risk-assessment",
                            "coverage-gap-analysis", "solution-plan"],
        "produced_artifacts": ["product-recommendation"],
        "required_eval": ["recommendation_eval"],
    },
    "report_generation": {
        "task_type": "report_generation",
        "stage_id": "report-generation",
        "executor": "python",
        "description": "生成保险需求分析报告",
        "required_inputs": ["client-profile", "requirement-analysis", "risk-assessment"],
        "produced_artifacts": ["insurance-report"],
        "required_eval": ["report_generation_eval"],
    },
}

# canonical chain (used for default planning + harness fallback)
CANONICAL_CHAIN = [
    "client_profile", "requirement_analysis", "risk_analysis",
    "coverage_gap", "solution", "knowledge_search",
    "product_candidates", "recommendation", "report_generation",
]

# valid task statuses (Planner may only set PLANNED; others are runtime-managed)
TASK_STATUSES = frozenset({
    "PLANNED", "READY", "RUNNING", "PASSED", "FAILED",
    "BLOCKED", "SKIPPED", "NEEDS_REVIEW",
})


def get(task_type: str) -> Optional[dict]:
    return TASK_REGISTRY.get(task_type)


def is_valid(task_type: str) -> bool:
    return task_type in TASK_REGISTRY


def produced_artifacts(task_type: str) -> list:
    d = TASK_REGISTRY.get(task_type)
    return d["produced_artifacts"] if d else []


def required_inputs(task_type: str) -> list:
    d = TASK_REGISTRY.get(task_type)
    return d["required_inputs"] if d else []


from typing import Optional  # noqa: E402
