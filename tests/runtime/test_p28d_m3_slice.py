"""Phase 28.D (M3) — Planning Slice tests.

Contract: docs/production/phase-28d-planning-slice-contract.md; the
behavior unit mounts the SAME chat tool-stack on the planning registry
entry — E1 equivalence is enforced by the B4 gate (17 cases incl. 5
real planning E1 dual-runs) and the committed baseline tripwire
(test_p28b6_preflight). This suite pins the slice mechanics: flag
semantics, identity recording, isolation, guard, crash semantics, and
the guard-fallback path.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client, wait_terminal  # noqa: E402

from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.planning_agent import (  # noqa: E402
    guard_ok, planning_slice_enabled, run_planning_turn)
from runtime.intent.classifier import classify  # noqa: E402

ASK = ("agent_decide", {"action": "ask_user",
                        "reason": "insufficient_client_information",
                        "required_fields": ["age", "health", "goal",
                                            "budget"],
                        "message": "请补充：1) 为谁配置 2) 预算"})


def _shadow(rid):
    from runtime.intent import shadow as sh
    recs = [r for r in sh.iter_records() if r.get("run_id") == rid]
    assert recs, rid
    return recs[0]


# --------------------------------------------------------------------- #
# flag + guard units
# --------------------------------------------------------------------- #

def test_flag_default_off():
    assert planning_slice_enabled({}) is False
    assert planning_slice_enabled(
        {"INSURANCE_AGENT_PLAN_SLICE": "1"}) is True


def test_guard_contract():
    assert guard_ok(classify("帮我规划保险")) is True
    md = classify("把保额调整到30万")
    assert md["clarification_required"] and guard_ok(md) is False
    assert guard_ok(classify("重疾险的等待期是什么")) is False
    assert guard_ok({"intent_id": "bogus"}) is False
    # guard failure => None (legacy fallback), never raises
    assert run_planning_turn({"intent_id": "bogus"}, lambda: "x") is None
    assert run_planning_turn(classify("帮我规划保险"),
                             lambda: "OUT") == "OUT"


# --------------------------------------------------------------------- #
# e2e: identity + equivalence shape + isolation
# --------------------------------------------------------------------- #

def _plan_turn(env_flag=None):
    if env_flag is not None:
        os.environ["INSURANCE_AGENT_PLAN_SLICE"] = env_flag
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider([ASK])
        rid = client.post("/api/chats/chat_m3_%s/messages" % (env_flag or
                                                              "off"),
                          json={"text": "帮我规划保险"}).json()["run_id"]
        run = wait_terminal(client, rid)
        view = client.get("/api/chats/chat_m3_%s" % (env_flag or
                                                     "off")).json()
        answer = next((m["content"] for m in reversed(view["messages"])
                       if m.get("role") == "assistant"), "")
        evs = client.get("/api/runs/%s/events" % rid).json()["events"]
        return run, answer, _shadow(rid), [e["event_type"] for e in evs]
    finally:
        if env_flag is not None:
            del os.environ["INSURANCE_AGENT_PLAN_SLICE"]


def test_slice_on_identity_and_equivalence_shape():
    run_off, ans_off, rec_off, evs_off = _plan_turn("0")
    run_on, ans_on, rec_on, evs_on = _plan_turn("1")
    # identity: flag ON executes AS the planning agent
    assert rec_on["actual_execution"] == "insurance-planning-agent"
    assert rec_on["slice_decision"] == {"slice": "plan", "fired": True,
                                        "reason": "fired"}
    assert rec_off["actual_execution"] == "existing-agent"
    assert rec_off["slice_decision"]["reason"] == "flag_off"
    # equivalence shape: same user-visible outcome + same event types
    assert run_on["status"] == run_off["status"] == "waiting"
    assert ans_on == ans_off
    assert evs_on == evs_off
    # no new event vocabulary: only existing types appear
    assert not [t for t in evs_on if t in ("qa_answered",
                                           "grounding_started")]


def test_modify_clarification_never_fires_slice():
    os.environ["INSURANCE_AGENT_PLAN_SLICE"] = "1"
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider([
            "请问您想调整哪份方案的什么内容？"])
        rid = client.post("/api/chats/chat_m3_md/messages",
                          json={"text": "把保额调整到30万"}).json()["run_id"]
        run = wait_terminal(client, rid)
        assert run["status"] == "completed"
        rec = _shadow(rid)
        assert rec["actual_execution"] == "existing-agent"
        assert rec["slice_decision"] == {"slice": "plan", "fired": False,
                                         "reason": "clarification_required"}
    finally:
        del os.environ["INSURANCE_AGENT_PLAN_SLICE"]


def test_plan_flag_does_not_affect_other_intents():
    os.environ["INSURANCE_AGENT_PLAN_SLICE"] = "1"
    try:
        # knowledge QA slice still owns insurance_qa
        c1, m1, _b = make_client()
        m1.agent_provider = FakeLLMProvider([
            "重大疾病保险常见等待期为90天[E1]。"])
        r1 = c1.post("/api/chats/chat_m3_iso_qa/messages",
                     json={"text": "重疾险的等待期是什么"}).json()["run_id"]
        run1 = wait_terminal(c1, r1)
        assert run1["result_status"] == "QA_ANSWERED", run1
        rec1 = _shadow(r1)
        assert rec1["actual_execution"] == "insurance-qa-agent"
        assert rec1["slice_decision"]["slice"] == "knowledge-qa"
        # unknown still legacy
        c2, m2, _b2 = make_client()
        m2.agent_provider = FakeLLMProvider(["这个问题和保险无关呢。"])
        r2 = c2.post("/api/chats/chat_m3_iso_unk/messages",
                     json={"text": "今天天气怎么样"}).json()["run_id"]
        run2 = wait_terminal(c2, r2)
        assert run2["status"] == "completed"
        rec2 = _shadow(r2)
        assert rec2["actual_execution"] == "existing-agent"
        assert rec2["slice_decision"] is None
    finally:
        del os.environ["INSURANCE_AGENT_PLAN_SLICE"]


def test_crash_semantics_identical_to_legacy():
    # a spine crash mid-turn must produce the SAME run_failed outcome
    # with the flag on or off (E1 crash equivalence; no double-run)
    results = {}
    for flag in ("0", "1"):
        os.environ["INSURANCE_AGENT_PLAN_SLICE"] = flag
        try:
            client, mgr, _bus = make_client()

            class _Boom:
                name, model = "boom", "boom-model"

                def generate(self, messages, tools):
                    raise RuntimeError("spine crash")

            mgr.agent_provider = _Boom()
            rid = client.post("/api/chats/chat_m3_crash_%s/messages" % flag,
                              json={"text": "帮我规划保险"}
                              ).json()["run_id"]
            run = wait_terminal(client, rid)
            evs = [e["event_type"] for e in client.get(
                "/api/runs/%s/events" % rid).json()["events"]]
            results[flag] = (run["status"], run["result_status"],
                             "run_failed" in evs)
        finally:
            del os.environ["INSURANCE_AGENT_PLAN_SLICE"]
    assert results["0"] == results["1"], results
    # the agent loop degrades a provider crash to its designed
    # fail-closed terminal (needs_review via agent_step_error), NOT a
    # hard run_failed — and the flag must not change that semantics
    assert results["1"][0] in ("needs_review", "failed")
    assert results["1"][0] == results["0"][0]


def test_guard_fallback_annotates_and_uses_legacy():
    # if the unit's guard refuses after the slice fired (defense in
    # depth), the turn falls back to legacy + slice_error is recorded
    import runtime.planning_agent as pmod
    os.environ["INSURANCE_AGENT_PLAN_SLICE"] = "1"
    orig = pmod.run_planning_turn
    pmod.run_planning_turn = lambda ir, ex, conversation_context=None: None
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider([ASK])
        rid = client.post("/api/chats/chat_m3_guard/messages",
                          json={"text": "帮我规划保险"}).json()["run_id"]
        run = wait_terminal(client, rid)
        assert run["status"] == "waiting"      # legacy completed the turn
        rec = _shadow(rid)
        assert rec["actual_execution"] == "insurance-planning-agent"
        assert rec.get("slice_error") == "planning_guard_fallback"
    finally:
        pmod.run_planning_turn = orig
        del os.environ["INSURANCE_AGENT_PLAN_SLICE"]


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
