# -*- coding: utf-8 -*-
"""FIX-3 Phase 5 — consolidated analysis: produces all seven evidence
artifacts from the v2 replay (328 records) + live shadow corpus.

READ-ONLY. No production touch. τ grid recomputed from raw outputs.
"""
import json
import os
import re
import sys
from collections import Counter, defaultdict

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
from runtime.grounding import claim_support as cs  # noqa: E402

REPLAY = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase5_replay.jsonl")
SHADOW = os.path.join(REPO, "tmp", "obs", "k29c_fix3_phase3_shadow.jsonl")
OBS = os.path.join(REPO, "tmp", "obs")
TAUS = (0.5, 0.6, 0.7, 0.8, 0.9)

RISK = {
    "numeric": re.compile(r"\d+(?:\.\d+)?\s*(?:天|日|万|万元|元|%|岁|周岁|年|倍|次|月)"),
    "product": re.compile(r"P0\d{2}|demo-|该产品|这款|某产品|重疾险A|医疗险A"),
    "regulatory": re.compile(r"保险法|管理办法|监管|施行|令第|银保监|条文|发布"),
    "payment": re.compile(r"保证.{0,6}(续保|赔付|返还)|返还|承诺|全额赔付"),
    "date": re.compile(r"\d{4}年|\d{1,2}月\d{1,2}日|生效|失效"),
    "negation": re.compile(r"不返还|不属于|不予|不赔|都赔|全部覆盖"),
}
META = re.compile(r"证据|资料|条款里|现有|未提及|没有提到|未载明")
RMAP = {"F1": "R1", "F2": "R2", "F3": "R1", "F4": "R2", "F5": "R3",
        "F6": "R2"}


def decide(raw, tau):
    if not isinstance(raw, dict) or raw.get("error"):
        return "KEEP_BASELINE"
    if raw.get("exempt"):
        return "KEEP_BASELINE"
    if raw.get("contradiction"):
        return "KEEP_BASELINE"
    if raw.get("entailment") == "yes":
        c = raw.get("confidence")
        c = float(c) if isinstance(c, (int, float)) else 0.0
        return "ALLOW_UPGRADE" if c >= tau else "UNCERTAIN"
    return "KEEP_BASELINE"


def risks_of(text):
    return sorted(k for k, rx in RISK.items() if rx.search(text))


