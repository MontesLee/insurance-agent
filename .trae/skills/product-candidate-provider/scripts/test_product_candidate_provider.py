#!/usr/bin/env python3
"""product-candidate-provider: architecture invariants + Step 2 negative tests.

Machine-checkable only. No MANUAL assertions count as a pass (AGENTS.md section 6).

Covers spec section 20:
  Test 1  fake product            -> PRODUCT_NOT_IN_CATALOG
  Test 2  age ineligible          -> ELIGIBILITY_INELIGIBLE
  Test 3  wrong coverage direction-> COVERAGE_DIRECTION_MISMATCH
  Test 4  no evidence             -> EVIDENCE_MISSING
  Test 5  unknown product name    -> NOT_FOUND

Plus anti-fake-pass invariants and a negative probe that mutates the rules file to prove
the guards actually read it (a test that cannot fail is not a test).
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_DIR = os.path.dirname(HERE)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from product_candidate_engine import (  # noqa: E402
    build_candidates, check_eligibility, load_catalog, load_rules, lookup_product,
    match_coverage_direction, resolve_product_types,
)

LOG = os.path.join(SKILL_DIR, "evals", "cases", "_candidate_unit_log.txt")
CHECKS = []


def chk(name, cond, detail=""):
    CHECKS.append((name, bool(cond), detail))


MEDICAL_DIRECTION = "以大额医疗支出敞口确定保额，优先覆盖社保目录外费用与免赔额以上部分"
LIFE_DIRECTION = "以家庭责任（房贷、子女抚养、赡养）与收入替代缺口确定保障额度，保障期限覆盖主要责任期"


def ev(status="success", docs=("01_medical_insurance.md",)):
    return {
        "artifact_type": "knowledge-evidence",
        "payload": {
            "status": status,
            "evidence": [
                {"evidence_id": "CH-%03d" % (i + 1), "document_id": "DOC-%03d" % (i + 1),
                 "document_name": d, "content": "demo", "source": d,
                 "relevance": 0.8, "confidence": 0.8}
                for i, d in enumerate(docs)
            ],
            "conflict": False,
        },
    }


def sol(sid="SOL-001", stype="MEDICAL", direction=MEDICAL_DIRECTION, gap="GAP-001"):
    return {"artifact_type": "solution-plan", "payload": {"solutions": [
        {"solution_id": sid, "solution_type": stype, "objective": "o",
         "coverage_direction": direction, "priority": "P1",
         "related_gap_ids": [gap], "related_risk_ids": ["R1-001"]}]}}


def gap(domain="medical"):
    return {"artifact_type": "coverage-gap-analysis", "payload": {"gaps": [
        {"gap_id": "GAP-001", "domain": domain, "gap_level": "CRITICAL"}]}}


def client(age=30):
    return {"client_id": "C-T", "profile": {"age": age}}


def main():
    rules = load_rules()
    catalog = load_catalog(rules=rules)
    by_id = {p["product_id"]: p for p in catalog["products"]}

    # ---------------- Test 1: FAKE-001 ---------------------------------- #
    out = build_candidates({
        "client_profile": client(), "coverage_gap_analysis": gap(), "solution_plan": sol(),
        "knowledge_evidence": ev(), "requested_product_ids": ["FAKE-001"],
    }, rules, catalog)
    ids = [c["product_id"] for c in out["candidates"]]
    chk("Test1 FAKE-001 不出现在候选中", "FAKE-001" not in ids, str(ids))
    chk("Test1 FAKE-001 被拒且原因=PRODUCT_NOT_IN_CATALOG",
        any(r.get("product_id") == "FAKE-001"
            and "PRODUCT_NOT_IN_CATALOG" in (r.get("reason_codes") or [])
            for r in out["rejected"]),
        str(out["rejected"]))

    # ---------------- Test 2: age ineligible ----------------------------- #
    out2= build_candidates({
        "client_profile": client(age=85), "coverage_gap_analysis": gap(),
        "solution_plan": sol(), "knowledge_evidence": ev(),
    }, rules, catalog)
    chk("Test2 85岁客户：候选全部 ELIGIBILITY_INELIGIBLE",
        bool(out2["candidates"]) and all(
            (c["eligibility"] or {}).get("status") == "INELIGIBLE" for c in out2["candidates"]),
        str([(c["product_id"], (c["eligibility"] or {}).get("status"))
             for c in out2["candidates"]]))
    chk("Test2 无可准入候选", not out2["admissible_candidate_ids"],
        str(out2["admissible_candidate_ids"]))
    # Invariant: an INELIGIBLE product must never be admissible
    chk("不变量：INELIGIBLE 候选绝不进入 admissible",
        all(not c["admissible"] for c in out2["candidates"]
            if (c["eligibility"] or {}).get("status") == "INELIGIBLE"), "")

    # ---------------- Test 3: wrong coverage direction ------------------- #
    out3= build_candidates({
        "client_profile": client(), "coverage_gap_analysis": gap("life"),
        "solution_plan": sol(stype="TERM_LIFE", direction=LIFE_DIRECTION),
        "knowledge_evidence": ev(docs=("04_life_insurance.md",)),
    }, rules, catalog)
    p007 = [c for c in out3["candidates"] if c["product_id"] == "P007"]
    p008 = [c for c in out3["candidates"] if c["product_id"] == "P008"]
    chk("Test3 寿险策略下 P007（家庭责任方向）匹配",
        bool(p007) and p007[0]["coverage_direction_match"] == "MATCH",
        str(p007[0]["coverage_direction_match"]) if p007 else "missing")
    chk("Test3 寿险策略下 P008（储蓄/传承方向）判定 MISMATCH",
        bool(p008) and "COVERAGE_DIRECTION_MISMATCH" in p008[0]["reject_reason_codes"],
        str(p008[0]["reject_reason_codes"]) if p008 else "missing")
    chk("Test3 P008 不得准入", bool(p008) and not p008[0]["admissible"], "")

    # ---------------- Test 4: no evidence -------------------------------- #
    out4= build_candidates({
        "client_profile": client(), "coverage_gap_analysis": gap(), "solution_plan": sol(),
        "knowledge_evidence": {"artifact_type": "knowledge-evidence",
                               "payload": {"status": "insufficient_evidence",
                                           "evidence": [], "conflict": False}},
    }, rules, catalog)
    chk("Test4 无证据时全部候选 EVIDENCE_MISSING",
        bool(out4["candidates"]) and all(
            "EVIDENCE_MISSING" in c["reject_reason_codes"] for c in out4["candidates"]),
        str([(c["product_id"], c["reject_reason_codes"]) for c in out4["candidates"]]))
    chk("Test4 无证据时无可准入候选", not out4["admissible_candidate_ids"], "")

    # ---------------- Test 5: unknown product name ----------------------- #
    st, prod = lookup_product(catalog, "不存在的万能险X")
    chk("Test5 虚构产品名解析为 NOT_FOUND", st == "NOT_FOUND" and prod is None, str(st))
    st2, prod2 = lookup_product(catalog, "P001")
    chk("Test5 真实产品 id 解析为 FOUND", st2 == "FOUND" and prod2 is not None, str(st2))

    # ---------------- Anti-fake-pass invariants -------------------------- #
    chk("不变量：候选 product_id 全部存在于 Catalog",
        all(c["product_id"] in by_id for c in out["candidates"]), "")
    chk("不变量：所有候选 is_demo=true", all(c["is_demo"] for c in out["candidates"]), "")

    # Unknown age must be UNKNOWN -- never silently ELIGIBLE.
    st_unk, checks_unk, _ = check_eligibility({}, by_id["P001"], rules)
    chk("不变量：年龄未知时 eligibility=UNKNOWN（不得静默通过）",
        st_unk == "UNKNOWN", st_unk)
    st_ok, _, _ = check_eligibility(client(30), by_id["P001"], rules)
    chk("不变量：年龄已知且合规时 eligibility=ELIGIBLE", st_ok == "ELIGIBLE", st_ok)

    # Empty direction must not count as a match.
    m, _ = match_coverage_direction("", by_id["P001"]["coverage_directions"], rules)
    chk("不变量：空保障方向判定 UNKNOWN 而非 MATCH", m == "UNKNOWN", m)

    # GENERAL with no gap domain must yield no product types (and therefore no candidates).
    chk("不变量：GENERAL 且缺口域为 general 时无产品类型",
        resolve_product_types({"solution_type": "GENERAL", "related_gap_ids": ["GAP-X"]},
                              {"payload": {"gaps": [{"gap_id": "GAP-X", "domain": "general"}]}},
                              rules) == [], "")

    # ---------------- Negative probe: rules are really consulted --------- #
    # If the mapping is flipped, the candidate set MUST change. A guard that ignores the
    # rules file would keep producing the same answer and this probe would fail.
    tampered = copy.deepcopy(rules)
    tampered["solution_type_to_product_types"]["MEDICAL"] = ["savings"]
    out_t= build_candidates({
        "client_profile": client(), "coverage_gap_analysis": gap(), "solution_plan": sol(),
        "knowledge_evidence": ev(),
    }, tampered, catalog)
    ids_t = [c["product_id"] for c in out_t["candidates"]]
    chk("负向探针：篡改险种映射后候选集必须改变（证明规则被真正读取）",
        ids_t and ids_t != ids and all(i.startswith("P012") for i in ids_t),
        f"before={ids} after={ids_t}")

    # ---------------- Report --------------------------------------------- #
    for name, ok_, detail in CHECKS:
        print("[%s] %s%s" % ("PASS" if ok_ else "FAIL", name,
                             ("  -- " + detail) if detail and not ok_ else ""))
    passed = sum(1 for _, o, _ in CHECKS if o)
    total = len(CHECKS)
    print()
    print(f"CANDIDATE PROVIDER: {passed}/{total} passed")
    result = "ALL GREEN" if passed == total else "FAILURES PRESENT"
    print("RESULT: " + result)
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "w", encoding="utf-8") as f:
        for name, ok_, detail in CHECKS:
            f.write("[%s] %s%s\n" % ("PASS" if ok_ else "FAIL", name,
                                     ("  -- " + detail) if detail and not ok_ else ""))
        f.write(f"\nCANDIDATE PROVIDER: {passed}/{total} passed\n")
        f.write("RESULT: " + result + "\n")
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
