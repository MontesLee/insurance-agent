"""Solution deterministic engine (V2 Phase 3).

Strategy layer. It answers ONLY:
    "针对已判定的保障缺口，应该采用什么解决策略？"

Design boundaries (see CONTRACT.md / docs/architecture-v2.md §3.1):
- Solution != Product: this engine emits STRATEGY (objective / coverage_direction /
  trade-offs / rejected directions). It NEVER names a concrete insurance product or
  insurer. Every emitted string comes from resources/config/solution-mapping.rules.json
  templates, so free-text product names are structurally impossible.
- Solution != Risk: it does NOT recompute severity / likelihood / residual_risk. It only
  *references* gap_id / risk_id.
- Solution != Coverage Gap: it does NOT re-judge coverage status; it consumes the
  CoverageGapAnalysis artifact's verdict.
- No invented quantities: coverage_direction states HOW to size coverage, never a
  fabricated amount.

Inputs (each may be a Canonical envelope with a "payload" key, or the raw dict):
    coverage_gap_analysis  -> CoverageGapAnalysis (authoritative driver)
    requirement_analysis   -> RequirementAnalysis (constraints / stated priorities)
    risk_assessment        -> RiskAssessment (context; referenced, not recomputed)

Output: the strict SolutionPlan payload (validates against
contracts/solution-plan.schema.json).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "..", "resources", "config", "solution-mapping.rules.json")


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_payload(artifact: Any) -> Any:
    """Accept either a Canonical envelope ({"payload": ...}) or a raw dict."""
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def _build_constraints(gap: dict, req_by_id: dict, req_status: Optional[str], rules: dict) -> list:
    constraints: list[dict] = []

    cov_status = (gap.get("current_coverage") or {}).get("status", "UNKNOWN")
    default = (rules.get("default_constraints") or {}).get(cov_status)
    if default:
        constraints.append(
            {
                "constraint": default["constraint"],
                "value": default["value"],
                "source": gap.get("gap_id"),
            }
        )

    for req_id in gap.get("related_requirement_ids") or []:
        req = req_by_id.get(req_id)
        if not isinstance(req, dict):
            continue
        if req.get("boundary"):
            constraints.append(
                {
                    "constraint": "需求分析边界",
                    "value": str(req["boundary"]),
                    "source": req_id,
                }
            )
        if req.get("priority"):
            constraints.append(
                {
                    "constraint": "客户已声明的需求优先级",
                    "value": str(req["priority"]),
                    "source": req_id,
                }
            )

    if req_status and req_status != "COMPLETE":
        constraints.append(
            {
                "constraint": "需求分析状态",
                "value": req_status,
                "source": "requirement_analysis",
            }
        )
    return constraints


def _direction_for(gap: dict, rules: dict) -> str:
    domain = gap.get("domain", "general")
    cov_status = (gap.get("current_coverage") or {}).get("status", "UNKNOWN")
    prefix = (rules.get("coverage_status_prefix") or {}).get(cov_status, "")
    body = (rules.get("domain_coverage_direction") or {}).get(
        domain, rules["domain_coverage_direction"]["general"]
    )
    return f"{prefix}{body}"


def analyze(
    coverage_gap_analysis: Any,
    requirement_analysis: Any = None,
    risk_assessment: Any = None,
    rules: Optional[dict] = None,
) -> dict:
    rules = rules or load_rules()
    gap_art = extract_payload(coverage_gap_analysis) or {}
    req_art = extract_payload(requirement_analysis) or {}
    # risk_assessment is referenced only (for traceability); not recomputed here.
    _risk = extract_payload(risk_assessment) or {}

    gaps = gap_art.get("gaps") or []
    req_by_id = {
        r.get("requirement_id"): r
        for r in (req_art.get("requirements") or [])
        if isinstance(r, dict) and r.get("requirement_id")
    }
    req_status = req_art.get("analysis_status")

    prio_rank = rules["priority_rank"]
    level_rank = rules["gap_level_rank"]
    level_to_prio = rules["gap_level_to_priority"]
    sol_type = rules["domain_to_solution_type"]
    objectives = rules["domain_objective"]

    solutions: list[dict] = []
    information_gaps: list[dict] = []
    has_unknown = False

    for gap in gaps:
        gap_id = gap.get("gap_id", "GAP-?")
        domain = gap.get("domain", "general")
        gap_level = gap.get("gap_level", "UNKNOWN")
        cov_status = (gap.get("current_coverage") or {}).get("status", "UNKNOWN")

        if gap_level == "UNKNOWN" or cov_status == "UNKNOWN":
            has_unknown = True
            information_gaps.append(
                {
                    "gap_id": gap_id,
                    "domain": domain,
                    "reason": "覆盖情况未知，需先明确现有保障再确定解决策略",
                }
            )

        ev = list(gap.get("evidence_refs") or [])
        ev.append(f"from:{gap_id}")

        solutions.append(
            {
                "solution_id": "",  # assigned after sorting (stable, order-independent of input)
                "solution_type": sol_type.get(domain, "GENERAL"),
                "objective": objectives.get(domain, objectives["general"]),
                "coverage_direction": _direction_for(gap, rules),
                "priority": level_to_prio.get(gap_level, "P3"),
                "constraints": _build_constraints(gap, req_by_id, req_status, rules),
                "trade_offs": list(rules["domain_trade_offs"].get(domain, [])),
                "rejected_directions": list(rules["domain_rejected_directions"].get(domain, [])),
                "related_gap_ids": [gap_id],
                "related_risk_ids": list(gap.get("related_risk_ids") or []),
                "confidence": gap.get("confidence"),
                "evidence_refs": ev,
            }
        )

    solutions.sort(
        key=lambda s: (
            prio_rank.get(s["priority"], 3),
            -level_rank.get(
                next(
                    (g.get("gap_level", "UNKNOWN") for g in gaps if g.get("gap_id") == s["related_gap_ids"][0]),
                    "UNKNOWN",
                ),
                0,
            ),
        )
    )
    for i, s in enumerate(solutions, start=1):
        s["solution_id"] = f"SOL-{i:03d}"

    placeholders = rules["placeholders"]
    if solutions:
        primary = solutions[0]
        objective = primary["objective"]
        coverage_direction = primary["coverage_direction"]
        priority = primary["priority"]
        solution_type = primary["solution_type"]
        constraints = primary["constraints"]
        trade_offs = primary["trade_offs"]
        rejected = primary["rejected_directions"]
    else:
        objective = placeholders["no_gap_objective"]
        coverage_direction = placeholders["no_gap_coverage_direction"]
        priority = placeholders["no_gap_priority"]
        solution_type = None
        constraints = []
        trade_offs = []
        rejected = []

    gap_status = gap_art.get("status")
    if not solutions and gap_status == "COMPLETE":
        status = "COMPLETE"
    elif has_unknown:
        status = "NEED_MORE_INFORMATION"
    elif gap_status == "PRELIMINARY":
        status = "PRELIMINARY"
    elif gap_status in ("NEED_MORE_INFORMATION", "INSUFFICIENT_INFORMATION"):
        status = "PRELIMINARY"
    elif not solutions:
        status = "INSUFFICIENT_INFORMATION"
    else:
        status = "COMPLETE"

    payload: dict = {
        "solutions": solutions,
        "objective": objective,
        "coverage_direction": coverage_direction,
        "priority": priority,
        "constraints": constraints,
        "trade_offs": trade_offs,
        "rejected_directions": rejected,
        "related_gap_ids": [s["related_gap_ids"][0] for s in solutions],
        "information_gaps": information_gaps,
        "status": status,
    }
    if solution_type:
        payload["solution_type"] = solution_type
    return payload