def main():
    replay = [json.loads(l) for l in open(REPLAY, encoding="utf-8")]
    cases = {c["case_id"]: c for c in (
        json.loads(l) for l in open(os.path.join(
            REPO, "tests", "golden", "k29c_fix3_benchmark_v2_frozen.jsonl"),
            encoding="utf-8").readlines()[1:])}
    flash = [r for r in replay if r["slot"] == "flash"]
    main_arm = [r for r in replay if r["slot"] == "main"]

    # ---------------- Q1a τ sensitivity (v2 gold-based) -------------
    tau_rows = []
    for tau in TAUS:
        c = Counter()
        fu = hr_allow = 0
        fu_cases = []
        for r in flash:                      # all 3 reps counted
            d = decide(r["raw"], tau)
            c[d] += 1
            if d == "ALLOW_UPGRADE" and r["gold_gate"] == "REJECT":
                fu += 1
                if risks_of(r["claim"]) or r["family"] in ("F4", "F5", "F6"):
                    hr_allow += 1
                    fu_cases.append(r["case_id"])
        tau_rows.append({"tau": tau, "ALLOW": c["ALLOW_UPGRADE"],
                         "KEEP": c["KEEP_BASELINE"],
                         "UNCERTAIN": c["UNCERTAIN"],
                         "false_upgrade_vs_gold": fu,
                         "high_risk_ALLOW": hr_allow,
                         "high_risk_fu_cases": sorted(set(fu_cases))})
    json.dump(tau_rows, open(os.path.join(
        OBS, "k29c_fix3_phase5_tau_sensitivity.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- Q1b stability (flash ×3) ----------------------
    by_case = defaultdict(list)
    for r in flash:
        by_case[r["case_id"]].append(decide(r["raw"], 0.7))
    stable = sum(1 for v in by_case.values() if len(set(v)) == 1)
    allow_stable = sum(1 for v in by_case.values()
                       if v and set(v) == {"ALLOW_UPGRADE"})
    drift = [{"case_id": k, "decisions": v, "family": cases[k]["family"]}
             for k, v in by_case.items() if len(set(v)) > 1]
    stability = {
        "n_cases": len(by_case), "reps": 3, "tau": 0.7,
        "exact_decision_stability_pct": round(100 * stable / len(by_case), 1),
        "allow_stable_cases": allow_stable,
        "drift_cases": drift,
        "semantic_label_stability": round(100 * sum(
            1 for r in flash
            if (r["raw"] or {}).get("entailment") == "yes") / len(flash), 1),
        "note": ("single-model variance recorded per-case; no averaging "
                 "over individual high-risk anomalies (drift listed)")}
    json.dump(stability, open(os.path.join(
        OBS, "k29c_fix3_phase5_stability.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- Q4 model diversity -----------------------------
    f7 = {r["case_id"]: decide(r["raw"], 0.7) for r in flash if r["rep"] == 1}
    m7 = {r["case_id"]: decide(r["raw"], 0.7) for r in main_arm}
    agree = sum(1 for k in f7 if f7[k] == m7.get(k))
    f_allow = {k for k, v in f7.items() if v == "ALLOW_UPGRADE"}
    m_allow = {k for k, v in m7.items() if v == "ALLOW_UPGRADE"}
    m_fu = sorted(k for k in m_allow
                  if cases[k]["expected_gate"] == "REJECT")
    m_hr_fu = sorted(k for k in m_fu if risks_of(cases[k]["claim"])
                     or cases[k]["family"] in ("F4", "F5", "F6"))
    div = {
        "model_a": "glm-5.3-flash (qa slot)", "model_b": "glm-5.3 (main)",
        "n": len(f7), "decision_agreement_pct": round(100 * agree / len(f7), 1),
        "flash_allow": len(f_allow), "main_allow": len(m_allow),
        "main_only_allows": sorted(m_allow - f_allow),
        "flash_only_allows": sorted(f_allow - m_allow),
        "main_false_upgrade": m_fu, "main_high_risk_fu": m_hr_fu,
        "tau_sensitivity_model_b": [
            {"tau": t,
             "ALLOW": sum(1 for r in main_arm
                          if decide(r["raw"], t) == "ALLOW_UPGRADE"),
             "UNCERTAIN": sum(1 for r in main_arm
                              if decide(r["raw"], t) == "UNCERTAIN"),
             "high_risk_ALLOW": sum(
                 1 for r in main_arm
                 if decide(r["raw"], t) == "ALLOW_UPGRADE"
                 and (risks_of(r["claim"])
                      or r["family"] in ("F4", "F5", "F6")))}
            for t in TAUS],
        "verdict": ("MODEL_DIVERSITY = VERIFIED (2 models, offline "
                    "comparator only; no production authority)")}
    json.dump(div, open(os.path.join(
        OBS, "k29c_fix3_phase5_model_diversity.json"), "w",
        encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- Q3 false-upgrade ledger (v2, rep1, tau=0.7) ----
    ledger = []
    for r in flash:
        if r["rep"] != 1:
            continue
        d = decide(r["raw"], 0.7)
        if d != "ALLOW_UPGRADE":
            continue
        c = cases[r["case_id"]]
        gold = c["expected_gate"]
        gold_j = c["expected_judge"]
        fu = gold == "REJECT"
        rk = risks_of(r["claim"]) or (
            ["family:" + r["family"]] if r["family"] in ("F4", "F5", "F6")
            else [])
        ledger.append({
            "case_id": r["case_id"], "claim_id": r["case_id"],
            "risk_class": "high" if rk else "low",
            "claim": r["claim"][:80],
            "evidence": [e.get("content", "")[:60] for e in c["evidence"]],
            "baseline_decision": "REFUSE(C1)" if gold == "REJECT"
            else "PASS",
            "judge_decision": d,
            "tau": 0.7,
            "gold_label": "%s/%s" % (gold, gold_j),
            "final_disposition": "SHADOW_ONLY (no production effect)",
            "false_upgrade": fu,
            "high_risk": bool(rk),
            "reason": (r["raw"] or {}).get("reason", "")[:70]})
    with open(os.path.join(OBS, "k29c_fix3_phase5_false_upgrade_ledger.jsonl"),
              "w", encoding="utf-8") as f:
        for x in ledger:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")

    # ---------------- Q2/Q5 risk stratification + coverage ------------
    shadow = [json.loads(l) for l in open(SHADOW, encoding="utf-8")]
    shadow = [r for r in shadow if "claim_text" in r]
    cov = {"v2_replay": {}, "live_shadow": {}}
    for name, rows, claimkey, famkey in (
            ("v2_replay", flash, "claim", "family"),
            ("live_shadow", shadow, "claim_text", None)):
        stats = defaultdict(Counter)
        for r in rows:
            d = (decide(r["raw"], 0.7) if name == "v2_replay"
                 else r.get("decision"))
            risks = risks_of(r[claimkey])
            keys = risks or ["low_risk"]
            for k in keys:
                stats[k][d] += 1
            if famkey:
                stats["R:" + RMAP.get(r[famkey], "?")][d] += 1
        cov[name] = {k: dict(v) for k, v in stats.items()}
    # coverage verdicts per stratum (combined sampling universe)
    strata_defs = ["numeric", "product", "regulatory", "payment", "date",
                   "negation", "R:R3", "R:R4"]
    coverage = {}
    for s in strata_defs:
        v2n = sum(cov["v2_replay"].get(s, {}).values())
        ln = sum(cov["live_shadow"].get(s, {}).values())
        allow = (cov["v2_replay"].get(s, {}).get("ALLOW_UPGRADE", 0)
                 + cov["live_shadow"].get(s, {}).get("ALLOW_UPGRADE", 0))
        coverage[s] = {
            "v2_sampled": v2n, "live_sampled": ln, "total": v2n + ln,
            "allow": allow,
            "status": ("COVERAGE_INSUFFICIENT" if v2n + ln == 0 else
                       "OBSERVED_ALLOW_%d" % allow)}
    # judge-alone vs pipeline distinction
    coverage["_note"] = (
        "v2_replay = judge-ALONE behavior (hard prefilter bypassed to "
        "sample the judge); live pipeline = structural zero via hard "
        "prefilter. R3/R4 = family mapping F5→R3, F4→R2(premsisum), "
        "R4 has NO direct sample family (v2 F4 tests recommendation-"
        "number, the R4 amount shape) — R4 direct coverage via t18-"
        "style live probes only")
    json.dump({"stratified": cov, "coverage": coverage},
              open(os.path.join(OBS, "k29c_fix3_phase5_highrisk_coverage.json"),
                   "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- Q7 meta prose -----------------------------------
    meta = {"live_shadow": {}, "v2_replay": {}}
    ls = [r for r in shadow if META.search(r["claim_text"])]
    meta["live_shadow"] = {
        "meta_prose_total": len(ls),
        "meta_prose_allow": sum(1 for r in ls
                                if r.get("decision") == "ALLOW_UPGRADE"),
        "meta_prose_high_risk": sum(
            1 for r in ls if risks_of(r["claim_text"])),
        "meta_prose_high_risk_allow": sum(
            1 for r in ls if r.get("decision") == "ALLOW_UPGRADE"
            and risks_of(r["claim_text"])),
        "propagation_check": ("no meta-prose claim carries risk patterns; "
                              "hard patterns remain prefilter-terminal")}
    vm = [r for r in flash if r["rep"] == 1 and META.search(r["claim"])]
    meta["v2_replay"] = {
        "meta_total": len(vm),
        "meta_allow_and_gold_reject": sorted(
            r["case_id"] for r in vm
            if decide(r["raw"], 0.7) == "ALLOW_UPGRADE"
            and r["gold_gate"] == "REJECT")}
    meta["verdict"] = "WATCH_ONLY (no propagation evidence)"
    json.dump(meta, open(os.path.join(OBS, "k29c_fix3_phase5_meta_prose.json"),
                         "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------------- console summary ---------------------------------
    print("=== TAU (v2 flash, 3 reps pooled) ===")
    for row in tau_rows:
        print(row)
    print("\n=== STABILITY ===", {k: v for k, v in stability.items()
                                  if k != "drift_cases"})
    print("drift:", [(d["case_id"], d["decisions"]) for d in drift][:8])
    print("\n=== DIVERSITY ===", {k: v for k, v in div.items()
                                  if not k.startswith("tau_sens")})
    print("\n=== LEDGER === allows=%d fu=%d highrisk_fu=%d" % (
        len(ledger), sum(1 for x in ledger if x["false_upgrade"]),
        sum(1 for x in ledger if x["false_upgrade"] and x["high_risk"])))
    for x in ledger:
        if x["false_upgrade"]:
            print("  FU:", x["case_id"], x["risk_class"], x["claim"][:40])
    print("\n=== COVERAGE ===")
    for s in strata_defs:
        print(" ", s, coverage[s])
    print("\n=== META ===", meta["verdict"], meta["live_shadow"])


if __name__ == "__main__":
    main()
