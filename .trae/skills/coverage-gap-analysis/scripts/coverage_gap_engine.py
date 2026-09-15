"""Coverage-gap-analysis deterministic engine (V2 Phase 2).

Independent business-judgment layer. It answers ONLY:
    "针对已识别的风险与已声明的需求，客户当前保障覆盖到什么程度（缺口在哪）？"

Design boundaries (see CONTRACT.md / docs/architecture/architecture-v2.md §3.1):
- Risk != Coverage Gap: this engine does NOT recompute severity / likelihood /
  residual_risk / priority of a risk. It only *references* risk_id.
- It does NOT recommend products or strategies (that is solution / product-recommendation).
- It does NOT modify upstream artifacts; it only consumes them.

Inputs (each may be a Canonical envelope with a "payload" key, or the raw legacy dict):
    client_profile        -> ClientState (free-form; used for supplementary evidence)
    requirement_analysis  -> RequirementAnalysisOutput
    risk_assessment       -> RiskAnalysisOutput (authoritative risk layer)

Output: the strict CoverageGapAnalysis payload (validates against
contracts/coverage-gap-analysis.schema.json).
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_PATH = os.path.join(HERE, "..", "resources", "config", "coverage-mapping.rules.json")


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or RULES_PATH, encoding="utf-8") as f:
        return json.load(f)


def extract_payload(artifact: Any) -> Any:
    """Accept either a Canonical envelope ({"payload": ...}) or a raw legacy dict."""
    if isinstance(artifact, dict) and isinstance(artifact.get("payload"), dict):
        return artifact["payload"]
    return artifact


def _status_from_coverage(risk: dict, rules: dict) -> tuple[str, str]:
    """Return (coverage_status, evidence_note).

    Primary signal: risk-analysis coverage_assessment (protected/unprotected amounts).
    Fallback: keyword scan of the per-risk existing_protection free text.
    """
    ca = risk.get("coverage_assessment") or {}
    protected = ca.get("protected_amount")
    unprotected = ca.get("unprotected_amount")
    if isinstance(protected, (int, float)) and isinstance(unprotected, (int, float)):
        if protected > 0 and unprotected <= 0:
            return "SUFFICIENT", "coverage_assessment 显示已充分覆盖（未暴露缺口）"
        if protected <= 0 and unprotected > 0:
            return "NONE", "coverage_assessment 显示无任何覆盖"
        if protected > 0 and unprotected > 0:
            return "PARTIAL", "coverage_assessment 显示部分覆盖"
        # both 0 -> cannot judge numerically

    text = (risk.get("existing_protection") or "").lower()
    none_kw = rules["coverage_keywords"]["none"]
    pos_kw = rules["coverage_keywords"]["positive"]
    for kw in none_kw:
        if kw in text:
            return "NONE", f"现有保障描述含否定词「{kw}」"
    for kw in pos_kw:
        if kw in text:
            strong = ["百万医疗", "重疾", "寿险", "意外", "年金", "医疗险", "已配置", "已购", "已有", "保单"]
            if any(s in text for s in strong):
                return "PARTIAL", f"现有保障描述含覆盖词「{kw}」（视为部分覆盖）"
            return "PARTIAL", f"现有保障描述含覆盖词「{kw}」（视为部分覆盖）"
    return "UNKNOWN", "现有保障信息不足，无法判定覆盖程度"


def _risk_priority(risks: list, risk_id: str) -> str:
    for r in risks:
        if r.get("risk_id") == risk_id:
            return r.get("priority", "P3")
    return "P3"


def _describe_status(status: str) -> str:
    return {
        "NONE": "无覆盖",
        "PARTIAL": "部分覆盖",
        "SUFFICIENT": "已充分覆盖",
        "UNKNOWN": "覆盖情况未知",
    }.get(status, status)


def analyze(
    client_profile: Any,
    requirement_analysis: Any,
    risk_assessment: Any,
    rules: Optional[dict] = None,
) -> dict:
    rules = rules or load_rules()
    ra = extract_payload(risk_assessment) or {}
    req = extract_payload(requirement_analysis) or {}
    # client_profile is only consulted for supplementary evidence; not required.
    _cp = extract_payload(client_profile) or {}

    risks = ra.get("risks") or []
    requirements = req.get("requirements") or []
    req_by_domain: dict[str, list] = {}
    for r in requirements:
        d = r.get("requirement_type")
        if d:
            req_by_domain.setdefault(d, []).append(r.get("requirement_id"))

    cat_to_domain = rules["risk_category_to_domain"]
    matrix = rules["gap_level_matrix"]
    rank = rules["gap_level_rank"]
    dom_req = rules["domain_required_protection"]
    dom_labels = rules["domain_labels"]

    overall_conf = ra.get("overall_confidence")
    if not isinstance(overall_conf, (int, float)):
        overall_conf = 0.5

    gaps: list[dict] = []
    gap_prio: dict[str, str] = {}
    information_gaps: list[dict] = []

    for risk in risks:
        risk_id = risk.get("risk_id", "R?")
        cat = risk.get("risk_category")
        domain = cat_to_domain.get(cat, "general")
        status, note = _status_from_coverage(risk, rules)

        if status == "SUFFICIENT":
            # 已充分覆盖 -> 不是缺口，不生成 Gap。
            continue

        gap_level = (
            "UNKNOWN"
            if status == "UNKNOWN"
            else matrix.get(risk.get("priority", "P3"), {}).get(status, "MEDIUM")
        )
        rel_req = req_by_domain.get(domain, [])
        direction = dom_req.get(domain, {}).get("direction", "补充对应保障")
        rationale = dom_req.get(domain, {}).get("rationale", "")

        conf = overall_conf
        ca = risk.get("coverage_assessment") or {}
        if isinstance(ca.get("confidence"), (int, float)):
            conf = min(conf, ca["confidence"])
        if status == "UNKNOWN":
            conf = round(conf * 0.5, 2)
        conf = round(conf, 2)

        ev = risk.get("reasoning_evidence_refs") or []
        if not ev:
            ev = [
                e.get("evidence_id")
                for e in (risk.get("evidence") or [])
                if isinstance(e, dict) and e.get("evidence_id")
            ]
        if not ev:
            ev = [f"from:{risk_id}"]

        gap_id = f"GAP-{risk_id}"
        gaps.append(
            {
                "gap_id": gap_id,
                "domain": domain,
                "subject": risk.get("risk_name", dom_labels.get(domain, domain)),
                "related_requirement_ids": rel_req,
                "related_risk_ids": [risk_id],
                "current_coverage": {
                    "status": status,
                    "evidence_refs": [note] if note else [],
                },
                "target_coverage": {"direction": direction, "rationale": rationale},
                "gap_level": gap_level,
                "confidence": conf,
                "evidence_refs": ev,
            }
        )
        gap_prio[gap_id] = risk.get("priority", "P3")
        if status == "UNKNOWN":
            information_gaps.append(
                {"gap_id": gap_id, "domain": domain, "reason": note}
            )

    # 需求无对应风险 -> 信息缺口（非保障缺口），需补风险评估。
    risk_domains = {cat_to_domain.get(r.get("risk_category")) for r in risks}
    for r in requirements:
        d = r.get("requirement_type")
        if d and d not in risk_domains:
            information_gaps.append(
                {
                    "gap_id": f"REQ-{r.get('requirement_id', '?')}",
                    "domain": d,
                    "reason": "该需求无对应风险分析，需补充风险评估以判定保障缺口",
                }
            )

    ra_status = ra.get("analysis_status")
    if any(g["gap_level"] == "UNKNOWN" for g in gaps):
        status = "NEED_MORE_INFORMATION"
    elif ra_status == "FORMAL":
        status = "COMPLETE"
    elif ra_status == "PRELIMINARY":
        status = "PRELIMINARY"
    else:
        status = "NEED_MORE_INFORMATION"

    prio_order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    ordered = sorted(
        gaps,
        key=lambda g: (-rank.get(g["gap_level"], 0), prio_order.get(gap_prio.get(g["gap_id"], "P3"), 3)),
    )
    priorities = [
        {
            "gap_id": g["gap_id"],
            "priority": gap_prio.get(g["gap_id"], "P3"),
            "reason": f"{dom_labels.get(g['domain'], g['domain'])}保障{_describe_status(g['current_coverage']['status'])}",
        }
        for g in ordered[:5]
    ]

    return {
        "gaps": gaps,
        "priorities": priorities,
        "information_gaps": information_gaps,
        "status": status,
    }
