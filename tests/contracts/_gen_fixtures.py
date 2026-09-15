#!/usr/bin/env python3
"""Generate real legacy-output fixtures for the contract tests (Phase 1).

Sources genuine artifacts so the adapters are validated against actual skill outputs:
- client_profile / recommendation / report_generation : from report-generation dataset
  (complete_client case, which embeds full 5-upstream input and is exercised by Skill 6 eval)
- requirement_analysis : the skill's own schema-validation fixture (output.valid.json)
- knowledge_search    : a live run of the knowledge-search engine
- risk_assessment     : a representative RiskAnalysisOutput sample (synthetic, since the
  risk-analysis engine is PowerShell-driven and not executed here; the canonical contract
  for risk-assessment uses a permissive payload, so this sample validates the adapter boundary)
"""
import json
import os
import shutil
import sys

REPO = "D:/Workspace/insurance-agent"
FIX = os.path.join(REPO, "tests", "contracts", "fixtures")
os.makedirs(FIX, exist_ok=True)


def _load_report_dataset():
    p = os.path.join(
        REPO, ".trae", "skills", "report-generation", "evals", "cases", "dataset-manifest.json"
    )
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    ds = _load_report_dataset()
    cases = {c["name"]: c for c in ds["cases"]}
    cc = cases["complete_client"]
    inp = cc["input"]

    # 1) client_profile (real CanonicalClientState)
    with open(os.path.join(FIX, "client_profile.json"), "w", encoding="utf-8") as f:
        json.dump(inp["client_profile"], f, ensure_ascii=False, indent=2)

    # 2) recommendation (real RecommendationOutput)
    with open(os.path.join(FIX, "recommendation.json"), "w", encoding="utf-8") as f:
        json.dump(inp["recommendation"], f, ensure_ascii=False, indent=2)

    # 3) report_generation (real ReportGenerationResult via Skill 6 engine)
    rg = os.path.join(REPO, ".trae", "skills", "report-generation", "scripts")
    sys.path.insert(0, rg)
    from report_generation_engine import generate_report, load_rules

    out = generate_report(inp, load_rules())
    with open(os.path.join(FIX, "report_generation.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    # 4) requirement_analysis (real schema-valid output fixture)
    ra_valid = os.path.join(
        REPO,
        ".trae",
        "skills",
        "requirement_analysis",
        "evals",
        "fixtures",
        "unit",
        "schema",
        "output.valid.json",
    )
    shutil.copy(ra_valid, os.path.join(FIX, "requirement_analysis.json"))

    # 5) knowledge_search (live engine run)
    if REPO not in sys.path:
        sys.path.insert(0, REPO)
    from knowledge.rag.store import KnowledgeStore
    from knowledge.rag.engine import KnowledgeSearchEngine

    ks_skill = os.path.join(REPO, ".trae", "skills", "knowledge-search")
    kb_dir = os.path.join(ks_skill, "evals", "fixtures", "kb")
    ret_rules = json.load(open(os.path.join(ks_skill, "resources", "config", "retrieval.rules.json"), encoding="utf-8-sig"))
    rk_rules = json.load(open(os.path.join(ks_skill, "resources", "config", "ranking.rules.json"), encoding="utf-8-sig"))
    ret_rules.update(rk_rules)
    store = KnowledgeStore()
    store.ingest_dir(kb_dir)
    engine = KnowledgeSearchEngine(store, ret_rules)
    res = engine.search("百万医疗险 保障范围 免赔额", top_k=3)
    ks_out = res.to_dict()
    with open(os.path.join(FIX, "knowledge_search.json"), "w", encoding="utf-8") as f:
        json.dump(ks_out, f, ensure_ascii=False, indent=2)

    # 6) risk_assessment (representative sample; permissive payload)
    risk = {
        "output_version": "1.0",
        "layer": "risk_analysis",
        "upstream": "requirement_analysis",
        "analysis_status": "FORMAL",
        "overall_confidence": 0.85,
        "family_risk_overview": "家庭主要经济支柱，医疗与身故责任风险偏高。",
        "risks": [
            {
                "risk_id": "R1-001",
                "risk_category": "R1",
                "risk_name": "医疗费用",
                "status": "KNOWN",
                "residual_risk": "HIGH",
                "severity": "HIGH",
                "likelihood": "HIGH",
                "priority": "P0",
                "conclusion": "医疗费用存在自付缺口",
            },
            {
                "risk_id": "R4-001",
                "risk_category": "R4",
                "risk_name": "家庭责任",
                "status": "KNOWN",
                "residual_risk": "HIGH",
                "severity": "HIGH",
                "likelihood": "LOW",
                "priority": "P0",
                "conclusion": "寿险保障严重不足",
            },
        ],
        "risk_matrix": [
            {"risk_id": "R1-001", "risk_category": "R1", "severity": "HIGH", "likelihood": "HIGH",
             "residual_risk": "HIGH", "priority": "P0"}
        ],
        "top_priorities": [{"risk_id": "R1-001", "priority": "P0", "reason": "高发生高影响"}],
        "unknowns": [],
        "assumptions": [],
        "next_information_needed": [],
        "missing_from_upstream": [],
        "guardrails": {
            "product_recommendation_included": False,
            "sales_language_detected": False,
            "layer_note": "风险层不推荐产品",
        },
    }
    with open(os.path.join(FIX, "risk_assessment.json"), "w", encoding="utf-8") as f:
        json.dump(risk, f, ensure_ascii=False, indent=2)

    with open(os.path.join(FIX, "_gen_log.txt"), "w", encoding="utf-8") as f:
        f.write("fixtures generated:\nclient_profile.json\nrecommendation.json\n"
                "report_generation.json\nrequirement_analysis.json\nknowledge_search.json\n"
                "risk_assessment.json\n")
    print("FIXTURES GENERATED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import traceback
        with open(os.path.join(FIX, "_gen_error.txt"), "w", encoding="utf-8") as ef:
            ef.write(traceback.format_exc())
        print("GEN_ERROR", repr(e))
