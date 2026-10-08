# -*- coding: utf-8 -*-
"""FIX-3 Phase 13 — write remaining artifacts."""
import json

OBS = "tmp/obs"

latency = {
  "phase13_reentry": {
    "n": 31, "p50": 10.8, "p90": 18.0, "p95": 22.82, "p99": 24.99,
    "max": 24.99, "timeout_count": 0, "threshold_s": 30.0,
    "kill_fired": False,
    "root_cause_fixed": ("judge wall-cap 25s (long tails collapse to "
                         "KEEP_BASELINE) + per-text memoization "
                         "(5 cache hits / 31 calls)"),
    "phase12_comparison": {"p95": 40.98, "kill_fired": True},
    "verdict": ("p95 22.82s <= 30s WITHIN_THRESHOLD (no kill; wall-cap "
                "verified by max=24.99 cliff)")}}
json.dump(latency, open(OBS + "/k29c_fix3_phase13_latency.json", "w",
                        encoding="utf-8"), ensure_ascii=False, indent=1)

delivery = {
  "check_level": {
    "authority_upgrades": 20, "check_call_flips": 20,
    "production_final_source_at_check": "AUTHORITY_REGEN_RESULT x20",
    "conversion_at_check_level": "20/20 = 100%"},
  "answer_level": {
    "probes": 12, "delivered": 0,
    "conversion_at_answer_level": "0/20 user-visible deliveries",
    "root_cause": ("final delivery requires EVERY sentence to pass the "
      "CITATION gate (ggate). Model answers contain residual uncited "
      "sentences (D-04 limitation). Authority upgraded 20 cited PARTIAL "
      "sentences (flips verified), but whole-answer ggate failures on "
      "OTHER uncited sentences block the final verdict. Authority "
      "cannot upgrade uncited sentences (contract: citation valid).")},
  "remaining_gap": ("verified-subset answer assembly (K.29 design §8 "
    "partial delivery) requires control over the DELIVERED ANSWER "
    "TEXT, which lives inside loop.generate_grounded (SEALED). All "
    "ops-layer seams (csupp/ggate/gctx.refused) either lack the answer "
    "text or cannot alter it."),
  "blocker": ("SEALED_COMPONENT_CHANGE_REQUIRED: "
              "runtime/grounding/loop.py (answer assembly)"),
  "safety_note": ("no safety gate weakened; refusals fail-closed; "
                  "authority re-killed after probe"),
  "verdict": "DELIVERY_CLOSED_AT_CHECK_LEVEL / OPEN_AT_ANSWER_LEVEL"}
json.dump(delivery, open(OBS + "/k29c_fix3_phase13_authority_delivery.json",
                         "w", encoding="utf-8"), ensure_ascii=False,
          indent=1)

raw = json.load(open(OBS + "/k29c_fix3_phase13_reentry_probe_raw.json",
                     encoding="utf-8"))
reentry = {
  "probe": raw,
  "safety": {"negatives_baseline": "6/6",
             "positives_refused_safe": "6/6 (no unsafe delivery)",
             "hard_intercepts": 10, "judge_allow": 20,
             "judge_reject": 16, "errors": 0, "timeouts": 0},
  "post_kill": {"baseline_refused": True, "latency_s": 17.2},
  "verdict": ("SAFE; check-level conversion 20/20; answer-level 0/20 "
               "(see authority_delivery)")}
json.dump(reentry, open(OBS + "/k29c_fix3_phase13_reentry_probe.json",
                        "w", encoding="utf-8"), ensure_ascii=False,
          indent=1)
print("artifacts written")
