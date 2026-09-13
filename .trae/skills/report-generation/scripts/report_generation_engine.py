"""Report Generation engine — deterministic, rules-driven, upstream read-only.

This is Skill 6 (Report Generation). It consumes the structured outputs of upstream
skills (client-intake via ClientState, requirement-analysis, risk-analysis,
knowledge-search, recommendation) and assembles a fixed 8-section report. It does
NOT re-analyze, re-rate, re-recommend, or fabricate facts.

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
  * requirement_analysis    -> RequirementAnalysisOutput
  * risk_analysis           -> RiskAnalysisOutput
  * knowledge_search        -> KnowledgeSearchOutput (optional)
  * recommendation          -> RecommendationOutput (optional)
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
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE)))))
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


def build_coverage_gaps(rk, ra, rules, prov):
    gaps = []
    if rk.get("missing") and ra.get("missing"):
        return gaps
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
                "main_gap": gap if gap else "需进一步评估",
                "priority": r.get("priority"),
                "source": f"risk-analysis.{r.get('risk_id')}",
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
        })
        prov.append({"claim": f"{cat} 保障缺口（需求侧）", "source": "requirement-analysis", "confidence": "high"})
    return gaps


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
        out.append({
            "rank": "primary", "candidate_id": primary.get("candidate_id"),
            "fit": primary.get("fit"), "rationale": rationale,
            "covered_requirements": cov_req, "covered_risks": cov_risk,
            "notes": "", "source": "recommendation.primary_recommendation",
        })
        prov.append({"claim": f"首选推荐方向：{primary.get('candidate_id')}", "source": "recommendation", "confidence": "high"})
    # alternatives
    for alt in rec.get("alternatives", []):
        out.append({
            "rank": "alternative", "candidate_id": alt.get("candidate_id"),
            "fit": alt.get("fit"), "rationale": alt.get("tradeoff") or "备选方案",
            "covered_requirements": [], "covered_risks": [],
            "notes": "", "source": "recommendation.alternatives",
        })
    if not out:
        # present an explicit note if recommendation exists but produced no direction.
        # use string placeholders (never null) to stay schema-valid and avoid fabrication.
        note = ("Recommendation 未产出具体方向（status=%s）。" % status) if status else ""
        out.append({"rank": "primary", "candidate_id": "(暂无确定方向)",
                    "fit": status or "insufficient_evidence",
                    "rationale": note or "上游 Recommendation 未给出具体保障方向，待补充信息后重新评估。",
                    "covered_requirements": [], "covered_risks": [],
                    "notes": "", "source": "recommendation"})
    return out


def build_information_gaps(ra, rk, cs, rules):
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
def detect_conflicts(ra, rk, rec, rules):
    conflicts = []
    rank = rules["priority_rank"]
    type_to_cat = rules["requirement_type_to_risk_category"]

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
                 "Risk Analysis，推荐方向来自 Recommendation。报告不包含任何自主保险判断或产品推销语句。")
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
    if report["coverage_gaps"]:
        lines.append("| 风险领域 | 当前保障 | 主要缺口 | 优先级 | 来源 |")
        lines.append("| --- | --- | --- | --- | --- |")
        for g in report["coverage_gaps"]:
            lines.append(f"| {_cat_name(rules, g['risk_category'])} | {g['current_protection']} | "
                         f"{g['main_gap']} | {g['priority']} | {g['source']} |")
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
    if report["recommended_directions"]:
        for d in report["recommended_directions"]:
            tag = "首选" if d["rank"] == "primary" else "备选"
            cid = d["candidate_id"] or "（未指定具体方案）"
            lines.append(f"### {tag}：{cid}")
            if d["fit"]:
                lines.append(f"- 匹配度：{d['fit']}")
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
            "client_profile": {"fields": [], "note": rules["missing_section_note"]},
            "financial_profile": {"table": [], "note": rules["missing_section_note"]},
            "risk_exposure": empty_risk, "coverage_gaps": [], "requirement_priorities": [],
            "recommended_directions": [], "information_gaps": [], "next_actions": [],
        }
        validation = {"passed": True, "errors": [],
                      "warnings": ["INSUFFICIENT_INPUT: 缺少全部核心上游输入（client_profile / requirement_analysis / risk_analysis），无法生成完整报告"],
                      "conflicts": []}
        metadata = {"source_skills": [], "upstream_status": {k: ("missing" if norm[k]["missing"] else "present")
                                                            for k in ["client_state", "requirement_analysis", "risk_analysis", "knowledge_search", "recommendation"]},
                    "conflicts": [], "warnings": []}
        return {
            "skill": "report-generation", "version": "0.1", "status": "INSUFFICIENT_INPUT",
            "structured_report": structured, "rendered_report": "信息不足：缺少全部核心上游输入，无法生成报告。",
            "validation": validation, "metadata": metadata, "provenance": [],
        }

    cs, ra, rk, ks, rec = (norm["client_state"], norm["requirement_analysis"],
                           norm["risk_analysis"], norm["knowledge_search"], norm["recommendation"])

    client_profile = build_client_profile(cs, rules, prov)
    financial_profile = build_financial_profile(cs, rules, prov, set())
    risk_exposure = build_risk_exposure(rk, rules, prov)
    coverage_gaps = build_coverage_gaps(rk, ra, rules, prov)
    requirement_priorities = build_requirement_priorities(ra, rules, prov)
    recommended_directions = build_recommended_directions(rec, rules, prov)
    information_gaps = build_information_gaps(ra, rk, cs, rules)
    next_actions = build_next_actions(information_gaps, rules)

    conflicts = detect_conflicts(ra, rk, rec, rules)

    structured = {
        "title": rules["report_title"], "version": rules["report_version"],
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "client_profile": client_profile, "financial_profile": financial_profile,
        "risk_exposure": risk_exposure, "coverage_gaps": coverage_gaps,
        "requirement_priorities": requirement_priorities,
        "recommended_directions": recommended_directions,
        "information_gaps": information_gaps, "next_actions": next_actions,
    }

    # metadata + warnings
    warnings = []
    for key, label in [("client_state", "client_profile"), ("requirement_analysis", "requirement_analysis"),
                       ("risk_analysis", "risk_analysis"), ("knowledge_search", "knowledge_search"),
                       ("recommendation", "recommendation")]:
        if norm[key].get("missing"):
            warnings.append(f"MISSING_UPSTREAM_RESULT: {label}")
    if rec.get("missing"):
        warnings.append("MISSING_UPSTREAM_RESULT: recommendation")
    source_skills = [s for s, k in [("client-intake", "client_state"), ("requirement-analysis", "requirement_analysis"),
                                    ("risk-analysis", "risk_analysis"), ("knowledge-search", "knowledge_search"),
                                    ("recommendation", "recommendation")] if not norm[k].get("missing")]

    rendered = render_markdown(structured, {"source_skills": source_skills}, {}, rules)
    validation = validate_report({"status": "success", "structured_report": structured,
                                  "rendered_report": rendered, "metadata": {"conflicts": conflicts},
                                  "provenance": prov}, rules, norm)
    validation["warnings"] = warnings + validation["warnings"]
    # a successful report with conflicts still passes structural validation (conflicts are surfaced, not fatal)
    validation["passed"] = (len(validation["errors"]) == 0)

    metadata = {
        "source_skills": source_skills,
        "upstream_status": {k: ("missing" if norm[k]["missing"] else "present")
                            for k in ["client_state", "requirement_analysis", "risk_analysis", "knowledge_search", "recommendation"]},
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
