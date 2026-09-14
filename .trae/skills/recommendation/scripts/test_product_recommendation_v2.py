"""Architecture invariants for Phase 5 (product-recommendation V2).

These assert the structural guarantees that make the P1 fix real, not cosmetic:
  * candidate_solutions is REJECTED as a V2 input (it must be derived),
  * the translator never fabricates product-level facts,
  * an unverifiable constraint is never silently counted as a pass.
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from jsonschema import Draft7Validator  # noqa: E402
import solution_to_candidates as stc  # noqa: E402

LOG = os.path.join(SKILL_DIR, "evals", "cases", "_pr_v2_unit_log.txt")
INPUT_SCHEMA = os.path.join(SKILL_DIR, "schemas", "product-recommendation-input.schema.json")

RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, ""))
    except AssertionError as e:
        RESULTS.append((name, False, str(e)))
    except Exception as e:  # noqa: BLE001
        RESULTS.append((name, False, "EXCEPTION: %r" % e))


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


RULES = stc.load_rules()

SOLUTION_PLAN = {
    "status": "COMPLETE",
    "solution_type": "TERM_LIFE",
    "objective": "建立家庭责任保障",
    "coverage_direction": "以家庭责任与收入替代缺口确定保障额度",
    "priority": "P0",
    "solutions": [
        {"solution_id": "SOL-001", "solution_type": "TERM_LIFE", "objective": "建立家庭责任保障",
         "coverage_direction": "以家庭责任与收入替代缺口确定保障额度", "priority": "P0",
         "related_gap_ids": ["GAP-LIFE-001"], "related_risk_ids": ["R4-001"],
         "evidence_refs": ["EVD-001"]},
        {"solution_id": "SOL-002", "solution_type": "MEDICAL", "objective": "建立大额医疗支出保障",
         "coverage_direction": "以大额医疗支出敞口确定保额", "priority": "P1",
         "related_gap_ids": ["GAP-MED-001"], "related_risk_ids": ["R1-001"],
         "evidence_refs": ["EVD-002"]},
    ],
    "information_gaps": [],
}

RISK = {"risks": [
    {"risk_id": "R4-001", "risk_category": "R4", "residual_risk": "HIGH", "priority": "P0"},
    {"risk_id": "R1-001", "risk_category": "R1", "residual_risk": "HIGH", "priority": "P0"},
]}

GAP = {"status": "COMPLETE", "gaps": [
    {"gap_id": "GAP-LIFE-001", "domain": "life", "gap_level": "CRITICAL"},
    {"gap_id": "GAP-MED-001", "domain": "medical", "gap_level": "HIGH"},
]}

EVIDENCE = {"status": "success", "conflict": False, "evidence": [
    {"evidence_id": "EVD-001", "content": "定期寿险...", "source": "kb://life", "relevance": 0.9, "confidence": 0.8},
    {"evidence_id": "EVD-002", "content": "百万医疗...", "source": "kb://med", "relevance": 0.8, "confidence": 0.8},
]}


def t_input_rejects_candidate_solutions():
    """The P1 guard: V2 input carrying candidate_solutions must fail validation."""
    schema = _load(INPUT_SCHEMA)
    v = Draft7Validator(schema)
    base = {"requirement_analysis": {}, "risk_assessment": {},
            "coverage_gap_analysis": {}, "solution_plan": {}}
    assert not list(v.iter_errors(base)), "baseline V2 input should be valid"
    with_cs = dict(base, candidate_solutions=[{"candidate_id": "X"}])
    errs = list(v.iter_errors(with_cs))
    assert errs, "V2 input carrying candidate_solutions MUST be rejected (P1 guard)"


def t_one_candidate_per_solution():
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    ids = [c["candidate_id"] for c in t["candidate_solutions"]]
    assert ids == ["SOL-001", "SOL-002"], ids


def t_no_fabricated_product_facts():
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    for c in t["candidate_solutions"]:
        for f in ("premium", "term", "insurer", "product_name"):
            assert f not in c, "translator fabricated product-level field %r" % f
        assert c["liquidity_impact"] == "unknown", c["liquidity_impact"]


def t_empty_solutions_yields_no_candidate():
    plan = dict(SOLUTION_PLAN, solutions=[])
    t = stc.translate(plan, GAP, RISK, None, EVIDENCE, RULES)
    assert t["candidate_solutions"] == [], "empty solutions[] must not be back-filled"

    placeholder = {"status": "COMPLETE", "solution_type": "GENERAL",
                   "objective": "（当前无待解决的保障缺口，暂无解决策略）",
                   "coverage_direction": "（无可执行缺口，无需确定保障方向）", "priority": "P3"}
    t2 = stc.translate(placeholder, GAP, RISK, None, EVIDENCE, RULES)
    assert t2["candidate_solutions"] == [], "placeholder objective must not become a candidate"


def t_risk_categories_from_real_data():
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    by_id = {c["candidate_id"]: c for c in t["candidate_solutions"]}
    assert by_id["SOL-001"]["covers_risk_categories"] == ["R4"], by_id["SOL-001"]["covers_risk_categories"]
    assert by_id["SOL-002"]["covers_risk_categories"] == ["R1"], by_id["SOL-002"]["covers_risk_categories"]


def t_evidence_ids_preserved():
    ks = stc.build_knowledge_view(EVIDENCE, RULES)
    assert {r["chunk_id"] for r in ks["results"]} == {"EVD-001", "EVD-002"}
    assert ks["status"] == "success" and ks["conflict"] is False


def t_coverage_structure_from_rules():
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    by_id = {c["candidate_id"]: c for c in t["candidate_solutions"]}
    assert by_id["SOL-001"]["coverage_structure"] == ["life"]
    assert by_id["SOL-002"]["coverage_structure"] == ["medical"]


def t_strategy_trace_present():
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    assert len(t["_strategy_trace"]) == 2
    assert t["_strategy_trace"][0]["related_gap_ids"] == ["GAP-LIFE-001"]


def t_no_brand_names_in_output():
    brands = ["中国人寿", "平安保险", "太平洋保险", "友邦保险", "泰康人寿", "新华保险"]
    t = stc.translate(SOLUTION_PLAN, GAP, RISK, None, EVIDENCE, RULES)
    blob = json.dumps(t, ensure_ascii=False)
    assert not any(b in blob for b in brands), "no insurer/product names may appear"


def t_unverifiable_is_not_a_pass():
    """A candidate with no premium/term must not have budget/term counted as satisfied."""
    spec = importlib.util.spec_from_file_location(
        "invoke_product_recommendation",
        os.path.join(HERE, "invoke-product-recommendation.py"))
    ipr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ipr)

    v2 = {
        "requirement_analysis": {"analysis_status": "COMPLETE",
                                 "information_sufficiency": {"sufficiency_status": "SUFFICIENT"},
                                 "requirements": [{"requirement_id": "REQ-LIFE",
                                                   "requirement_type": "life",
                                                   "priority": "P0_CRITICAL"}],
                                 "guardrails": {"product_recommendation_included": False}},
        "risk_assessment": {"risks": [{"risk_id": "R4-001", "risk_category": "R4",
                                       "residual_risk": "HIGH", "priority": "P0"}]},
        "coverage_gap_analysis": GAP,
        "solution_plan": {"status": "COMPLETE", "solution_type": "TERM_LIFE",
                          "objective": "建立家庭责任保障", "coverage_direction": "x",
                          "priority": "P0", "solutions": [SOLUTION_PLAN["solutions"][0]],
                          "information_gaps": []},
        "knowledge_evidence": EVIDENCE,
        "constraints": {"budget_max": 30000, "term_min_years": 10, "liquidity_required": True},
    }
    result, warnings = ipr.run(v2)
    assert not warnings, warnings
    ev = result["payload"]["candidate_evaluations"][0]
    cf = ev["constraint_fit"]
    assert cf["hard_constraints"] == [], "unverifiable must NOT be recorded as a pass, got %s" % cf["hard_constraints"]
    assert {u["type"] for u in cf["unverifiable_constraints"]} == {"budget", "term", "liquidity"}
    codes = result["payload"]["primary_recommendation"]["reason_codes"]
    assert "within_budget" not in codes and "meets_term" not in codes, codes
    assert result["payload"]["human_review_required"] is True
    assert result["payload"]["status"] == "COMPLETE"


def main():
    check("input_rejects_candidate_solutions", t_input_rejects_candidate_solutions)
    check("one_candidate_per_solution", t_one_candidate_per_solution)
    check("no_fabricated_product_facts", t_no_fabricated_product_facts)
    check("empty_solutions_yields_no_candidate", t_empty_solutions_yields_no_candidate)
    check("risk_categories_from_real_data", t_risk_categories_from_real_data)
    check("evidence_ids_preserved", t_evidence_ids_preserved)
    check("coverage_structure_from_rules", t_coverage_structure_from_rules)
    check("strategy_trace_present", t_strategy_trace_present)
    check("no_brand_names_in_output", t_no_brand_names_in_output)
    check("unverifiable_is_not_a_pass", t_unverifiable_is_not_a_pass)

    lines = ["product-recommendation V2 invariants", ""]
    for name, ok, msg in RESULTS:
        lines.append("[%s] %s%s" % ("PASS" if ok else "FAIL", name, ("  -- " + msg) if msg else ""))
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    lines.append("")
    lines.append("RESULT: %s (%d/%d passed)" % ("ALL GREEN" if not failed else "FAILURES PRESENT",
                                                len(RESULTS) - failed, len(RESULTS)))
    text = "\n".join(lines)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        f.write(text)
    print(text)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
