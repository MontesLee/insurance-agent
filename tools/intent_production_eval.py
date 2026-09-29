# -*- coding: utf-8 -*-
"""28.K.28-I Intent Production Readiness evaluator (AUDIT ONLY).

Runs the FROZEN golden corpus (tests/golden/intent-golden-corpus.v1.json)
against the REAL production classifier + router in-process. Zero
production mutation: classify()/route() are pure; nothing is written to
the production shadow ledger. Outputs tmp/obs/k28i_results.json.

Modes:
  main            full corpus, N stability repeats, all metrics
  --ablation      context ablation for S4 (alone / +ctx / +ctx+pending)
  --llm-subset    live LLM-candidate runs on rule-miss subset (separate)
"""
from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.intent.classifier import classify  # noqa: E402
from runtime.router import route  # noqa: E402
from runtime.agent_registry import default_registry  # noqa: E402

CORPUS = os.path.join(REPO, "tests", "golden",
                      "intent-golden-corpus.v1.json")
OUT = os.path.join(REPO, "tmp", "obs", "k28i_results.json")

AGENT_FOR = {"insurance_qa": "insurance-qa-agent",
             "product_qa": "insurance-qa-agent",
             "insurance_plan": "insurance-planning-agent",
             "modify_existing_plan": "insurance-planning-agent",
             "unknown_insurance_intent": "conversation-agent"}


def behavior_of(ir):
    # unknown is ALWAYS clarify=True at the intent layer; the governed/
    # ungoverned distinction is behavioral (server seam), so check it first
    if ir["intent_id"] == "unknown_insurance_intent":
        return ("governed_unknown"
                if "domain:insurance_anchor" in ir.get("reason_codes", [])
                else "ungoverned_unknown")
    if ir["clarification_required"]:
        return "clarify"
    if ir["intent_id"] in ("insurance_plan", "modify_existing_plan"):
        return "auto_plan"
    return "auto_qa"


def run_case(case, pending_override=None, ctx_mode="full", case_ctx=None):
    conv = case["conversation"]
    target = conv[-1]
    if ctx_mode == "alone":
        ctx, pending = [], False
    else:
        ctx = conv[:-1][-8:]
        pending = (case.get("prev") == "waiting_plan"
                   if pending_override is None else pending_override)
    ac = "case_ablate_001" if case.get("ablate_active_case") else None
    ir = classify(target, conversation_context=ctx,
                  active_case_id=ac, pending_clarification=pending)
    rd = route(ir, case_ctx or default_registry())
    return ir, rd


def severity_of(case, ir, actual_behavior, agent_ok):
    exp_b = case["expected_behavior"]
    exp_i = case["expected_intent"]
    act_i = ir["intent_id"]
    if exp_i == act_i and exp_b == actual_behavior and agent_ok:
        return "OK"
    conv_anchor = any(k in "".join(case["conversation"])
                      for k in ("险", "保险", "保障", "保额", "保费", "重疾",
                                "医疗", "意外", "年金", "投保", "理赔", "条款",
                                "健康告知", "健康")) or bool(re.search(
                      r"P0\d{2}", "".join(case["conversation"])))
    # P0: insurance content escaping governance — ONLY when the TARGET
    # MESSAGE itself carries an insurance anchor (message-level anchor
    # structurally forces the governed marker, so this should be
    # impossible: the check PROVES the fail-closed guarantee). A
    # conversation anchor alone (e.g. weather inside a planning chat)
    # must NOT count — ungoverned there is by-design (D7/A4).
    msg_anchor = any(k in case["conversation"][-1]
                     for k in ("险", "保险", "保障", "保额", "保费", "重疾",
                               "医疗", "意外", "年金", "投保", "理赔", "条款",
                               "健康告知", "健康")) or bool(re.search(
                      r"P0\d{2}", case["conversation"][-1]))
    if (actual_behavior == "ungoverned_unknown" and msg_anchor
            and exp_b != "ungoverned_unknown"):
        return "P0"
    if (actual_behavior in ("auto_qa",) and exp_b == "ungoverned_unknown"
            and exp_i == "unknown_insurance_intent"
            and act_i != "unknown_insurance_intent" and not conv_anchor):
        return "P1"  # out-of-domain content auto-routed into insurance chain
    # P1: wrong agent family (qa<->plan<->product workflow divergence)
    fam_exp = ("plan" if exp_i in ("insurance_plan", "modify_existing_plan")
               else "qa" if exp_i in ("insurance_qa", "product_qa")
               else "unknown")
    fam_act = ("plan" if act_i in ("insurance_plan", "modify_existing_plan")
               else "qa" if act_i in ("insurance_qa", "product_qa")
               else "unknown")
    if fam_exp != fam_act and "unknown" not in (fam_exp, fam_act):
        return "P1"
    if fam_exp != fam_act:
        return "P1" if conv_anchor else "P2"
    # same family: behavior-level divergence
    return "P3" if (exp_i != act_i and AGENT_FOR[exp_i] == AGENT_FOR[act_i]
                    ) else "P2"


