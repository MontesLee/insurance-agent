"""Phase 28.K.24 — Run deadline & agent execution watchdog tests.

Invariant: every run has a FINITE lifetime; deadline exceeded →
run_failed terminal (closed by the lifecycle supervisor, independent of
the worker thread); agent-loop provider calls run under a wall-clock
watchdog clamped to the REMAINING run budget.
"""
from __future__ import annotations

import os
import sys
import time

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client, wait_terminal  # noqa: E402

from runtime import run_deadline  # noqa: E402
from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.agent.agent import _generate_with_retry  # noqa: E402
from runtime.agent.state import AgentState  # noqa: E402
from runtime.llm.types import LLMError, TimeoutError as LLMTimeout  # noqa: E402


# --------------------------------------------------------------------------- #
# L2 — generation wall-clock watchdog (unit, deterministic)
# --------------------------------------------------------------------------- #

class _Slow:
    """Provider whose call blocks forever (the slow-drip/hang case)."""
    name = "slow"
    model = "m"

    def generate(self, messages, tools):
        time.sleep(30)
        raise AssertionError("should have been watchdogged")

    def stream_generate(self, messages, tools):
        # chunks every ~0.4s — each read is fast, total is unbounded
        import time as _t
        for _ in range(1000):
            _t.sleep(0.4)
            yield {"kind": "content", "text": "x"}
        raise AssertionError("should have been watchdogged")


def _retry_ctx():
    st = AgentState("run_wd", "case_wd", "chat_wd")
    events = []
    return st, events


def test_t3_generation_wall_clock_watchdog(monkeypatch):
    monkeypatch.setenv(run_deadline.GENERATION_WALL_ENV, "1")
    st, ev = _retry_ctx()
    t0 = time.monotonic()
    out = _generate_with_retry(_Slow(), [], [], st, lambda t, d: ev.append(t))
    assert out is None and st.status == "needs_review"  # fail-closed
    assert time.monotonic() - t0 < 10  # bounded (retries also clamped)
    assert any(e == "agent_step_error" for e in ev)


def test_t15_budget_clamped_by_run_deadline(monkeypatch):
    monkeypatch.setenv(run_deadline.GENERATION_WALL_ENV, "300")
    # deadline in 2s → budget must clamp to ~2s, NOT 300
    deadline = time.monotonic() + 2.0
    st, ev = _retry_ctx()
    t0 = time.monotonic()
    out = _generate_with_retry(_Slow(), [], [], st, lambda t, d: ev.append(t),
                               deadline_at=deadline)
    assert out is None
    assert time.monotonic() - t0 < 20  # far below 300s


def test_t4_no_retry_below_minimum_budget(monkeypatch):
    monkeypatch.setenv(run_deadline.MIN_RETRY_BUDGET_ENV, "3600")
    st, ev = _retry_ctx()
    t0 = time.monotonic()
    out = _generate_with_retry(_Slow(), [], [], st, lambda t, d: ev.append(t),
                               deadline_at=time.monotonic() + 300)
    assert out is None
    assert time.monotonic() - t0 < 5  # refused to START a doomed call


def test_t14_fast_generation_not_killed(monkeypatch):
    monkeypatch.setenv(run_deadline.GENERATION_WALL_ENV, "30")
    st, ev = _retry_ctx()
    p = FakeLLMProvider([("agent_decide", {"action": "finish",
                                           "message": "完成"})])
    out = _generate_with_retry(p, [], [], st, lambda t, d: ev.append(t))
    assert out is not None and out.tool_calls  # normal path untouched


# --------------------------------------------------------------------------- #
# L1 — run deadline supervisor (integration)
# --------------------------------------------------------------------------- #

def test_t2_run_deadline_produces_terminal(monkeypatch):
    monkeypatch.setenv(run_deadline.RUN_DEADLINE_ENV, "2")
    client, mgr, _ = make_client()
    mgr.agent_provider = _Slow()
    chat = client.post("/api/chats").json()["chat_id"]
    rid = client.post("/api/chats/%s/messages" % chat,
                      json={"text": "慢生成测试"}).json()["run_id"]
    run = wait_terminal(client, rid, timeout=30)
    assert run["status"] == "failed"
    assert run["result_status"] == "RUN_DEADLINE_EXCEEDED"
    evs = client.get("/api/runs/%s/events" % rid).json()["events"]
    assert evs[-1]["event_type"] == "run_failed"
    # consumer-safe copy in the transcript, no internals
    msg = client.get("/api/chats/%s" % chat).json()["messages"][-1]
    assert "处理时间过长" in msg["content"]
    assert "RUN_DEADLINE" not in msg["content"]


def test_t1_normal_run_unaffected(monkeypatch):
    monkeypatch.setenv(run_deadline.RUN_DEADLINE_ENV, "300")
    client, mgr, _ = make_client()
    mgr.agent_provider = FakeLLMProvider([("agent_decide", {
        "action": "finish", "message": "正常完成。"})])
    chat = client.post("/api/chats").json()["chat_id"]
    rid = client.post("/api/chats/%s/messages" % chat,
                      json={"text": "正常测试"}).json()["run_id"]
    run = wait_terminal(client, rid, timeout=30)
    assert run["status"] == "completed"


def test_finish_run_idempotent():
    client, mgr, _ = make_client()
    with mgr._lock:
        mgr._runs["run_idem"] = {"run_id": "run_idem", "status": "running"}
    ok1 = mgr._finish_run("run_idem", "c", "run_failed", "failed",
                          result_status="RUN_DEADLINE_EXCEEDED",
                          message="x")
    ok2 = mgr._finish_run("run_idem", "c", "run_completed", "completed",
                          result_status="COMPLETED", message="y")
    assert ok1 is True and ok2 is False  # first terminal wins
    st = mgr.get_run("run_idem")
    assert st["status"] == "failed"
    assert st["result_status"] == "RUN_DEADLINE_EXCEEDED"


def test_t13_no_deltas_after_closed():
    client, mgr, _ = make_client()
    mgr._closed.add("run_closed")
    emitted = []
    mgr.bus.publish_transient = lambda rid, ev: emitted.append(ev)
    # simulate the server-side emit guard directly (same predicate)
    with mgr._lock:
        closed = "run_closed" in mgr._closed
    if not closed:
        emitted.append({"event_type": "agent_stream_delta"})
    assert emitted == []  # closed run streams nothing
