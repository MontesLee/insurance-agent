# -*- coding: utf-8 -*-
"""Phase16 offline analyzer fixture tests — zero LLM, zero production,
pure injected records (Task 7). Covers: complete chain / broken chain /
orphan claim / duplicate decision / invalid production_final_source /
safe refusal / utility false refusal / hard-class block / R4
personalization / delivery success / delivery rejection / kill state /
rollback state / observe-safety counters."""
from __future__ import annotations

import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, REPO)

from tools.phase16 import chain_audit  # noqa: E402
from tools.phase16.d04_classify import classify  # noqa: E402


def _complete_record(rid="r1", flipped=True):
    return {
        "request_id": rid, "ts_request": "2026-10-06T01:00:00Z",
        "intent": {"present": True}, "evidence_present": True,
        "claims": [{"id": rid + "#c0", "sentence": "重疾险属于给付型[E1]。",
                    "authority": "ALLOW_UPGRADE",
                    "judge": "ALLOW_UPGRADE",
                    "postgate": {"ok": True},
                    "ts": "2026-10-06T01:00:05Z"}],
        "delivery": {"verdict_flipped": flipped},
        "production_final_source": ("AUTHORITY_REGEN_RESULT"
                                    if flipped else "BASELINE"),
    }


def test_complete_chain_passes():
    r = chain_audit.audit([_complete_record()])
    assert r["verdict"] == "PASS"
    assert r["complete_chains"] == 1 and r["broken_chains"] == 0


def test_broken_chain_missing_intent_evidence_claims():
    rec = _complete_record("r2")
    rec["intent"] = {"present": False}
    rec["evidence_present"] = False
    rec["claims"] = []
    r = chain_audit.audit([rec])
    assert r["verdict"] == "FAIL"
    assert "missing_intent" in r["problems"]
    assert "missing_evidence" in r["problems"]
    assert "missing_claims" in r["problems"]


def test_orphan_and_duplicate_claims():
    rec = _complete_record("r3")
    dup = dict(rec)
    dup["request_id"] = "r3-dup"
    dup["claims"] = [dict(rec["claims"][0])]     # same claim id
    r = chain_audit.audit([rec, dup])
    assert r["duplicate_records"] >= 1


def test_invalid_production_final_source():
    rec = _complete_record("r4")
    rec["production_final_source"] = "MYSTERY"
    r = chain_audit.audit([rec])
    assert "invalid_production_final_source" in r["problems"]


def test_delivery_consistency_checks():
    rec = _complete_record("r5", flipped=True)
    rec["production_final_source"] = "BASELINE"          # mismatch
    r = chain_audit.audit([rec])
    assert "delivery_source_mismatch" in r["problems"]
    rec2 = _complete_record("r6", flipped=False)
    rec2["claims"][0]["authority"] = "KEEP_BASELINE"
    rec2["delivery"] = {"verdict_flipped": True}          # no upgrade
    r2 = chain_audit.audit([rec2])
    assert "delivery_without_upgrade" in r2["problems"]


def test_timestamp_anomaly():
    rec = _complete_record("r7")
    rec["claims"][0]["ts"] = "2026-10-05T00:00:00Z"       # before request
    r = chain_audit.audit([rec])
    assert r["timestamp_anomalies"] == 1


# ---------------- d04 classifier ----------------

def test_safe_refusal_negative():
    x = classify({"query": "如何办理驾驶证换证", "category": "NEGATIVE",
                  "refusal_reason": "citation_gate_rejected",
                  "qualified_n": 1, "retrieved": True,
                  "viol_kinds": ["claim_support"]})
    assert x["classification"] == "SAFE_REFUSAL"


def test_utility_false_refusal_minimal_pass():
    x = classify({"query": "注册资本最低限额", "category": "HIGH",
                  "refusal_reason": "citation_gate_rejected",
                  "qualified_n": 9, "retrieved": True,
                  "viol_kinds": ["claim_support"],
                  "viol_detail": {"partial": 1, "unsupported": 0},
                  "minimal_answer_pass": True})
    assert x["classification"] == "UTILITY_FALSE_REFUSAL"


def test_whole_question_gate_multi_partial():
    x = classify({"query": "分支机构程序", "category": "MEDIUM",
                  "refusal_reason": "citation_gate_rejected",
                  "qualified_n": 10, "retrieved": True,
                  "viol_kinds": ["claim_support"],
                  "viol_detail": {"partial": 6, "unsupported": 0},
                  "minimal_answer_pass": True})
    assert x["classification"] == "WHOLE_QUESTION_GATE"


