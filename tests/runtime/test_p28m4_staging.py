"""Phase 28.M4 — Router Authority staging tests.

Staged authority (ADR-025 §5): slices (default) -> no-plan (QA-class
authoritative) -> full (all three verified paths). The B4 gate with
staged candidate flags IS the unified dual-run; this suite pins the
staging mechanics: resolution matrix, fail-closed config, authority-
mode equivalence vs flag-mode, telemetry honesty (reason=authority),
rollback to slices, and production-gate discipline (nothing reads the
env outside the resolver).
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
from runtime.router_authority import (  # noqa: E402
    AuthorityConfigError, authority_governs, authority_mode,
    authoritative_intents)

ASK = ("agent_decide", {"action": "ask_user",
                        "reason": "insufficient_client_information",
                        "required_fields": ["age", "health", "goal",
                                            "budget"],
                        "message": "请补充信息"})


# --------------------------------------------------------------------- #
# resolution matrix + fail-closed config
# --------------------------------------------------------------------- #

def test_authority_resolution_matrix():
    assert authority_mode({}) == "slices"
    assert authority_mode({"INSURANCE_AGENT_ROUTER_AUTHORITY": "slices"}) \
        == "slices"
    assert authoritative_intents("slices") == frozenset()
    np_ = authoritative_intents("no-plan")
    assert np_ == frozenset({"insurance_qa", "product_qa"})
    assert authoritative_intents("full") == frozenset({
        "insurance_qa", "product_qa", "insurance_plan",
        "modify_existing_plan"})
    # unknown never staged
    for m in ("slices", "no-plan", "full"):
        assert not authority_governs(m, "unknown_insurance_intent")


def test_authority_invalid_fails_closed():
    for bad in ("yes", "FULL!", "1", "off"):
        try:
            authority_mode({"INSURANCE_AGENT_ROUTER_AUTHORITY": bad})
            raise AssertionError(bad)
        except AuthorityConfigError:
            pass


def _shadow(rid):
    from runtime.intent import shadow as sh
    recs = [r for r in sh.iter_records() if r.get("run_id") == rid]
    assert recs, rid
    return recs[0]


# --------------------------------------------------------------------- #
# staging e2e: authority mode == flag mode (unified candidate)
# --------------------------------------------------------------------- #

def _turn(env, chat, text, script):
    for k, v in env.items():
        os.environ[k] = v
    try:
        client, mgr, _bus = make_client()
        mgr.agent_provider = FakeLLMProvider(list(script))
        rid = client.post("/api/chats/%s/messages" % chat,
                          json={"text": text}).json()["run_id"]
        run = wait_terminal(client, rid)
        return run, _shadow(rid)
    finally:
        for k in env:
            os.environ.pop(k, None)


def test_no_plan_authority_equals_flag_mode_for_qa():
    # knowledge QA: authority (no flags at all) == slice flag ON
    run_a, rec_a = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "no-plan"},
                         "chat_m4_auth_qa", "重疾险的等待期是什么",
                         ["重大疾病保险常见等待期为90天[E1]。"])
    run_f, rec_f = _turn({"INSURANCE_AGENT_QA_SLICE": "1"},
                         "chat_m4_flag_qa", "重疾险的等待期是什么",
                         ["重大疾病保险常见等待期为90天[E1]。"])
    assert run_a["result_status"] == run_f["result_status"] == \
        "QA_ANSWERED"
    assert rec_a["actual_execution"] == rec_f["actual_execution"] == \
        "insurance-qa-agent"
    # telemetry honesty: authority path says WHY it fired
    assert rec_a["slice_decision"]["reason"] == "authority"
    assert rec_f["slice_decision"]["reason"] == "fired"


def test_no_plan_leaves_planning_flag_governed():
    run_p, rec_p = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "no-plan"},
                         "chat_m4_np_plan", "帮我规划保险", [ASK])
    assert rec_p["actual_execution"] == "existing-agent"
    assert rec_p["slice_decision"] == {"slice": "plan", "fired": False,
                                       "reason": "flag_off"}


def test_full_authority_covers_planning():
    run_p, rec_p = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "full"},
                         "chat_m4_full_plan", "帮我规划保险", [ASK])
    assert rec_p["actual_execution"] == "insurance-planning-agent"
    assert rec_p["slice_decision"] == {"slice": "plan", "fired": True,
                                       "reason": "authority"}
    # full also covers QA without any flag
    run_q, rec_q = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "full"},
                         "chat_m4_full_qa", "重疾险的等待期是什么",
                         ["重大疾病保险常见等待期为90天[E1]。"])
    assert rec_q["actual_execution"] == "insurance-qa-agent"
    assert rec_q["slice_decision"]["reason"] == "authority"


def test_modify_clarification_stays_out_under_full():
    run_m, rec_m = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "full"},
                         "chat_m4_full_md", "把保额调整到30万",
                         ["请问您想调整什么？"])
    assert rec_m["actual_execution"] == "existing-agent"
    assert rec_m["slice_decision"] == {"slice": "plan", "fired": False,
                                       "reason": "clarification_required"}


def test_rollback_to_slices_all_legacy():
    # authority back to slices with ALL slice flags off => EVERYTHING
    # legacy (note: the QA slice flag is DEFAULT-ON per ruling D4 —
    # rollback of authority alone does not disable it)
    _all_off = {"INSURANCE_AGENT_ROUTER_AUTHORITY": "slices",
                "INSURANCE_AGENT_QA_SLICE": "0",
                "INSURANCE_AGENT_PRODUCT_QA_SLICE": "0",
                "INSURANCE_AGENT_PLAN_SLICE": "0"}
    for chat, text, script in (
            ("chat_m4_rb_qa", "重疾险的等待期是什么",
             ["重大疾病保险常见等待期为90天[E1]。"]),
            ("chat_m4_rb_plan", "帮我规划保险", [ASK])):
        run, rec = _turn(dict(_all_off), chat, text, script)
        assert rec["actual_execution"] == "existing-agent", chat
        assert rec["slice_decision"]["reason"] == "flag_off", chat


def test_invalid_authority_env_fires_nothing():
    # invalid grant is refused AND the default-ON QA flag is zeroed so
    # this isolates the authority failure itself
    run, rec = _turn({"INSURANCE_AGENT_ROUTER_AUTHORITY": "banana",
                      "INSURANCE_AGENT_QA_SLICE": "0"},
                     "chat_m4_bad_qa", "重疾险的等待期是什么",
                     ["重大疾病保险常见等待期为90天[E1]。"])
    # fail-closed: the invalid grant is refused; the turn still lives
    assert run["status"] == "completed"
    assert rec["actual_execution"] == "existing-agent"
    assert rec["slice_decision"]["reason"] == "flag_off"


def test_single_reader_discipline():
    import subprocess
    out = subprocess.run(
        ["git", "grep", "-l", "--untracked",
         "INSURANCE_AGENT_ROUTER_AUTHORITY", "--", "runtime/"], capture_output=True, text=True).stdout
    readers = sorted(l for l in out.splitlines() if l.strip())
    # exactly two legitimate mentions: the RESOLVER (sole reader) and
    # the hermetic B4 runner, which PINS the env to "slices" for its
    # legacy baseline (a pin, not a reader — no dispatch logic there)
    assert readers == ["runtime/evaluation/router_equivalence/runner.py",
                       "runtime/router_authority.py"], readers


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
