"""Upstream Results Adapter for Skill 6 Report Generation.

Normalizes the five upstream Skill outputs into a single unified intermediate
(`NormalizedInput`) that the report engine consumes. The adapter is READ-ONLY:
it never mutates upstream objects and degrades gracefully (MISSING_FROM_UPSTREAM)
when an upstream result is absent or malformed.

Upstream shapes consumed (see AGENTS.md + upstream schemas):
  * client_profile         -> CanonicalClientState (client_state) or equivalent
  * requirement_analysis    -> RequirementAnalysisOutput
  * risk_analysis           -> RiskAnalysisOutput (risks under risk_analysis[] or risks[])
  * knowledge_search        -> KnowledgeSearchOutput (optional)
  * recommendation          -> RecommendationOutput (optional)

Design mirrors Skill 5 (recommendation) adapters: tolerant, provenance-preserving,
no upstream mutation.
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
    raw = rk.get("risk_analysis")
    if raw is None and "risks" in rk:
        raw = rk["risks"]
    if raw is None and isinstance(rk, list):
        raw = rk
    if raw is None:
        raw = []
    risks = []
    for r in raw:
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
# knowledge_search adapter
# --------------------------------------------------------------------------- #
def adapt_knowledge_search(ks):
    if not ks or not isinstance(ks, dict):
        return {"missing": True, "status": None, "results": [], "conflict": False}
    return {
        "missing": False,
        "status": ks.get("status"),
        "results": _as_list(ks.get("results")),
        "conflict": bool(ks.get("conflict", False)),
    }


# --------------------------------------------------------------------------- #
# recommendation adapter
# --------------------------------------------------------------------------- #
def adapt_recommendation(rec, rules):
    if not rec or not isinstance(rec, dict):
        return {
            "missing": True, "status": None, "primary": None, "alternatives": [],
            "not_recommended": [], "tradeoffs": [], "uncertainties": [],
            "evidence_refs": [], "human_review_required": None, "candidate_evaluations": [],
        }
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
def normalize_input(input_dict, rules=None):
    if rules is None:
        from report_generation_engine import load_rules  # local import to avoid cycle
        rules = load_rules()
    cs = adapt_client_state(input_dict.get("client_profile"))
    ra = adapt_requirement_analysis(input_dict.get("requirement_analysis"), rules)
    rk = adapt_risk_analysis(input_dict.get("risk_analysis"), rules)
    ks = adapt_knowledge_search(input_dict.get("knowledge_search"))
    rec = adapt_recommendation(input_dict.get("recommendation"), rules)

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
        "knowledge_search": ks,
        "recommendation": rec,
        "missing_core": missing_core,
        "all_core_missing": (len(missing_core) == 3),
    }
