# -*- coding: utf-8 -*-
"""K.29-C FIX-3 Phase 4 — Semantic Judge S0 offline evaluator.

OFFLINE ONLY: never imported by runtime, never gates anything.
Implements the shadow design (k29c-semantic-shadow-design.md):

  claim -> [deterministic hard filter spec] -> semantic judge -> decision

Decision vocabulary: ALLOW_UPGRADE / KEEP_BASELINE / UNCERTAIN.
Any error/timeout/unparseable/low-confidence => KEEP_BASELINE (INV-2).

Evaluation targets: false-upgrade focus.
  FALSE UPGRADE := baseline(C1) = REFUSE  ∧  judge = ALLOW_UPGRADE
                   ∧ gold = REJECT
Measured on the frozen v2 corpus (+ 3x stability on a subset).

Output: tmp/obs/k29c_fix3_semantic_judge_s0.json
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
sys.path.insert(0, os.path.join(REPO, "tools"))

from k29c_fix3_simulation import case_pass, clause_verdicts  # noqa: E402

V2 = os.path.join(REPO, "tests", "golden", "k29c_fix3_benchmark_v2_frozen.jsonl")
OUT = os.path.join(REPO, "tmp", "obs", "k29c_fix3_semantic_judge_s0.json")
TAU = 0.7          # confidence threshold (initial; Owner freezes later)
STABILITY_N = 20   # 3x repeat subset

JUDGE_SYS = """You are a strict insurance-claim evidence judge. Given ONE claim and its evidence text(s), decide:
1. entailment: "yes" only if the evidence FULLY entails the claim as stated; "partial" if only part; "no" if not.
2. contradiction: true if the evidence explicitly denies what the claim asserts (negation flip, opposite value/direction/scope).
3. exempt: true ONLY for pure procedural guidance / methodology / an honest statement that evidence does not mention something (no checkable insurance fact, no number, no product fact).
4. confidence: your confidence 0.0-1.0.
Watch scope words (所有/全部/一律/任何/都), units (万/元/倍/%), numbers, product identities, and condition qualifiers (等待期内/仅/除外). Output STRICT JSON only:
{"entailment":"yes|partial|no","contradiction":true|false,"exempt":true|false,"confidence":0.0,"reason":"<short>"}"""


def call_judge(claim, evidence, provider):
    ev_txt = "\n\n".join("证据%d：%s" % (i + 1, e.get("content", ""))
                         for i, e in enumerate(evidence)) or "（无证据）"
    msgs = [{"role": "system", "content": JUDGE_SYS},
            {"role": "user", "content": "断言：%s\n\n%s" % (claim, ev_txt)}]
    r = provider.generate(msgs, [])
    txt = (getattr(r, "text", "") or "").strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        return {"error": "unparseable"}
    try:
        d = json.loads(m.group(0))
        if not isinstance(d.get("confidence"), (int, float)):
            return {"error": "no-confidence"}
        return d
    except Exception:
        return {"error": "unparseable"}


def decide(d):
    """Map judge JSON -> ALLOW_UPGRADE / KEEP_BASELINE / UNCERTAIN.
    Errors collapse to KEEP_BASELINE (INV-2)."""
    if d.get("error"):
        return "KEEP_BASELINE", "error"
    if d.get("exempt"):
        return "KEEP_BASELINE", "exempt-not-upgradable"
    if d.get("contradiction"):
        return "KEEP_BASELINE", "contradiction"
    if d.get("entailment") == "yes" and float(d["confidence"]) >= TAU:
        return "ALLOW_UPGRADE", "entailed"
    if d.get("entailment") == "yes":
        return "UNCERTAIN", "low-confidence"
    return "KEEP_BASELINE", "not-entailed"


def risk_class(c):
    f = set(c.get("high_risk_flags", []))
    txt = c["claim"]
    out = set()
    if "number" in f or re.search(r"\d", txt):
        out.add("numeric")
    if "product" in f or re.search(r"P0\d|demo-|该产品|这款|某产品", txt):
        out.add("product")
    if "regulatory" in f or re.search(r"保险法|管理办法|监管|施行|令第", txt):
        out.add("regulatory")
    if "payout_promise" in f or re.search(r"续保|返还|赔付|承诺", txt):
        out.add("payout")
    return out


def main():
    from runtime.agent.config import load_llm_config
    cfg = load_llm_config()
    prov = cfg.to_provider(qa=True)        # glm-5.3-flash judge
    cases = [json.loads(l) for l in open(V2, encoding="utf-8").readlines()[1:]]

    retries = 0
    rows = []
    latencies = []
    for c in cases:
        d = None
        for attempt in (1, 2, 3):          # retry policy <=2
            t0 = time.time()
            d = call_judge(c["claim"], c["evidence"], prov)
            latencies.append(round(time.time() - t0, 1))
            if not d.get("error"):
                break
            retries += 1
            time.sleep(2.0)
        dec, why = decide(d)
        # baseline (C1) outcome for THIS case from the Phase-3 sim
        vs = clause_verdicts(c["claim"], c["evidence"])
        base_pass = case_pass("C1", c["claim"], c["evidence"], vs)
        gold = c["expected_gate"]
        rows.append({
            "case_id": c["case_id"], "family": c["family"],
            "gold": gold, "baseline_C1_pass": base_pass,
            "judge_decision": dec, "judge_why": why,
            "judge_raw": d, "risk": sorted(risk_class(c)),
            "latency_s": latencies[-1]})
        print("%-6s fam=%s gold=%-6s C1=%-5s judge=%-13s (%s)" % (
            c["case_id"], c["family"], gold, base_pass, dec, why),
            flush=True)
        time.sleep(1.0)

    # ---- metrics ----
    def m(sel):
        return sum(1 for r in rows if sel(r))

    false_upgrade = [r for r in rows if not r["baseline_C1_pass"]
                     and r["judge_decision"] == "ALLOW_UPGRADE"
                     and r["gold"] == "REJECT"]
    fu_high = [r for r in false_upgrade if r["risk"]]
    upgrades = [r for r in rows if r["judge_decision"] == "ALLOW_UPGRADE"]
    correct_upgrade = [r for r in upgrades if r["gold"] == "ACCEPT"]
    # judge accuracy on its own labels (vs expected_judge where defined)
    acc = sum(1 for r in rows if (
        (r["judge_raw"].get("contradiction") and
         r["family"] in ("F2",)) or
        (r["judge_raw"].get("entailment") == "yes" and
         r["gold"] == "ACCEPT"))) if rows else 0
    metrics = {
        "n": len(rows), "tau": TAU, "retries": retries,
        "decisions": dict(Counter(r["judge_decision"] for r in rows)),
        "upgrades": len(upgrades),
        "correct_upgrades_gold_ACCEPT": len(correct_upgrade),
        "FALSE_UPGRADE": len(false_upgrade),
        "false_upgrade_cases": [r["case_id"] for r in false_upgrade],
        "HIGH_RISK_FALSE_UPGRADE": len(fu_high),
        "high_risk_fu_cases": [r["case_id"] for r in fu_high],
        "fu_by_risk": dict(Counter(
            x for r in false_upgrade for x in r["risk"])),
        "contradiction_detected_F2": sum(
            1 for r in rows if r["family"] == "F2"
            and r["judge_raw"].get("contradiction")),
        "F2_total": sum(1 for r in rows if r["family"] == "F2"),
        "uncertain_rate_pct": round(100 * m(
            lambda r: r["judge_decision"] == "UNCERTAIN") / len(rows), 1),
        "latency_med_s": sorted(latencies)[len(latencies) // 2],
        "latency_max_s": max(latencies),
        "approx_calls": len(rows) + retries}

    # ---- stability subset (3x) ----
    stab_rows = rows[:STABILITY_N]
    stable = 0
    for r in stab_rows:
        decs = [r["judge_decision"]]
        for _ in range(2):
            d = None
            for attempt in (1, 2, 3):
                d = call_judge(
                    next(c["claim"] for c in cases
                         if c["case_id"] == r["case_id"]),
                    next(c["evidence"] for c in cases
                         if c["case_id"] == r["case_id"]), prov)
                if not d.get("error"):
                    break
                retries += 1
                time.sleep(2.0)
            decs.append(decide(d)[0])
            time.sleep(1.0)
        r["stability_decs"] = decs
        if len(set(decs)) == 1:
            stable += 1
    metrics["stability_subset_n"] = len(stab_rows)
    metrics["stability_consistent"] = stable
    metrics["stability_rate_pct"] = round(100 * stable / len(stab_rows), 1)
    metrics["approx_calls"] += 2 * len(stab_rows)

    out = {"ts": "2026-10-02", "judge_model": "glm-5.3-flash (qa slot)",
           "tau": TAU, "metrics": metrics, "rows": rows}
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\nMETRICS:", json.dumps(
        {k: v for k, v in metrics.items()}, ensure_ascii=False, indent=1))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
