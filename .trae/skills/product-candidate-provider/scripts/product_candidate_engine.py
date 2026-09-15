"""Product Candidate Provider engine (Step 2, Phase 4).

WHY THIS SKILL EXISTS
---------------------
Before Step 2 the chain had a hole that looked harmless but was not:

    SolutionPlan -> (solution_to_candidates) -> candidate_solutions -> recommendation

`solution_to_candidates` turns a STRATEGY ("建立家庭责任保障") into a candidate. A strategy
carries no product, no premium, no term, no eligibility and no evidence -- so
`recommendation` was ranking objects that cannot exist in a catalog. That is not candidate
generation; it is placeholder propagation.

This engine closes the hole properly:

    SolutionPlan + CoverageGap + ClientState + ProductCatalog + KnowledgeEvidence
        -> ProductCandidates (real catalog products, deterministically filtered)

DESIGN RULES (AGENTS.md + Step 2 spec)
  * Deterministic: every mapping/threshold lives in
    resources/config/candidate-provider.rules.json. The engine never hardcodes one.
  * No invented products: a candidate exists ONLY if its product_id is in the catalog.
  * It does NOT recommend. It answers "which catalog products could possibly fit?".
    Ranking/choosing is `recommendation`'s job (see CONTRACT.md).
  * Honest failure: a product that exists but has no evidence is emitted with
    `EVIDENCE_MISSING` -- never silently promoted.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
# scripts -> product-candidate-provider -> skills -> .trae -> insurance-agent
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

DEFAULT_RULES = os.path.join(SKILL_DIR, "resources", "config", "candidate-provider.rules.json")


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_rules(path=None):
    with open(path or DEFAULT_RULES, encoding="utf-8") as f:
        return json.load(f)


def load_catalog(path=None, rules=None):
    rules = rules or load_rules()
    p = path or rules.get("catalog_path") or "catalog/product-catalog.v0.1.json"
    if not os.path.isabs(p):
        p = os.path.join(REPO_ROOT, p)
    with open(p, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def extract_payload(artifact):
    """Accept a canonical envelope ({artifact_type, payload}) or a bare payload."""
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact if isinstance(artifact, dict) else {}


def _get_path(d, path):
    cur = d
    for part in str(path).split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _num(v, value_keys=("value", "amount")):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        # Canonical FactValue carries the scalar as a string (e.g. age "35"); coerce it.
        try:
            return float(v)
        except ValueError:
            return None
    if isinstance(v, dict):
        for k in value_keys:
            if k in v:
                x = v[k]
                if isinstance(x, bool):
                    continue
                if isinstance(x, (int, float)):
                    return float(x)
                if isinstance(x, str):
                    try:
                        return float(x)
                    except ValueError:
                        continue
    return None


def _first(d, paths):
    for p in paths:
        v = _get_path(d, p)
        if v is not None:
            return v
    return None


# --------------------------------------------------------------------------- #
# Catalog lookup
# --------------------------------------------------------------------------- #
def index_catalog(catalog):
    by_id = {}
    for p in catalog.get("products", []) or []:
        pid = p.get("product_id")
        if pid:
            by_id[pid] = p
    return by_id


def lookup_product(catalog_or_index, name_or_id):
    """Resolve a product by id or name.

    Step 2 spec, Negative Test 5: an unknown product name must resolve to NOT_FOUND.
    It must never be auto-created or fuzzy-matched into an existing product.
    """
    if isinstance(catalog_or_index, dict) and "products" in catalog_or_index:
        idx = index_catalog(catalog_or_index)
    else:
        idx = catalog_or_index or {}
    if name_or_id in idx:
        return "FOUND", idx[name_or_id]
    for p in idx.values():
        if p.get("product_name") == name_or_id:
            return "FOUND", p
    return "NOT_FOUND", None


# --------------------------------------------------------------------------- #
# Product type resolution
# --------------------------------------------------------------------------- #
def _solutions(solution_plan):
    p = extract_payload(solution_plan)
    sols = p.get("solutions")
    if isinstance(sols, list) and sols:
        return sols
    if isinstance(sols, list):
        return []
    # Degenerate envelope carrying only the derived top-level triple.
    if p.get("solution_id") or p.get("objective"):
        return [p]
    return []


def _gaps(coverage_gap_analysis):
    return extract_payload(coverage_gap_analysis).get("gaps") or []


def _gap_domains(solution, coverage_gap_analysis):
    ids = set(solution.get("related_gap_ids") or [])
    if not ids:
        return []
    out = []
    for g in _gaps(coverage_gap_analysis):
        if g.get("gap_id") in ids and g.get("domain") and g["domain"] not in out:
            out.append(g["domain"])
    return out


def resolve_product_types(solution, coverage_gap_analysis, rules):
    """solution_type -> product_types, with gap-domain fallback for GENERAL."""
    stype = solution.get("solution_type") or "GENERAL"
    types = list(rules["solution_type_to_product_types"].get(stype, []) or [])
    if types:
        return types
    if rules.get("general_fallback_to_gap_domains"):
        d2p = rules["domain_to_product_types"]
        for d in _gap_domains(solution, coverage_gap_analysis):
            for t in d2p.get(d, []) or []:
                if t not in types:
                    types.append(t)
    return types


# --------------------------------------------------------------------------- #
# Coverage direction match
# --------------------------------------------------------------------------- #
def match_coverage_direction(solution_direction, product_directions, rules):
    cfg = rules["coverage_direction"]
    if not solution_direction:
        return cfg["empty_direction_status"], []
    if not product_directions:
        return cfg["empty_product_directions_status"], []
    hits = [t for t in product_directions if t and t in solution_direction]
    if cfg["match_mode"] == "any_token":
        return ("MATCH" if hits else "MISMATCH"), hits
    return ("MATCH" if len(hits) == len(product_directions) else "MISMATCH"), hits


# --------------------------------------------------------------------------- #
# Eligibility
# --------------------------------------------------------------------------- #
def check_eligibility(client_profile, product, rules):
    """Deterministic eligibility check. Returns (status, checks, reasons).

    UNKNOWN is a third state, never folded into ELIGIBLE: a missing age must not
    silently become a pass (that is the fake-pass trap from earlier phases).
    """
    cfg = rules["eligibility"]
    client = extract_payload(client_profile) or {}
    checks, reasons = [], []
    hard_fail, unverifiable = False, False

    for rule in product.get("eligibility_rules", []) or []:
        name = rule.get("rule")
        if name not in cfg["enforce_rules"]:
            continue
        if name == "age":
            raw = _first(client, cfg["age_paths"])
            age = _num(raw, cfg.get("age_value_keys", ["value", "amount"]))
            if age is None:
                unverifiable = True
                checks.append({"rule": "age", "status": "UNKNOWN", "detail": "client age not available"})
                reasons.append("客户年龄未知，无法判定投保年龄")
                continue
            lo, hi = rule.get("min"), rule.get("max")
            ok = True
            if lo is not None and age < lo:
                ok = False
            if hi is not None and age > hi:
                ok = False
            if ok:
                checks.append({"rule": "age", "status": "PASS", "detail": f"age={age:g}"})
            else:
                hard_fail = True
                checks.append({"rule": "age", "status": "FAIL",
                               "detail": f"age={age:g} outside [{lo}, {hi}]"})
                reasons.append(f"客户年龄 {age:g} 岁不在产品投保年龄区间 [{lo}, {hi}]")
        elif name == "occupation_class":
            raw = _first(client, cfg["occupation_paths"])
            occ = _num(raw, cfg.get("age_value_keys", ["value", "amount"]))
            if occ is None:
                if cfg.get("unknown_occupation_skips_check"):
                    checks.append({"rule": "occupation_class", "status": "UNKNOWN",
                                   "detail": "occupation class not available; check skipped"})
                else:
                    unverifiable = True
                    checks.append({"rule": "occupation_class", "status": "UNKNOWN",
                                   "detail": "occupation class not available"})
                    reasons.append("客户职业类别未知，无法判定")
                continue
            mx = rule.get("max")
            if mx is not None and occ > mx:
                hard_fail = True
                checks.append({"rule": "occupation_class", "status": "FAIL",
                               "detail": f"occupation_class={occ:g} > max {mx}"})
                reasons.append(f"客户职业类别 {occ:g} 超出产品上限 {mx}")
            else:
                checks.append({"rule": "occupation_class", "status": "PASS",
                               "detail": f"occupation_class={occ:g}"})

    if hard_fail:
        return "INELIGIBLE", checks, reasons
    if unverifiable:
        return "UNKNOWN", checks, reasons
    if not checks:
        return "UNKNOWN", [{"rule": "none", "status": "UNKNOWN",
                            "detail": "product declares no enforceable eligibility rule"}], \
                          ["产品未声明可校验的投保条件"]
    return "ELIGIBLE", checks, reasons


# --------------------------------------------------------------------------- #
# Evidence resolution
# --------------------------------------------------------------------------- #
def _evidence_domain(item, rules):
    cfg = rules["evidence"]
    doc = item.get("document_name") or item.get("source") or ""
    if doc:
        head = doc.replace("-", "_").split("_")[0]
        if head in cfg["domain_by_document_prefix"]:
            return cfg["domain_by_document_prefix"][head]
        low = doc.lower()
        for token, dom in cfg["domain_of_document_by_name_contains"].items():
            if token in low:
                return dom
    return None


def resolve_evidence(product, knowledge_evidence, rules, grounding_rules=None):
    """Attach KnowledgeEvidence to a product. A product with no evidence is MISSING,
    not silently supported.

    Step 4 Phase 7: domain availability alone is NOT enough. The evidence that matched the
    product's domains is additionally grounded ATTRIBUTE BY ATTRIBUTE (see
    evidence/attribute_grounding.py). A product whose evidence exists but does not actually
    state a required attribute (rollup=UNSUPPORTED) is no longer treated as available --
    "there is a medical document" must not read as "the product's terms are backed".
    NOT_CHECKABLE is a distinct third state and does NOT block on its own.
    """
    cfg = rules["evidence"]
    p = extract_payload(knowledge_evidence) or {}
    items = p.get("evidence", []) or []
    if not items:
        return {"status": cfg["missing_evidence_status"], "available": False,
                "evidence_ids": [], "documents": [], "domains_matched": [],
                "grounding": None, "attribute_rollup": None}

    required = set(product.get("required_evidence_domains") or [])
    declared = set(product.get("evidence_refs") or [])
    ids, docs, doms, matched = [], [], [], []
    for it in items:
        dom = _evidence_domain(it, rules)
        doc = it.get("document_name") or ""
        hit = (dom is not None and dom in required) or (doc and doc in declared)
        if hit:
            matched.append(it)
            if it.get("evidence_id"):
                ids.append(it["evidence_id"])
            if doc and doc not in docs:
                docs.append(doc)
            if dom and dom not in doms:
                doms.append(dom)

    grounding = None
    rollup = None
    try:
        from knowledge.evidence import attribute_grounding as ag  # shared Evidence layer
        grounding = ag.ground_product_attributes(product, matched, grounding_rules)
        rollup = grounding.get("rollup")
    except Exception as e:  # noqa: BLE001 - grounding must never break candidate build
        grounding = {"rollup": "NOT_CHECKABLE", "attributes": {},
                     "error": "%s: %s" % (type(e).__name__, e)}
        rollup = "NOT_CHECKABLE"

    if ids or docs:
        # only a POSITIVE "unsupported" downgrades; NOT_CHECKABLE stays non-blocking.
        degraded = rollup == "UNSUPPORTED"
        return {"status": cfg["missing_evidence_status"] if degraded else "AVAILABLE",
                "available": not degraded, "evidence_ids": ids,
                "documents": docs, "domains_matched": doms,
                "grounding": grounding, "attribute_rollup": rollup}
    return {"status": cfg["missing_evidence_status"], "available": False,
            "evidence_ids": [], "documents": [], "domains_matched": [],
            "grounding": grounding, "attribute_rollup": rollup}


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def build_candidates(input_dict, rules=None, catalog=None):
    rules = rules or load_rules()
    catalog = catalog or load_catalog(rules=rules)
    by_id = index_catalog(catalog)

    client_profile = input_dict.get("client_profile")
    solution_plan = input_dict.get("solution_plan")
    coverage_gap_analysis = input_dict.get("coverage_gap_analysis")
    knowledge_evidence = input_dict.get("knowledge_evidence")
    requested = input_dict.get("requested_product_ids") or []

    # --- Negative Test 1: a requested product that is not in the catalog ---
    rejected_unknown = []
    for pid in requested:
        status, _ = lookup_product(by_id, pid)
        if status == "NOT_FOUND":
            rejected_unknown.append({
                "product_id": pid, "candidate_id": None,
                "reason_codes": ["PRODUCT_NOT_IN_CATALOG"],
                "reason": rules["reject_reason_codes"]["PRODUCT_NOT_IN_CATALOG"],
            })

    candidates, rejected = [], []
    seq = 0
    for sol in _solutions(solution_plan):
        sid = sol.get("solution_id") or "SOL-UNKNOWN"
        ptypes = resolve_product_types(sol, coverage_gap_analysis, rules)
        if not ptypes:
            # No product type can serve this strategy. This MUST mean zero candidates --
            # NOT "every product qualifies". An empty type list falling through to the
            # per-product filter would silently nominate the whole catalog, which is the
            # exact fake-pass shape this layer exists to prevent.
            continue
        direction = sol.get("coverage_direction") or ""
        gap_ids = list(sol.get("related_gap_ids") or [])
        risk_ids = list(sol.get("related_risk_ids") or [])

        for product in catalog.get("products", []) or []:
            pid = product.get("product_id")
            codes = []

            # 1. product type match
            if ptypes and product.get("product_type") not in ptypes:
                # Not even a candidate for this strategy -- skip entirely (do not spam).
                continue

            # 2. coverage direction match
            dstatus, hits = match_coverage_direction(
                direction, product.get("coverage_directions") or [], rules)
            if dstatus == "MISMATCH":
                codes.append("COVERAGE_DIRECTION_MISMATCH")
            elif dstatus == "UNKNOWN":
                codes.append("COVERAGE_DIRECTION_MISMATCH")

            # 3. eligibility
            estatus, checks, reasons = check_eligibility(client_profile, product, rules)
            if estatus == "INELIGIBLE":
                codes.append("ELIGIBILITY_INELIGIBLE")
            elif estatus == "UNKNOWN":
                codes.append("ELIGIBILITY_UNKNOWN")

            # 4. evidence availability + attribute-level grounding (Step 4 Phase 7)
            ev = resolve_evidence(product, knowledge_evidence, rules)
            if rules["evidence"].get("require_evidence_for_admissible") and not ev["available"]:
                # distinguish "no evidence at all" from "evidence exists but does not
                # actually state the product's required attributes".
                codes.append("EVIDENCE_UNSUPPORTED"
                             if ev.get("attribute_rollup") == "UNSUPPORTED"
                             else "EVIDENCE_MISSING")

            seq += 1
            cand = {
                "candidate_id": "C%03d" % seq,
                "product_id": pid,
                "product_name": product.get("product_name"),
                "product_type": product.get("product_type"),
                "company": product.get("company"),
                "is_demo": bool(product.get("is_demo", False)),
                # Step 4 Phase 8: pin the exact catalog edition + product edition the
                # candidate was selected from, so a historical case can still explain
                # "why was THIS product recommended THEN" after the catalog moves on.
                "product_version": product.get("product_version"),
                "catalog_version": catalog.get("catalog_version"),
                "effective_from": product.get("effective_from"),
                "effective_to": product.get("effective_to"),
                "solution_id": sid,
                "related_gap_ids": gap_ids,
                "related_risk_ids": risk_ids,
                "product_type_match": "MATCH",
                "coverage_direction_match": dstatus,
                "coverage_direction_hits": hits,
                "eligibility": {"status": estatus, "checks": checks, "reasons": reasons},
                "evidence": ev,
                "features": list(product.get("features") or []),
                "constraints": list(product.get("constraints") or []),
                "premium": dict(product.get("premium") or {}),
                "term": dict(product.get("term") or {}),
                "liquidity_impact": product.get("liquidity_impact"),
                "admissible": not codes,
                "reject_reason_codes": codes,
                "provenance": [
                    {"source_type": "PRODUCT_CATALOG", "source_id": pid, "confidence": None},
                    {"source_type": "SOLUTION", "source_id": sid, "confidence": None},
                ],
            }
            for gid in gap_ids:
                cand["provenance"].append({"source_type": "GAP", "source_id": gid, "confidence": None})
            for eid in ev["evidence_ids"]:
                cand["provenance"].append(
                    {"source_type": "EVIDENCE", "source_id": eid, "confidence": None})

            candidates.append(cand)
            if codes:
                rejected.append({
                    "product_id": pid,
                    "candidate_id": cand["candidate_id"],
                    "reason_codes": codes,
                    "reason": "; ".join(rules["reject_reason_codes"].get(c, c) for c in codes),
                })

    rejected = rejected_unknown + rejected
    admissible = [c["candidate_id"] for c in candidates if c["admissible"]]

    if not candidates:
        status = rules["status_when_no_products_matched"]
    elif requested and rejected_unknown and not admissible:
        status = rules["status_when_unknown_product_requested"]
    else:
        status = "COMPLETE"

    unknowns, needed = [], []
    for c in candidates:
        if "ELIGIBILITY_UNKNOWN" in c["reject_reason_codes"]:
            unknowns.append({"type": "eligibility_unverifiable",
                             "candidate_id": c["candidate_id"],
                             "detail": "; ".join(c["eligibility"]["reasons"])})
    seen = set()
    for r in rejected:
        for code in r["reason_codes"]:
            if code in rules["next_information_needed_by_reason"] and code not in seen:
                seen.add(code)
                needed.append({"reason_code": code,
                               "needed": rules["next_information_needed_by_reason"][code]})

    # NO_CANDIDATES must still explain itself: why nothing matched, and what is needed
    # next (spec section 18). Silence here is what tempts a caller to force-fit the
    # closest product instead of admitting the catalog has no answer.
    if not candidates:
        g = rules.get("no_candidates_guidance") or {}
        unknowns.append({"type": "no_candidate",
                         "detail": g.get("detail", "no catalog product covers this strategy")})
        needed.append({"reason_code": g.get("reason_code", "NO_PRODUCT_COVERS_DIRECTION"),
                       "needed": g.get("needed", "")})

    return {
        "skill": "product-candidate-provider",
        "version": "0.1",
        "status": status,
        "candidates": candidates,
        "admissible_candidate_ids": admissible,
        "rejected": rejected,
        "unknowns": unknowns,
        "next_information_needed": needed,
        "catalog": {
            "catalog_id": catalog.get("catalog_id"),
            "catalog_version": catalog.get("catalog_version"),
            "is_demo": bool(catalog.get("is_demo", False)),
            "product_count": len(catalog.get("products", []) or []),
        },
        "provenance": [
            {"source_type": "PRODUCT_CATALOG",
             "source_id": catalog.get("catalog_id", "unknown"), "confidence": None},
            {"source_type": "SOLUTION_PLAN",
             "source_id": ",".join(s.get("solution_id", "?") for s in _solutions(solution_plan)),
             "confidence": None},
        ],
    }


def run(input_dict, rules=None, catalog=None):
    """Returns (output, ok, errors). ok=False only on contract/input failure."""
    rules = rules or load_rules()
    if not input_dict or not isinstance(input_dict, dict):
        return ({"skill": "product-candidate-provider", "version": "0.1",
                 "status": rules["status_when_input_invalid"],
                 "candidates": [], "admissible_candidate_ids": [], "rejected": [],
                 "unknowns": [{"type": "missing_information", "detail": "empty input"}],
                 "next_information_needed": [], "catalog": {}, "provenance": []},
                False, ["EMPTY_INPUT"])
    if not extract_payload(input_dict.get("solution_plan")):
        out = dict(build_candidates(input_dict, rules, catalog))
        out["status"] = rules["status_when_input_invalid"]
        return (out, False, ["MISSING_SOLUTION_PLAN"])
    return (build_candidates(input_dict, rules, catalog), True, [])