def root_cause(case, ir):
    exp, act = case["expected_intent"], ir["intent_id"]
    msg = case["conversation"][-1]
    reasons = ir.get("reason_codes", [])
    if exp == act:
        return "OK"
    plan_nouns = ("规划", "配置", "方案", "买保险", "怎么买", "投保", "预算",
                  "保障")
    if exp == "insurance_qa" and act == "insurance_plan":
        return "RULE_PRIORITY" if any(n in msg for n in plan_nouns) \
            else "RULE_GAP"
    if exp == "insurance_plan" and case.get("prev") == "waiting_plan" \
            and act in ("insurance_qa", "product_qa"):
        return "CONTINUATION_GAP"
    if exp == "product_qa" and act == "unknown_insurance_intent":
        return "RULE_GAP" if any(d in msg for d in
                                 ("这个", "那个", "这个呢", "第二", "第一")) \
            else "CONTEXT_MISSING"
    if exp == "unknown_insurance_intent" and act != "unknown_insurance_intent":
        return "RULE_PRIORITY"
    if exp == "insurance_qa" and act == "product_qa":
        return "RULE_PRIORITY"
    if case.get("suite") == "S4":
        return "CONTEXT_UNUSED" if case.get("expected_alone") == act \
            else "CONTEXT_MISSING"
    if "llm" in str(ir.get("confidence_source")):
        return "LLM_CANDIDATE_ERROR"
    return "UNKNOWN"


def prf(matrix, labels):
    rows = {}
    ps, rs, fs = [], [], []
    for lab in labels:
        tp = matrix.get((lab, lab), 0)
        fp = sum(v for (e, a), v in matrix.items() if a == lab and e != lab)
        fn = sum(v for (e, a), v in matrix.items() if e == lab and a != lab)
        p = tp / (tp + fp) if tp + fp else 0.0
        r = tp / (tp + fn) if tp + fn else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        rows[lab] = {"precision": round(p, 4), "recall": round(r, 4),
                     "f1": round(f, 4), "support": tp + fn}
        if tp + fn:
            ps.append(p); rs.append(r); fs.append(f)
    macro = sum(fs) / len(fs) if fs else 0.0
    return rows, round(macro, 4)


