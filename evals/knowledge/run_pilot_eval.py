#!/usr/bin/env python3
"""Real Knowledge Pilot evaluation — Phase 14.7 §20–§30.

Runs the REAL pilot corpus (3 official partial-copy documents, real
metadata, real hashes) through the existing architecture — the same
Provider/Governance/Evidence/Provenance stack — and applies the
phase's hard gates. Deterministic (fixed clock, fixed as-of dates).
Exit 0 iff all cases pass AND all hard gates are clean.
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from knowledge.governance import (  # noqa: E402
    GovernanceDecision, QueryContext, SourceRegistry, build_evidence_item,
    validate_decision_provenance, validate_hit, validate_provenance)
from knowledge.provider import MockKnowledgeProvider  # noqa: E402
from knowledge.provider import ProviderUnavailable, WeKnoraKnowledgeProvider
from knowledge.service import KnowledgeService  # noqa: E402

PILOT = os.path.join(REPO, "knowledge", "pilot")
DOCS = os.path.join(PILOT, "documents")
TABLE = os.path.join(PILOT, "registry", "pilot_sources.json")
FIXED_NOW = "2026-09-20T00:00:00Z"
TODAY = "2026-09-20"


def pilot_registry(path=TABLE):
    return SourceRegistry.from_kb(DOCS, path)


def pilot_service(reg=None):
    reg = reg or pilot_registry()
    return KnowledgeService(
        provider=MockKnowledgeProvider(kb_dir=DOCS,
                                        stamps=reg.provider_stamps()),
        registry=reg, now_fn=lambda: FIXED_NOW), reg


def _evidence(query, as_of=TODAY, jurisdiction="CN", svc=None):
    if svc is None:
        svc, reg = pilot_service()
    else:
        reg = svc.registry()
    items, gov, dec, ctx = svc.build_evidence(
        query, top_k=5, as_of=as_of, jurisdiction=jurisdiction)
    return items, dec, reg, svc


def real_item(document_id="pilot_law_medical_fund_2021"):
    """One governance-built evidence item from a REAL document."""
    items, _, reg, svc = _evidence("骗取 医疗保障基金 罚款")
    for i in items:
        if i["document_id"] == document_id:
            return copy.deepcopy(i), reg
    # fallback: build directly from the first available real hit
    if items:
        return copy.deepcopy(items[0]), reg
    raise AssertionError("no real evidence produced for %s" % document_id)


# ------------------------------------------------------------------ #
# cases
# ------------------------------------------------------------------ #
def c_retrieval_positive(results, r, case):
    items, _, reg, _ = _evidence(case["query"])
    docs = {i["document_id"] for i in items}
    ok = case["expected_document"] in docs
    r.append({"case_id": case["case_id"], "status": "PASS" if ok
              else "FAIL", "hard_gate": "none", "detail": sorted(docs)})


def c_abstention(results, r, case):
    items, _, reg, _ = _evidence(case["query"])
    ok = len(items) == 0
    r.append({"case_id": case["case_id"], "status": "PASS" if ok
              else "FAIL", "hard_gate": "unsafe_accept",
              "detail": {"items": len(items)}})


def c_temporal(results, r, case):
    items, dec, reg, _ = _evidence("骗取 医疗保障基金 罚款",
                                   as_of=case["as_of"])
    if case["expect"] == "deny_all":
        ok = len(items) == 0 and all(
            d["status"] == "FUTURE" for d in dec if not d["allowed"])
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "expired_knowledge_accepted",
                  "detail": {"items": len(items)}})
    else:
        ok = len(items) > 0 and all(d["status"] == "CURRENT"
                                    for d in dec if d["allowed"])
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "none",
                  "detail": {"items": len(items)}})


def c_jurisdiction(results, r, case):
    items, dec, reg, _ = _evidence("定点 医疗保障 申请",
                                   jurisdiction=case["jurisdiction"])
    if case["expect"] == "national_applies":
        ok = len(items) > 0 and all(
            reg.get_entry(i["document_id"])["jurisdiction"] == "CN"
            for i in items)
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "none",
                  "detail": {"items": len(items)}})


def c_license(results, r, case):
    items, _, reg, _ = _evidence("骗取 医疗保障基金 罚款")
    if case["expect"] == "allowed_on_all":
        ok = items and all(i["license_status"] == "ALLOWED"
                           and i.get("license_note") is not None or True
                           for i in items)
        ok = bool(items) and all(i["license_status"] == "ALLOWED"
                                 for i in items)
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "none",
                  "detail": {"statuses": {i["license_status"]
                                          for i in items}}})
    elif case["expect"] == "unknown_denied":
        reg2 = pilot_registry()
        reg2.get_entry("pilot_law_medical_fund_2021")[
            "license_status"] = "UNKNOWN"
        svc2, _ = pilot_service(reg2)
        items2, dec2, _, _ = _evidence("骗取 医疗保障基金 罚款", svc=svc2)
        ok = all(i["document_id"] != "pilot_law_medical_fund_2021"
                 for i in items2)
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "UNKNOWN_license_accepted",
                  "detail": {"leaked": [i["document_id"]
                                        for i in items2]}})


def c_mutation(results, r, case):
    base, reg = real_item()
    m = case["mutate"]
    if m == "flip_hash_char":
        base["content_hash"] = ("0" if base["content_hash"][0] != "0"
                                else "1") + base["content_hash"][1:]
        want_rule = "P007"
    elif m == "version_to_2020":
        base["version_id"] = base["version_id"].replace("@2021", "@2020")
        base["version"] = "2020"
        want_rule = "P004"
    elif m == "license_forged_allowed":
        reg2 = pilot_registry()
        reg2.get_entry(base["document_id"])["license_status"] = "UNKNOWN"
        reg = reg2                     # registry says UNKNOWN; item lies
        want_rule = "P009"
    elif m == "jurisdiction_swap":
        base["jurisdiction"] = "CN-SH"
        want_rule = "P008"
    elif m == "authority_flip":
        base["authority_level"] = "D"
        want_rule = "P006"
    else:
        want_rule = ""
    ok_prov, why = validate_provenance(base, reg)
    ok = (not ok_prov) and any(w.startswith(want_rule) for w in why)
    r.append({"case_id": case["case_id"], "status": "PASS" if ok
              else "FAIL", "hard_gate": "hash_mismatch_accepted"
              if m == "flip_hash_char" else
              ("UNKNOWN_license_accepted" if "license" in m
               else "false_allow"),
              "detail": {"prov_ok": ok_prov, "why": why[:3]}})


def c_provenance_chain(results, r, case):
    item, reg = real_item()
    ok, why = validate_provenance(item, reg)
    entry = reg.get_entry(item["document_id"])
    chain = ok \
        and item["source_id"] == entry["source_id"] \
        and item["version"] == entry["version"] \
        and item["effective_from"] == entry["effective_from"] \
        and item["knowledge_hit_id"] in entry["content_hashes"] \
        and bool(item["retrieved_at"]) \
        and item["content_hash"] == entry["content_hashes"][
            item["knowledge_hit_id"]]
    r.append({"case_id": case["case_id"], "status": "PASS" if chain
              else "FAIL", "hard_gate": "invalid_provenance_pass",
              "detail": {"valid": ok, "why": why[:2],
                         "source": item["source_id"],
                         "uri": entry["canonical_uri"]}})


def c_decision(results, r, case):
    items, _, reg, _ = _evidence("骗取 医疗保障基金 罚款")
    index = {i["evidence_id"]: i for i in items}
    dec = {"payload": {"evidence_refs": [items[0]["evidence_id"]]
           if case["expect"] == "ok" else ["PILOT-NOPE"]}}
    ok, why = validate_decision_provenance(dec, index, reg)
    passed = (ok is (case["expect"] == "ok"))
    r.append({"case_id": case["case_id"], "status": "PASS" if passed
              else "FAIL", "hard_gate": "fabricated_evidence"
              if case["expect"] == "fail" else "none",
              "detail": {"ok": ok, "why": why[:2]}})


def c_isolation(results, r, case):
    if case["mode"] == "default_never_sees_pilot":
        # default service (no injection) must NOT serve pilot docs
        from knowledge.service import default_service, reset_default_service
        reset_default_service()
        items_default, _, _, _ = (default_service().build_evidence(
            "定点 执业药师 医疗保障基金 健康保险管理办法 强制保险"))
        reg = pilot_registry()
        pilot_ids = {e["document_id"] for e in reg.entries}
        leaked = sorted({i["document_id"] for i in items_default}
                        & pilot_ids)
        ok = not leaked
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "mock_silent_fallback",
                  "detail": leaked})
    elif case["mode"] == "pilot_never_sees_synthetic":
        items, _, reg, _ = _evidence("等待期 免赔额 健康告知")
        pilot_ids = {e["document_id"] for e in reg.entries}
        synthetic = {i["document_id"] for i in items} - pilot_ids
        ok = not synthetic
        r.append({"case_id": case["case_id"], "status": "PASS" if ok
                  else "FAIL", "hard_gate": "mock_silent_fallback",
                  "detail": sorted(synthetic)})


def c_provider_failure(results, r, case):
    svc = KnowledgeService(provider=WeKnoraKnowledgeProvider(),
                           registry=pilot_registry(),
                           now_fn=lambda: FIXED_NOW)
    try:
        svc.build_evidence("骗取 医疗保障基金 罚款")
        ok, detail = False, "expected ProviderUnavailable"
    except ProviderUnavailable:
        ok, detail = True, "fail-closed"
    r.append({"case_id": case["case_id"], "status": "PASS" if ok
              else "FAIL", "hard_gate": "fabricated_evidence",
              "detail": detail})


def c_grounding(results, r, case):
    from knowledge.evidence.attribute_grounding import \
        ground_product_attributes
    item, _ = real_item()
    g = ground_product_attributes(
        {"product_id": "SYN-REAL-1",
         "constraints": [{"constraint": "deductible", "value": "10000元"}]},
        [{"content": item["content"]}])
    attr = g["attributes"].get("deductible", {})
    # Existing policy (14.3/14.6): the product DECLARES a matchable
    # value and the real regulatory text does not mention it →
    # UNSUPPORTED ("evidence does not say this"). Real regulatory
    # texts never fabricate a product deductible — absence stays
    # absence; nothing is auto-filled.
    ok = attr.get("status") == "UNSUPPORTED"
    r.append({"case_id": case["case_id"], "status": "PASS" if ok
              else "FAIL", "hard_gate": "fabricated_evidence",
              "detail": {"got": attr.get("status")}})


CASES = [
    {"case_id": "P-RET-001", "kind": "retrieval_positive",
     "query": "骗取 医疗保障基金 罚款 2倍 5倍",
     "expected_document": "pilot_law_medical_fund_2021"},
    {"case_id": "P-RET-002", "kind": "retrieval_positive",
     "query": "零售药店 定点 执业药师 申请条件",
     "expected_document": "pilot_reg_pharmacy_2021"},
    {"case_id": "P-RET-003", "kind": "retrieval_positive",
     "query": "定点医疗机构 申请 医师执业证书 条件",
     "expected_document": "pilot_reg_hospital_2021"},
    {"case_id": "P-RET-004", "kind": "retrieval_positive",
     "query": "机动车交通事故责任强制保险 条例 赔偿责任",
     "expected_document": "pilot_law_tpll_2006"},
    {"case_id": "P-RET-005", "kind": "retrieval_positive",
     "query": "健康保险 经营 医疗保险 疾病保险 管理办法",
     "expected_document": "pilot_reg_health_ins_2019"},
    {"case_id": "P-RET-006", "kind": "retrieval_positive",
     "query": "互联网保险业务 监管办法 保险公司 经营",
     "expected_document": "pilot_reg_internet_ins_2020"},
    {"case_id": "P-RET-007", "kind": "retrieval_positive",
     "query": "保险欺诈 防范 打击 工作办法",
     "expected_document": "pilot_reg_antifraud_2024"},
    {"case_id": "P-RET-008", "kind": "retrieval_positive",
     "query": "人身保险产品 信息披露 管理办法",
     "expected_document": "pilot_reg_disclosure_2022"},
    {"case_id": "P-ABS-001", "kind": "abstention",
     "query": "量子计算机 显卡 价格 评测"},
    {"case_id": "P-TMP-001", "kind": "temporal", "as_of": "2021-01-01",
     "expect": "deny_all"},
    {"case_id": "P-TMP-002", "kind": "temporal", "as_of": TODAY,
     "expect": "current_allowed"},
    {"case_id": "P-JUR-001", "kind": "jurisdiction",
     "jurisdiction": "CN-BJ", "expect": "national_applies"},
    {"case_id": "P-LIC-001", "kind": "license", "expect": "allowed_on_all"},
    {"case_id": "P-LIC-002", "kind": "license", "expect": "unknown_denied"},
    {"case_id": "P-MUT-001", "kind": "mutation", "mutate": "flip_hash_char"},
    {"case_id": "P-MUT-002", "kind": "mutation", "mutate": "version_to_2020"},
    {"case_id": "P-MUT-003", "kind": "mutation",
     "mutate": "license_forged_allowed"},
    {"case_id": "P-MUT-004", "kind": "mutation", "mutate": "jurisdiction_swap"},
    {"case_id": "P-MUT-005", "kind": "mutation", "mutate": "authority_flip"},
    {"case_id": "P-PROV-001", "kind": "provenance_chain"},
    {"case_id": "P-DEC-001", "kind": "decision", "expect": "ok"},
    {"case_id": "P-DEC-002", "kind": "decision", "expect": "fail"},
    {"case_id": "P-ISO-001", "kind": "isolation",
     "mode": "default_never_sees_pilot"},
    {"case_id": "P-ISO-002", "kind": "isolation",
     "mode": "pilot_never_sees_synthetic"},
    {"case_id": "P-FAIL-001", "kind": "provider_failure"},
    {"case_id": "P-GRD-001", "kind": "grounding"},
]

DISPATCH = {"retrieval_positive": c_retrieval_positive,
            "abstention": c_abstention, "temporal": c_temporal,
            "jurisdiction": c_jurisdiction, "license": c_license,
            "mutation": c_mutation, "provenance_chain": c_provenance_chain,
            "decision": c_decision, "isolation": c_isolation,
            "provider_failure": c_provider_failure,
            "grounding": c_grounding}


def run_all():
    results = []
    for case in CASES:
        try:
            DISPATCH[case["kind"]](results, results, case)
        except Exception as e:  # noqa: BLE001 — a crash IS a failure
            results.append({"case_id": case["case_id"], "status": "FAIL",
                            "hard_gate": "exception",
                            "detail": {"detail": str(e)[:140]}})
    return results


def hard_gates(results):
    v = {}
    for r in results:
        if r["hard_gate"] not in ("none",) and r["status"] == "FAIL":
            v[r["hard_gate"]] = v.get(r["hard_gate"], 0) + 1
    return v


def main():
    results = run_all()
    gates = hard_gates(results)
    passed = sum(1 for r in results if r["status"] == "PASS")
    ok = passed == len(results) and not gates
    lines = ["", "REAL KNOWLEDGE PILOT EVAL (Phase 14.7) — %s"
             % ("ALL GREEN" if ok else "FAILURES PRESENT"), ""]
    for r in results:
        safe = json.loads(json.dumps(r["detail"], ensure_ascii=False,
                                     default=list))
        lines.append("[%s] %-11s %s %s" % (r["status"], r["case_id"],
                                           r["hard_gate"],
                                           json.dumps(safe,
                                                      ensure_ascii=False)[:80]))
    lines += ["", "HARD GATES: " + (json.dumps(gates) if gates else "CLEAN"),
              "OVERALL: %s (%d/%d)" % ("PASS" if ok else "FAIL", passed,
                                       len(results))]
    print("\n".join(lines))
    with open(os.path.join(REPO, "tmp", "pilot_eval_report.json"), "w",
              encoding="utf-8") as f:
        json.dump({"results": json.loads(json.dumps(
            results, ensure_ascii=False, default=list)),
            "hard_gates": gates,
            "overall": "PASS" if ok else "FAIL"}, f,
            ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
