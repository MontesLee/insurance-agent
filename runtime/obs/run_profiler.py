"""Run Profiler — End-to-End latency instrumentation (Phase 28.K.28).

Pure OBSERVATION tap on the existing EventBus: for every run, one
dedicated subscriber + one daemon reader thread stamp each incoming
event (durable AND transient) with a monotonic arrival time. The
recorded timeline answers, per chat turn:

    T0  attach (run registration — request received + worker spawn)
    ..  run_started / intent_classified (data.latency_ms already exact)
    ..  tool_started/tool_completed  (knowledge search & tool spans)
    ..  agent_step_started × N       (per-step spans)
    ..  agent_stream_delta arrivals  (TTFT / TTFC per step, sub-ms)
    T7  run_completed / run_failed   (terminal)

Design rules (this module can never affect a run):
  * everything is wrapped fail-quiet — a profiler bug degrades to a
    missing profile file, never a broken turn;
  * the reader thread drains a bounded subscriber queue (the bus drops
    for a slow subscriber rather than blocking the publisher);
  * finalize on CLOSED / terminal / idle-timeout; the profile is
    written ONCE to tmp/obs/run-profiles/{run_id}.json (gitignored).

This is INSTRUMENTATION ONLY (profiling phase): no business logic, no
prompts, no timeouts, no retries are read or changed here.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Optional

from runtime.event_bus import CLOSED

# idle safety: a run whose stream goes silent longer than this is
# finalized defensively (deadline is 900s; +300s slack) — the reader
# thread never lingers forever on a crashed run.
_IDLE_FINALIZE_S = 1200.0

_PROFILE_DIR = os.path.join("tmp", "obs", "run-profiles")

_lock = threading.Lock()
_profiles: dict = {}      # run_id -> {"events": [...], "finalized": bool}
_threads: dict = {}       # run_id -> threading.Thread


def attach(run_id: str, bus) -> None:
    """Start profiling ONE run. Never raises; idempotent per run."""
    try:
        with _lock:
            if run_id in _profiles:
                return
            _profiles[run_id] = {
                "run_id": run_id,
                "attach_wall": time.time(),
                "attach_mono": time.perf_counter(),
                "attach_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime()),
                "events": [],
                "finalized": False,
            }
        sub = bus.subscribe(run_id)

        def _reader():
            last_seen = time.monotonic()
            while True:
                try:
                    item = sub.get(timeout=5.0)
                except Exception:  # queue.Empty — idle check
                    if time.monotonic() - last_seen > _IDLE_FINALIZE_S:
                        _finalize(run_id, reason="idle_timeout")
                        return
                    continue
                if item is CLOSED:
                    _finalize(run_id, reason="closed")
                    return
                _record(run_id, item)
                last_seen = time.monotonic()
                if item.get("event_type") in ("run_completed",
                                              "run_failed"):
                    # terminal: still drain briefly for stragglers, then
                    # finalize (the bus closes subscribers on terminal,
                    # so CLOSED normally arrives immediately)
                    _finalize(run_id, reason="terminal")
                    return

        t = threading.Thread(target=_reader, daemon=True,
                             name="run-profiler-" + run_id)
        with _lock:
            _threads[run_id] = t
        t.start()
    except Exception as e:  # noqa: BLE001 — observation must never break
        print("[run_profiler] attach failed for %s (ignored): %r"
              % (run_id, e), file=sys.stderr)


def _record(run_id: str, item: dict) -> None:
    """Stamp one event arrival (sub-ms, monotonic, relative to attach)."""
    try:
        now = time.perf_counter()
        with _lock:
            prof = _profiles.get(run_id)
            if prof is None or prof["finalized"]:
                return
            data = item.get("data") or {}
            delta = data if item.get("event_type") == \
                "agent_stream_delta" else {}
            # tool attribution lives in TWO shapes by path: the QA slice
            # emits {data: {tool}}; the agent loop's server emit() maps
            # the tool name into the top-level `skill` field. Capture
            # both so tool spans pair identically on every path.
            tool = (data.get("tool") if isinstance(data, dict)
                    and data.get("tool") else item.get("skill"))
            prof["events"].append({
                # arrival time relative to attach, milliseconds
                "t_ms": round((now - prof["attach_mono"]) * 1000.0, 1),
                # the event's own (second-resolution) timestamp
                "ts": item.get("timestamp"),
                "event_id": item.get("event_id"),
                "event_type": item.get("event_type"),
                "status": item.get("status"),
                "step": (data.get("step")
                         if isinstance(data, dict) else None),
                "tool": tool,
                # deltas: kind only — never the text payload (PII/E-2)
                "delta_kind": (delta.get("kind")
                               if isinstance(delta, dict) else None),
                # 28.K.29-A: answer-channel routing (final/ask message
                # stream) vs step-channel content
                "delta_channel": (delta.get("channel")
                                  if isinstance(delta, dict) else None),
                "intent_latency_ms": (
                    data.get("latency_ms")
                    if item.get("event_type") == "intent_classified"
                    and isinstance(data, dict) else None),
            })
    except Exception as e:  # noqa: BLE001
        print("[run_profiler] record failed for %s (ignored): %r"
              % (run_id, e), file=sys.stderr)


def _finalize(run_id: str, reason: str) -> None:
    """Freeze the profile and write it ONCE to disk."""
    try:
        with _lock:
            prof = _profiles.get(run_id)
            if prof is None or prof["finalized"]:
                return
            prof["finalized"] = True
            prof["finalize_reason"] = reason
            prof["wall_duration_ms"] = round(
                (time.perf_counter() - prof["attach_mono"]) * 1000.0, 1)
            payload = dict(prof)
        os.makedirs(_PROFILE_DIR, exist_ok=True)
        path = os.path.join(_PROFILE_DIR, "%s.json" % run_id)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
        os.replace(tmp_path, path)
        # bound the in-memory registry (keep the most recent 200)
        with _lock:
            if len(_profiles) > 200:
                for rid in sorted(_profiles)[:len(_profiles) - 200]:
                    _profiles.pop(rid, None)
                    _threads.pop(rid, None)
    except Exception as e:  # noqa: BLE001
        print("[run_profiler] finalize failed for %s (ignored): %r"
              % (run_id, e), file=sys.stderr)


def get_profile(run_id: str) -> Optional[dict]:
    """In-memory profile (tests / live inspection); None when unknown."""
    with _lock:
        prof = _profiles.get(run_id)
        return dict(prof) if prof else None


def reset() -> None:
    """Test seam: drop all in-memory state."""
    with _lock:
        _profiles.clear()
        _threads.clear()
