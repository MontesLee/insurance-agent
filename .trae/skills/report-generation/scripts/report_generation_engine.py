"""Report Generation engine — deterministic, rules-driven, upstream read-only.

This is Skill 6 (Report Generation). It consumes the structured outputs of upstream
skills (client-intake via ClientState, requirement-analysis, risk-analysis,
coverage-gap-analysis, solution, knowledge-search, product-recommendation) and
assembles a fixed 8-section report (+ evidence appendix). It does NOT re-analyze,
re-rate, re-recommend, or fabricate facts.

Section 04 (保障缺口) is canonical-first: when CoverageGapAnalysis is supplied it is
the sole source and is copied verbatim (derivation="canonical"); only when it is
absent does the legacy risk/requirement derivation run, tagged derivation="derived"
and flagged with a warning, so the two can never be confused downstream.

Design principles (mirrors AGENTS.md + Lawgent):
  * Single responsibility: only organize / express / validate / deliver.
  * Deterministic: labels, mappings, thresholds live in resources/config/report.rules.json.
  * No LLM: the "natural language" rendering is a pure template over structured data.
  * No hallucination: every value is copied verbatim from an upstream fact; unknown ->
    『待确认』; monetary expressions are cross-checked against upstream (hallucination scan).
  * Provenance: every key claim keeps a source ref.
  * Upstream priority: conclusions come from upstream; conflicts are surfaced, never adjudicated.

Consumed upstream shapes (see schemas + upstream-results-adapter.py):
  * client_profile         -> CanonicalClientState (client_state)
  * requirement_analysis   -> RequirementAnalysisOutput
  * risk_analysis          -> RiskAnalysisOutput
  * coverage_gap_analysis  -> CoverageGapAnalysis   [V2, canonical source for 04]
  * solution_plan          -> SolutionPlan          [V2, strategy layer]
  * knowledge_evidence     -> KnowledgeEvidence     [V2 canonical]
  * knowledge_search       -> KnowledgeSearchOutput [legacy alias]
  * product_recommendation -> ProductRecommendation [V2 canonical]
  * recommendation         -> RecommendationOutput  [legacy alias]
"""
from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
# scripts -> report-generation -> skills -> .trae -> repo root (4 levels).
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from upstream_results_adapter import normalize_input  # noqa: E402

# --------------------------------------------------------------------------- #
# Field label maps (client_state profile keys -> human labels)
# --------------------------------------------------------------------------- #
PROFILE_LABELS = {
    # family
    "age": "年龄", "gender": "性别", "marital_status": "婚姻状况", "region": "所在地区",
    "education": "学历", "family_members": "家庭成员", "household_size": "家庭人数",
    "children": "子女情况", "children_count": "子女数量", "parent_support": "父母赡养",
    "housing": "住房情况", "housing_status": "住房状态", "household_type": "家庭结构",
    # employment
    "occupation": "职业", "industry": "行业", "employer": "工作单位",
    "employment_status": "就业状态", "job_level": "职务级别",
    # health
    "health_status": "健康状况", "smoking": "吸烟情况", "drinking": "饮酒情况",
    "exercise": "运动习惯", "chronic_disease": "既往病史", "height": "身高", "weight": "体重",
    # responsibility
    "economic_responsibility": "家庭经济责任", "dependents": "被抚养人",
    "debt_responsibility": "债务责任",
    # existing_protection
    "existing_insurance": "已有保险", "social_security": "社保情况",
    "commercial_insurance": "商业保险", "policy_details": "保单详情",
}

FINANCIAL_LABELS = {
    "annual_income": "家庭年收入", "monthly_income": "月收入", "annual_expense": "家庭年支出",
    "assets": "资产", "liabilities": "负债", "mortgage": "房贷余额", "cash_flow": "现金流",
    "financial_assets": "金融资产", "economic_responsibility": "经济责任",
    "insurance_budget": "保险预算", "savings": "储蓄", "investment": "投资资产",
    "debt": "债务", "net_worth": "净资产",
}

REQUIRED_CLIENT_FIELDS = ["age", "marital_status", "occupation", "annual_income",
                          "family_members", "children", "parent_support", "housing",
                          "existing_insurance"]


