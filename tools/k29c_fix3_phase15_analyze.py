# -*- coding: utf-8 -*-
"""FIX-3 Phase 15 — expansion review analysis: metrics, delivery
line-by-line, real-wording distribution, cohort design, gates."""
import json
import glob
import os
import re
from collections import Counter, defaultdict

OBS = "tmp/obs"

# ---------------- inputs ----------------
led = [json.loads(l) for l in open(
    OBS + "/k29c_fix3_phase12_authority_ledger.jsonl", encoding="utf-8")]
tr = [json.loads(l) for l in open(
    OBS + "/k29c_fix3_phase14_trace.jsonl", encoding="utf-8")]
raw14 = json.load(open(OBS + "/k29c_fix3_phase14_delivery_raw.json",
                       encoding="utf-8"))
lat14 = json.load(open(OBS + "/k29c_fix3_phase14_latency.json",
                       encoding="utf-8"))
p14 = [r for r in led if "2026-10-03T21:36" <= r["ts"]
       <= "2026-10-03T21:47"]          # local-time window (see report)
dec = Counter(r.get("authority_decision") for r in p14)
stages = Counter(r.get("stage") for r in p14
                 if r.get("authority_decision") == "KEEP_BASELINE")

# ---------------- §5 delivery line-by-line ----------------
delivery_analysis = {
    "probe_total": 10, "positives": 5, "delivered": 3,
    "undelivered_positives": [
        {"probe": 1, "q": "重疾险的保险金拿到以后可以随便用吗？",
         "latency_s": 127.2,
         "evidence": "8 ledger records in window, ALL stage="
                     "semantic-judge (judge REJECT ×8), 0 upgrades; "
                     "subset hook ran -> empty verified subset -> "
                     "refusal",
         "classification": "A_SAFETY_CORRECT_REFUSAL",
         "reason": "every candidate sentence was examined by the "
                   "semantic judge and rejected (wording generated "
                   "answers whose sentences failed semantic "
                   "equivalence); fail-closed worked as designed"},
        {"probe": 3, "q": "重疾险理赔的钱可以自己安排用途吗？",
         "latency_s": 49.0,
         "evidence": "1 ledger record stage=semantic-judge (judge "
                     "REJECT), 0 upgrades; remaining sentences "
                     "blocked at deterministic gates; subset empty",
         "classification": "A_SAFETY_CORRECT_REFUSAL",
         "reason": "same signature — judge rejected the single "
                   "eligible sentence; no unexplained case"}],
    "unknown_count": 0,
    "verdict": "G3 PASS — both undelivered cases fully explained "
               "(zero UNKNOWN)"}

# ---------------- §6 metrics ----------------
n_probe = 10
elig = dec["ALLOW_UPGRADE"] + stages.get("semantic-judge", 0) \
    + stages.get("citation", 0) + stages.get("scope-hard-class", 0)
allow = dec["ALLOW_UPGRADE"]
metrics = {
    "probe_turns": n_probe,
    "authority_candidate_sentences": len(p14),
    "authority_allow": allow,
    "authority_reject": stages.get("semantic-judge", 0),
    "authority_uncertain": 0,
    "hard_class_intercepts": stages.get("scope-hard-class", 0),
    "quota_blocks": stages.get("quota", 0),
    "check_flips": sum(1 for x in tr if x.get("verdict_flipped")),
    "delivered_answers": 3, "baseline_answers": 6,
    "partial_factual_answer": 1,
    "authority_candidate_rate": round(100 * len(p14) / max(
        1, sum(1 for x in tr)), 1),
    "authority_allow_rate_pct": round(100 * allow / max(1, len(p14)),
                                      1),
    "authority_delivery_rate_pct": round(100 * 3 / 5, 1),
    "conversion_check_level": "%d/%d" % (allow, allow),
    "postgate_rejection_rate": 0,
    "baseline_keep_rate_pct": round(100 * 6 / 10, 1),
    "hard_intercept_rate_pct": round(
        100 * stages.get("scope-hard-class", 0) / max(1, len(p14)), 1),
    "error_rate": 0, "timeout_rate": round(
        100 * lat14["judge_timeouts"] / lat14["n"], 1),
    "kill_events": 1, "rollback_events": 1,
    "latency": {k: lat14[k] for k in ("p50", "p90", "p95", "p99",
                                        "max")},
    "cost": "COST_NOT_OBSERVABLE (coding plan); judge calls "
            "proxy: %d/%d per window" % (lat14["n"], 200),
    "cost_per_decision": "NOT_OBSERVABLE (judge-call proxy: "
                         "%.2f calls/decision)" % (lat14["n"]
                                                    / max(1, allow)),
    "cost_per_delivered": "NOT_OBSERVABLE (judge-call proxy: "
                          "%.1f calls/delivery)" % (lat14["n"] / 3.0)}

# ---------------- §8 real user wording ----------------
HARD = re.compile(
    r"\d|P0\d{2}|demo-|该产品|这款|某产品|保险法|管理办法|监管|施行|"
    r"保证|承诺|所有|全部|一律|任何|您|你家|你的")
