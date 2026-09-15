"""Step 2: ProductCandidates -> candidate_solutions (adapter only).

WHY THIS EXISTS
---------------
`recommendation_engine` is a stable component with an 11-case regression baseline. Step 2
must NOT rewrite it. Instead this module projects real, catalog-backed ProductCandidates
onto the candidate shape the engine already understands:

    ProductCandidate -> {candidate_id, coverage_structure, covers_risk_categories,
                         premium, term, liquidity_impact, source_refs, _product_validation}

Two guarantees:
  * No product is invented here. Every projected candidate carries the product_id it came
    from, and the engine hard-blocks any candidate whose validation did not pass.
  * Legacy behaviour is untouched: when no `product_candidates` are supplied, the caller
    falls back to `solution_to_candidates` (strategy-level) exactly as before.
"""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RULES = os.path.join(HERE, "..", "resources", "config",
                             "product-candidate-to-solution.rules.json")


def load_rules(path=None):
    with open(path or DEFAULT_RULES, encoding="utf-8") as f:
        return json.load(f)


def _payload(artifact):
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact if isinstance(artifact, dict) else {}


def _candidates(product_candidates):
    """Accept the provider output envelope, a bare payload, or a plain list."""
    if isinstance(product_candidates, list):
        return product_candidates
    p = _payload(product_candidates)
    return p.get("candidates") or []


def _risk_category_index(risk_assessment):
    p = _payload(risk_assessment)
    raw = p.get("risks")
    if raw is None:
        raw = p.get("risk_analysis")
    idx = {}
    for r in raw or []:
        if isinstance(r, dict) and r.get("risk_id") and r.get("risk_category"):
            idx[r["risk_id"]] = r["risk_category"]
    return idx


def project(product_candidates, risk_assessment=None, rules=None):
    """Return (candidate_solutions, trace)."""
    rules = rules or load_rules()
    type_to_req = rules["product_type_to_requirement_types"]
    fallback_cat = rules["risk_category_fallback_by_product_type"]
    blocked_by = rules["blocked_reason_by_code"]
    hard_codes = set(rules["hard_block_codes"])
    unknown_codes = set(rules["unknown_block_codes"])
    risk_idx = _risk_category_index(risk_assessment)

    out, trace = [], []
    for c in _candidates(product_candidates):
        ptype = c.get("product_type") or ""
        cats = []
        for rid in c.get("related_risk_ids") or []:
            cat = risk_idx.get(rid)
            if cat and cat not in cats:
                cats.append(cat)
        if not cats:
            cats = list(fallback_cat.get(ptype, []) or [])

        codes = list(c.get("reject_reason_codes") or [])
        blockers = []
        for code in codes:
            b = blocked_by.get(code, code)
            severity = "hard" if code in hard_codes else (
                "unverifiable" if code in unknown_codes else "soft")
            blockers.append({"code": code, "blocked_reason": b, "severity": severity})

        term = c.get("term") or {}
        prem = c.get("premium") or {}
        cand = {
            "candidate_id": c.get("candidate_id"),
            "solution_name": c.get("product_name") or c.get("candidate_id"),
            "coverage_structure": list(type_to_req.get(ptype, [ptype] if ptype else [])),
            "coverage_partial": [],
            "covers_risk_categories": cats,
            "liquidity_impact": c.get("liquidity_impact"),
            "source_refs": list((c.get("evidence") or {}).get("evidence_ids") or []),
            "premium": {"annual": prem.get("annual")},
            "term": {"years": term.get("years")},
            "_product_validation": {
                "product_id": c.get("product_id"),
                "product_type": ptype,
                # Step 4 Phase 8: carry the catalog/product edition through the projection,
                # so the final recommendation can pin which edition it was based on.
                "product_version": c.get("product_version"),
                "catalog_version": c.get("catalog_version"),
                "effective_from": c.get("effective_from"),
                "effective_to": c.get("effective_to"),
                "is_demo": bool(c.get("is_demo", False)),
                "admissible": bool(c.get("admissible", False)),
                "reject_reason_codes": codes,
                "blockers": blockers,
                "eligibility": (c.get("eligibility") or {}).get("status", "UNKNOWN"),
                "evidence_status": (c.get("evidence") or {}).get("status", "MISSING"),
                # Step 4 Phase 7: carry the attribute-level verdict so a downstream reader
                # can see WHY evidence was rejected (which attribute was not backed).
                "evidence_attribute_rollup": (c.get("evidence") or {}).get("attribute_rollup"),
                "evidence_unsupported_attributes": sorted(
                    k for k, v in ((((c.get("evidence") or {}).get("grounding") or {})
                                    .get("attributes")) or {}).items()
                    if isinstance(v, dict) and v.get("status") == "UNSUPPORTED"),
                "related_gap_ids": list(c.get("related_gap_ids") or []),
                "solution_id": c.get("solution_id"),
            },
        }
        out.append(cand)
        trace.append({
            "candidate_id": c.get("candidate_id"),
            "product_id": c.get("product_id"),
            "solution_id": c.get("solution_id"),
            "related_gap_ids": list(c.get("related_gap_ids") or []),
            "related_risk_ids": list(c.get("related_risk_ids") or []),
            "evidence_ids": list((c.get("evidence") or {}).get("evidence_ids") or []),
        })
    return out, trace


def build_v2_input_from_product_candidates(
    requirement_analysis, risk_assessment, coverage_gap_analysis, solution_plan,
    knowledge_evidence, product_candidates, constraints=None, rules=None,
):
    """Assemble the legacy-shaped input dict, but with REAL catalog candidates.

    KnowledgeEvidence is still projected through the existing `build_knowledge_view` so
    evidence matching stays identical to the strategy-level path.
    """
    from solution_to_candidates import _payload, build_knowledge_view

    rules = rules or load_rules()
    candidates, trace = project(product_candidates, risk_assessment, rules)
    ks_view = build_knowledge_view(
        knowledge_evidence,
        __import__("solution_to_candidates").load_rules(),
    )
    return {
        "requirement_analysis": _payload(requirement_analysis),
        "risk_analysis": _payload(risk_assessment),
        "candidate_solutions": candidates,
        "knowledge_search_results": ks_view,
        "constraints": constraints,
        "_strategy_trace": trace,
        "_candidate_source": "product_candidate_provider",
    }
