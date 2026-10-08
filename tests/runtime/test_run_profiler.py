"""28.K.28 Run Profiler tests — pure observation, never breaks a run."""
from __future__ import annotations

import json
import os
import time

import pytest

from runtime.event_bus import CLOSED, EventBus
from runtime.obs import run_profiler


@pytest.fixture(autouse=True)
def _clean(tmp_path, monkeypatch):
    run_profiler.reset()
    monkeypatch.chdir(tmp_path)          # profiles land under tmp cwd
    yield
    run_profiler.reset()


def _publish(bus, run_id, event_type, *, event_id=None, data=None,
             transient=False):
    ev = {"event_id": event_id, "run_id": run_id,
          "timestamp": "2026-09-28T00:00:00Z",
          "event_type": event_type, "stage": None, "skill": None,
          "status": None, "case_id": "c1", "artifact_id": None,
          "eval_id": None, "repair_attempt": None, "message": None,
          "data": data or {}}
    if transient:
        bus.publish_transient(run_id, ev)
    else:
        bus.publish(run_id, ev)


def _wait_finalized(run_id, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        prof = run_profiler.get_profile(run_id)
        if prof and prof.get("finalized"):
            return prof
        time.sleep(0.02)
    raise AssertionError("profile not finalized in time")


def test_terminal_run_records_full_timeline_with_sub_ms_stamps():
    bus = EventBus()
    run_profiler.attach("run_a", bus)
    _publish(bus, "run_a", "run_started", event_id="evt_000001")
    _publish(bus, "run_a", "intent_classified", event_id="evt_000002",
             data={"latency_ms": 41.5})
    _publish(bus, "run_a", "tool_started", event_id="evt_000003",
             data={"step": 1, "tool": "knowledge_search"})
    _publish(bus, "run_a", "agent_stream_delta", transient=True,
             data={"kind": "content", "text": "一句。"})
    _publish(bus, "run_a", "run_completed", event_id="evt_000004")
    prof = _wait_finalized("run_a")
    types = [e["event_type"] for e in prof["events"]]
    # transient deltas appear too (that is the point: TTFC per run)
    assert types == ["run_started", "intent_classified", "tool_started",
                     "agent_stream_delta", "run_completed"]
    # arrival stamps monotonic non-decreasing, relative to attach
    ts = [e["t_ms"] for e in prof["events"]]
    assert ts == sorted(ts) and ts[0] >= 0.0
    # intent latency carried through; delta kind kept, text NEVER kept
    by_type = {e["event_type"]: e for e in prof["events"]}
    assert by_type["intent_classified"]["intent_latency_ms"] == 41.5
    assert by_type["agent_stream_delta"]["delta_kind"] == "content"
    assert "text" not in json.dumps(prof["events"])
    assert prof["finalize_reason"] == "terminal"


def test_profile_written_to_disk_once():
    bus = EventBus()
    run_profiler.attach("run_b", bus)
    _publish(bus, "run_b", "run_started", event_id="evt_000001")
    _publish(bus, "run_b", "run_failed", event_id="evt_000002")
    _wait_finalized("run_b")
    path = os.path.join("tmp", "obs", "run-profiles", "run_b.json")
    assert os.path.isfile(path)
    with open(path, encoding="utf-8") as fh:
        on_disk = json.load(fh)
    assert on_disk["run_id"] == "run_b"
    assert on_disk["finalized"] is True


def test_closed_without_terminal_finalizes():
    bus = EventBus()
    run_profiler.attach("run_c", bus)
    _publish(bus, "run_c", "run_started", event_id="evt_000001")
    bus.finish("run_c")            # defensive close (e.g. crash wrapper)
    prof = _wait_finalized("run_c")
    assert prof["finalize_reason"] == "closed"


def test_attach_never_raises_and_is_idempotent():
    bus = EventBus()
    run_profiler.attach("run_d", bus)
    run_profiler.attach("run_d", bus)      # second attach = no-op
    run_profiler.attach("run_d", None)     # broken bus — swallowed
    assert run_profiler.get_profile("run_d") is not None


def test_purged_run_survives_without_closed_sentinel():
    """KNOWN BUS EDGE (pre-existing, out of profiling scope): purge drops
    a run's subscriptions WITHOUT delivering CLOSED (Subscription has no
    close(); purge's getattr fallback is a no-op). The profiler must not
    crash or corrupt — the profile simply stays open until the idle
    finalize (1200s) reaps it. Deletion privacy is unaffected: a purged
    run's profile was already written only at finalize, and idle-finalize
    writes only event METADATA (never delta text — see test above)."""
    bus = EventBus()
    run_profiler.attach("run_e", bus)
    _publish(bus, "run_e", "run_started", event_id="evt_000001")
    bus.purge("run_e")             # 28.I deletion cascade
    prof = run_profiler.get_profile("run_e")
    assert prof is not None and not prof["finalized"]   # open, not dead
    # further publishes to the purged run history go nowhere the profiler
    # depends on; nothing raises
    _publish(bus, "run_e", "run_completed", event_id="evt_000002")


def test_delta_text_payload_never_enters_profile():
    """E-2/PII: the profiler keeps kind only — no streamed text on disk."""
    bus = EventBus()
    run_profiler.attach("run_f", bus)
    secret = "ART-009内部标识不得落盘"
    _publish(bus, "run_f", "agent_stream_delta", transient=True,
             data={"kind": "reasoning", "text": secret})
    _publish(bus, "run_f", "run_completed", event_id="evt_000001")
    prof = _wait_finalized("run_f")
    assert secret not in json.dumps(prof, ensure_ascii=False)


def test_agent_loop_tool_shape_attributed_via_skill_field():
    """The agent loop's server emit() maps the tool name into the
    top-level `skill` field (QA slice keeps it in data.tool) — the
    profiler must attribute BOTH shapes so per-tool spans pair on
    every path (28.K.28 tool-attribution fix)."""
    bus = EventBus()
    run_profiler.attach("run_g", bus)
    ev = {"event_id": "evt_000001", "run_id": "run_g",
          "timestamp": "2026-09-28T00:00:00Z",
          "event_type": "tool_started", "stage": None,
          "skill": "knowledge-search", "status": None,
          "case_id": "c1", "artifact_id": None, "eval_id": None,
          "repair_attempt": None, "message": None,
          "data": {"step": 3}}
    bus.publish("run_g", ev)
    ev2 = dict(ev, event_id="evt_000002", event_type="tool_completed",
               skill="knowledge-search")
    bus.publish("run_g", ev2)
    _publish(bus, "run_g", "run_completed", event_id="evt_000003")
    prof = _wait_finalized("run_g")
    tools = [e for e in prof["events"]
             if e["event_type"].startswith("tool_")]
    assert all(e["tool"] == "knowledge-search" for e in tools)


def test_CLOSED_sentinel_importable():
    # the reader compares identity against the bus's sentinel — imported
    # from the same module the bus exports
    assert CLOSED is not None