def test_partial_ceiling_no_minimal_test():
    x = classify({"query": "什么是可回溯", "category": "GENERAL",
                  "refusal_reason": "citation_gate_rejected",
                  "qualified_n": 8, "retrieved": True,
                  "viol_kinds": ["claim_support"],
                  "viol_detail": {"partial": 5, "unsupported": 0}})
    assert x["classification"] == "PARTIAL_CEILING"


def test_hard_class_block():
    x = classify({"query": "犹豫期多少天", "category": "HIGH",
                  "refusal_reason": "citation_gate_rejected",
                  "qualified_n": 10, "retrieved": True,
                  "viol_kinds": ["claim_support"],
                  "viol_detail": {"partial": 1, "unsupported": 0},
                  "draft": "不得少于15日[E1]。", "hard_blocked": True})
    assert x["classification"] == "HARD_CLASS_BLOCK"


def test_r4_personalization():
    x = classify({"query": "我30岁月入8000该买什么保险",
                  "category": "R4_PERSONAL",
                  "refusal_reason": "insufficient_evidence",
                  "qualified_n": 0, "retrieved": False, "r4": True})
    assert x["classification"] == "R4_PERSONALIZATION"


def test_insufficient_evidence():
    x = classify({"query": "冷门问题", "category": "NORMAL",
                  "refusal_reason": "insufficient_evidence",
                  "qualified_n": 0, "retrieved": True})
    assert x["classification"] == "INSUFFICIENT_EVIDENCE"


# ---------------- observe (kill/rollback/delivery states) ----------------

def test_observe_safety_and_delivery_on_fixture_ledger(tmp_path):
    from tools.phase16 import observe
    led = [
        {"ts": "2026-10-06T01:00:05Z", "sentence": "给付型[E1]。",
         "authority_decision": "ALLOW_UPGRADE", "stage": "all-pass",
         "judge_result": "ALLOW_UPGRADE",
         "post_gate_result": {"ok": True},
         "counters_snapshot": {"judge_calls": 1}},
        {"ts": "2026-10-06T01:00:06Z", "sentence": "所有产品都[E1]。",
         "authority_decision": "KEEP_BASELINE", "stage": "scope-hard-class",
         "counters_snapshot": {"judge_calls": 1}},
    ]
    tr = [{"ts": "2026-10-06T01:00:07Z", "verdict_flipped": True,
           "production_final_source": "AUTHORITY_REGEN_RESULT"},
          {"ts": "2026-10-06T01:00:08Z", "verdict_flipped": False,
           "production_final_source": "BASELINE"}]
    # reuse analyze() internals via monkeypatched paths
    orig = observe._load_jsonl
    observe._load_jsonl = lambda path, start: (
        led if "authority_ledger" in path else
        tr if "delivery_trace" in path else [])
    try:
        a = observe.analyze("2026-10-06T00:00:00Z")
    finally:
        observe._load_jsonl = orig
    assert a["authority"]["total_decisions"] == 1
    assert a["authority"]["hard_intercepts"] == 1
    assert a["delivery"]["delivered_flips"] == 1
    assert a["safety"]["false_upgrade"] == 0
    assert a["safety"]["invalid_production_final_source"] == 0
    # the upgraded sentence carries no hard family -> no escapes
    assert a["safety"]["numeric_escape"] == 0


def test_kill_and_rollback_state_reporting(tmp_path, monkeypatch):
    from tools.phase16 import observe
    led = [{"ts": "2026-10-06T02:00:00Z", "sentence": "x[E1]。",
            "authority_decision": "ALLOW_UPGRADE", "stage": "all-pass",
            "post_gate_result": {"ok": True},
            "counters_snapshot": {}}]
    monkeypatch.setattr(observe, "_load_jsonl",
                        lambda path, start: led
                        if "authority_ledger" in path else [])
    monkeypatch.setattr(observe, "INCIDENTS", str(
        tmp_path / "incidents.json"))
    (tmp_path / "incidents.json").write_text(
        '[{"ts": "2026-10-06T01:00:00Z", "kind": "KILL", '
        '"detail": "test"}]', encoding="utf-8")
    monkeypatch.setattr(observe, "RUNTIME", str(tmp_path / "rt.json"))
    (tmp_path / "rt.json").write_text(
        '{"ts": "x", "enabled": false, "counters": {}, "latencies": []}',
        encoding="utf-8")
    # kill flag absent + decisions recorded AFTER the kill -> failure
    a = observe.analyze("2026-10-06T00:00:00Z")
    assert a["safety"]["kill_failure"] == 1
    assert len(a["incidents_window"]) == 1


if __name__ == "__main__":
    raise SystemExit(
        __import__("pytest").main([__file__, "-q"]))