def main():
    corpus = json.load(open(CORPUS, encoding="utf-8"))
    cases = corpus["cases"]
    registry = default_registry()
    N = 5  # stability repeats
    records = []
    for case in cases:
        seen = []
        ir = rd = None
        for _ in range(N):
            ir, rd = run_case(case, case_ctx=registry)
            seen.append((ir["intent_id"], behavior_of(ir)))
        stable = len(set(seen)) == 1
        beh = behavior_of(ir)
        agent_ok = True
        route_note = ""
        if case["expected_behavior"] in ("auto_qa", "auto_plan"):
            agent_ok = rd["agent_id"] == AGENT_FOR[case["expected_intent"]] \
                and rd["decision_source"] == "registry_lookup"
        elif case["expected_behavior"] == "clarify":
            agent_ok = rd["agent_id"] == "conversation-agent"
        else:  # unknown family: conversation-agent either way
            agent_ok = rd["agent_id"] == "conversation-agent"
        if not agent_ok:
            route_note = "router=%s src=%s" % (rd["agent_id"],
                                               rd["decision_source"])
        records.append({
            "case_id": case["case_id"], "suite": case["suite"],
            "boundary_class": case["boundary_class"],
            "difficulty": case["difficulty"], "source": case["source"],
            "taxonomy_issue": bool(case.get("taxonomy_issue")),
            "conversation": case["conversation"],
            "prev": case.get("prev"),
            "expected_intent": case["expected_intent"],
            "expected_behavior": case["expected_behavior"],
            "actual_intent": ir["intent_id"],
            "actual_behavior": beh,
            "confidence": ir["confidence"],
            "confidence_source": ir["confidence_source"],
            "reason_codes": ir.get("reason_codes", []),
            "router_agent": rd["agent_id"],
            "router_source": rd["decision_source"],
            "router_ok": agent_ok, "route_note": route_note,
            "intent_ok": ir["intent_id"] == case["expected_intent"],
            "behavior_ok": beh == case["expected_behavior"],
            "severity": severity_of(case, ir, beh, agent_ok),
            "root_cause": root_cause(case, ir),
            "stable": stable,
        })

    def metrics(recs, label):
        core = [r for r in recs if not r["taxonomy_issue"]]
        matrix = Counter((r["expected_intent"], r["actual_intent"])
                         for r in core)
        labels = corpus["taxonomy"]
        total = len(core)
        acc = sum(1 for r in core if r["intent_ok"]) / total if total else 0
        per, macro_f1 = prf(matrix, labels)
        bacc = sum(1 for r in core if r["behavior_ok"]) / total \
            if total else 0
        sev = Counter(r["severity"] for r in core)
        biz = [r for r in core if r["severity"] in ("P0", "P1")]
        unstable = [r["case_id"] for r in core if not r["stable"]]
        bounds = defaultdict(lambda: [0, 0])
        for r in core:
            b = bounds[r["boundary_class"]]
            b[0] += int(r["intent_ok"]); b[1] += 1
        suites = defaultdict(lambda: [0, 0])
        for r in core:
            s = suites[r["suite"]]
            s[0] += int(r["intent_ok"]); s[1] += 1
        # business-impacting: wrong intent AND wrong agent family
        fam = lambda i: ("plan" if i in ("insurance_plan",
                                         "modify_existing_plan")
                         else "qa" if i in ("insurance_qa", "product_qa")
                         else "unknown")
        biz_impacting = [r["case_id"] for r in core
                         if fam(r["expected_intent"]) != fam(
                             r["actual_intent"])]
        return {
            "label": label, "n": total,
            "accuracy": round(acc, 4), "behavior_accuracy": round(bacc, 4),
            "macro_f1": macro_f1, "per_intent": per,
            "severity_counts": dict(sev),
            "business_impacting_rate": round(
                len(biz_impacting) / total, 4) if total else 0,
            "business_impacting_cases": biz_impacting,
            "boundary_accuracy": {k: "%d/%d" % (v[0], v[1])
                                  for k, v in sorted(bounds.items())},
            "suite_accuracy": {k: "%d/%d" % (v[0], v[1])
                               for k, v in sorted(suites.items())},
            "unstable_cases": unstable,
            "confusion": {"%s|%s" % k: v for k, v in sorted(
                matrix.items()) if v},
        }

    core_metrics = metrics(records, "core_no_taxonomy_issue")
    all_metrics = metrics(records, "all")

    # continuation metrics (task §20) over pending corpus
    pend = [r for r in records if r["prev"] == "waiting_plan"]
    answer_like = [r for r in pend
                   if r["expected_behavior"] == "auto_plan"
                   and r["boundary_class"] in ("plan_vs_continuation",
                                               "context_dependent",
                                               "ambiguous")
                   and not r["taxonomy_issue"]]
    switched = [r for r in pend if r["boundary_class"] ==
                "continuation_vs_topic_switch"]
    ack = [r for r in pend if r["expected_behavior"] == "clarify"]
    cont_fired = lambda r: any(x.startswith("plan:continuation")
                               for x in r["reason_codes"])
    # tp = answer-like pending case that LANDS on plan auto-route — the
    # reason PATH (plan:continuation vs a plan-signal in the message,
    # e.g. 预算/保障 content) is secondary and reported separately
    def _landed_plan(r):
        return (r["actual_intent"] == "insurance_plan"
                and r["actual_behavior"] == "auto_plan")
    tp = sum(1 for r in answer_like if _landed_plan(r))
    fp_cont = sum(1 for r in switched + ack
                  if _landed_plan(r) and cont_fired(r))
    cont_prec = tp / (tp + fp_cont) if tp + fp_cont else None
    cont_rec = tp / len(answer_like) if answer_like else None
    false_cont = fp_cont / (len(switched) + len(ack)) if (
        switched + ack) else None
    missed = sum(1 for r in answer_like
                 if not (r["actual_intent"] == "insurance_plan"
                         and r["actual_behavior"] == "auto_plan"))
    missed_rate = missed / len(answer_like) if answer_like else None
    via_cont = sum(1 for r in answer_like if _landed_plan(r) and cont_fired(r))
    via_plansig = [r["case_id"] for r in answer_like
                   if _landed_plan(r) and not cont_fired(r)]
    continuation = {
        "landed_via_continuation_reason": via_cont,
        "landed_via_plan_signal_reason": via_plansig,
        "pending_n": len(pend), "answer_like_n": len(answer_like),
        "switch_n": len(switched), "ack_n": len(ack),
        "continuation_precision": round(cont_prec, 4) if cont_prec is not None else None,
        "continuation_recall": round(cont_rec, 4) if cont_rec is not None else None,
        "false_continuation_rate": round(false_cont, 4) if false_cont is not None else None,
        "missed_continuation_rate": round(missed_rate, 4) if missed_rate is not None else None,
        "false_continuation_cases": [r["case_id"] for r in switched + ack
                                     if r["actual_behavior"] == "auto_plan"
                                     and cont_fired(r)],
        "missed_continuation_cases": [r["case_id"] for r in answer_like
                                      if not (
                                          r["actual_intent"] == "insurance_plan"
                                          and r["actual_behavior"] == "auto_plan")],
    }

    # ablation (S4 cases)
    ablation = []
    for case in cases:
        if case["suite"] != "S4":
            continue
        ir_a, _ = run_case(case, ctx_mode="alone", case_ctx=registry)
        ir_c, _ = run_case(case, ctx_mode="ctx_no_pending",
                           pending_override=False, case_ctx=registry)
        ir_f, _ = run_case(case, case_ctx=registry)
        ablation.append({
            "case_id": case["case_id"],
            "expected": case["expected_intent"],
            "expected_alone": case.get("expected_alone"),
            "alone": {"intent": ir_a["intent_id"],
                      "behavior": behavior_of(ir_a),
                      "conf": ir_a["confidence"]},
            "ctx_only": {"intent": ir_c["intent_id"],
                         "behavior": behavior_of(ir_c)},
            "full": {"intent": ir_f["intent_id"],
                     "behavior": behavior_of(ir_f)},
            "expected_full_ok": ir_f["intent_id"] == case["expected_intent"],
            "expected_alone_ok": (ir_a["intent_id"]
                                  == case.get("expected_alone"))
            if case.get("expected_alone") else None,
        })

    out = {
        "corpus_version": corpus["version"], "n_cases": len(cases),
        "stability_repeats": N,
        "core": core_metrics, "all_incl_taxonomy_issue": all_metrics,
        "continuation": continuation, "ablation": ablation,
        "failures": [r for r in records if r["severity"] != "OK"],
        "taxonomy_issue_cases": [r for r in records
                                 if r["taxonomy_issue"]],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w", encoding="utf-8"), ensure_ascii=False,
              indent=1)
    c = core_metrics
    print("N=%d acc=%.4f beh=%.4f macroF1=%.4f bizRate=%.4f sev=%s" % (
        c["n"], c["accuracy"], c["behavior_accuracy"], c["macro_f1"],
        c["business_impacting_rate"], c["severity_counts"]))
    print("continuation:", json.dumps(
        {k: v for k, v in continuation.items()
         if not k.endswith("cases")}, ensure_ascii=False))
    print("unstable:", c["unstable_cases"])
    print("WROTE", OUT)


if __name__ == "__main__":
    main()
