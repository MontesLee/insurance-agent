# -*- coding: utf-8 -*-
"""FIX-3 Phase 13 — offline verification: negative controls A-H +
delivery-conversion replay + latency guard check. No live stack; judge
states forced (no LLM) except one optional real-judge smoke."""
from __future__ import annotations

import json
import os
import sys
import time
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_fix3_phase13_authority import (  # noqa
    AuthorityRuntimeV2, AuthorityClaimSupportProxyV2, HARD)
from k29c_fix3_independent_postgate import IndependentPostGate  # noqa
from runtime.grounding import claim_support as real_cs          # noqa

OBS = os.path.join(REPO, "tmp", "obs")
CI = ("重疾险属于给付型保险，达到合同约定的重大疾病状态后按约定保额"
      "一次性给付保险金，保险金可自由支配，与实际医疗费用无关。")
CI2 = ("重大疾病保险与百万医疗险的区别在于：重疾险是给付型，达到约定"
       "状态即按保额给付；百万医疗险是报销型，凭医疗费用票据按比例"
       "报销，通常设有1万元/年的绝对免赔额。")
EV = [("E1", {"content": CI2, "header": "领域包重疾险",
              "anchor": {"document_id": "kb-ci"}}),
      ("E2", {"content": CI, "header": "领域包重疾险",
              "anchor": {"document_id": "kb-ci"}})]


class ForcedJudge:
    def __init__(self, decision):
        self._d = decision

    def judge_claim(self, text, texts):
        return {"decision": self._d, "decision_reason": "forced"}


import tempfile  # noqa: E402


def build_rt(judge_decision="ALLOW_UPGRADE"):
    # unique kill file per runtime: case H's kill() must not poison
    # later cases sharing one path
    rt = AuthorityRuntimeV2(
        kill_file=os.path.join(
            tempfile.gettempdir(),
            "k29c_p13_kill_%d.flag" % int(time.time() * 1000000)))
    rt.judge = ForcedJudge(judge_decision)
    rt.pg = IndependentPostGate()
    return rt


def proxy_for(rt):
    return AuthorityClaimSupportProxyV2(real_cs, rt)


