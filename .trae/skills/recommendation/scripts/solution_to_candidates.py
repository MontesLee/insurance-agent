"""Phase 5: SolutionPlan -> candidate_solutions translator.

WHY THIS EXISTS
---------------
Phase 0 audit found the single fatal break in the V1 chain:

    requirement -> risk -> ??? candidate_solutions -> recommendation

`candidate_solutions` was a required input of `recommendation` that **no skill produced**.
Phase 5 closes it by making `SolutionPlan` the canonical producer:

    CoverageGapAnalysis -> SolutionPlan -> (this translator) -> candidate_solutions

The V2 public input contract of product-recommendation therefore no longer declares
`candidate_solutions` at all; it is derived here, at an explicit adapter boundary.

HONESTY BOUNDARY
----------------
A SolutionPlan is a STRATEGY ("建立家庭责任保障"), not a product. It carries no premium,
no term, no insurer, no product name. This translator therefore:
  * derives coverage_structure / risk coverage FROM THE RULES, and
  * leaves premium / term / insurer / product_name ABSENT.

It never invents a number or a product. Absent product-level fields are surfaced by the
engine as `unverifiable_constraints` (never as a silent pass) -- see
`unverifiable_constraint_policy` in the rules file.

NO BUSINESS-LOGIC REWRITE
-------------------------
The evaluation itself still runs through the legacy `recommendation_engine`. This module
only prepares inputs; it does not re-implement scoring, ranking or evidence policy.
"""
from __future__ import annotations

import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))


