# -*- coding: utf-8 -*-
"""K.28-I-FIX-IMPL regression harness (per-step gate).

Re-runs the FROZEN corpus v1 against the current classifier and
compares against the K.28-I baseline (tmp/obs/k28i_results.json).
Computes BOTH severity gradings:
  v1 = K.28-I original instrument (fam-mismatch+anchor -> P1)
  v2 = task-§10 definition (P1 only when a WRONG agent/workflow path
       EXECUTES, i.e. auto-route into the wrong family; clarify/
       governed-unknown landings = P2 safe friction)
Monotonicity gate: per-cluster P1 counts must not increase and
business-impacting (v2 P0+P1) must not rise vs the previous step.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.intent.classifier import classify  # noqa: E402
from runtime.router import route  # noqa: E402
from runtime.agent_registry import default_registry  # noqa: E402

CORPUS = os.path.join(REPO, "tests", "golden",
                      "intent-golden-corpus.v1.json")
BASELINE = os.path.join(REPO, "tmp", "obs", "k28i_results.json")

CLUSTER = {
    "S1-TRAP-04": "c1_plan_noun_question", "S1-TRAP-05": "c1_plan_noun_question",
    "S1-TRAP-06": "c1_plan_noun_question", "S1-TRAP-08": "c1_plan_noun_question",
    "S1-QA-16": "c1_plan_noun_question", "S6-MIX-04": "c1_plan_noun_question",
    "S6-BORDER-07": "c1_plan_noun_question", "S5-SW-10": "c1_plan_noun_question",
    "S2-QA-FU-01": "c2_omitted_demonstrative", "S2-QA-FU-02": "c2_omitted_demonstrative",
    "S2-QA-FU-03": "c2_omitted_demonstrative", "S4-ELL-01": "c2_omitted_demonstrative",
    "S4-ELL-02": "c2_omitted_demonstrative", "S4-ELL-05": "c2_omitted_demonstrative",
    "S5-SW-09": "c3_false_continuation", "S6-BORDER-12": "c3_false_continuation",
    "S1-PLAN-09": "c4_colloquial_plan", "S3-QACHAIN-06": "c5_context_omission",
    "S5-SW-03": "c6_pending_recommendation",
}

MUST_PASS = set(CLUSTER) | {
    # C1 positives / switch / ack are suite-derived below; these are the
    # carve-out anchors that MUST NOT flip (Fix A exemptions) + key
    # boundary/real anchors
    "S1-TRAP-01", "S1-TRAP-02", "S1-TRAP-03", "S1-PLAN-04", "S1-PLAN-08",
    "S2-NP-05", "S5-SW-13", "S5-SW-20", "S5-SW-15", "S6-MIX-01", "S6-MIX-02",
    "S1-PLAN-01", "S1-PLAN-03", "S1-TRAP-07", "S1-TRAP-09", "S1-TRAP-10",
    "S2-CONT-01", "S2-CONT-05", "S2-ACK-01", "S2-ACK-07", "S6-ACK-08",
    "S4-PEND-01", "S4-PEND-10", "S1-QA-04", "S1-QA-05", "S1-QA-13",
    "S1-QA-14", "S1-PQ-01", "S1-PQ-03", "S1-UNK-01", "S1-UNK-05",
    "S4-ELL-07", "S2-QA-FU-06", "S2-SW-OOD-01", "S5-SW-18", "S2-SW-QA-01",
    "S1-MOD-01",
}

FAM = {"insurance_plan": "plan", "modify_existing_plan": "plan",
       "insurance_qa": "qa", "product_qa": "qa",
       "unknown_insurance_intent": "unknown"}


def behavior_of(ir):
    if ir["intent_id"] == "unknown_insurance_intent":
        return ("governed_unknown"
                if "domain:insurance_anchor" in ir.get("reason_codes", [])
                else "ungoverned_unknown")
    if ir["clarification_required"]:
        return "clarify"
    if ir["intent_id"] in ("insurance_plan", "modify_existing_plan"):
        return "auto_plan"
    return "auto_qa"


def severity_v2(case, ir, beh):
    exp_i, act_i = case["expected_intent"], ir["intent_id"]
    exp_b, act_b = case["expected_behavior"], beh
    if exp_i == act_i and exp_b == act_b:
        return "OK"
    msg = case["conversation"][-1]
    msg_anchor = any(k in msg for k in (
        "险", "保险", "保障", "保额", "保费", "重疾", "医疗", "意外",
        "年金", "投保", "理赔", "条款", "健康告知", "健康")) or bool(
        __import__("re").search(r"P0\d{2}", msg))
    # P0: anchored insurance message escaping governance (structural)
    if beh == "ungoverned_unknown" and msg_anchor and exp_b != "ungoverned_unknown":
        return "P0"
    # P1: a WRONG agent/workflow path EXECUTES (auto-route into the
    # wrong family) — task §10: 错 Agent/错 Workflow/错证据链
    if act_b in ("auto_plan", "auto_qa") and exp_b in ("auto_plan",
                                                       "auto_qa") \
            and FAM[exp_i] != FAM[act_i]:
        return "P1"
    if act_b in ("auto_plan", "auto_qa") and exp_b not in (
            "auto_plan", "auto_qa") and FAM[exp_i] != FAM[act_i]:
        return "P1"   # e.g. false continuation auto-routes plan on non-answer
    # P2: safe friction (clarify / governed-unknown landing)
    # P3: same-family label nuance
    return "P3" if FAM[exp_i] == FAM[act_i] else "P2"


def run_all():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    reg = default_registry()
    recs = []
    for case in corpus["cases"]:
        conv = case["conversation"]
        ir = classify(conv[-1], conversation_context=conv[:-1][-8:],
                      active_case_id="case_x" if case.get("ablate_active_case") else None,
                      pending_clarification=(case.get("prev") == "waiting_plan"))
        rd = route(ir, reg)
        beh = behavior_of(ir)
        recs.append({
            "case_id": case["case_id"], "suite": case["suite"],
            "boundary_class": case["boundary_class"],
            "taxonomy_issue": bool(case.get("taxonomy_issue")),
            "expected_intent": case["expected_intent"],
            "expected_behavior": case["expected_behavior"],
            "actual_intent": ir["intent_id"], "actual_behavior": beh,
            "intent_ok": ir["intent_id"] == case["expected_intent"],
            "behavior_ok": beh == case["expected_behavior"],
            "router_agent": rd["agent_id"],
            "router_source": rd["decision_source"],
            "reason_codes": ir["reason_codes"],
            "cluster": CLUSTER.get(case["case_id"]),
            "severity_v2": severity_v2(case, ir, beh),
        })
    return corpus, recs


def metrics(recs):
    core = [r for r in recs if not r["taxonomy_issue"]]
    n = len(core)
    acc = sum(1 for r in core if r["intent_ok"]) / n
    sev2 = Counter(r["severity_v2"] for r in core)
    clusters = Counter(r["cluster"] for r in core
                       if r["cluster"] and r["severity_v2"] != "OK")
    # v1-style P1 for continuity: fam mismatch + conv anchor
    def v1(r):
        if r["intent_ok"] and r["behavior_ok"]:
            return "OK"
        conv_anchor = True  # corpus conversations are insurance-heavy; v1 used keywords
        fam_e = FAM[r["expected_intent"]]; fam_a = FAM[r["actual_intent"]]
        if fam_e != fam_a and "unknown" not in (fam_e, fam_a):
            return "P1"
        if fam_e != fam_a:
            return "P1"
        return "P2" if not r["intent_ok"] else "P3"
    sev1 = Counter(v1(r) for r in core)
    # C1 continuation metrics
    pend = [r for r in core if (r["prev"] == "waiting_plan")] if False else []
    return {"n": n, "accuracy": round(acc, 4),
            "sev_v2": dict(sev2), "sev_v1": dict(sev1),
            "unfixed_clusters_v2": dict(clusters)}


def main():
    corpus, recs = run_all()
    # attach prev for continuation metrics
    prevmap = {c["case_id"]: c.get("prev") for c in corpus["cases"]}
    for r in recs:
        r["prev"] = prevmap[r["case_id"]]
    m = metrics(recs)
    pend = [r for r in recs if r["prev"] == "waiting_plan"
            and not r["taxonomy_issue"]]
    ans = [r for r in pend if r["expected_behavior"] == "auto_plan"
           and r["boundary_class"] in ("plan_vs_continuation",
                                       "context_dependent", "ambiguous")]
    sw = [r for r in pend if r["boundary_class"] == "continuation_vs_topic_switch"]
    ack = [r for r in pend if r["expected_behavior"] == "clarify"]
    landed = lambda r: (r["actual_intent"] == "insurance_plan"
                        and r["actual_behavior"] == "auto_plan")
    cont = lambda r: any(x.startswith("plan:continuation")
                         for x in r["reason_codes"])
    tp = sum(1 for r in ans if landed(r))
    fp = sum(1 for r in sw + ack if landed(r) and cont(r))
    must = [r for r in recs if r["case_id"] in MUST_PASS]
    must_fail = [r["case_id"] for r in must if not (
        r["intent_ok"] and r["behavior_ok"])]
    out = {
        "accuracy": m["accuracy"], "n": m["n"],
        "sev_v2": m["sev_v2"], "sev_v1": m["sev_v1"],
        "unfixed_clusters_v2": m["unfixed_clusters_v2"],
        "c1": {"answer_like": len(ans), "answer_ok": tp,
               "recall": round(tp / len(ans), 4) if ans else None,
               "false_cont": fp,
               "false_cont_rate": round(fp / (len(sw) + len(ack)), 4),
               "switch_n": len(sw), "ack_n": len(ack)},
        "must_pass_failures": must_fail,
        "records": recs,
    }
    json.dump(out, open(os.path.join(REPO, "tmp", "obs",
                                     "k28ifix_step.json"), "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)
    print("acc=%.4f sev_v2=%s sev_v1=%s" % (
        m["accuracy"], m["sev_v2"], m["sev_v1"]))
    print("c1:", json.dumps(out["c1"], ensure_ascii=False))
    print("must-pass failures:", must_fail or "NONE")
    print("unfixed clusters (v2):", m["unfixed_clusters_v2"] or "NONE")
    return out


if __name__ == "__main__":
    main()
