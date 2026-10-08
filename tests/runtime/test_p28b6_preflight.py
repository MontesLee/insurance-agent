"""Phase 28.B6 — M3 planning preflight tests.

Governance (ADR-025 approval record, ownership boundaries, prompt
freeze) + planning baseline tripwire (the committed legacy fingerprints
M3 candidates must reproduce) + routing/rollback preflight.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client, wait_terminal  # noqa: E402

from runtime.agent import FakeLLMProvider  # noqa: E402

FROZEN_PROMPT_SHA = ("193ed7da5865708ecd2dbe550d9630581a59c5299c02f8c"
                     "1f4f4d1bcbaddd5bc")
BASELINE_PATH = os.path.join(REPO, "tests", "golden",
                             "planning-baseline.json")


# ==========================================================================
# Governance
# ==========================================================================

def test_adr025_approved_and_decision_intact():
    src = open(os.path.join(REPO, "docs", "adr",
                            "ADR-025-router-authority-migration.md"),
               encoding="utf-8").read()
    assert src.index("APPROVED") < src.index("## Context")
    assert "M3 remains separately gated" in src
    assert "rollback requirement" in src.lower().replace("Rollback", "rollback")
    # the technical decision content was not rewritten by the approval
    for section in ("### 1. 当前执行路径", "### 3. Authority Ownership",
                    "### 4. Migration Stages", "## Alternatives considered",
                    "## Validation criteria"):
        assert section in src, section


def test_planning_prompt_frozen():
    src = open(os.path.join(REPO, "runtime", "agent", "prompts.py"),
               encoding="utf-8").read()
    assert hashlib.sha256(src.encode("utf-8")).hexdigest() == \
        FROZEN_PROMPT_SHA, (
            "runtime/agent/prompts.py changed after the M3 freeze — "
            "update PLANNING_PROMPT_FREEZE.md + re-capture the planning "
            "baseline in the same change (three-part discipline)")


def test_planning_prompt_has_no_router_authority():
    # P10: the planning prompt defines HOW to plan, never WHETHER it
    # should be called — no agent selection / dispatch language
    src = open(os.path.join(REPO, "runtime", "agent", "prompts.py"),
               encoding="utf-8").read().lower()
    for banned in ("use agent", "choose which agent", "select the agent",
                   "route to", "dispatch", "router"):
        assert banned not in src, banned


def test_registry_planning_entry_and_ownership():
    from runtime.agent_registry import load_registry
    reg = load_registry()
    planning = [a for a in reg["agents"]
                if a["id"] == "insurance-planning-agent"]
    assert planning and set(planning[0]["supported_intents"]) == {
        "insurance_plan", "modify_existing_plan"}
    # dispatch ownership: every intent resolves to exactly one agent
    assert reg["intent_agent_map"]["insurance_plan"] == \
        "insurance-planning-agent"
    assert reg["intent_agent_map"]["insurance_qa"] == "insurance-qa-agent"


def test_router_decision_has_no_llm_authority():
    with open(os.path.join(REPO, "schema", "router-decision.schema.json"),
              encoding="utf-8") as fh:
        schema = json.load(fh)
    assert "llm" not in schema["properties"]["decision_source"]["enum"]


def test_frontend_mapping_not_production_authority():
    # mapPromptToCase exists ONLY for demo-case selection metadata; the
    # CONSUMER chat (28.E-1) is agent-ONLY and routes via the backend
    # Intent Layer. Updated for the E-1 three-space shell: ChatLayout
    # has no mode toggle and must never start runs itself (demo-run
    # execution lives behind the developer console only) — strictly
    # stronger than the pre-E-1 toggle-string assertions.
    chat_dir = os.path.join(REPO, "web", "src", "components", "chat")
    layout = open(os.path.join(chat_dir, "ChatLayout.tsx"),
                  encoding="utf-8").read()
    composer = open(os.path.join(chat_dir, "Composer.tsx"),
                    encoding="utf-8").read()
    chat_state = open(os.path.join(REPO, "web", "src", "state",
                                   "chatState.ts"), encoding="utf-8").read()
    assert "api.createRun" not in layout, \
        "consumer chat must not create runs directly (backend routes)"
    assert "chatMode" not in layout, \
        "consumer chat is agent-only (28.E-1): no demo/agent toggle"
    assert "mapPromptToCase" not in layout, \
        "keyword mapping must not live in the consumer chat layout"
    # the mapping itself stays confined to Composer (demo metadata) and
    # its chatState definition
    assert "mapPromptToCase" in composer or "mapPromptToCase" in chat_state
    # and no frontend file references the production agent ids
    for fn in ("ChatLayout.tsx", "Composer.tsx"):
        src = open(os.path.join(chat_dir, fn), encoding="utf-8").read()
        assert "insurance-planning-agent" not in src
        assert "insurance-qa-agent" not in src


# ==========================================================================
# Planning baseline tripwire (P9 — the M3 E1 baseline)
# ==========================================================================

def _fingerprint(case, root):
    from runtime.evaluation.router_equivalence import normalizer as nm
    from runtime.evaluation.router_equivalence import runner
    from runtime.evaluation.router_equivalence.comparator import (
        _eval_verdicts, _risk_signals)
    cap = runner.run_side(case, "legacy", root)
    assert not cap.error, cap.error
    ev = nm.normalize_events(cap.events)
    return {
        "run_status": cap.status,
        "event_chain_hash": nm.stable_hash(ev),
        "artifact_hashes": [nm.stable_hash(a) for a in cap.artifacts],
        "eval_verdicts": _eval_verdicts(ev),
        "risk_signals": _risk_signals(ev),
        "artifact_count": len(cap.artifacts),
    }


def test_planning_baseline_matches_committed(monkeypatch):
    # Determinism (M5-C.2 §14/§15): the ONE date-rolling field in the
    # fingerprinted artifacts is governance `as_of`, which by documented
    # design defaults to the LOCAL system date at the knowledge-service
    # seam (knowledge/service.py — time.strftime("%Y-%m-%d"), the only
    # "%Y-%m-%d" user in runtime/+knowledge/). The committed baseline
    # was captured on 2026-09-25; after the first local-midnight
    # rollover the fresh hash legitimately differed (728/729, M5-C.1
    # §12.1). Pin the seam to the baseline capture date — a pure
    # TEST-harness clock freeze; production as_of semantics untouched.
    import time as _time

    real_strftime = _time.strftime

    def _pinned_strftime(fmt, *args):
        if fmt == "%Y-%m-%d":
            return "2026-09-25"
        return real_strftime(fmt, *args)

    monkeypatch.setattr(_time, "strftime", _pinned_strftime)

    from runtime.evaluation.router_equivalence.models import load_cases
    committed = json.load(open(BASELINE_PATH, encoding="utf-8"))["baseline"]
    root = os.path.join(REPO, "tmp", "b6-tripwire")
    for case in load_cases():
        if not case.case_id.startswith("GC-PL-"):
            continue
        fresh = _fingerprint(case, os.path.join(root, case.case_id))
        want = committed[case.case_id]
        for key in ("run_status", "event_chain_hash", "artifact_hashes",
                    "eval_verdicts", "risk_signals", "artifact_count"):
            assert fresh[key] == want[key], (case.case_id, key)


# ==========================================================================
# Routing / rollback preflight
# ==========================================================================

def test_planning_default_off_and_authority_env_still_inert():
    # M4 made ROUTER_AUTHORITY real (staged resolver): UNSET keeps every
    # intent flag-governed (plan stays legacy/flag_off); authority=full
    # is the AUTHORIZED staging that fires the plan slice (covered in
    # test_p28m4_staging); invalid values fail closed (resolver raises).
    client, mgr, _bus = make_client()          # authority UNSET -> slices
    mgr.agent_provider = FakeLLMProvider([
        ("agent_decide", {"action": "finish", "message": "分析完成。"})])
    rid = client.post("/api/chats/chat_b6_plan/messages",
                      json={"text": "帮我规划保险"}).json()["run_id"]
    run = wait_terminal(client, rid)
    assert run["status"] == "completed"
    from runtime.intent import shadow as sh
    rec = [r for r in sh.iter_records() if r.get("run_id") == rid][0]
    assert rec["actual_execution"] == "existing-agent"
    assert rec["predicted_intent"] == "insurance_plan"
    assert rec["slice_decision"]["reason"] == "flag_off"
    evs = client.get("/api/runs/%s/events" % rid).json()["events"]
    assert not [e for e in evs if e["event_type"] == "qa_answered"]
    # static: since M4 the authority env IS read — by exactly ONE
    # resolver module (fail-closed staging); no other runtime reader
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


def test_candidate_failure_fallback_pattern_proven():
    # the M3 fallback contract (candidate crash -> legacy + slice_error)
    # is already proven by the QA slice; assert the pattern's existence
    # so M3 must replicate it (28.B4 test also pins behavior directly)
    import inspect
    from runtime import server as srv
    src = inspect.getsource(srv)
    assert "slice_error" in src and "QA slice failed closed" in src


def test_non_planning_intents_never_reach_planning():
    from runtime import router as rt
    from runtime.agent_registry import load_registry
    from runtime.intent.classifier import classify
    reg = load_registry()
    for msg, intent in (("重疾险的等待期是什么", "insurance_qa"),
                        ("P001是什么产品", "product_qa"),
                        ("今天天气怎么样", "unknown_insurance_intent")):
        rd = rt.route(classify(msg), reg)
        assert rd["agent_id"] != "insurance-planning-agent", msg
    # and modify without case -> clarification -> fallback (never planning)
    rd = rt.route(classify("把保额调整到30万"), reg)
    assert rd["decision_source"] == "fallback"
    assert rd["agent_id"] == "conversation-agent"


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
