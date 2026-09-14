"""Upstream Results Adapter for Skill 6 Report Generation.

Normalizes the upstream Skill outputs into a single unified intermediate
(`NormalizedInput`) that the report engine consumes. The adapter is READ-ONLY:
it never mutates upstream objects and degrades gracefully (MISSING_FROM_UPSTREAM)
when an upstream result is absent or malformed.

V2 upstream shapes consumed (see AGENTS.md + contracts/):
  * client_profile         -> CanonicalClientState (client_state) or equivalent
  * requirement_analysis   -> RequirementAnalysisOutput
  * risk_analysis          -> RiskAnalysisOutput (risks under risk_analysis[] or risks[])
  * coverage_gap_analysis  -> CoverageGapAnalysis   [V2, canonical source for section 04]
  * solution_plan          -> SolutionPlan          [V2, strategy layer]
  * knowledge_evidence     -> KnowledgeEvidence     [V2 canonical]
  * knowledge_search       -> KnowledgeSearchOutput [legacy alias of knowledge_evidence]
  * product_recommendation -> ProductRecommendation [V2 canonical]
  * recommendation         -> RecommendationOutput  [legacy alias of product_recommendation]

Alias rule: a canonical key wins over its legacy alias; if only the legacy key is
supplied it is used and recorded in `aliases` so the report can be explicit about
which name the data arrived under.

Canonical envelope rule: artifacts produced through `adapters/` carry
`{artifact_type, skill, payload, provenance, ...}`. Consumers unwrap `payload`
when present so the same code handles both canonical and raw Skill output.

Design mirrors Skill 5 (recommendation) adapters: tolerant, provenance-preserving,
no upstream mutation, and NO business judgment (the adapter never computes a gap,
a level, or a strategy — it only reshapes what upstream already decided).
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def _dig(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def _as_list(v):
    if v is None:
        return []
    if isinstance(v, list):
        return v
    return [v]


def _payload(obj):
    """Unwrap a Canonical envelope ({..., payload: {...}}) when present.

    Canonical artifacts always carry `payload`; raw Skill outputs do not. Returning
    the inner payload lets downstream code read one shape. Non-dict input -> {}.
    """
    if not isinstance(obj, dict):
        return {}
    if isinstance(obj.get("payload"), dict):
        return obj["payload"]
    return obj


# --------------------------------------------------------------------------- #
# client_profile (CanonicalClientState) adapter
# --------------------------------------------------------------------------- #
def adapt_client_state(cs):
    if not cs or not isinstance(cs, dict):
        return {
            "missing": True,
            "family_profile": {}, "financial_profile": {}, "responsibility_profile": {},
            "existing_protection": {}, "health_profile": {}, "employment_profile": {},
            "missing_from_upstream": [], "conflicts": [],
        }
    return {
        "missing": False,
        "family_profile": cs.get("family_profile", {}) or {},
        "financial_profile": cs.get("financial_profile", {}) or {},
        "responsibility_profile": cs.get("responsibility_profile", {}) or {},
        "existing_protection": cs.get("existing_protection", {}) or {},
        "health_profile": cs.get("health_profile", {}) or {},
        "employment_profile": cs.get("employment_profile", {}) or {},
        "missing_from_upstream": cs.get("missing_from_upstream", []) or [],
        "conflicts": cs.get("conflicts", []) or [],
    }


# --------------------------------------------------------------------------- #
# requirement_analysis adapter
# --------------------------------------------------------------------------- #
def adapt_requirement_analysis(ra, rules):
    if not ra or not isinstance(ra, dict):
        return {
            "missing": True, "status": None, "requirements": [], "priorities": [],
            "coverage_gaps": [], "information_gaps": [], "next_actions": [],
            "sufficiency": None, "unknowns": [], "assumptions": [], "scope": [],
        }
    status = ra.get("analysis_status")
    reqs = _as_list(ra.get("requirements"))
    priorities = _as_list(ra.get("priorities"))
    gaps = _as_list(ra.get("coverage_gaps"))
    info_gaps = _as_list(ra.get("information_gaps"))
    next_actions = _as_list(ra.get("next_actions"))
    suff = _dig(ra, "information_sufficiency", "sufficiency_status")
    unknowns = _as_list(ra.get("unknowns"))
    assumptions = _as_list(ra.get("assumptions"))
    scope = _as_list(ra.get("analysis_scope"))
    return {
        "missing": False, "status": status, "requirements": reqs, "priorities": priorities,
        "coverage_gaps": gaps, "information_gaps": info_gaps, "next_actions": next_actions,
        "sufficiency": suff, "unknowns": unknowns, "assumptions": assumptions, "scope": scope,
    }


# --------------------------------------------------------------------------- #
# risk_analysis adapter
# --------------------------------------------------------------------------- #
def adapt_risk_analysis(rk, rules):
    if not rk or not isinstance(rk, dict):
        return {
            "missing": True, "risks": [], "top_priorities": [],
            "next_information_needed": [], "missing_from_upstream": [], "unknowns": [],
        }
    rk = _payload(rk)
    raw = rk.get("risk_analysis")
    if raw is None and "risks" in rk:
        raw = rk["risks"]
    if raw is None and isinstance(rk, list):
        raw = rk
    if raw is None:
        raw = []
    risks = []
    for r in raw:
        if not isinstance(r, dict):
            continue
        risks.append({
            "risk_id": r.get("risk_id"),
            "risk_category": r.get("risk_category"),
            "risk_name": r.get("risk_name"),
            "status": r.get("status"),
            "residual_risk": r.get("residual_risk"),
            "priority": r.get("priority"),
            "severity": r.get("severity"),
            "likelihood": r.get("likelihood"),
            "conclusion": r.get("conclusion"),
            "trigger_event": _dig(r, "trigger", "event"),
            "why_exposed": _dig(r, "exposure", "why_exposed"),
            "potential_impact": _dig(r, "potential_impact"),
            "coverage_assessment": r.get("coverage_assessment", {}) or {},
            "existing_protection": r.get("existing_protection"),
            "reasoning_evidence_refs": _as_list(r.get("reasoning_evidence_refs")),
            "unknowns": _as_list(r.get("unknowns")),
        })
    return {
        "missing": False, "risks": risks,
        "top_priorities": _as_list(rk.get("top_priorities")),
        "next_information_needed": _as_list(rk.get("next_information_needed")),
        "missing_from_upstream": _as_list(rk.get("missing_from_upstream")),
        "unknowns": _as_list(rk.get("unknowns")),
    }


# --------------------------------------------------------------------------- #
# coverage_gap_analysis adapter  [V2]
# --------------------------------------------------------------------------- #
def adapt_coverage_gap_analysis(cga, rules):
    """CoverageGapAnalysis -> normalized gap layer.

    Pure reshape. gap_level / current_coverage.status / target_coverage.direction
    are copied verbatim; the adapter never recomputes or re-ranks them.
    """
    empty = {
        "missing": True, "status": None, "gaps": [],
        "priorities": [], "information_gaps": [],
    }
    if not cga or not isinstance(cga, dict):
        return empty
    p = _payload(cga)
    gaps = []
    for g in _as_list(p.get("gaps")):
        if not isinstance(g, dict):
            continue
        cur = g.get("current_coverage") or {}
        tgt = g.get("target_coverage") or {}
        gaps.append({
            "gap_id": g.get("gap_id"),
            "domain": g.get("domain"),
            "subject": g.get("subject"),
            "current_coverage_status": cur.get("status"),
            "current_coverage_evidence_refs": _as_list(cur.get("evidence_refs")),
            "target_direction": tgt.get("direction"),
            "target_rationale": tgt.get("rationale"),
            "gap_level": g.get("gap_level"),
            "confidence": g.get("confidence"),
            "related_requirement_ids": _as_list(g.get("related_requirement_ids")),
            "related_risk_ids": _as_list(g.get("related_risk_ids")),
            "evidence_refs": _as_list(g.get("evidence_refs")),
        })
    return {
        "missing": False,
        "status": p.get("status"),
        "gaps": gaps,
        "priorities": _as_list(p.get("priorities")),
        "information_gaps": _as_list(p.get("information_gaps")),
    }


# --------------------------------------------------------------------------- #
# solution_plan adapter  [V2]
# --------------------------------------------------------------------------- #
def adapt_solution_plan(sp, rules):
    """SolutionPlan -> normalized strategy layer.

    Pure reshape. objective / coverage_direction / priority / trade_offs /
    rejected_directions are copied verbatim — the report must never paraphrase a
    strategy, because paraphrasing is where a strategy would silently become a
    different strategy.
    """
    empty = {"missing": True, "status": None, "solutions": []}
    if not sp or not isinstance(sp, dict):
        return empty
    p = _payload(sp)
    sols = []
    raw = _as_list(p.get("solutions"))
    if not raw and p.get("objective"):
        # Degenerate envelope: top-level triple only.
        raw = [p]
    for s in raw:
        if not isinstance(s, dict):
            continue
        sols.append({
            "solution_id": s.get("solution_id"),
            "solution_type": s.get("solution_type"),
            "objective": s.get("objective"),
            "coverage_direction": s.get("coverage_direction"),
            "priority": s.get("priority"),
            "constraints": _as_list(s.get("constraints")),
            "trade_offs": _as_list(s.get("trade_offs")),
            "rejected_directions": _as_list(s.get("rejected_directions")),
            "related_gap_ids": _as_list(s.get("related_gap_ids")),
            "related_risk_ids": _as_list(s.get("related_risk_ids")),
            "status": s.get("status"),
        })
    return {"missing": False, "status": p.get("status"), "solutions": sols}


# --------------------------------------------------------------------------- #
# knowledge_evidence adapter  [V2]  (+ legacy knowledge_search alias)
# --------------------------------------------------------------------------- #
def adapt_knowledge_evidence(ke):
    """KnowledgeEvidence (canonical) or KnowledgeSearchOutput (legacy) -> evidence layer.

    Canonical payload: {status, query, evidence[], conflict}.
    Legacy output:     {status, results[], conflict}.
    Both are accepted; `shape` records which one was read.
    """
    empty = {"missing": True, "status": None, "query": None, "evidence": [],
             "conflict": False, "shape": None}
    if not ke or not isinstance(ke, dict):
        return empty
    p = _payload(ke)
    if isinstance(p.get("evidence"), list):
        items, shape = p.get("evidence"), "canonical"
    else:
        items, shape = _as_list(p.get("results")), "legacy"
    ev = []
    for e in items:
        if not isinstance(e, dict):
            continue
        ev.append({
            "evidence_id": e.get("evidence_id") or e.get("chunk_id") or e.get("id"),
            "content": e.get("content"),
            "source": e.get("source") or e.get("document_name") or e.get("source_id"),
            "source_type": e.get("source_type"),
            "relevance": e.get("relevance") if e.get("relevance") is not None else e.get("score"),
            "confidence": e.get("confidence"),
            "conflict": e.get("conflict"),
        })
    return {
        "missing": False,
        "status": p.get("status"),
        "query": p.get("query"),
        "evidence": ev,
        "conflict": bool(p.get("conflict", False)),
        "shape": shape,
    }


# --------------------------------------------------------------------------- #
# product_recommendation adapter  [V2]  (+ legacy recommendation alias)
# --------------------------------------------------------------------------- #
def adapt_recommendation(rec, rules):
    if not rec or not isinstance(rec, dict):
        return {
            "missing": True, "status": None, "primary": None, "alternatives": [],
            "not_recommended": [], "tradeoffs": [], "uncertainties": [],
            "evidence_refs": [], "human_review_required": None, "candidate_evaluations": [],
        }
    rec = _payload(rec)
    return {
        "missing": False,
        "status": rec.get("status"),
        "primary": rec.get("primary_recommendation"),
        "alternatives": _as_list(rec.get("alternatives")),
        "not_recommended": _as_list(rec.get("not_recommended")),
        "tradeoffs": _as_list(rec.get("tradeoffs")),
        "uncertainties": _as_list(rec.get("uncertainties")),
        "evidence_refs": _as_list(rec.get("evidence_refs")),
        "human_review_required": rec.get("human_review_required"),
        "candidate_evaluations": _as_list(rec.get("candidate_evaluations")),
    }


# --------------------------------------------------------------------------- #
# Unified normalization
# --------------------------------------------------------------------------- #
def _pick(input_dict, canonical_key, legacy_key):
    """Canonical key wins; fall back to legacy alias. Returns (value, used_key, alias_used)."""
    v = input_dict.get(canonical_key)
    if v is not None:
        return v, canonical_key, False
    v = input_dict.get(legacy_key)
    if v is not None:
        return v, legacy_key, True
    return None, canonical_key, False


def _supplied(input_dict, canonical_key, legacy_key):
    """Which key did the caller actually name (even if its value is null)?

    Used so a MISSING_UPSTREAM_RESULT warning names the artifact the caller asked
    for. V1 callers name `recommendation`; V2 callers name `product_recommendation`.
    Reporting the caller's own key keeps V1 warning text byte-identical.
    """
    if canonical_key in input_dict:
        return canonical_key
    if legacy_key in input_dict:
        return legacy_key
    # Neither named: default to the canonical name. A V2 caller that simply omits
    # the artifact should be told the canonical name, not the deprecated one.
    return canonical_key


def normalize_input(input_dict, rules=None):
    if rules is None:
        from report_generation_engine import load_rules  # local import to avoid cycle
        rules = load_rules()

    cs = adapt_client_state(input_dict.get("client_profile"))
    ra = adapt_requirement_analysis(input_dict.get("requirement_analysis"), rules)
    rk = adapt_risk_analysis(input_dict.get("risk_analysis"), rules)

    cga_raw, cga_key, _ = _pick(input_dict, "coverage_gap_analysis", None)
    cga = adapt_coverage_gap_analysis(cga_raw, rules)

    sp_raw, sp_key, _ = _pick(input_dict, "solution_plan", None)
    sp = adapt_solution_plan(sp_raw, rules)

    ke_raw, ke_key, ke_alias = _pick(input_dict, "knowledge_evidence", "knowledge_search")
    ke = adapt_knowledge_evidence(ke_raw)

    rec_raw, rec_key, rec_alias = _pick(input_dict, "product_recommendation", "recommendation")
    rec = adapt_recommendation(rec_raw, rules)

    core = [cs, ra, rk]
    missing_core = []
    if cs["missing"]:
        missing_core.append("client_profile")
    if ra["missing"]:
        missing_core.append("requirement_analysis")
    if rk["missing"]:
        missing_core.append("risk_analysis")

    return {
        "client_state": cs,
        "requirement_analysis": ra,
        "risk_analysis": rk,
        "coverage_gap_analysis": cga,
        "solution_plan": sp,
        # internal keys kept stable for the engine; aliases recorded for honesty
        "knowledge_search": ke,
        "recommendation": rec,
        "missing_core": missing_core,
        "all_core_missing": (len(missing_core) == 3),
        "aliases": {
            "knowledge_evidence": ke_key,
            "product_recommendation": rec_key,
        },
        "supplied_keys": {
            "knowledge_evidence": _supplied(input_dict, "knowledge_evidence", "knowledge_search"),
            "product_recommendation": _supplied(input_dict, "product_recommendation", "recommendation"),
        },
        "legacy_alias_used": {
            "knowledge_evidence": ke_alias,
            "product_recommendation": rec_alias,
        },
    }