def load_rules(path=None):
    if path is None:
        path = os.path.join(HERE, "..", "resources", "config", "solution-to-candidate.rules.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Canonical envelope helpers
# --------------------------------------------------------------------------- #
def _payload(artifact):
    """Accept either a canonical envelope ({artifact_type, payload, ...}) or a raw payload."""
    if isinstance(artifact, dict) and "payload" in artifact and isinstance(artifact["payload"], dict):
        return artifact["payload"]
    return artifact if isinstance(artifact, dict) else {}


def _solutions(solution_plan, rules=None):
    """Return the strategy list.

    `solutions: []` is an EXPLICIT statement that there is no actionable strategy -- it must
    never be back-filled from the derived top-level triple, or we would fabricate a
    candidate out of a placeholder objective (exactly the "no producer -> invent something"
    failure this Phase exists to eliminate).
    """
    p = _payload(solution_plan)
    sols = p.get("solutions")
    if sols is not None:
        return sols if isinstance(sols, list) else []

    # Degenerate: envelope without solutions[] but with the derived top-level triple.
    obj = p.get("objective") or ""
    markers = (rules or {}).get("no_action_objective_markers", []) or []
    if obj and not any(m in obj for m in markers):
        return [{
            "solution_id": p.get("solution_id") or "SOL-000",
            "solution_type": p.get("solution_type") or "GENERAL",
            "objective": p.get("objective"),
            "coverage_direction": p.get("coverage_direction") or "",
            "priority": p.get("priority") or "P3",
            "related_gap_ids": p.get("related_gap_ids", []) or [],
            "related_risk_ids": p.get("related_risk_ids", []) or [],
            "evidence_refs": p.get("evidence_refs", []) or [],
        }]
    return []


def _risks(risk_assessment):
    p = _payload(risk_assessment)
    raw = p.get("risks")
    if raw is None:
        raw = p.get("risk_analysis")
    return raw if isinstance(raw, list) else []


def _gaps(coverage_gap_analysis):
    p = _payload(coverage_gap_analysis)
    raw = p.get("gaps")
    return raw if isinstance(raw, list) else []


# --------------------------------------------------------------------------- #
# KnowledgeEvidence -> knowledge_search_results view
# --------------------------------------------------------------------------- #
def build_knowledge_view(knowledge_evidence, rules):
    """Project canonical KnowledgeEvidence onto the shape the legacy engine reads.

    The engine only consumes: status, conflict, results[].chunk_id. Everything else in
    KnowledgeEvidence (content, relevance, confidence, provenance) is preserved on each
    result so downstream consumers keep full evidence fidelity.
    """
    if not knowledge_evidence:
        return {"status": None, "conflict": False, "results": []}
    p = _payload(knowledge_evidence)
    mapping = rules["evidence_status_to_ks_status"]
    status = mapping.get(p.get("status"), None)
    ev = p.get("evidence", []) or []
    results = []
    for e in ev:
        eid = e.get("evidence_id")
        if not eid:
            continue
        results.append({
            "chunk_id": eid,
            "content": e.get("content"),
            "source": e.get("source"),
            "relevance": e.get("relevance"),
            "confidence": e.get("confidence"),
        })
    return {
        "status": status,
        "conflict": bool(p.get("conflict", False)),
        "results": results,
    }


# --------------------------------------------------------------------------- #
# Risk category resolution
# --------------------------------------------------------------------------- #
def _risk_category_index(risk_assessment):
    idx = {}
    for r in _risks(risk_assessment):
        rid = r.get("risk_id")
        cat = r.get("risk_category")
        if rid and cat:
            idx[rid] = cat
    return idx


def _resolve_risk_categories(solution, solution_type, risk_idx, rules):
    """Prefer explicit related_risk_ids -> real risk_category; fall back to id pattern,
    then to the solution_type default. Never invent a category that contradicts data."""
    cats = []
    pattern = re.compile(rules["risk_category_from_id_pattern"])
    for rid in solution.get("related_risk_ids", []) or []:
        if rid in risk_idx:
            cat = risk_idx[rid]
        else:
            m = pattern.match(str(rid))
            cat = m.group(1) if m else None
        if cat and cat not in cats:
            cats.append(cat)
    if cats:
        return cats
    return list(rules["solution_type_to_risk_categories"].get(solution_type, []) or [])


# --------------------------------------------------------------------------- #
# Translator
# --------------------------------------------------------------------------- #
def translate(solution_plan, coverage_gap_analysis=None, risk_assessment=None,
              requirement_analysis=None, knowledge_evidence=None, rules=None):
    """SolutionPlan -> candidate_solutions[] + knowledge view + trace."""
    if rules is None:
        rules = load_rules()

    type_to_req = rules["solution_type_to_requirement_types"]
    liquidity = rules["liquidity_impact_by_solution_type"]
    product_fields = rules["product_level_fields"]
    risk_idx = _risk_category_index(risk_assessment)

    candidates = []
    trace = []
    for sol in _solutions(solution_plan, rules):
        sid = sol.get("solution_id") or "SOL-UNKNOWN"
        stype = sol.get("solution_type") or "GENERAL"

        coverage_structure = list(type_to_req.get(stype, []) or [])
        # GENERAL (or unknown type) falls back to the gap domain when it is a known
        # requirement type, so an unmapped strategy still carries a testable claim.
        if not coverage_structure:
            gap_domains = _gap_domains(sol, coverage_gap_analysis)
            known = {t for v in type_to_req.values() for t in v}
            coverage_structure = [d for d in gap_domains if d in known]

        cats = _resolve_risk_categories(sol, stype, risk_idx, rules)

        cand = {
            "candidate_id": sid,
            "solution_name": sol.get("objective") or sid,
            "coverage_structure": coverage_structure,
            "coverage_partial": [],
            "covers_risk_categories": cats,
            "liquidity_impact": liquidity.get(stype, liquidity["__default__"]),
            "source_refs": list(sol.get("evidence_refs", []) or []),
        }
        # Product-level facts are deliberately absent -- never fabricated.
        cand.update({k: v for k, v in product_fields.items() if v is not None})

        candidates.append(cand)
        trace.append({
            "candidate_id": sid,
            "solution_type": stype,
            "related_gap_ids": list(sol.get("related_gap_ids", []) or []),
            "related_risk_ids": list(sol.get("related_risk_ids", []) or []),
            "strategy_priority": sol.get("priority"),
        })

    return {
        "candidate_solutions": candidates,
        "knowledge_search_results": build_knowledge_view(knowledge_evidence, rules),
        "_strategy_trace": trace,
    }


def _gap_domains(solution, coverage_gap_analysis):
    ids = set(solution.get("related_gap_ids", []) or [])
    if not ids:
        return []
    out = []
    for g in _gaps(coverage_gap_analysis):
        if g.get("gap_id") in ids and g.get("domain"):
            if g["domain"] not in out:
                out.append(g["domain"])
    return out


def build_v2_input(requirement_analysis, risk_assessment, coverage_gap_analysis,
                   solution_plan, knowledge_evidence=None, constraints=None, rules=None):
    """Assemble the legacy-shaped input dict the engine consumes, from V2 canonical artifacts."""
    t = translate(solution_plan, coverage_gap_analysis, risk_assessment,
                  requirement_analysis, knowledge_evidence, rules)
    return {
        "requirement_analysis": _payload(requirement_analysis),
        "risk_analysis": _payload(risk_assessment),
        "candidate_solutions": t["candidate_solutions"],
        "knowledge_search_results": t["knowledge_search_results"],
        "constraints": constraints,
        "_strategy_trace": t["_strategy_trace"],
    }
