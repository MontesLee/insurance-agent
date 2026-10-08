"""Phase 28.A-2 — Intent completion tests (LLM candidate adapter,
context signals, shadow observability, calibration).

The five MANDATED cases (28.A-2 spec Step 4) plus context/timeout/shape/
mismatch/calibration coverage. All offline: the LLM candidate is exercised
through a fake provider object satisfying the LLMProvider protocol — never
a live endpoint.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time as time_mod

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from runtime.agent.model import LLMResponse  # noqa: E402
from runtime.agent_registry import load_registry  # noqa: E402
from runtime.intent import classifier as ic  # noqa: E402
from runtime.intent import llm_candidate as lc  # noqa: E402
from runtime.intent import report as rp  # noqa: E402
from runtime.intent import shadow as sh  # noqa: E402
from runtime import router as rt  # noqa: E402

RULE_MISS_MSG = "有个事儿想问下"          # fires no v1 rule (A-1 corpus-verified)


class _FakeProvider:
    """LLMProvider-protocol fake returning a canned response text."""
    name = "fake-candidate"
    model = "fake-model"

    def __init__(self, text=None, raise_exc=None, sleep=None):
        self.text = text
        self.raise_exc = raise_exc
        self.sleep = sleep
        self.calls = []

    def generate(self, messages, tools):
        self.calls.append(messages)
        if self.sleep:
            time_mod.sleep(self.sleep)
        if self.raise_exc:
            raise self.raise_exc
        return LLMResponse(text=self.text, tool_calls=[])


# --------------------------------------------------------------------------
# mandated case 1 — LLM returns a valid candidate: resolver accepts/rejects
# --------------------------------------------------------------------------

def test_llm_valid_candidate_accepted_and_rejected():
    ok = _FakeProvider(text=json.dumps(
        {"intent": "insurance_qa", "confidence": 0.9,
         "explanation": "concept question", "evidence": ["百万医疗险"]}))
    r = ic.classify(RULE_MISS_MSG,
                    llm_candidate=lc.make_candidate(ok, timeout=5.0))
    assert r["intent_id"] == "insurance_qa", r
    assert r["confidence_source"] == "llm" and r["confidence"] == 0.9
    assert r["clarification_required"] is False          # resolver ACCEPTED

    # high-risk proposal below the floor: the resolver REJECTS auto-routing
    risky = _FakeProvider(text=json.dumps(
        {"intent": "insurance_plan", "confidence": 0.6}))
    r2 = ic.classify(RULE_MISS_MSG,
                     llm_candidate=lc.make_candidate(risky, timeout=5.0))
    assert r2["intent_id"] == "insurance_plan"
    assert r2["clarification_required"] is True
    assert "threshold:high_risk_llm_floor" in r2["reason_codes"]

    # fast path still wins: rules hit -> the candidate is never consulted
    fast = _FakeProvider(text=json.dumps(
        {"intent": "product_qa", "confidence": 0.99}))
    r3 = ic.classify("帮我规划保险",
                     llm_candidate=lc.make_candidate(fast, timeout=5.0))
    assert not fast.calls and r3["intent_id"] == "insurance_plan"
    assert r3["confidence_source"] == "rule"


# --------------------------------------------------------------------------
# mandated case 2 — LLM tries to output agent/workflow/decision_source
# --------------------------------------------------------------------------

def test_llm_agent_shaped_output_is_schema_rejected():
    for bad in (
        {"agent": "insurance-qa-agent", "intent": "insurance_qa",
         "confidence": 0.9},
        {"workflow": "insurance-analysis", "intent": "insurance_plan",
         "confidence": 0.9},
        {"intent": "insurance_qa", "confidence": 0.9,
         "decision_source": "llm"},
        {"tool": "knowledge_search", "intent": "insurance_qa",
         "confidence": 0.9},
    ):
        assert lc.parse_candidate(json.dumps(bad)) is None, bad
    # end-to-end: rejected output degrades to unknown via the rule path
    prov = _FakeProvider(text=json.dumps(
        {"agent": "insurance-qa-agent", "intent": "insurance_qa",
         "confidence": 0.95}))
    r = ic.classify(RULE_MISS_MSG,
                    llm_candidate=lc.make_candidate(prov, timeout=5.0))
    assert r["intent_id"] == "unknown_insurance_intent", r
    assert "llm:invalid_proposal" in r["reason_codes"]


def test_parse_candidate_shape_contracts():
    good = json.dumps({"intent": "insurance_qa", "confidence": 0.88,
                       "explanation": "x", "evidence": ["y"]})
    assert lc.parse_candidate(good) == ("insurance_qa", 0.88)
    # markdown fence + surrounding prose are tolerated, shape is not
    assert lc.parse_candidate("```json\n%s\n```" % good) == ("insurance_qa", 0.88)
    assert lc.parse_candidate("Sure! %s hope that helps" % good) == \
        ("insurance_qa", 0.88)
    minimal = json.dumps({"intent": "product_qa", "confidence": 1})
    assert lc.parse_candidate(minimal) == ("product_qa", 1.0)
    for bad_text in (
        json.dumps({"intent": "insurance_qa"}),                      # no conf
        json.dumps({"intent": "insurance_qa", "confidence": "0.9"}),  # str conf
        json.dumps({"intent": "insurance_qa", "confidence": 1.5}),    # range
        json.dumps({"intent": "insurance_qa", "confidence": True}),   # bool
        json.dumps({"intent": "", "confidence": 0.9}),                # empty
        json.dumps({"intent": "insurance_qa", "confidence": 0.9,
                    "mood": "happy"}),                                 # extra key
        json.dumps(["insurance_qa", 0.9]),                             # not obj
        "not json at all",
        "",
        None,
    ):
        assert lc.parse_candidate(bad_text) is None, bad_text


# --------------------------------------------------------------------------
# mandated case 3 — LLM unavailable: rule fallback continues
# --------------------------------------------------------------------------

def test_llm_unavailable_falls_back_to_rules():
    down = _FakeProvider(raise_exc=RuntimeError("provider down"))
    r = ic.classify(RULE_MISS_MSG,
                    llm_candidate=lc.make_candidate(down, timeout=5.0))
    assert r["intent_id"] == "unknown_insurance_intent"
    assert "llm:candidate_error" in r["reason_codes"]
    # and the rules fast path is unaffected by the outage
    r2 = ic.classify("帮我规划保险",
                     llm_candidate=lc.make_candidate(down, timeout=5.0))
    assert r2["intent_id"] == "insurance_plan"
    assert r2["confidence_source"] == "rule"


def test_llm_candidate_timeout_degrades_closed():
    slow = _FakeProvider(
        text=json.dumps({"intent": "insurance_qa", "confidence": 0.9}),
        sleep=0.4)
    cand = lc.make_candidate(slow, timeout=0.05)
    r = ic.classify(RULE_MISS_MSG, llm_candidate=cand)
    assert r["intent_id"] == "unknown_insurance_intent"
    assert "llm:candidate_error" in r["reason_codes"]


def test_candidate_toggle_and_timeout_config():
    assert lc.enabled({}) is False                     # default OFF
    assert lc.enabled({"INSURANCE_AGENT_INTENT_LLM": "1"}) is True
    assert lc.enabled({"INSURANCE_AGENT_INTENT_LLM": "0"}) is False
    assert lc.timeout_seconds({}) == 4.0               # rules-file default
    assert lc.timeout_seconds(
        {"INSURANCE_AGENT_INTENT_LLM_TIMEOUT": "1.5"}) == 1.5


# --------------------------------------------------------------------------
# mandated case 4 — modify request with no context -> clarification
# --------------------------------------------------------------------------

def test_modify_without_active_case_fails_closed_even_with_conversation():
    # conversation context EXISTS but no active case: M1 still fails closed
    r = ic.classify("把保额调整到30万",
                    conversation_context=["帮我规划保险", "好的，方案如下"],
                    conversation_id="chat_1", active_case_id=None)
    assert r["intent_id"] == "modify_existing_plan", r
    assert r["clarification_required"] is True
    assert "context:active_case_missing" in r["reason_codes"]


# --------------------------------------------------------------------------
# context-aware classification (ADR-019 rule 7, externalized switch)
# --------------------------------------------------------------------------

def test_demonstrative_followup_inherits_context_anchor():
    ctx = ["我想给全家配置保险", "这款重疾险怎么样"]
    r = ic.classify("那款怎么样", conversation_context=ctx)
    assert r["intent_id"] == "product_qa", r
    assert "context:anchor_inherited" in r["reason_codes"]
    # without context the same elliptical message degrades closed
    r2 = ic.classify("那款怎么样")
    assert r2["intent_id"] == "unknown_insurance_intent"


def test_evaluative_followup_never_inherits_anchor():
    # mid-conversation out-of-domain: NO demonstrative -> no inheritance
    r = ic.classify("今天天气怎么样，适合出去玩吗",
                    conversation_context=["重疾险怎么买"])
    assert r["intent_id"] == "unknown_insurance_intent", r


def test_anchor_inheritance_switch_off():
    rules = ic.load_rules()
    rules = json.loads(json.dumps(rules, ensure_ascii=False))
    rules["context"]["anchor_inheritance"] = False
    r = ic.classify("那款怎么样",
                    conversation_context=["我想给全家配置保险"],
                    rules=rules)
    assert r["intent_id"] == "unknown_insurance_intent", r


def test_corpus_classification_unchanged_with_no_context():
    # regression guard: the context rule must not move any corpus label
    for msg, expected, _legacy in rp.CORPUS:
        r = ic.classify(msg)          # context=None — corpus conditions
        assert r["intent_id"] == expected, (msg, r["intent_id"], expected)


# --------------------------------------------------------------------------
# mandated case 5 — legacy/shadow disagreement: record only, no execution
# --------------------------------------------------------------------------

def test_legacy_shadow_disagreement_recorded_only():
    reg = load_registry()
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "shadow.jsonl")
        ir = ic.classify("帮我规划保险")
        before = json.dumps(reg, sort_keys=True)
        rec = sh.record("run_d", "chat_d", "帮我规划保险", ir,
                        rt.route(ir, reg), latency_ms=7, file=f)
        # legacy claims TASK_EXECUTION (modify) where shadow said plan
        assert sh.annotate("run_d", file=f, legacy_intent="TASK_EXECUTION",
                           legacy_action="finish")
        recs = list(sh.iter_records(file=f))
        assert len(recs) == 1
        out = recs[0]
        assert out["actual_execution"] == "existing-agent"   # unchanged
        assert out["mismatch_type"] == ["intent_difference"]
        assert out["latency_ms"] == 7
        assert out["resolver"] == "rule_fast_path"
        # purity: the whole shadow pass left the registry untouched and
        # classification is deterministic (twice -> same verdict)
        assert json.dumps(reg, sort_keys=True) == before
        assert ic.classify("帮我规划保险")["intent_id"] == \
            ic.classify("帮我规划保险")["intent_id"]


def test_mismatch_type_vocabulary():
    base = {"legacy_intent": "CLIENT_ADVISORY",
            "predicted_intent": "insurance_plan",
            "confidence_source": "rule", "confidence": 1.0,
            "clarification_required": False, "reason_codes": []}
    assert sh.mismatch_types(dict(base)) == []                       # agree
    differ = dict(base, legacy_intent="TASK_EXECUTION")
    assert sh.mismatch_types(differ) == ["intent_difference"]
    noctx = dict(base, predicted_intent="modify_existing_plan",
                 clarification_required=True,
                 reason_codes=["rule:modify:调整",
                               "context:active_case_missing"])
    assert sh.mismatch_types(noctx) == ["intent_difference",
                                        "missing_context"]
    conf = dict(base, confidence_source="llm", confidence=0.6)
    assert sh.mismatch_types(conf, floor=0.75) == ["confidence_difference"]
    assert sh.mismatch_types({"legacy_intent": None}) == []          # n/a
    unmapped = dict(base, legacy_intent="SOMETHING_ELSE")
    assert sh.mismatch_types(unmapped) == ["intent_difference"]


def test_resolver_outcome_derivation():
    assert sh.resolver_outcome(ic.classify("帮我规划保险")) == "rule_fast_path"
    assert sh.resolver_outcome(
        ic.classify("把保额调整到30万")) == "rule_clarify"
    assert sh.resolver_outcome(
        ic._fallback_unknown(["fallback:no_signal_match"], None, None,
                             None)) == "fail_closed_unknown"
    degraded = ic._fallback_unknown(["schema_validation_failed"], None,
                                    None, None)
    assert sh.resolver_outcome(degraded) == "schema_gate_degrade"
    llm_ok = {"intent_id": "insurance_qa", "confidence_source": "llm",
              "clarification_required": False, "reason_codes": ["llm:proposal"]}
    assert sh.resolver_outcome(llm_ok) == "llm_accepted"
    llm_floor = dict(llm_ok, intent_id="insurance_plan",
                     clarification_required=True)
    assert sh.resolver_outcome(llm_floor) == "llm_floor_clarify"


# --------------------------------------------------------------------------
# shadow privacy + calibration report
# --------------------------------------------------------------------------

def test_shadow_record_metadata_only():
    reg = load_registry()
    with tempfile.TemporaryDirectory() as td:
        f = os.path.join(td, "s.jsonl")
        msg = "把刚才孩子的重疾险保额从50万改成30万"
        ir = ic.classify(msg)
        rec = sh.record("run_p", None, msg, ir, rt.route(ir, reg), file=f)
        dumped = json.dumps({k: v for k, v in rec.items()
                             if k != "message_head"})
        assert msg not in dumped                     # full text never stored
        assert rec["message_len"] == len(msg)


def test_calibration_report_from_records():
    recs = [
        {"predicted_intent": "insurance_plan", "confidence_source": "rule",
         "confidence": 1.0, "clarification_required": False,
         "resolver": "rule_fast_path", "latency_ms": 3,
         "legacy_intent": "CLIENT_ADVISORY", "mismatch_type": []},
        {"predicted_intent": "unknown_insurance_intent",
         "confidence_source": "rule", "confidence": 0.0,
         "clarification_required": True, "resolver": "fail_closed_unknown",
         "latency_ms": 2, "legacy_intent": None, "mismatch_type": None},
        {"predicted_intent": "insurance_qa", "confidence_source": "llm",
         "confidence": 0.9, "clarification_required": False,
         "resolver": "llm_accepted", "latency_ms": 120,
         "legacy_intent": "GENERAL_KNOWLEDGE", "mismatch_type": []},
    ]
    text = rp.build_calibration_report(recs)
    assert "shadow records: **3**" in text
    assert "unknown 比例: **1/3 (33%)**" in text
    assert "p95" in text and "120" in text
    assert "llm_accepted: **1**" in text
    assert "intent_difference: **0**" in text
    assert "provisional" in text                    # floor quoted, not set
    empty = rp.build_calibration_report([])
    assert "No shadow records" in empty


def test_llm_candidate_module_import_boundary():
    src = open(os.path.join(REPO, "runtime", "intent", "llm_candidate.py"),
               encoding="utf-8").read()
    import_lines = [ln.strip() for ln in src.splitlines()
                    if ln.strip().startswith(("import ", "from "))]
    for banned in ("router", "orchestrator", "agent_registry", "skills",
                   "tools", "model", "server"):
        for ln in import_lines:
            assert banned not in ln, (
                "runtime/intent/llm_candidate.py import %r violates the "
                "adapter boundary (provider object is INJECTED, never "
                "constructed/imported here)" % ln)


if __name__ == "__main__":
    failures = 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (len(fns), failures))
    sys.exit(1 if failures else 0)
