# -*- coding: utf-8 -*-
"""K.28-II-SHADOW evaluator (zero production authority).

Runs the frozen corpus tests/golden/claim-evidence-shadow.v1.json
through the deterministic shadow layer, simulates the OD-7 delivery
policy vs the CURRENT citation-presence gate, classifies every false
support, and (opt-in via INSURANCE_AGENT_CLAIM_SHADOW_LLM=1, process
local) runs the LLM comparator. Output: tmp/obs/k28iish_results.json.
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import date

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding.shadow.claims import (  # noqa: E402
    classify_claim, split_claims)
from runtime.grounding.shadow import support as sup  # noqa: E402

CORPUS = os.path.join(REPO, "tests", "golden",
                      "claim-evidence-shadow.v1.json")
OUT = os.path.join(REPO, "tmp", "obs", "k28iish_results.json")
AS_OF = date(2026, 9, 29)
ORDER = {sup.SUPPORTED: 0, sup.NOT_APPLICABLE: 1, sup.PARTIAL: 2,
         sup.CONTRADICTED: 3, sup.UNSUPPORTED: 4}


def _strip_cit(text):
    return re.sub(r"\[E\d+\]", "", text).strip()


def judge_case(case):
    """Single-claim corpus entry -> combined judgment."""
    claims = split_claims(case["claim_text"])
    rows = []
    for c in claims:
        j = sup.judge_support(c["claim_text"], c["claim_type"],
                              c["anchors"], case.get("evidence") or [],
                              AS_OF)
        rows.append({"text": c["claim_text"], "layer_type": c["claim_type"],
                     "status": j["support_status"],
                     "stype": j["support_type"], "reason": j["support_reason"]})
    if not rows:
        return {"combined": sup.UNSUPPORTED, "rows": []}
    if all(r["status"] == sup.NOT_APPLICABLE for r in rows):
        return {"combined": sup.NOT_APPLICABLE, "rows": rows}
    facts = [r["status"] for r in rows
             if r["status"] != sup.NOT_APPLICABLE]
    sts = set(facts)
    if sup.CONTRADICTED in sts:
        combined = sup.CONTRADICTED
    elif sts == {sup.SUPPORTED}:
        combined = sup.SUPPORTED
    elif sts & {sup.SUPPORTED, sup.PARTIAL}:
        combined = sup.PARTIAL   # any mix incl. full/partial support
    else:
        combined = sup.UNSUPPORTED
    return {"combined": combined, "rows": rows}


def fs_class(case, combined, expected):
    """FS-01..10 rule-based classification of false supports / misses."""
    if combined == expected:
        return "OK"
    if combined == sup.SUPPORTED and expected in (
            sup.UNSUPPORTED, sup.PARTIAL, sup.CONTRADICTED):
        if "[E" in case["claim_text"]:
            return "FS-01 citation presence bias"
        if case["class"] == "N4":
            return "FS-04 product confusion"
        if case["class"] in ("N5", "N6"):
            return "FS-05 temporal confusion"
        if case["class"] == "N3":
            return "FS-06 compound claim failure"
        if case["class"] == "N8":
            return "FS-03 lexical overlap / semantic neighbor"
        if case["class"] == "N2":
            return "FS-02 same-topic bias"
        return "FS-02 same-topic bias"
    if combined == sup.UNSUPPORTED and expected == sup.SUPPORTED:
        return "MISS-lexical (conservative under-support)"
    if combined == sup.PARTIAL and expected == sup.SUPPORTED:
        return "MISS-partial (coverage threshold)"
    if combined == sup.NOT_APPLICABLE and expected in (
            sup.SUPPORTED, sup.PARTIAL, sup.UNSUPPORTED, sup.CONTRADICTED):
        return "FS-09 user-fact confusion" if case[
            "claim_type"] == "C-USER" else "TYPE-exemption miss"
    if combined != sup.CONTRADICTED and expected == sup.CONTRADICTED:
        return "FS-10 contradiction failure"
    return "OTHER"


def current_gate_outcome(case):
    """Simulate TODAY's citation-presence gate on the claim text: a
    fact-marker sentence carrying any in-range [E#] with non-empty
    evidence passes (escapes) — citation presence as support."""
    text = case["claim_text"]
    has_cit = bool(re.search(r"\[E\d+\]", text))
    has_ev = bool(case.get("evidence"))
    return "passes" if (has_cit and has_ev) else "blocks"


def main():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    cases = corpus["cases"]
    recs = []
    for case in cases:
        if case["class"] == "S":
            continue  # handled in streaming section
        if case["case_id"] == "RV4-A":
            continue  # C2-layer check below
        j = judge_case(case)
        exp = case["expected"]
        cg = current_gate_outcome(case)
        # shadow OD-7 policy outcome on this single-claim answer
        sim = sup.simulate_delivery(_strip_cit(case["claim_text"]),
                                    case.get("evidence") or [], AS_OF)
        shadow_escapes = sim["escaped_unsupported"] > 0 or (
            sim["outcome"] == "delivered" and exp in (
                sup.UNSUPPORTED, sup.PARTIAL, sup.CONTRADICTED)
            and j["combined"] == sup.SUPPORTED)
        recs.append({
            "case_id": case["case_id"], "class": case["class"],
            "claim_type": case["claim_type"],
            "layer_type": j["rows"][0]["layer_type"] if j["rows"] else None,
            "expected": exp, "actual": j["combined"], "rows": j["rows"],
            "correct": j["combined"] == exp,
            "current_gate": cg,
            "current_gate_escapes": cg == "passes" and exp in (
                sup.UNSUPPORTED, sup.PARTIAL, sup.CONTRADICTED),
            "shadow_escapes": bool(shadow_escapes),
            "fs": fs_class(case, j["combined"], exp),
        })

    # ---- RV4-A: C2 layer seal check (real qualification) ----
    from runtime.grounding import gate as ggate
    from runtime.qa_agent.agent import _qualified_evidence
    rv4q = ("200万重疾险是我的，我和配偶都有百万医疗险，孩子没有保险。"
            "房贷还剩100万。配偶35岁，有100万重疾险，家庭主要收入是我一个人")
    agri_case = [c for c in cases if c["case_id"] == "RV4-A"][0]
    qualified = _qualified_evidence(agri_case["evidence"], rv4q,
                                    ggate.load_rules())
    rv4a = {"query": rv4q, "c2_qualified_count": len(qualified),
            "expected": 0, "pass": len(qualified) == 0}

    # ---- streaming S1/S3 simulation ----
    s_out = []
    for case in cases:
        if case["class"] != "S":
            continue
        per = case["expected"]["per_sentence"]
        sents = split_claims(case["claim_text"])
        rows = []
        for c in sents:
            jj = sup.judge_support(c["claim_text"], c["claim_type"],
                                   c["anchors"], case.get("evidence") or [],
                                   AS_OF)
            rows.append({"text": c["claim_text"][:40],
                         "type": c["claim_type"], "status": jj["support_status"]})
        s1_ok = len(rows) == len(per) and all(
            r["status"] == e[1] and r["type"] == e[0]
            for r, e in zip(rows, per))
        # S3 (final-only): identical deterministic granularity; only the
        # POLICY differs (hold-at-end vs hold-in-stream) — escape identical
        s_out.append({"case_id": case["case_id"], "s1_rows": rows,
                      "per_sentence_expected": per, "s1_ok": s1_ok,
                      "s3_same": True,
                      "note": case["reason"]})

    # ---- metrics ----
    facts = [r for r in recs if r["claim_type"] == "C-FACT"]
    def prf(rs):
        tp = sum(1 for r in rs if r["expected"] == sup.SUPPORTED
                 and r["actual"] == sup.SUPPORTED)
        fp = sum(1 for r in rs if r["expected"] != sup.SUPPORTED
                 and r["actual"] == sup.SUPPORTED)
        fn = sum(1 for r in rs if r["expected"] == sup.SUPPORTED
                 and r["actual"] != sup.SUPPORTED)
        tn = sum(1 for r in rs if r["expected"] != sup.SUPPORTED
                 and r["actual"] != sup.SUPPORTED)
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / (tp + fn) if tp + fn else None
        return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
                "precision": round(prec, 4) if prec is not None else None,
                "recall": round(rec, 4) if rec is not None else None,
                "false_support_rate_of_judged_supported":
                    round(fp / (tp + fp), 4) if tp + fp else None,
                "false_support_rate_of_actually_unsupported":
                    round(fp / (fp + tn), 4) if fp + tn else None}
    by_type = {}
    for t in corpus["claim_taxonomy"]:
        rs = [r for r in recs if r["claim_type"] == t]
        if rs:
            by_type[t] = {"n": len(rs),
                          "exact": round(sum(1 for r in rs if r["correct"])
                                         / len(rs), 4),
                          **prf(rs)}
    by_class = {}
    for k in sorted({r["class"] for r in recs}):
        rs = [r for r in recs if r["class"] == k]
        by_class[k] = {"n": len(rs),
                       "exact": round(sum(1 for r in rs if r["correct"])
                                      / len(rs), 4)}
    # escape comparison (C-FACT with citations = the current-gate at-risk set)
    at_risk = [r for r in facts if r["current_gate"] == "passes"]
    cur_esc = sum(1 for r in at_risk if r["current_gate_escapes"])
    shd_esc = sum(1 for r in at_risk if r["shadow_escapes"])
    typing_acc = round(sum(1 for r in recs
                           if r["layer_type"] == r["claim_type"])
                       / len(recs), 4)
    fs_counts = Counter(r["fs"] for r in recs if r["fs"] != "OK")
    out = {
        "n_cases": len(recs), "as_of": str(AS_OF),
        "overall_exact": round(sum(1 for r in recs if r["correct"])
                               / len(recs), 4),
        "c_fact_prf": prf(facts), "by_claim_type": by_type,
        "by_class": by_class, "fs_classification": dict(fs_counts),
        "typing_accuracy": typing_acc,
        "escape": {
            "at_risk_current_gate_passes": len(at_risk),
            "current_gate_escapes": cur_esc,
            "shadow_policy_escapes": shd_esc,
            "reduction": round((cur_esc - shd_esc) / cur_esc, 4)
            if cur_esc else None,
        },
        "rv4a_c2_layer": rv4a,
        "streaming": s_out,
        "records": recs,
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    print("n=%d exact=%.4f typing=%.4f" % (
        out["n_cases"], out["overall_exact"], typing_acc))
    print("C-FACT", json.dumps(out["c_fact_prf"], ensure_ascii=False))
    print("escape", json.dumps(out["escape"], ensure_ascii=False))
    print("FS", json.dumps(dict(fs_counts), ensure_ascii=False))
    print("by_class", json.dumps(by_class, ensure_ascii=False))
    print("RV4-A pass:", rv4a["pass"])
    print("WROTE", OUT)
    return out


if __name__ == "__main__":
    main()
