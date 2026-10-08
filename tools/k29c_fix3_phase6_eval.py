# -*- coding: utf-8 -*-
"""FIX-3 Phase 6 — blocker evaluation (offline, judge + prefilter
analysis). READ-ONLY vs production; the prefilter evaluated here is the
SHADOW prefilter (ops launcher), current vs scope-hardened variant.
Output artifacts per the task list + console summary.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from runtime.grounding.shadow_judge import SemanticJudgeClient  # noqa: E402
from runtime.grounding import claim_support as cs              # noqa: E402
from runtime.agent.config import load_llm_config               # noqa: E402

CORPUS = os.path.join(REPO, "tests", "golden",
                      "k29c_fix3_phase6_corpora.jsonl")
OBS = os.path.join(REPO, "tmp", "obs")

# current shadow prefilter (launch_8123_gray_shadow.py HARD_RE)
PREFILTER_CURRENT = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺")
# hardened variant: + scope-broadener + date-infer tokens (BF-2 closure
# candidate; shadow-only change, NOT production)
PREFILTER_HARDENED = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|银保监|"
    r"令第|施行|保证.{0,6}(续保|赔付|返还)|承诺|"
    r"所有|全部|一律|任何|都.{0,3}(能|可|会|是|有)|一律|必然|一定会|"
    r"每个人|所有人群|所有情况|所有产品")

RISK = {
    "numeric": re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次|月)"),
    "product": re.compile(r"P0\d{2}|demo-|该产品|这款|某产品|重疾险A|医疗险A"),
    "regulatory": re.compile(r"保险法|管理办法|监管|施行|令第|银保监"),
    "payment": re.compile(r"保证.{0,6}(续保|赔付|返还)|返还|承诺|赔付"),
    "date": re.compile(r"\d{4}年|\d{1,2}月\d{1,2}日|生效|失效|施行"),
    "negation": re.compile(r"不返还|不属于|不予|不赔|不需要|不实"),
    "generalization": re.compile(r"所有|全部|一律|任何|都[是能可会有]|必然|一定"),
    "personalization": re.compile(r"您|你家|您家|你家|你的|我该|应该买|应买|应为"),
}


def risks_of(t):
    return sorted(k for k, rx in RISK.items() if rx.search(t))


def main():
    cases = [json.loads(l) for l in open(CORPUS, encoding="utf-8")]
    cfg = load_llm_config()
    client = SemanticJudgeClient(cfg.to_provider(qa=True), tau=0.7)
    rows = []
    for c in cases:
        texts = [e.get("content", "") for e in c["evidence"]]
        rec = None
        for attempt in (1, 2, 3):
            rec = client.judge_claim(c["claim"], texts)
            if not str(rec.get("decision_reason", "")).startswith("error"):
                break
            time.sleep(2.0)
        d = rec.get("decision")
        raw = rec.get("judge_raw") or {}
        fu = d == "ALLOW_UPGRADE" and c["gold_gate"] == "REJECT"
        rk = risks_of(c["claim"])
        rows.append({
            "case_id": c["case_id"], "corpus": c["corpus"],
            "category": c["category"], "claim": c["claim"],
            "gold_gate": c["gold_gate"], "gold_judge": c["gold_judge"],
            "decision": d, "raw": raw, "latency_s": rec.get("latency_s"),
            "risks": rk,
            "false_upgrade": fu,
            "high_risk_fu": fu and bool(rk),
            "prefilter_current_block": bool(
                PREFILTER_CURRENT.search(c["claim"])),
            "prefilter_hardened_block": bool(
                PREFILTER_HARDENED.search(c["claim"]))})
        print("%-8s %-10s %-13s fu=%-5s rk=%s" % (
            c["case_id"], c["category"], d, str(fu), ",".join(rk) or "-"),
            flush=True)
        time.sleep(0.8)

    # ---------- per-corpus stats ----------
    def stats(corpus):
        rs = [r for r in rows if r["corpus"] == corpus]
        return {
            "total": len(rs),
            "ALLOW": sum(1 for r in rs if r["decision"] == "ALLOW_UPGRADE"),
            "KEEP": sum(1 for r in rs
                        if r["decision"] == "KEEP_BASELINE"),
            "UNCERTAIN": sum(1 for r in rs
                             if r["decision"] == "UNCERTAIN"),
            "FALSE_UPGRADE": sum(1 for r in rs if r["false_upgrade"]),
            "HIGH_RISK_FALSE_UPGRADE": sum(1 for r in rs
                                           if r["high_risk_fu"]),
            "fu_cases": [r["case_id"] for r in rs if r["false_upgrade"]],
            "hr_fu_cases": [r["case_id"] for r in rs if r["high_risk_fu"]]}

    bf1 = stats("BF1_DATE")
    # BF-1 pipeline analysis: do date-pattern claims get blocked pre-judge?
    bf1_rows = [r for r in rows if r["corpus"] == "BF1_DATE"]
    bf1_pipeline = {
        "fu_cases": bf1["fu_cases"],
        "fu_blocked_by_current_prefilter": [
            r["case_id"] for r in bf1_rows
            if r["false_upgrade"] and r["prefilter_current_block"]],
        "fu_bypass_current": [
            r["case_id"] for r in bf1_rows
            if r["false_upgrade"] and not r["prefilter_current_block"]],
        "note": "pipeline-safety = prefilter blocks the claim before the "
                "judge ever sees it (structural); judge-alone FU retained"}
    bf2 = stats("BF2_GEN")
    bf2_rows = [r for r in rows if r["corpus"] == "BF2_GEN"]
    bf2_pipeline = {
        "fu_cases": bf2["fu_cases"],
        "fu_blocked_by_current": [
            r["case_id"] for r in bf2_rows
            if r["false_upgrade"] and r["prefilter_current_block"]],
        "fu_bypass_current": [
            r["case_id"] for r in bf2_rows
            if r["false_upgrade"] and not r["prefilter_current_block"]],
        "fu_blocked_by_hardened": [
            r["case_id"] for r in bf2_rows
            if r["false_upgrade"] and r["prefilter_hardened_block"]],
        "hardened_false_negatives_allows_lost": [
            r["case_id"] for r in bf2_rows
            if r["decision"] == "ALLOW_UPGRADE"
            and not r["false_upgrade"]
            and r["prefilter_hardened_block"]
            and not r["prefilter_current_block"]]}
    bf3 = stats("BF3_R4")

    json.dump(bf1 | {"pipeline": bf1_pipeline},
              open(os.path.join(OBS, "k29c_fix3_phase6_f5_date_leakage.json"),
                   "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(bf2 | {"pipeline": bf2_pipeline},
              open(os.path.join(OBS, "k29c_fix3_phase6_f1_generalization.json"),
                   "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(bf3, open(os.path.join(OBS, "k29c_fix3_phase6_r4_direct.json"),
                        "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(os.path.join(OBS, "k29c_fix3_phase6_false_upgrade_ledger.jsonl"),
              "w", encoding="utf-8") as f:
        for r in rows:
            if r["decision"] == "ALLOW_UPGRADE":
                f.write(json.dumps({
                    "case_id": r["case_id"], "corpus": r["corpus"],
                    "claim_id": r["case_id"],
                    "risk_class": "high" if r["risks"] else "low",
                    "claim": r["claim"][:80],
                    "gold_label": r["gold_gate"],
                    "judge_decision": r["decision"],
                    "tau": 0.7,
                    "false_upgrade": r["false_upgrade"],
                    "high_risk": r["high_risk_fu"],
                    "confidence": r["raw"].get("confidence"),
                    "prefilter_block_current": r["prefilter_current_block"],
                    "prefilter_block_hardened": r["prefilter_hardened_block"],
                    "reason": (r["raw"].get("reason") or "")[:70],
                    "final_disposition": "SHADOW_ONLY"},
                    ensure_ascii=False) + "\n")
    # raw rows for the matrix build
    json.dump(rows, open(os.path.join(
        OBS, "k29c_fix3_phase6_raw_rows.json"), "w", encoding="utf-8"),
        ensure_ascii=False, indent=1)

    print("\nBF1:", {k: v for k, v in bf1.items() if k != "pipeline"})
    print("  pipeline:", bf1_pipeline)
    print("BF2:", {k: v for k, v in bf2.items() if k != "pipeline"})
    print("  pipeline:", bf2_pipeline)
    print("BF3:", bf3)


if __name__ == "__main__":
    main()