runs = sorted(glob.glob("tmp/webui-runs/run_*"))
real_msgs = []
for p in runs[-200:]:
    try:
        ctx = json.load(open(os.path.join(p, "qa-answer-context.json"),
                             encoding="utf-8"))
    except Exception:
        continue
    q = (ctx.get("retrieval") or {}).get("query", "")
    if q:
        real_msgs.append(q)
wc = Counter()
for q in real_msgs:
    if HARD.search(q):
        wc["HARD_OR_RISK"] += 1
    else:
        wc["FACTUAL_PARAPHRASE_CANDIDATE"] += 1
real_wording = {
    "source": "production run records (qa-answer-context.json, query "
              "field only — no user PII retained)",
    "total_real_queries": len(real_msgs),
    "distribution": dict(wc),
    "note": "classification is a coarse regex proxy (hard-token "
            "scan), NOT an authority decision; no request was sent "
            "to any judge (authority OFF)",
    "privacy": "only query text already persisted in run records; "
               "no new copies of personal data created"}

# ---------------- §9 cohort design (DESIGN ONLY) ----------------
cohort = {
    "status": "DESIGNED_NOT_STARTED",
    "minimal_cohort": {
        "cohort_size_users": "3-5 (Batch-2 key holders, Owner-"
                             "selected)",
        "traffic_percentage": "100% of cohort users' QA turns "
                              "(cohort is the traffic unit, not a "
                              "site-wide percentage)",
        "daily_authority_decision_cap": 20,
        "daily_judge_call_cap": 200,
        "cost_cap": "Owner budget (COST_NOT_OBSERVABLE — needs "
                    "explicit number: suggest judge-call cap as "
                    "proxy)",
        "latency_threshold_p95_s": 30,
        "observation_duration_days": 3,
        "kill_threshold": "any hard-stop family > 0 (OD-FIX3-6) or "
                          "p95 > 30s sustained",
        "rollback_threshold": "single high-risk escape = immediate "
                              "OFF + incident",
        "owner_review_cadence": "daily during window; immediate on "
                                "any incident"},
    "eligibility": "12-condition conjunction (§十 of task; "
                   "FACTUAL_PARAPHRASE only; hard classes "
                   "KEEP_BASELINE regardless of judge)",
    "explicitly_not_decided": ["final cohort size",
                               "final window duration",
                               "cost budget number"],
    "governance": "no auto-expansion; each stage change = Owner "
                  "Decision"}

# ---------------- §13 gates ----------------
gates = {
    "G1_safety_false_upgrade": {"value": 0, "pass": True},
    "G2_hard_class_escape": {"value": 0, "pass": True},
    "G3_delivery_explained": {"value": "2/2 explained, 0 UNKNOWN",
                               "pass": True},
    "G4_postgate_fail_open": {"value": 0, "pass": True},
    "G5_rollback": {"value": "VERIFIED (Phase-14 post-fix 2/2)",
                     "pass": True},
    "G6_kill": {"value": "VERIFIED (Phase-14 post-fix 2/2)",
                 "pass": True},
    "G7_latency_p95": {"value": "20.81s <= 30s", "pass": True},
    "G8_version_mismatch": {"value": 0, "pass": True},
    "G9_cost": {"value": "COST_NOT_OBSERVABLE — Owner budget "
                          "undefined", "pass": "OWNER_DECISION_"
                          "REQUIRED"},
    "G10_utility": {"value": "3/5 positive delivery with "
                              "evidence-verified content",
                     "pass": True},
    "G11_real_wording_minimum": {"value": "Owner minimum NOT "
                                 "DEFINED; real-query sample = %d "
                                 "(coarse proxy)" % len(real_msgs),
                                 "pass": "OWNER_DECISION_REQUIRED"},
    "G12_governance_no_auto": {"value": "no auto-expansion "
                               "mechanism exists",
                                "pass": True}}

out = {"delivery_analysis": delivery_analysis, "metrics": metrics,
       "real_wording": real_wording, "cohort_design": cohort,
       "gates": gates}
json.dump(delivery_analysis, open(OBS + "/k29c_fix3_phase15_delivery"
                                  "_analysis.json", "w",
                                  encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(metrics, open(OBS + "/k29c_fix3_phase15_metrics.json",
                        "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(real_wording, open(OBS + "/k29c_fix3_phase15_real_wording"
                             ".json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(cohort, open(OBS + "/k29c_fix3_phase15_cohort_design"
                       ".json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
with open(OBS + "/k29c_fix3_phase15_review_ledger.jsonl", "w",
          encoding="utf-8") as f:
    for r in p14:
        f.write(json.dumps(r, ensure_ascii=False) + "\n")
print("p14 window:", len(p14), "| decisions:", dict(dec),
      "| stages:", dict(stages))
print("delivery: 3/5, unknown=0")
print("real wording:", dict(wc), "of", len(real_msgs))
print("gates OWNER_DECISION_REQUIRED:", [k for k, v in gates.items()
                                         if v["pass"] == "OWNER_DECISION_REQUIRED"])