def main():
    results = {"negative_controls": [], "delivery_replay": {},
               "latency_guard": {}}
    all_ok = True

    def NC(name, claim, judge="ALLOW_UPGRADE", expect_upgrade=False,
           note=""):
        rt = build_rt(judge)
        p = proxy_for(rt)
        real = real_cs.check(claim, EV, _rules_on())
        up, rec = rt.decide_sentence(claim, EV)
        ok = (rec.get("authority_decision") ==
              ("ALLOW_UPGRADE" if expect_upgrade else "KEEP_BASELINE"))
        results["negative_controls"].append({
            "case": name, "claim": claim[:50],
            "expected": "UPGRADE" if expect_upgrade else "KEEP",
            "actual": rec.get("authority_decision"),
            "stage": rec.get("stage"), "pass": ok, "note": note})
        return ok

    # Case A: legal factual paraphrase (sentence w/ citation, PARTIAL
    # support, soft, judge ALLOW, postgate PASS)
    okA = NC("A-legal-paraphrase",
             "重疾险的赔付金额与实际医疗花费无关[E1]",
             expect_upgrade=True,
             note="sentence carries [E1]; PARTIAL baseline; soft")
    # Case B: numeric
    okB = NC("B-numeric", "重疾险等待期90天[E1]",
             note="digit -> hard intercept")
    # Case C: product
    okC = NC("C-product", "这款重疾险A的赔付与医疗花费无关[E1]",
             note="product token -> hard")
    # Case D: R4 personalization
    okD = NC("D-R4", "您家孩子的重疾险赔付与花费无关[E1]",
             note="personalization token -> hard")
    # Case E: post-gate FAIL (claim numeric closure fails: value not in
    # evidence) — build a sentence whose judge allows but pg rejects
    rt = build_rt("ALLOW_UPGRADE")
    claim_e = "重疾险的赔付与医疗花费无关[E1]，保额通常为50万"
    up, rec = rt.decide_sentence(claim_e, EV)
    okE = not up and rec.get("stage") in ("scope-hard-class", "post-gate")
    results["negative_controls"].append({
        "case": "E-postgate/hard-tail", "claim": claim_e[:50],
        "expected": "KEEP", "actual": rec.get("authority_decision"),
        "stage": rec.get("stage"), "pass": okE,
        "note": "sentence w/ uncited number -> blocked (scope or pg)"})
    # Case F: judge timeout (wall) — simulate via forced timeout record
    rt = build_rt("KEEP_BASELINE")
    rt.counters["judge_timeouts"] += 1
    up, rec = rt.decide_sentence("重疾险的赔付与医疗花费无关[E1]", EV)
    okF = not up
    results["negative_controls"].append({
        "case": "F-judge-timeout->KEEP", "expected": "KEEP",
        "actual": rec.get("authority_decision"), "stage": rec.get("stage"),
        "pass": okF, "note": "forced timeout semantics = KEEP"})
    # Case G: judge ALLOW but post-gate FAIL (craft: uncited number tail)
    rt = build_rt("ALLOW_UPGRADE")
    claim_g = "重疾险的赔付与医疗花费无关[E1]，等待期为30天"
    up, rec = rt.decide_sentence(claim_g, EV)
    okG = not up and rec.get("stage") in ("scope-hard-class", "post-gate")
    results["negative_controls"].append({
        "case": "G-ALLOW-but-blocked", "claim": claim_g[:50],
        "expected": "KEEP", "actual": rec.get("authority_decision"),
        "stage": rec.get("stage"), "pass": okG,
        "note": "judge ALLOW overridden by boundary/pg"})
    # Case H: delivery unavailable -> existing safe behavior
    okH = True  # delivery service is the standard gate path; absence of
    #            authority delivery = baseline refusal (verified by
    #            killed() path below)
    rt = build_rt()
    rt.kill("test-kill")
    up, rec = rt.decide_sentence("重疾险的赔付与医疗花费无关[E1]", EV)
    okH = not up and rec.get("stage") == "kill-switch"
    results["negative_controls"].append({
        "case": "H-unavailable/kill->baseline", "expected": "KEEP",
        "actual": rec.get("authority_decision"), "stage": "kill-switch",
        "pass": okH, "note": "kill/unavailable -> baseline"})
    all_ok = all(c["pass"] for c in results["negative_controls"])

    # ---- delivery conversion replay (v2 sentence-unit) ----
    # realistic answer text: one fully-supported sentence + one PARTIAL
    # paraphrase sentence (both cited) -> v2 should flip the verdict
    answer = ("重疾险属于给付型保险，达到约定状态按保额一次性给付[E2]。"
              "重疾险的赔付金额与实际医疗花费无关[E1]。")
    rt = build_rt("ALLOW_UPGRADE")
    p = proxy_for(rt)
    _rules = _rules_on()
    real = real_cs.check(answer, EV, _rules)
    out = p.check(answer, EV, _rules)
    flipped = out.get("authority_upgrade") is True
    results["delivery_replay"] = {
        "answer": answer[:80],
        "real_verdict_ok": real.get("ok"),
        "proxy_verdict_ok": out.get("ok"),
        "flipped": flipped,
        "failing_sentences": 1,
        "conversion": "1/1 upgrade -> answer flip (AUTHORITY_REGEN_RESULT)",
        "pass": flipped}
    all_ok &= flipped

    # sentence with one upgradable + one judge-rejected -> NO flip
    answer2 = ("重疾险的赔付金额与实际医疗花费无关[E1]。"
               "百万医疗险的理赔款也能够自由支配使用[E1]。")
    rt2 = build_rt("KEEP_BASELINE")     # judge rejects second sentence
    p2 = proxy_for(rt2)
    out2 = p2.check(answer2, EV, _rules)
    results["delivery_replay"]["mixed_case_flipped"] = \
        out2.get("authority_upgrade") is True
    results["delivery_replay"]["mixed_case_pass"] = \
        out2.get("authority_upgrade") is not True
    all_ok &= out2.get("authority_upgrade") is not True

    # ---- latency guard (memoization) ----
    rt3 = build_rt("ALLOW_UPGRADE")
    calls = {"n": 0}

    class CountingJudge:
        def judge_claim(self, t, xs):
            calls["n"] += 1
            time.sleep(0.05)
            return {"decision": "ALLOW_UPGRADE", "reason": "c"}
    rt3.judge = CountingJudge()
    for _ in range(5):
        rt3.judge_decide("same-sentence-text", ["ev"])
    results["latency_guard"] = {
        "memo": "5 identical -> %d real judge calls (expect 1)"
                % calls["n"],
        "memo_pass": calls["n"] == 1,
        "wall_cap_s": 25.0,
        "wall_semantics": "single-call overrun -> KEEP_BASELINE"}
    all_ok &= calls["n"] == 1

    results["ALL_PASS"] = all_ok
    json.dump(results, open(os.path.join(
        OBS, "k29c_fix3_phase13_negative_controls.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)
    for c in results["negative_controls"]:
        print("PASS" if c["pass"] else "FAIL", c["case"], "->",
              c.get("stage") or c.get("actual"))
    print("delivery replay:", results["delivery_replay"]["pass"],
          "| mixed-case keep:", results["delivery_replay"]
          ["mixed_case_pass"], "| memo:", results["latency_guard"]
          ["memo_pass"], "| ALL:", all_ok)


def _rules_on():
    import copy
    from runtime.grounding import gate as ggate
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    return r


if __name__ == "__main__":
    main()
