"""Recommendation engine — deterministic, rules-driven decision support.

This is Skill 5 (Recommendation). It consumes the structured outputs of upstream skills
(requirement-analysis, risk-analysis, knowledge-search) plus candidate solutions and an
optional constraints block, then produces an evidence-backed, explainable recommendation.

Design principles (mirrors AGENTS.md + Lawgent):
  * Deterministic: all weights/thresholds live in resources/config/recommendation.rules.json.
    The engine only consumes rules; it never invents a score or a fact.
  * No LLM: judgment is realized as explainable, provenance-bearing structured reasoning.
  * No fabrication: a candidate claiming coverage with no evidence backing is marked
    `insufficient_evidence`, never guessed into a recommendation.
  * No upstream mutation: the engine reads; it never edits requirement/risk outputs.

Consumed upstream shapes (see AGENTS.md; adapters are tolerant and mark MISSING_FROM_UPSTREAM):
  * requirement_analysis: RequirementAnalysisOutput
  * risk_analysis: RiskAnalysisOutput (risks under risk_analysis[] or risks[])
  * knowledge_search_results: KnowledgeSearchOutput (results[].chunk_id)
  * candidate_solutions: array of minimal solution objects (see schemas / references/04)
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# REPO_ROOT = .trae/skills/recommendation -> up to insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

FIT_LABELS = ["strong_fit", "good_fit", "partial_fit", "poor_fit", "not_suitable", "insufficient_evidence"]

# Step 2: violation types produced by product validation (never by constraint maths).
PRODUCT_BLOCK_TYPES = {
    "product_ineligible",
    "product_type_mismatch",
    "coverage_direction_mismatch",
    "product_not_in_catalog",
    "evidence_missing",
    "product_rejected",
}


def _dig(d, *keys, default=None):
    cur = d
    for k in keys:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


def _as_num(*vals):
    for v in vals:
        if isinstance(v, (int, float)):
            return float(v)
    return None


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def load_rules(path=None):
    if path is None:
        path = os.path.join(HERE, "..", "resources", "config", "recommendation.rules.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Adapters (normalize upstream outputs; never mutate them)
# --------------------------------------------------------------------------- #
def adapt_requirement_analysis(ra, rules):
    if not ra or not isinstance(ra, dict):
        return {"missing": True, "requirements": [], "priorities": [], "risk_gaps": [],
                "sufficiency": None, "status": None, "guardrails_ok": True,
                "unknowns": [], "assumptions": [], "scope": []}
    status = ra.get("analysis_status")
    reqs = ra.get("requirements", []) or []
    requirements = [{
        "requirement_id": r.get("requirement_id"),
        "requirement_type": r.get("requirement_type"),
        "summary": r.get("summary"),
        "priority": r.get("priority"),
    } for r in reqs]
    priorities = ra.get("priorities", []) or []
    gaps = ra.get("coverage_gaps", []) or []
    suff = _dig(ra, "information_sufficiency", "sufficiency_status")
    guard = _dig(ra, "guardrails", "product_recommendation_included")
    unknowns = ra.get("unknowns", []) or []
    assumptions = ra.get("assumptions", []) or []
    scope = ra.get("analysis_scope", []) or []
    # guardrails.product_recommendation_included MUST be false per requirement_analysis contract.
    guardrails_ok = (guard is not True)
    return {
        "missing": False, "status": status, "requirements": requirements,
        "priorities": priorities, "risk_gaps": gaps, "sufficiency": suff,
        "guardrails_ok": guardrails_ok, "unknowns": unknowns,
        "assumptions": assumptions, "scope": scope,
    }


def adapt_risk_analysis(rk, rules):
    if not rk or not isinstance(rk, dict):
        return {"missing": True, "risks": []}
    raw = rk.get("risk_analysis")
    if raw is None and isinstance(rk, dict) and "risks" in rk:
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
            "reasoning_evidence_refs": r.get("reasoning_evidence_refs", []) or [],
            "coverage_assessment": r.get("coverage_assessment", {}) or {},
            "unknowns": r.get("unknowns", []) or [],
        })
    return {"missing": False, "risks": risks}


def adapt_knowledge_search(ks):
    if not ks or not isinstance(ks, dict):
        return {"status": None, "results": [], "conflict": False}
    return {
        "status": ks.get("status"),
        "results": ks.get("results", []) or [],
        "conflict": bool(ks.get("conflict", False)),
    }


# --------------------------------------------------------------------------- #
# Decision context
# --------------------------------------------------------------------------- #
def build_decision_context(req, risk, ks, constraints, rules):
    pw = rules["priority_weight"]
    goals = []
    for r in req["requirements"]:
        rt = r.get("requirement_type")
        pr = r.get("priority")
        goals.append({
            "requirement_id": r.get("requirement_id"),
            "requirement_type": rt,
            "priority": pr,
            "weight": pw.get(pr, 1),
        })
    major = [r for r in risk["risks"]
             if r["residual_risk"] in rules["residual_risk_major"]
             and r["priority"] in rules["risk_priority_major"]]
    risk_gaps = [{
        "risk_id": r["risk_id"],
        "risk_category": r["risk_category"],
        "priority": r["priority"],
    } for r in major]

    hard = []
    if constraints:
        if constraints.get("budget_max") is not None:
            hard.append({"type": "budget", "value": _as_num(constraints["budget_max"])})
        if constraints.get("term_min_years") is not None:
            hard.append({"type": "term", "value": constraints["term_min_years"]})
        if constraints.get("liquidity_required"):
            hard.append({"type": "liquidity", "value": True})

    uncertainties = []
    if req.get("missing"):
        uncertainties.append({"type": "missing_information",
                              "detail": "requirement_analysis input missing"})
    elif req["status"] in ("NEED_MORE_INFORMATION", "CONFLICTING_INFORMATION", "FAILED"):
        uncertainties.append({"type": "missing_information",
                              "detail": f"requirement_analysis status={req['status']}"})
    elif req["sufficiency"] in ("INSUFFICIENT", "CONFLICTING"):
        uncertainties.append({"type": "missing_information",
                              "detail": f"information_sufficiency={req['sufficiency']}"})
    if risk.get("missing"):
        uncertainties.append({"type": "missing_information",
                              "detail": "risk_analysis input missing"})
    if ks["status"] == "insufficient_evidence":
        uncertainties.append({"type": "insufficient_evidence",
                              "detail": "knowledge_search returned insufficient_evidence"})
    if ks["conflict"]:
        uncertainties.append({"type": "evidence_conflict",
                              "detail": "knowledge_search flagged a source conflict"})

    return {
        "priority_goals": goals,
        "risk_gaps": risk_gaps,
        "hard_constraints": hard,
        "constraints_raw": constraints or {},
        "uncertainties": uncertainties,
    }


# --------------------------------------------------------------------------- #
# Fit classification
# --------------------------------------------------------------------------- #
def classify_fit(score, rules):
    t = rules["fit_score_thresholds"]
    if score >= t["strong_fit_min"]:
        return "strong_fit"
    if score >= t["good_fit_min"]:
        return "good_fit"
    if score >= t["partial_fit_min"]:
        return "partial_fit"
    if score >= t["poor_fit_min"]:
        return "poor_fit"
    return "not_suitable"


# --------------------------------------------------------------------------- #
# Candidate evaluation
# --------------------------------------------------------------------------- #
def _candidate_num(cand, *path):
    cur = cand
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return None
    return _as_num(cur)


def evaluate_candidate(cand, ctx, ks, rules):
    cid = cand.get("candidate_id")
    cov = cand.get("coverage_structure", []) or []
    cov_partial = cand.get("coverage_partial", []) or []
    covers_risk = cand.get("covers_risk_categories", []) or []

    # --- requirement fit ---
    req_status = {}
    matched, partial, unmet = [], [], []
    for g in ctx["priority_goals"]:
        rt = g["requirement_type"]
        if rt in cov:
            req_status[rt] = "matched"; matched.append(g["requirement_id"])
        elif rt in cov_partial:
            req_status[rt] = "partial"; partial.append(g["requirement_id"])
        else:
            req_status[rt] = "unmet"; unmet.append(g["requirement_id"])
    fw = rules["requirement_fit_weights"]
    wsum = sum(g["weight"] * fw.get(req_status.get(g["requirement_type"], "unmet"), 0.0)
               for g in ctx["priority_goals"])
    wtot = sum(g["weight"] for g in ctx["priority_goals"]) or 1.0
    req_score = wsum / wtot
    req_overall = classify_fit(req_score, rules)

    # --- risk fit ---
    major = ctx["risk_gaps"]
    covered, remaining = [], []
    for rg in major:
        if rg["risk_category"] in covers_risk:
            covered.append(rg["risk_id"])
        else:
            remaining.append(rg["risk_id"])
    risk_score = (len(covered) / len(major)) if major else 1.0
    risk_overall = classify_fit(risk_score, rules) if major else "strong_fit"

    # --- constraint fit (hard) ---
    # Phase 5 honesty guard: when the candidate lacks the product-level field a hard
    # constraint needs, the constraint is UNVERIFIABLE -- it is neither a violation nor a
    # pass. Previously an absent premium/term fell into the `else` branch and was recorded
    # as a hard PASS, which fabricated a "within_budget"/"meets_term" assurance for
    # strategy-level candidates that carry no product quote.
    violations, hard_pass, unverifiable = [], [], []

    # --- Step 2: product validation ---
    # Catalog-backed candidates carry `_product_validation` from the Candidate Provider.
    # Strategy-level candidates (legacy path) do NOT, so this block never fires for them
    # and the 11 legacy eval cases are unaffected.
    # A product that failed eligibility / type / direction validation is a HARD reject --
    # never a "the model liked it" recommendation. An unverifiable eligibility is its own
    # third state (never silently a pass).
    pval = cand.get("_product_validation")
    if isinstance(pval, dict):
        pid = pval.get("product_id") or cand.get("candidate_id")
        for b in pval.get("blockers") or []:
            sev = b.get("severity")
            detail = "product %s rejected: %s" % (pid, b.get("code") or b.get("blocked_reason"))
            if sev == "hard":
                violations.append({"type": b.get("blocked_reason", "product_rejected"),
                                   "detail": detail, "severity": "hard"})
            elif sev == "unverifiable":
                unverifiable.append({"type": b.get("blocked_reason", "product_unverifiable"),
                                     "detail": detail, "severity": "unverifiable"})

    budget = _candidate_num(cand, "premium", "annual")
    term = _candidate_num(cand, "term", "years")
    liq = cand.get("liquidity_impact")
    known_liq = liq in rules.get("known_liquidity_impacts", ["low", "medium", "high"])
    unc_detail = rules.get("unverifiable_constraint_detail", {})
    for hc in ctx["hard_constraints"]:
        if hc["type"] == "budget":
            if budget is None:
                unverifiable.append({"type": "budget",
                                     "detail": unc_detail.get("budget", "premium unknown"),
                                     "severity": "unverifiable"})
            elif hc["value"] is not None and budget > hc["value"]:
                violations.append({"type": "budget",
                                   "detail": f"premium {budget:g} > budget_max {hc['value']:g}",
                                   "severity": "hard"})
            else:
                hard_pass.append("budget")
        elif hc["type"] == "term":
            if term is None:
                unverifiable.append({"type": "term",
                                     "detail": unc_detail.get("term", "term unknown"),
                                     "severity": "unverifiable"})
            elif hc["value"] is not None and term < hc["value"]:
                violations.append({"type": "term",
                                   "detail": f"term {term:g} < term_min {hc['value']:g}",
                                   "severity": "hard"})
            else:
                hard_pass.append("term")
        elif hc["type"] == "liquidity":
            if not known_liq:
                unverifiable.append({"type": "liquidity",
                                     "detail": unc_detail.get("liquidity", "liquidity impact unknown"),
                                     "severity": "unverifiable"})
            elif liq == "high":
                violations.append({"type": "liquidity",
                                   "detail": "candidate has high liquidity impact",
                                   "severity": "hard"})
            else:
                hard_pass.append("liquidity")

    # --- evidence ---
    ks_ids = {r.get("chunk_id") for r in ks["results"]}
    refs = set(cand.get("source_refs", []) or []) | set(cand.get("evidence_refs", []) or [])
    present = [x for x in refs if x in ks_ids]
    ev_status = "supported"
    missing_evidence = []
    if cov and rules["evidence_required_for_primary"]:
        if not present:
            ev_status = "insufficient"
            missing_evidence = list(cov)
        elif ks["status"] == "insufficient_evidence":
            ev_status = "insufficient"
            missing_evidence = list(cov)
    if ks["conflict"]:
        ev_status = "conflict"

    # --- tentative recommendation_status ---
    has_hard = any(v["severity"] == "hard" for v in violations)
    # Priority: a HARD product-validation block (ineligible / type / direction mismatch /
    # not-in-catalog) wins over evidence status. An ineligible product can NEVER be
    # recommended, so its evidence being missing or present is irrelevant. Previously the
    # evidence check ran first, which let an ineligible-but-evidence-missing candidate
    # masquerade as `insufficient_evidence` instead of `not_recommended` -- masking the
    # real blocker and pushing the overall status toward INCOMPLETE_EVIDENCE when the
    # correct status is NO_CANDIDATES.
    if has_hard:
        rec_status = "not_recommended"
    elif ev_status in ("insufficient", "conflict"):
        rec_status = "insufficient_evidence"
    elif req_overall in ("poor_fit", "not_suitable"):
        rec_status = "not_recommended"
    else:
        rec_status = "primary"

    # --- provenance ---
    prov = []
    for rid in matched:
        prov.append({"type": "requirement", "ref": rid})
    for rid in covered:
        prov.append({"type": "risk", "ref": rid})
    for x in present:
        prov.append({"type": "knowledge", "ref": x})

    # --- tradeoffs ---
    tradeoffs = []
    if covered:
        tradeoffs.append({"advantage": "covers high-priority risk(s)",
                          "cost": f"premium {budget:g}" if budget is not None else "premium n/a",
                          "impact": "medium"})
    if has_hard:
        tradeoffs.append({"advantage": "-", "cost": violations[0]["detail"], "impact": "high"})
    if not covered and major:
        tradeoffs.append({"advantage": "-", "cost": f"leaves gap(s): {', '.join(remaining)}",
                          "impact": "high"})

    candidate_uncs = []
    if ev_status == "insufficient":
        candidate_uncs.append({"type": "insufficient_evidence",
                               "detail": f"coverage {cov} lacks knowledge backing",
                               "candidate_id": cid})
    if ev_status == "conflict":
        candidate_uncs.append({"type": "evidence_conflict",
                               "detail": "knowledge conflict on this candidate",
                               "candidate_id": cid})
    for u in unverifiable:
        candidate_uncs.append({"type": "constraint_unverifiable",
                               "detail": u["detail"],
                               "candidate_id": cid,
                               "constraint": u["type"]})

    return {
        "candidate_id": cid,
        "requirement_fit": {
            "overall": req_overall, "score": round(req_score, 4),
            "matched": matched, "partial": partial, "unmet": unmet,
        },
        "risk_fit": {
            "overall": risk_overall, "score": round(risk_score, 4),
            "covered_risks": covered, "remaining_gaps": remaining,
        },
        "constraint_fit": {
            "hard_constraints": hard_pass, "soft_constraints": [], "violations": violations,
            "unverifiable_constraints": unverifiable,
        },
        "evidence": {
            "status": ev_status, "refs": list(refs),
            "missing_evidence": missing_evidence,
        },
        "tradeoffs": tradeoffs,
        "uncertainties": candidate_uncs,
        "recommendation_status": rec_status,
        "reason": (
            f"因为需求匹配度 {req_overall}（得分 {round(req_score, 4)}）、"
            f"风险覆盖 {risk_overall}（覆盖 {', '.join(covered) or '无'}），"
            + (f"触发硬约束冲突：{'; '.join(v['detail'] for v in violations)}，"
               if has_hard else "")
            + f"证据状态 {ev_status}，"
            f"所以判定推荐状态为 {rec_status}"
        ),
        "provenance": prov,
        "_composite": None,
    }


# --------------------------------------------------------------------------- #
# Aggregation
# --------------------------------------------------------------------------- #
def _composite(e, rules):
    w = rules["recommendation_weights"]
    ev = 1.0 if e["evidence"]["status"] == "supported" else 0.0
    return (w["requirement_fit"] * e["requirement_fit"]["score"]
            + w["risk_fit"] * e["risk_fit"]["score"]
            + w["evidence"] * ev)


def generate_recommendation(input_dict, rules=None):
    if rules is None:
        rules = load_rules()

    ra = adapt_requirement_analysis(input_dict.get("requirement_analysis"), rules)
    rk = adapt_risk_analysis(input_dict.get("risk_analysis"), rules)
    ks = adapt_knowledge_search(input_dict.get("knowledge_search_results"))
    constraints = input_dict.get("constraints")
    candidates = input_dict.get("candidate_solutions") or []

    # Step 1: validate inputs
    missing_inputs = []
    if ra.get("missing"):
        missing_inputs.append("requirement_analysis")
    if rk.get("missing"):
        missing_inputs.append("risk_analysis")
    if input_dict.get("candidate_solutions") is None:
        missing_inputs.append("candidate_solutions")

    ctx = build_decision_context(ra, rk, ks, constraints, rules)

    if missing_inputs:
        return {
            "skill": "recommendation",
            "version": "0.1",
            "status": "INSUFFICIENT_INPUT",
            "decision_context": ctx,
            "candidate_evaluations": [],
            "primary_recommendation": None,
            "alternatives": [],
            "not_recommended": [],
            "tradeoffs": [],
            "uncertainties": [{"type": "missing_information",
                               "detail": f"missing required input(s): {', '.join(missing_inputs)}"}],
            "evidence_refs": [],
            "human_review_required": True,
            "_missing_inputs": missing_inputs,
        }

    if not candidates:
        return {
            "skill": "recommendation",
            "version": "0.1",
            "status": "NO_CANDIDATES",
            "decision_context": ctx,
            "candidate_evaluations": [],
            "primary_recommendation": None,
            "alternatives": [],
            "not_recommended": [],
            "tradeoffs": [],
            "uncertainties": [{"type": "missing_information", "detail": "no candidate solutions provided"}],
            "evidence_refs": [],
            "human_review_required": True,
        }

    evals = [evaluate_candidate(c, ctx, ks, rules) for c in candidates]
    for e in evals:
        e["_composite"] = _composite(e, rules)

    # Step 8/9: rank eligible (not hard-blocked, not evidence-insufficient)
    eligible = [e for e in evals if e["recommendation_status"] == "primary"]
    # sort eligible by composite desc
    eligible.sort(key=lambda e: e["_composite"], reverse=True)

    primary = eligible[0] if eligible else None
    alternatives = [e for e in eligible[1:3]]
    not_rec = [e for e in evals if e["recommendation_status"] == "not_recommended"]
    insuff = [e for e in evals if e["recommendation_status"] == "insufficient_evidence"]

    # Step 2: keep the product identity alongside each evaluation so the final
    # recommendation traces back to a catalog product, never to a free-text invention.
    product_meta_by_cid = {}
    for c in candidates:
        pv = c.get("_product_validation")
        if isinstance(pv, dict) and c.get("candidate_id"):
            meta = dict(pv)
            meta["product_name"] = c.get("solution_name")
            product_meta_by_cid[c["candidate_id"]] = meta

    # Build not_recommended entries with reasons
    not_rec_out = []
    for e in not_rec:
        pviol = [v for v in e["constraint_fit"]["violations"]
                 if v.get("type") in PRODUCT_BLOCK_TYPES]
        if pviol:
            reason = ("因为产品校验未通过（" + ", ".join(sorted({str(v["type"]) for v in pviol}))
                      + "），所以不推荐")
        elif e["constraint_fit"]["violations"]:
            reason = ("因为触发硬约束（"
                      + "; ".join(v.get("detail", v.get("type", "")) for v in e["constraint_fit"]["violations"])
                      + "），所以不推荐")
        else:
            reason = ("因为需求匹配度 " + e["requirement_fit"]["overall"] + "、风险覆盖 "
                      + e["risk_fit"]["overall"] + "，匹配度不足，所以不推荐")
        not_rec_out.append({"candidate_id": e["candidate_id"], "reason": reason, "exception": False})
    for e in insuff:
        not_rec_out.append({"candidate_id": e["candidate_id"],
                            "reason": "因为该候选产品虽通过产品校验、但缺乏知识库证据支撑，所以暂不能推荐（INCOMPLETE_EVIDENCE）",
                            "exception": False})

    # primary recommendation object
    primary_out = None
    if primary:
        reason_codes = []
        if primary["risk_fit"]["covered_risks"]:
            reason_codes.append("covers_high_priority_risk")
        if "budget" in primary["constraint_fit"]["hard_constraints"]:
            reason_codes.append("within_budget")
        if "term" in primary["constraint_fit"]["hard_constraints"]:
            reason_codes.append("meets_term")
        if primary["requirement_fit"]["unmet"]:
            reason_codes.append("has_unmet_requirements")
        _prim_parts = ["需求匹配度 " + primary["requirement_fit"]["overall"]]
        if primary["risk_fit"]["covered_risks"]:
            _prim_parts.append("覆盖高优先级风险 " + ", ".join(primary["risk_fit"]["covered_risks"]))
        if "budget" in primary["constraint_fit"]["hard_constraints"]:
            _prim_parts.append("在预算内")
        if primary["requirement_fit"]["unmet"]:
            _prim_parts.append("未满足需求 " + ", ".join(primary["requirement_fit"]["unmet"]))
        _prim_parts.append("证据状态 " + primary["evidence"]["status"])
        primary_out = {
            "candidate_id": primary["candidate_id"],
            "fit": primary["requirement_fit"]["overall"],
            "reason_codes": reason_codes,
            "reason": "因为" + "、".join(_prim_parts) + "，所以作为主推荐",
            "provenance": primary["provenance"],
        }
        # Step 2: the recommendation must name a real catalog product, so the product
        # identity travels with it (product_id / is_demo / gap + solution lineage).
        pmeta = product_meta_by_cid.get(primary["candidate_id"])
        if pmeta:
            primary_out["product"] = {
                "product_id": pmeta.get("product_id"),
                "product_name": pmeta.get("product_name"),
                "product_type": pmeta.get("product_type"),
                # Step 4 Phase 8: the exact catalog + product edition this recommendation
                # was reasoned from, so a historical case stays explainable after the
                # catalog is updated.
                "product_version": pmeta.get("product_version"),
                "catalog_version": pmeta.get("catalog_version"),
                "effective_from": pmeta.get("effective_from"),
                "effective_to": pmeta.get("effective_to"),
                "is_demo": bool(pmeta.get("is_demo", False)),
                "solution_id": pmeta.get("solution_id"),
                "related_gap_ids": list(pmeta.get("related_gap_ids") or []),
                "eligibility": pmeta.get("eligibility"),
                "evidence_status": pmeta.get("evidence_status"),
            }

    alt_out = []
    for e in alternatives:
        entry = {
            "candidate_id": e["candidate_id"],
            "fit": e["requirement_fit"]["overall"],
            "reason": (
                f"因为 {e['candidate_id']} 同样通过产品校验、需求匹配度 {e['requirement_fit']['overall']}，"
                f"但综合评分低于主推，所以作为备选"
            ),
            "tradeoff": ("lower cost but weaker coverage" if e["requirement_fit"]["score"] < (primary["requirement_fit"]["score"] if primary else 1)
                         else "secondary option"),
        }
        ameta = product_meta_by_cid.get(e["candidate_id"])
        if ameta:
            entry["product"] = {
                "product_id": ameta.get("product_id"),
                "product_name": ameta.get("product_name"),
                "product_type": ameta.get("product_type"),
                "product_version": ameta.get("product_version"),
                "catalog_version": ameta.get("catalog_version"),
                "is_demo": bool(ameta.get("is_demo", False)),
            }
        alt_out.append(entry)

    # overall uncertainties
    uncertainties = list(ctx["uncertainties"])
    for e in evals:
        uncertainties.extend(e["uncertainties"])

    # evidence refs aggregation
    all_refs = set()
    for e in evals:
        all_refs.update(e["evidence"]["refs"])
    for p in (primary_out["provenance"] if primary_out else []):
        if p["type"] == "knowledge":
            all_refs.add(p["ref"])

    human_review = bool(uncertainties) or (primary is None)

    # Status: only EVIDENCE/information problems downgrade to INCOMPLETE_EVIDENCE.
    # Phase 5: a `constraint_unverifiable` uncertainty means "needs a human to verify a
    # constraint against real product data" -- the recommendation itself is complete, so
    # mislabeling it INCOMPLETE_EVIDENCE would misrepresent what is actually uncertain.
    blocking_types = set(rules.get("blocking_uncertainty_types",
                                   ["insufficient_evidence", "evidence_conflict", "missing_information"]))
    blocking = [u for u in uncertainties if u.get("type") in blocking_types]
    status = "COMPLETE"
    if primary is None:
        # No recommendable product. The status depends on WHY, not merely on whether any
        # candidate lacks evidence:
        #  - `insuff` holds candidates that PASSED product checks but only fail the
        #    evidence check (eligible, just no knowledge backing). Such a product IS
        #    buyable, we merely cannot justify it yet -> INCOMPLETE_EVIDENCE.
        #  - otherwise (every candidate is ineligible / poor-fit, or there are none)
        #    there is no product the client can actually buy -> NO_CANDIDATES.
        # Using the raw `evidence.status` here would be wrong: an ineligible candidate's
        # evidence may also read "insufficient" (e.g. an empty knowledge base), but that
        # does not make it a buyable product, so it must not elevate the status.
        status = "INCOMPLETE_EVIDENCE" if insuff else "NO_CANDIDATES"
    elif blocking:
        status = "INCOMPLETE_EVIDENCE"

    out = {
        "skill": "recommendation",
        "version": "0.1",
        "status": status,
        "decision_context": ctx,
        "candidate_evaluations": evals,
        "primary_recommendation": primary_out,
        "alternatives": alt_out,
        "not_recommended": not_rec_out,
        "tradeoffs": [t for e in evals for t in e["tradeoffs"]],
        "uncertainties": uncertainties,
        "evidence_refs": sorted(all_refs),
        "human_review_required": human_review,
    }
    # Phase 5: carry the SolutionPlan->candidate provenance so downstream can trace every
    # evaluated candidate back to the strategy (and hence the gap/risk) it came from.
    if input_dict.get("_strategy_trace"):
        out["strategy_trace"] = input_dict["_strategy_trace"]
    return out


def main():
    if len(sys.argv) < 2:
        print("usage: recommendation_engine.py <input.json> [rules.json]", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    rules = load_rules(sys.argv[2]) if len(sys.argv) > 2 else load_rules()
    out = generate_recommendation(data, rules)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