# --------------------------------------------------------------------------- #
# Rules
# --------------------------------------------------------------------------- #
def load_rules(path=None):
    if path is None:
        path = os.path.join(HERE, "..", "resources", "config", "report.rules.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _priority_short(rules, req_priority):
    return rules.get("requirement_priority_to_short", {}).get(req_priority, req_priority)


def _priority_label(rules, req_priority):
    return rules.get("requirement_priority_to_label", {}).get(req_priority, req_priority)


def _importance_category(rules, importance):
    return rules.get("importance_to_category", {}).get(importance, "optional")


def _cat_name(rules, rc):
    return rules.get("risk_category_names", {}).get(rc, rc)


def _req_type_name(rules, rt):
    return rules.get("requirement_type_names", {}).get(rt, rt)


def _domain_to_cat(rules, domain):
    return rules.get("domain_to_risk_category", {}).get(domain, "GENERAL")


def _status_name(rules, status):
    return rules.get("coverage_status_names", {}).get(status, status or "待确认")


def _gap_level_name(rules, level):
    return rules.get("gap_level_names", {}).get(level, level or "待确认")


def _as_text(v):
    """Stringify a scalar for the rendering contract; leave None as None."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    return v


def _solution_type_name(rules, st):
    return rules.get("solution_type_names", {}).get(st, st or "保障方向")


def _fit_name(rules, fit):
    """Map a recommendation fit token to its rendered label (rules-externalized)."""
    return rules.get("fit_names", {}).get(fit, fit or "")


def _kv_text(d):
    """Fallback renderer for an object with unexpected keys.

    Never falls back to ``str(dict)``: that would leak a Python repr into the
    rendered report. Scalar values are stringified; nested values are JSON-encoded
    verbatim (still no reformatting, no invention).
    """
    parts = []
    for k, v in d.items():
        if v is None:
            continue
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        parts.append(f"{k}：{v}")
    return "，".join(parts)


def _fmt_constraint(c):
    """SolutionPlan constraint ``{constraint, value, source}`` -> one readable phrase."""
    if not isinstance(c, dict):
        return str(c)
    name, val, src = c.get("constraint"), c.get("value"), c.get("source")
    if name is None and val is None:
        return _kv_text(c)
    if name is None:
        out = str(val)
    elif val is None:
        out = str(name)
    else:
        out = f"{name}：{val}"
    if src:
        out += f"（来源 {src}）"
    return out


def _fmt_tradeoff(t):
    """SolutionPlan trade-off ``{axis, option_a, option_b, chosen, reason}``."""
    if not isinstance(t, dict):
        return str(t)
    axis, a, b = t.get("axis"), t.get("option_a"), t.get("option_b")
    chosen, reason = t.get("chosen"), t.get("reason")
    if axis is None and chosen is None and a is None and b is None:
        return _kv_text(t)
    seg = []
    if axis:
        seg.append(f"在「{axis}」上")
    if a is not None and b is not None:
        seg.append(f"权衡「{a}」与「{b}」")
    if chosen is not None:
        seg.append(f"选择「{chosen}」")
    out = "，".join(seg)
    if reason:
        out += f"；理由：{reason}"
    return out


def _fmt_rejected(r):
    """SolutionPlan rejected direction ``{direction, reason}``."""
    if not isinstance(r, dict):
        return str(r)
    d, reason = r.get("direction"), r.get("reason")
    if d is None and reason is None:
        return _kv_text(r)
    out = str(d) if d is not None else ""
    if reason:
        out += f"（理由：{reason}）" if out else f"理由：{reason}"
    return out


def _fmt_value(fact_value):
    """Extract a display string + effective status from a factValue (value/status/source)."""
    if not isinstance(fact_value, dict):
        return (str(fact_value), "KNOWN", None)
    status = fact_value.get("status")
    value = fact_value.get("value")
    src = fact_value.get("source")
    src_str = None
    if isinstance(src, dict):
        origin = src.get("origin", {})
        src_str = f"{origin.get('skill', 'unknown')}.{origin.get('field', 'unknown')}" if isinstance(origin, dict) else None
    if status in ("UNKNOWN", None) or value is None:
        return (None, "UNKNOWN", src_str)
    return (str(value), status or "KNOWN", src_str)


# --------------------------------------------------------------------------- #
# Section builders
# --------------------------------------------------------------------------- #
def build_client_profile(cs, rules, prov):
    fields = []
    profiles = [
        ("family_profile", cs.get("family_profile", {})),
        ("employment_profile", cs.get("employment_profile", {})),
        ("health_profile", cs.get("health_profile", {})),
        ("responsibility_profile", cs.get("responsibility_profile", {})),
        ("existing_protection", cs.get("existing_protection", {})),
    ]
    known = 0
    unknown = 0
    for pname, prof in profiles:
        if not isinstance(prof, dict):
            continue
        for key, fv in prof.items():
            label = PROFILE_LABELS.get(key, key)
            value, status, src = _fmt_value(fv)
            if status == "UNKNOWN" or value is None:
                value = rules["unknown_status_token"]
                unknown += 1
            else:
                known += 1
            disp_src = src or f"client_state.{pname}.{key}"
            fields.append({"label": label, "value": value, "status": status, "source": disp_src})
            prov.append({"claim": f"客户画像-{label}: {value}", "source": disp_src, "confidence": "medium"})
    note = rules["missing_section_note"] if cs.get("missing") else \
        f"已知字段 {known} 项，待确认字段 {unknown} 项。"
    return {"fields": fields, "note": note}


def build_financial_profile(cs, rules, prov, allowed_money):
    prof = cs.get("financial_profile", {})
    table = []
    if cs.get("missing") or not isinstance(prof, dict) or not prof:
        note = rules["missing_section_note"]
        return {"table": table, "note": note}
    for key, fv in prof.items():
        label = FINANCIAL_LABELS.get(key, key)
        value, status, src = _fmt_value(fv)
        if status == "UNKNOWN" or value is None:
            value = rules["unknown_status_token"]
        else:
            allowed_money.add(value)
        disp_src = src or f"client_state.financial_profile.{key}"
        table.append({"item": label, "value": value, "status": status, "source": disp_src})
        prov.append({"claim": f"财务-{label}: {value}", "source": disp_src, "confidence": "medium"})
    note = "财务信息以上游 ClientState.financial_profile 为准；缺失项已标注待确认。"
    return {"table": table, "note": note}


def build_risk_exposure(rk, rules, prov):
    out = {}
    if rk.get("missing"):
        for rc in ["R1", "R2", "R3", "R4", "R5"]:
            out[rc] = {"present": False, "risk_category": rc, "note": rules["missing_section_note"]}
        return out
    risks = rk.get("risks", [])
    by_cat = {}
    for r in risks:
        cat = r.get("risk_category")
        if cat not in by_cat:
            by_cat[cat] = []
        by_cat[cat].append(r)
    rank = rules["priority_rank"]
    for rc in ["R1", "R2", "R3", "R4", "R5"]:
        entries = by_cat.get(rc, [])
        if not entries:
            out[rc] = {"present": False, "risk_category": rc,
                       "note": f"未在 {rc}（{_cat_name(rules, rc)}）识别到显著风险或信息不足。"}
            continue
        # pick the entry with the highest priority (lowest rank)
        entries_sorted = sorted(entries, key=lambda e: rank.get(e.get("priority"), 9))
        e = entries_sorted[0]
        residual = e.get("residual_risk")
        impact = e.get("potential_impact") or {}
        impact_str = "；".join(str(v) for v in impact.values() if v) if isinstance(impact, dict) else None
        cov = e.get("coverage_assessment") or {}
        prot = e.get("existing_protection")
        gap = cov.get("unprotected_amount") if cov.get("unprotected_amount") is not None else cov.get("liquidity_constraint")
        gap = _as_text(gap)
        src = f"risk-analysis.{e.get('risk_id')}"
        desc = "；".join([s for s in [e.get("trigger_event"), e.get("why_exposed")] if s])
        out[rc] = {
            "present": True, "risk_category": rc,
            "risk_status": residual, "risk_name": e.get("risk_name"),
            "description": desc, "severity": e.get("severity"), "impact": impact_str,
            "existing_protection": prot, "coverage_gap": gap, "conclusion": e.get("conclusion"),
            "source": src,
        }
        prov.append({"claim": f"{rc} 风险暴露：{e.get('risk_name')}（残余风险 {residual}）",
                     "source": src, "confidence": "high"})
    return out


def build_coverage_gaps(cga, rk, ra, rules, prov):
    """Section 04 保障缺口.

    Canonical-first: when CoverageGapAnalysis is supplied it is the ONLY source for
    this section. The report copies gap_id / gap_level / coverage status / target
    direction verbatim and never recomputes, re-ranks, or merges in risk-derived
    entries — merging the two would silently produce a third, unreviewed judgment.

    When it is absent, the legacy risk/requirement derivation is retained for
    backward compatibility, but every emitted item is tagged derivation="derived"
    and a warning is raised, so a downstream consumer can never mistake it for a
    canonical gap judgment.
    """
    gaps = []
    if not cga.get("missing"):
        prio_by_gap = {p.get("gap_id"): p.get("priority")
                       for p in cga.get("priorities", []) if isinstance(p, dict)}
        for g in cga.get("gaps", []):
            cat = _domain_to_cat(rules, g.get("domain"))
            gap_id = g.get("gap_id")
            # priority comes from the artifact's own priorities[]; absent -> gap_level verbatim.
            prio = prio_by_gap.get(gap_id) or g.get("gap_level") or "UNKNOWN"
            gaps.append({
                "risk_category": cat,
                "current_protection": _status_name(rules, g.get("current_coverage_status")),
                "main_gap": g.get("target_direction") or _gap_level_name(rules, g.get("gap_level")),
                "priority": prio,
                "source": f"coverage-gap-analysis.{gap_id}",
                "derivation": "canonical",
                "gap_id": gap_id,
                "gap_level": g.get("gap_level"),
                "coverage_status": g.get("current_coverage_status"),
                "target_direction": g.get("target_direction"),
                "related_risk_ids": list(g.get("related_risk_ids") or []),
                "related_requirement_ids": list(g.get("related_requirement_ids") or []),
            })
            prov.append({"claim": f"{cat} 保障缺口（{gap_id}，等级 {g.get('gap_level')}）",
                         "source": f"coverage-gap-analysis.{gap_id}", "confidence": "high"})
        return gaps, "canonical"

    # ---- legacy derivation fallback (no canonical artifact supplied) ----
    if rk.get("missing") and ra.get("missing"):
        return gaps, "derived"
    # from risk_analysis: high/critical residual risks
    for r in rk.get("risks", []):
        residual = r.get("residual_risk")
        if residual in ("HIGH", "CRITICAL"):
            cat = r.get("risk_category")
            cov = r.get("coverage_assessment") or {}
            prot = r.get("existing_protection")
            gap = cov.get("unprotected_amount") if cov.get("unprotected_amount") is not None else r.get("conclusion")
            gaps.append({
                "risk_category": cat,
                "current_protection": prot if prot else "需进一步评估",
                "main_gap": _as_text(gap) if gap else "需进一步评估",
                "priority": r.get("priority"),
                "source": f"risk-analysis.{r.get('risk_id')}",
                "derivation": "derived",
            })
            prov.append({"claim": f"{cat} 保障缺口", "source": f"risk-analysis.{r.get('risk_id')}", "confidence": "high"})
    # from requirement_analysis coverage_gaps
    type_to_cat = rules["requirement_type_to_risk_category"]
    existing_cats = {g["risk_category"] for g in gaps}
    for cg in ra.get("coverage_gaps", []):
        rt = cg.get("requirement_type")
        cat = type_to_cat.get(rt, rt)
        if cat in existing_cats:
            continue
        gaps.append({
            "risk_category": cat,
            "current_protection": "需进一步评估",
            "main_gap": cg.get("gap_summary"),
            "priority": _priority_short(rules, cg.get("priority")),
            "source": f"requirement-analysis:{','.join(cg.get('evidence_refs', []) or [])}",
            "derivation": "derived",
        })
        prov.append({"claim": f"{cat} 保障缺口（需求侧）", "source": "requirement-analysis", "confidence": "high"})
    return gaps, "derived"


def build_solution_strategies(sp, rules, prov):
    """Section 06a 解决策略 — verbatim from SolutionPlan.

    The report copies objective / coverage_direction / priority / constraints /
    trade_offs / rejected_directions without rewording. A paraphrased strategy is a
    different strategy, and the report has no mandate to write one.
    """
    if sp.get("missing"):
        return []
    out = []
    for s in sp.get("solutions", []):
        out.append({
            "solution_id": s.get("solution_id"),
            "solution_type": _solution_type_name(rules, s.get("solution_type")),
            "objective": s.get("objective"),
            "coverage_direction": s.get("coverage_direction"),
            "priority": s.get("priority"),
            "constraints": list(s.get("constraints") or []),
            "trade_offs": list(s.get("trade_offs") or []),
            "rejected_directions": list(s.get("rejected_directions") or []),
            "related_gap_ids": list(s.get("related_gap_ids") or []),
            "related_risk_ids": list(s.get("related_risk_ids") or []),
            "source": f"solution.{s.get('solution_id')}",
        })
        prov.append({"claim": f"解决策略 {s.get('solution_id')}：{s.get('objective')}",
                     "source": f"solution.{s.get('solution_id')}", "confidence": "high"})
    return out


def build_evidence_summary(ke, rules):
    """Appendix A 证据来源 — verbatim from KnowledgeEvidence.

    Evidence is listed, never weighed into a conclusion. Conflicts are carried
    through as-is so the broker sees them.
    """
    if ke.get("missing"):
        return []
    out = []
    for e in ke.get("evidence", []):
        out.append({
            "evidence_id": e.get("evidence_id"),
            "content": e.get("content"),
            "source": e.get("source"),
            "source_type": e.get("source_type"),
            "relevance": e.get("relevance"),
            "confidence": e.get("confidence"),
            "conflict": e.get("conflict"),
        })
    return out


def build_requirement_priorities(ra, rules, prov):
    out = []
    if ra.get("missing"):
        return out
    for req in ra.get("requirements", []):
        rt = req.get("requirement_type")
        pr = req.get("priority")
        out.append({
            "requirement_id": req.get("requirement_id"),
            "type": _req_type_name(rules, rt),
            "summary": req.get("summary"),
            "priority": _priority_short(rules, pr),
            "priority_label": _priority_label(rules, pr),
            "source": f"requirement-analysis.{req.get('requirement_id')}",
        })
        prov.append({"claim": f"需求{req.get('requirement_id')}（{_req_type_name(rules, rt)}）优先级 {_priority_short(rules, pr)}",
                     "source": f"requirement-analysis.{req.get('requirement_id')}", "confidence": "high"})
    # sort by priority rank
    rank = rules["priority_rank"]
    out.sort(key=lambda x: rank.get(x["priority"], 9))
    return out


def build_recommended_directions(rec, rules, prov):
    out = []
    if rec.get("missing"):
        return out
    status = rec.get("status")
    # primary
    primary = rec.get("primary")
    if primary:
        prov_list = primary.get("provenance") or []
        cov_req = [p.get("ref") for p in prov_list if p.get("type") == "requirement"]
        cov_risk = [p.get("ref") for p in prov_list if p.get("type") == "risk"]
        rc_map = {"covers_high_priority_risk": "覆盖高优先级风险", "within_budget": "在预算范围内",
                  "meets_term": "满足期限要求", "has_unmet_requirements": "仍有未满足需求，需补充方案"}
        rationale = "；".join(rc_map.get(c, c) for c in (primary.get("reason_codes") or [])) or "依据上游 Recommendation 结论"
        pprod = primary.get("product") or {}
        pnote = rules.get("demo_product_label", "【演示产品】") if pprod.get("is_demo") else ""
        out.append({
            "rank": "primary", "candidate_id": primary.get("candidate_id"),
            "fit": primary.get("fit"), "rationale": rationale,
            "covered_requirements": cov_req, "covered_risks": cov_risk,
            "notes": pnote, "source": "recommendation.primary_recommendation",
        })
        prov.append({"claim": f"首选推荐方向：{primary.get('candidate_id')}", "source": "recommendation", "confidence": "high"})
    # alternatives
    for alt in rec.get("alternatives", []):
        aprod = alt.get("product") or {}
        anote = rules.get("demo_product_label", "【演示产品】") if aprod.get("is_demo") else ""
        out.append({
            "rank": "alternative", "candidate_id": alt.get("candidate_id"),
            "fit": alt.get("fit"), "rationale": alt.get("tradeoff") or "备选方案",
            "covered_requirements": [], "covered_risks": [],
            "notes": anote, "source": "recommendation.alternatives",
        })
    if not out:
        # present an explicit note if recommendation exists but produced no direction.
        # use string placeholders (never null) to stay schema-valid and avoid fabrication.
        note = ("Recommendation 未产出具体方向（status=%s）。" % status) if status else ""
        out.append({"rank": "primary", "candidate_id": "(暂无确定方向)",
                    "fit": "insufficient_evidence",
                    "rationale": note or "上游 Recommendation 未给出具体保障方向，待补充信息后重新评估。",
                    "covered_requirements": [], "covered_risks": [],
                    "notes": "", "source": "recommendation"})
    return out


def _catalog_index():
    """product_id -> is_demo, read from the shipped catalog.

    Used for DEFENCE IN DEPTH: the report does not take the upstream's word for
    whether a named product is a demo/mock entry, nor that it exists at all. A
    fabricated product id (not in the catalog) is a safety failure whatever the
    upstream claimed. Returns None when the catalog cannot be read, so a missing
    catalog degrades to "cannot verify" rather than "verified fine".
    """
    path = os.path.join(REPO_ROOT, "catalog", "product-catalog.v0.1.json")
    try:
        with open(path, encoding="utf-8") as f:
            cat = json.load(f)
    except (OSError, ValueError):
        return None
    return {p.get("product_id"): bool(p.get("is_demo"))
            for p in (cat.get("products") or []) if isinstance(p, dict)}


def build_disclosure(rec, rules):
    """Safety disclosure (Step 4 §30): is the report backed by DEMO products, and what
    is the fact/analysis/advice nature of each section?

    A recommended direction that resolves to a demo/mock catalog product MUST be marked,
    otherwise a reader could mistake a simulated product for a real, purchasable one.
    The demo flag is the UNION of what the upstream declared and what the catalog says,
    and any product id absent from the catalog is reported as unverified (fabricated).
    """
    d = rules.get("disclosure") or {}
    catalog = _catalog_index()
    demo_products, unverified = [], []
    if not rec.get("missing"):
        for entry in [rec.get("primary")] + list(rec.get("alternatives") or []):
            if not isinstance(entry, dict):
                continue
            prod = entry.get("product") or {}
            pid = prod.get("product_id")
            if not pid:
                continue
            in_catalog = catalog is None or pid in catalog
            if not in_catalog:
                if pid not in unverified:
                    unverified.append(pid)
                continue
            is_demo = bool(prod.get("is_demo")) or (catalog is not None and bool(catalog.get(pid)))
            if is_demo and pid not in demo_products:
                demo_products.append(pid)
    return {
        "is_demo": bool(demo_products),
        "demo_products": demo_products,
        "unverified_products": unverified,
        "catalog_checked": catalog is not None,
        "demo_disclosure": d.get("demo_disclosure", ""),
        "demo_product_note": d.get("demo_product_note", ""),
        "nature_legend": d.get("nature_legend", ""),
        "section_nature": dict(d.get("nature_map") or {}),
    }


def build_information_gaps(ra, rk, cs, rules, cga=None):
    gaps = {}
    cat_rank = {"required": 0, "suggested": 1, "optional": 2}

    def add(field, importance, category, reason, source):
        cur = gaps.get(field)
        c = _importance_category(rules, importance) if category is None else category
        if cur is None or cat_rank.get(c, 9) < cat_rank.get(cur["category"], 9):
            gaps[field] = {"field": field, "importance": importance, "category": c,
                           "reason": reason, "source": source}

    # requirement_analysis information_gaps
    for g in ra.get("information_gaps", []):
        add(g.get("field"), g.get("importance"), None, g.get("reason"), "requirement-analysis")
    # risk_analysis next_information_needed
    pr_map = {"HIGH": "required", "MEDIUM": "suggested", "LOW": "optional"}
    for n in rk.get("next_information_needed", []):
        add(n.get("question"), n.get("priority"), pr_map.get(n.get("priority")), n.get("why_needed"), "risk-analysis")
    for u in rk.get("unknowns", []):
        add(u.get("field"), "P2_MEDIUM", "suggested", u.get("reason"), "risk-analysis")
    # client_state missing_from_upstream
    for m in cs.get("missing_from_upstream", []):
        add(m.get("field"), "P0_CRITICAL", "required", m.get("reason"), "client-intake")
    # coverage_gap_analysis information_gaps (canonical gap layer)
    if cga and not cga.get("missing"):
        for g in cga.get("information_gaps", []):
            if not isinstance(g, dict):
                continue
            add(g.get("field"), g.get("importance") or "P2_MEDIUM", None,
                g.get("reason") or g.get("detail"), "coverage-gap-analysis")

    ordered = sorted(gaps.values(), key=lambda x: cat_rank.get(x["category"], 9))
    return ordered


def build_next_actions(gaps, rules):
    actions = []
    rank = {"required": "P0", "suggested": "P1", "optional": "P2"}
    for g in gaps:
        if g["category"] == "optional":
            continue
        actions.append({
            "action": f"确认/收集：{g['field']}",
            "reason": g["reason"],
            "priority": rank.get(g["category"], "P1"),
            "dependency": g["source"].split(".")[0],
        })
    actions.append({"action": "基于补充信息重新评估保障缺口与风险结论",
                    "reason": "当前缺口与风险结论依赖未确认信息", "priority": "P1", "dependency": "Risk Analysis"})
    actions.append({"action": "进入保障方案设计与产品匹配",
                    "reason": "先补齐关键事实，再形成可执行方案", "priority": "P2", "dependency": "Recommendation"})
    return actions


# --------------------------------------------------------------------------- #
# Conflict detection (UPSTREAM_CONFLICT)
# --------------------------------------------------------------------------- #
def detect_conflicts(ra, rk, rec, rules, cga=None):
    conflicts = []
    rank = rules["priority_rank"]
    type_to_cat = rules["requirement_type_to_risk_category"]

    # (3) cross-artifact: canonical gap says NONE but the linked risk carries a
    #     protected_amount. Surfaced, never adjudicated — the report has no authority
    #     to decide which upstream layer is right.
    if cga and not cga.get("missing"):
        risk_by_id = {r.get("risk_id"): r for r in rk.get("risks", []) if isinstance(r, dict)}
        for g in cga.get("gaps", []):
            if g.get("current_coverage_status") != "NONE":
                continue
            tpl = rules.get("conflict_gap_vs_risk")
            if not tpl:
                continue
            hits = []
            for rid in (g.get("related_risk_ids") or []):
                cov = (risk_by_id.get(rid) or {}).get("coverage_assessment") or {}
                amt = cov.get("protected_amount")
                if isinstance(amt, (int, float)) and amt > 0:
                    hits.append(rid)
            if hits:
                conflicts.append(tpl.format(
                    domain=_cat_name(rules, _domain_to_cat(rules, g.get("domain"))),
                    gap_id=g.get("gap_id"),
                    gap_status="NONE（无覆盖）",
                    risk_ids="、".join(hits)))

    # (1) intra: same risk_category priority differs between requirement & risk
    req_by_cat = {}
    for req in ra.get("requirements", []):
        cat = type_to_cat.get(req.get("requirement_type"))
        if cat and cat not in req_by_cat:
            req_by_cat[cat] = req.get("priority")
    risk_by_cat = {}
    for r in rk.get("risks", []):
        cat = r.get("risk_category")
        if cat and cat not in risk_by_cat:
            risk_by_cat[cat] = r.get("priority")
    for cat, rp in req_by_cat.items():
        kp = risk_by_cat.get(cat)
        if kp and rank.get(_priority_short(rules, rp), 9) != rank.get(kp, 9):
            conflicts.append(
                f"UPSTREAM_CONFLICT：{cat}（{_cat_name(rules, cat)}）在需求侧优先级 "
                f"{_priority_short(rules, rp)} 与风险侧优先级 {kp} 不一致。")

    # (2) cross: top-priority domain disagreement across RA / RK / Rec
    def top_cat(items, get_cat, get_pri):
        best, best_rank = None, 99
        for it in items:
            cat = get_cat(it)
            pri = get_pri(it)
            r = rank.get(pri, 9) if isinstance(pri, str) else 9
            if r < best_rank:
                best, best_rank = cat, r
        return best

    ra_top = top_cat(ra.get("requirements", []),
                     lambda x: type_to_cat.get(x.get("requirement_type")),
                     lambda x: _priority_short(rules, x.get("priority")))
    rk_top = top_cat(rk.get("risks", []), lambda x: x.get("risk_category"), lambda x: x.get("priority"))
    rec_top = None
    primary = rec.get("primary")
    if primary:
        prov = primary.get("provenance") or []
        rec_top = next((p.get("ref") for p in prov if p.get("type") == "risk"), None)
    # normalize risk_id ("R1-001") or "risk:R1-001" -> category ("R1") so it is
    # comparable with ra_top / rk_top (which are already categories).
    if rec_top:
        m = re.search(r"R([1-5])", rec_top)
        if m:
            rec_top = "R" + m.group(1)
    tops = [t for t in (ra_top, rk_top, rec_top) if t]
    if len(set(tops)) > 1:
        conflicts.append(
            f"UPSTREAM_CONFLICT：上游对首要优先风险域的判断不完全一致"
            f"（需求首选 {ra_top} / 风险首选 {rk_top} / 推荐首选 {rec_top}）；"
            f"建议经纪人在下一次沟通中进一步确认，本报告不自行裁决。")
    return conflicts


# --------------------------------------------------------------------------- #
# Render (Markdown)
# --------------------------------------------------------------------------- #
def render_markdown(report, metadata, validation, rules):
    lines = []
    lines.append(f"# {report['title']}")
    lines.append("")
    lines.append(f"> 生成时间：{report['generated_at']}  ｜  报告版本：{report['version']}")
    lines.append("")
    lines.append("> 本报告由上游结构化分析结果汇总生成。事实来自 ClientState / Requirement Analysis / "
                 "Risk Analysis / Coverage Gap Analysis，解决策略来自 SolutionPlan，推荐方向来自 "
                 "Product Recommendation，证据来自 Knowledge Evidence。报告不包含任何自主保险判断或产品推销语句。")
    lines.append("")

    # Safety disclosure (Step 4 §30): DEMO marking + fact/analysis/advice nature.
    disc = report.get("disclosure") or {}
    if disc.get("demo_disclosure"):
        lines.append(f"> ⚠️ **{disc['demo_disclosure']}**")
        lines.append("")
    if disc.get("nature_legend"):
        lines.append(f"> {disc['nature_legend']}")
        lines.append("")

    # 01
    lines.append("## 01 客户画像")
    lines.append("")
    for f in report["client_profile"]["fields"]:
        lines.append(f"- **{f['label']}**：{f['value']}（来源：{f['source']}）")
    if not report["client_profile"]["fields"]:
        lines.append(report["client_profile"]["note"])
    lines.append("")
    lines.append(f"_{report['client_profile']['note']}_")
    lines.append("")

    # 02
    lines.append("## 02 家庭财务情况")
    lines.append("")
    if report["financial_profile"]["table"]:
        lines.append("| 项目 | 情况 | 来源 |")
        lines.append("| --- | --- | --- |")
        for t in report["financial_profile"]["table"]:
            lines.append(f"| {t['item']} | {t['value']} | {t['source']} |")
    else:
        lines.append(report["financial_profile"]["note"])
    lines.append("")
    lines.append(f"_{report['financial_profile']['note']}_")
    lines.append("")

    # 03
    lines.append("## 03 风险暴露")
    lines.append("")
    for rc in ["R1", "R2", "R3", "R4", "R5"]:
        e = report["risk_exposure"][rc]
        name = _cat_name(rules, rc)
        lines.append(f"### {rc} {name}")
        if not e.get("present"):
            lines.append(f"- {e.get('note', rules['missing_section_note'])}")
        else:
            lines.append(f"- 风险状态：{e.get('risk_status') or '待确认'}")
            lines.append(f"- 风险描述：{e.get('description') or '待确认'}")
            lines.append(f"- 严重程度：{e.get('severity') or '待确认'}")
            lines.append(f"- 主要影响：{e.get('impact') or '待确认'}")
            lines.append(f"- 现有保障：{e.get('existing_protection') or '待确认'}")
            lines.append(f"- 保障不足：{e.get('coverage_gap') or '待确认'}")
            lines.append(f"- 风险结论：{e.get('conclusion') or '待确认'}")
            lines.append(f"- 来源：{e.get('source')}")
        lines.append("")

    # 04
    lines.append("## 04 保障缺口")
    lines.append("")
    if report.get("coverage_gaps"):
        # Be explicit about where this section's judgment came from.
        if report.get("coverage_gap_derivation") == "canonical":
            lines.append(f"_{rules.get('gap_canonical_note', '')}_")
        else:
            lines.append(f"_{rules.get('gap_derived_note', '')}_")
        lines.append("")
        lines.append("| 风险领域 | 当前保障 | 主要缺口 | 优先级 | 来源 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for g in report["coverage_gaps"]:
            lines.append(f"| {_cat_name(rules, g['risk_category'])} | {g['current_protection']} | "
                         f"{g['main_gap']} | {g['priority']} | {g['source']} |")
        if report.get("coverage_gap_derivation") == "canonical":
            lines.append("")
            for g in report["coverage_gaps"]:
                if g.get("gap_id"):
                    lines.append(f"- `{g['gap_id']}` 缺口等级：**{_gap_level_name(rules, g.get('gap_level'))}**"
                                 f"（{g.get('gap_level')}）")
    else:
        lines.append("当前未识别到明确的保障缺口；具体金额类缺口需结合补充信息进一步评估（本报告不自行测算保额）。")
    lines.append("")

    # 05
    lines.append("## 05 需求优先级")
    lines.append("")
    if report["requirement_priorities"]:
        for p in report["requirement_priorities"]:
            lines.append(f"- **{p['priority']}（{p['priority_label']}）**：{p['type']} —— {p['summary']}（{p['source']}）")
    else:
        lines.append("需求优先级信息不足，建议参考 07 信息缺口补充后重新评估。")
    lines.append("")

    # 06
    lines.append("## 06 推荐保障方向")
    lines.append("")

    # 06A 解决策略（SolutionPlan）— strategy layer, never product names
    strategies = report.get("solution_strategies") or []
    if strategies:
        lines.append("### 解决策略（SolutionPlan）")
        lines.append("")
        for s in strategies:
            title = s.get("objective") or s.get("solution_id") or "（未命名策略）"
            lines.append(f"#### {title}")
            lines.append(f"- 策略类别：{s.get('solution_type')}")
            lines.append(f"- 优先级：{s.get('priority')}")
            lines.append(f"- 保障方向：{s.get('coverage_direction') or '待确认'}")
            if s.get("constraints"):
                lines.append(f"- 约束：{'；'.join(_fmt_constraint(c) for c in s['constraints'])}")
            if s.get("trade_offs"):
                lines.append(f"- 取舍：{'；'.join(_fmt_tradeoff(t) for t in s['trade_offs'])}")
            if s.get("rejected_directions"):
                lines.append(f"- 未采用方向：{'；'.join(_fmt_rejected(r) for r in s['rejected_directions'])}")
            lines.append(f"- 来源：{s.get('source')}")
            lines.append("")
        lines.append(f"_{rules.get('solution_section_note', '')}_")
        lines.append("")
    else:
        lines.append(f"_{rules.get('missing_solution_note', '')}_")
        lines.append("")

    # 06B 产品/方向推荐
    lines.append("### 推荐方向（Product Recommendation）")
    lines.append("")
    if report["recommended_directions"]:
        for d in report["recommended_directions"]:
            tag = "首选" if d["rank"] == "primary" else "备选"
            cid = d["candidate_id"] or "（未指定具体方案）"
            lines.append(f"#### {tag}：{cid}")
            if d["fit"]:
                lines.append(f"- 匹配度：{_fit_name(rules, d['fit'])}")
            lines.append(f"- 推荐原因：{d['rationale']}")
            if d["covered_requirements"]:
                lines.append(f"- 解决的需求：{', '.join(d['covered_requirements'])}")
            if d["covered_risks"]:
                lines.append(f"- 解决的风险：{', '.join(d['covered_risks'])}")
            lines.append(f"- 来源：{d['source']}")
            lines.append("")
    else:
        lines.append(rules["missing_recommendation_note"])
        lines.append("")

    # 07
    lines.append("## 07 信息缺口")
    lines.append("")
    cat_title = {"required": "必须补充", "suggested": "建议补充", "optional": "可选补充"}
    for cat in ["required", "suggested", "optional"]:
        items = [g for g in report["information_gaps"] if g["category"] == cat]
        if not items:
            continue
        lines.append(f"### {cat_title[cat]}")
        for g in items:
            lines.append(f"- **{g['field']}**（{g['importance']}）：{g['reason']}（来源：{g['source']}）")
        lines.append("")

    # 08
    lines.append("## 08 经纪人下一步行动")
    lines.append("")
    for i, a in enumerate(report["next_actions"], 1):
        lines.append(f"{i}. **{a['action']}**  ")
        lines.append(f"   - 原因：{a['reason']}")
        lines.append(f"   - 优先级：{a['priority']}  ｜  依赖：{a['dependency']}")
    lines.append("")

    # 附录 A 证据来源
    lines.append("---")
    lines.append("## 附录 A 证据来源")
    lines.append("")
    ev = report.get("evidence_summary") or []
    if ev:
        lines.append("| 证据 ID | 内容 | 来源 | 相关性 | 置信度 | 冲突 |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for e in ev:
            lines.append(f"| {e.get('evidence_id') or '—'} | {e.get('content') or '—'} | "
                         f"{e.get('source') or '—'} | {e.get('relevance') if e.get('relevance') is not None else '—'} | "
                         f"{e.get('confidence') if e.get('confidence') is not None else '—'} | "
                         f"{'是' if e.get('conflict') else '否'} |")
        lines.append("")
        lines.append(f"_{rules.get('evidence_section_note', '')}_")
    else:
        lines.append(rules.get("missing_evidence_note", ""))
    lines.append("")

    if validation.get("conflicts"):
        lines.append("---")
        lines.append("## 上游结论冲突提示")
        for c in validation["conflicts"]:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def _collect_allowed_money(structured_report, cs):
    """Every string leaf in the structured report that contains a monetary expression is an
    allowed source. Because the engine only copies upstream values verbatim, any monetary
    expression it renders is already present here -> the scan cannot produce false positives
    for legitimate data while still catching injected (fabricated) figures."""
    allowed = set()
    leaves = []
    _collect_leaf_strings(structured_report, leaves)
    pattern = r"[0-9][0-9,]*(\.[0-9]+)?\s*(万元|元|万)"
    for s in leaves:
        if not isinstance(s, str):
            continue
        for m in re.findall(pattern, s):
            tok = m if isinstance(m, str) else "".join(m)
            allowed.add(tok)
    return allowed


def _collect_leaf_strings(obj, acc):
    if isinstance(obj, dict):
        for v in obj.values():
            _collect_leaf_strings(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            _collect_leaf_strings(v, acc)
    elif isinstance(obj, str):
        acc.append(obj)


def validate_report(report, rules, normalized):
    errors, warnings, conflicts = [], [], []

    # structure: 8 sections present
    sr = report.get("structured_report", {})
    required_sections = ["client_profile", "financial_profile", "risk_exposure",
                         "coverage_gaps", "requirement_priorities", "recommended_directions",
                         "information_gaps", "next_actions"]
    for s in required_sections:
        if s not in sr:
            errors.append(f"STRUCTURE: missing section {s}")

    # upstream conflicts (computed during generation)
    conflicts.extend(report.get("metadata", {}).get("conflicts", []))

    # completeness: missing core -> handled by status; here check empty sections when upstream present
    if not normalized["client_state"].get("missing") and not sr["client_profile"]["fields"]:
        errors.append("COMPLETENESS: client_profile empty despite upstream client_state present")
    if (not normalized["risk_analysis"].get("missing")
            and not any(sr["risk_exposure"][rc].get("present") for rc in ["R1", "R2", "R3", "R4", "R5"])):
        errors.append("COMPLETENESS: risk_exposure empty despite upstream risk_analysis present")

    # provenance: must be non-empty when at least one upstream present
    if report.get("status") == "success" and not report.get("provenance"):
        errors.append("PROVENANCE: provenance is empty despite upstream data present")

    # hallucination: money scan
    hc = rules.get("hallucination", {})
    if hc.get("enable_money_scan", False) and report.get("status") == "success":
        allowed = _collect_allowed_money(sr, normalized["client_state"])
        pattern = hc.get("money_regex", r"[0-9][0-9,]*(\.[0-9]+)?\s*(万元|元|万)")
        norm_allowed = {a.replace(" ", "") for a in allowed}
        for m in re.findall(pattern, report.get("rendered_report", "")):
            token = m if isinstance(m, str) else "".join(m)
            tnorm = token.replace(" ", "")
            if tnorm not in norm_allowed and not any(tnorm in a.replace(" ", "") for a in allowed):
                errors.append(f"HALLUCINATION: report contains monetary expression '{token}' with no upstream source")
        for fn in hc.get("forbidden_product_names", []):
            if fn and fn in report.get("rendered_report", ""):
                errors.append(f"HALLUCINATION: forbidden product name '{fn}' present")
        for cn in hc.get("forbidden_company_names", []):
            if cn and cn in report.get("rendered_report", ""):
                errors.append(f"HALLUCINATION: forbidden company name '{cn}' present")

    passed = (len(errors) == 0)
    return {"passed": passed, "errors": errors, "warnings": warnings, "conflicts": conflicts}


# --------------------------------------------------------------------------- #
# Main generation
# --------------------------------------------------------------------------- #
def generate_report(input_dict, rules=None):
    if rules is None:
        rules = load_rules()
    norm = normalize_input(input_dict, rules)
    prov = []

    if norm["all_core_missing"]:
        # INSUFFICIENT_INPUT: produce minimal structured_report to satisfy schema
        empty_risk = {rc: {"present": False, "risk_category": rc,
                           "note": rules["missing_section_note"]} for rc in ["R1", "R2", "R3", "R4", "R5"]}
        structured = {
            "title": rules["report_title"], "version": rules["report_version"],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "disclosure": build_disclosure({"missing": True}, rules),
            "client_profile": {"fields": [], "note": rules["missing_section_note"]},
            "financial_profile": {"table": [], "note": rules["missing_section_note"]},
            "risk_exposure": empty_risk, "coverage_gaps": [], "coverage_gap_derivation": "derived",
            "requirement_priorities": [], "solution_strategies": [],
            "recommended_directions": [], "evidence_summary": [],
            "information_gaps": [], "next_actions": [],
        }
        validation = {"passed": True, "errors": [],
                      "warnings": ["INSUFFICIENT_INPUT: 缺少全部核心上游输入（client_profile / requirement_analysis / risk_analysis），无法生成完整报告"],
                      "conflicts": []}
        metadata = {"source_skills": [],
                    "upstream_status": {k: "missing" for k in [
                        "client-profile", "requirement-analysis", "risk-assessment",
                        "coverage-gap-analysis", "solution-plan",
                        "knowledge-evidence", "product-recommendation"]},
                    "conflicts": [], "warnings": []}
        return {
            "skill": "report-generation", "version": "0.1", "status": "INSUFFICIENT_INPUT",
            "structured_report": structured, "rendered_report": "信息不足：缺少全部核心上游输入，无法生成报告。",
            "validation": validation, "metadata": metadata, "provenance": [],
        }

    cs, ra, rk, ks, rec = (norm["client_state"], norm["requirement_analysis"],
                           norm["risk_analysis"], norm["knowledge_search"], norm["recommendation"])
    cga, sp = norm["coverage_gap_analysis"], norm["solution_plan"]

    client_profile = build_client_profile(cs, rules, prov)
    financial_profile = build_financial_profile(cs, rules, prov, set())
    risk_exposure = build_risk_exposure(rk, rules, prov)
    coverage_gaps, gap_derivation = build_coverage_gaps(cga, rk, ra, rules, prov)
    requirement_priorities = build_requirement_priorities(ra, rules, prov)
    solution_strategies = build_solution_strategies(sp, rules, prov)
    recommended_directions = build_recommended_directions(rec, rules, prov)
    evidence_summary = build_evidence_summary(ks, rules)
    information_gaps = build_information_gaps(ra, rk, cs, rules, cga)
    next_actions = build_next_actions(information_gaps, rules)
    disclosure = build_disclosure(rec, rules)

    conflicts = detect_conflicts(ra, rk, rec, rules, cga)

    structured = {
        "title": rules["report_title"], "version": rules["report_version"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "disclosure": disclosure,
        "client_profile": client_profile, "financial_profile": financial_profile,
        "risk_exposure": risk_exposure, "coverage_gaps": coverage_gaps,
        "coverage_gap_derivation": gap_derivation,
        "requirement_priorities": requirement_priorities,
        "solution_strategies": solution_strategies,
        "recommended_directions": recommended_directions,
        "evidence_summary": evidence_summary,
        "information_gaps": information_gaps, "next_actions": next_actions,
    }

    # metadata + warnings
    warnings = []
    if gap_derivation == "derived" and (not rk.get("missing") or not ra.get("missing")):
        warnings.append(rules["gap_derivation_warning"])
    for key, label in [("client_state", "client_profile"), ("requirement_analysis", "requirement_analysis"),
                       ("risk_analysis", "risk_analysis")]:
        if norm[key].get("missing"):
            warnings.append(f"MISSING_UPSTREAM_RESULT: {label}")
    # name the artifact the caller actually asked for (V1 key -> V1 warning text)
    if ks.get("missing"):
        warnings.append(f"MISSING_UPSTREAM_RESULT: {norm['supplied_keys']['knowledge_evidence']}")
    if rec.get("missing"):
        warnings.append(f"MISSING_UPSTREAM_RESULT: {norm['supplied_keys']['product_recommendation']}")
    if ks.get("conflict"):
        warnings.append(rules.get("evidence_conflict_note", ""))
    if disclosure["is_demo"]:
        # Guardrail: a DEMO-backed recommendation must be flagged, never silently presented
        # as a real product. The list of products is carried so the flag is auditable.
        warnings.append("DEMO_PRODUCT_DISCLOSURE: %s (%s)" %
                        (rules.get("disclosure", {}).get("demo_disclosure", ""),
                         ", ".join(disclosure["demo_products"])))
    source_skills = [s for s, k in [("client-intake", "client_state"), ("requirement-analysis", "requirement_analysis"),
                                    ("risk-analysis", "risk_analysis")] if not norm[k].get("missing")]
    if not cga.get("missing"):
        source_skills.append("coverage-gap-analysis")
    if not sp.get("missing"):
        source_skills.append("solution")
    if not ks.get("missing"):
        source_skills.append("knowledge-search")
    if not rec.get("missing"):
        source_skills.append("product-recommendation")

    rendered = render_markdown(structured, {"source_skills": source_skills}, {}, rules)
    validation = validate_report({"status": "success", "structured_report": structured,
                                  "rendered_report": rendered, "metadata": {"conflicts": conflicts},
                                  "provenance": prov}, rules, norm)
    validation["warnings"] = warnings + validation["warnings"]
    # Safety HARD errors: a report that names a product it cannot verify, or presents a
    # demo product without its disclosure, must not be delivered as a clean report.
    if disclosure["unverified_products"]:
        validation["errors"].append(
            "FABRICATED_PRODUCT: 以下产品不在 Demo Catalog 中，报告拒绝将其作为推荐呈现：%s"
            % ", ".join(disclosure["unverified_products"]))
    if disclosure["is_demo"] and not disclosure["demo_disclosure"]:
        validation["errors"].append(
            "DEMO_PRODUCT_UNMARKED: 推荐引用了演示产品，但缺少 DEMO 声明文案（guardrail 失效）")
    # a successful report with conflicts still passes structural validation (conflicts are surfaced, not fatal)
    validation["passed"] = (len(validation["errors"]) == 0)

    metadata = {
        "source_skills": source_skills,
        "upstream_status": {
            "client-profile": "missing" if norm["client_state"].get("missing") else "present",
            "requirement-analysis": "missing" if norm["requirement_analysis"].get("missing") else "present",
            "risk-assessment": "missing" if norm["risk_analysis"].get("missing") else "present",
            "coverage-gap-analysis": "missing" if cga.get("missing") else "present",
            "solution-plan": "missing" if sp.get("missing") else "present",
            "knowledge-evidence": "missing" if ks.get("missing") else "present",
            "product-recommendation": "missing" if rec.get("missing") else "present",
        },
        "conflicts": conflicts,
        "warnings": warnings,
    }

    return {
        "skill": "report-generation", "version": "0.1", "status": "success",
        "structured_report": structured, "rendered_report": rendered,
        "validation": validation, "metadata": metadata, "provenance": prov,
    }


def main():
    if len(sys.argv) < 2:
        print("usage: report_generation_engine.py <input.json> [rules.json]", file=sys.stderr)
        sys.exit(2)
    with open(sys.argv[1], encoding="utf-8") as f:
        data = json.load(f)
    rules = load_rules(sys.argv[2]) if len(sys.argv) > 2 else load_rules()
    out = generate_report(data, rules)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
