"""Web UI Phase 1 — SSE stream tests (GET /api/runs/{run_id}/stream).

Asserts the wire contract the future React UI will rely on:
  * text/event-stream with `event: runtime` + `id:` + `data:` framing;
  * a live run is streamed in order, every event carries an event_id;
  * the stream closes after the terminal event (run_completed / run_failed);
  * reconnection resumes from the cursor: ?after_event_id= AND the standard
    Last-Event-ID header — no duplicates, no gaps;
  * a completed run can still be streamed (full replay then close).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_sse.py`.
Exit 0 = all checks pass.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, make_client, run_sections, stream_events, wait_terminal  # noqa: E402

SECTIONS = []
_CACHE: dict = {}


def section(fn):
    SECTIONS.append(fn)
    return fn


def _ensure_streamed_run():
    """Stream one full bm-complete-001 run live and cache the results for sections."""
    if "run" not in _CACHE:
        client, mgr, bus = make_client()
        rid = client.post("/api/runs", json={"case_id": "bm-complete-001"}).json()["run_id"]

        with client.stream("GET", "/api/runs/%s/stream" % rid) as resp:
            raw = [l for l in resp.iter_lines()]
            meta = (resp.status_code, resp.headers.get("content-type"),
                    resp.headers.get("x-accel-buffering"))
        evs = [json.loads(l[6:]) for l in raw if l.startswith("data: ")]
        _CACHE["run"] = (client, mgr, bus, rid, raw, meta, evs)
    return _CACHE["run"]


@section
def test_stream_endpoint_validation(c: Checks):
    client, *_ = _ensure_streamed_run()
    r = client.get("/api/runs/run_nope/stream")
    c.chk("stream unknown run -> 404", r.status_code == 404)


@section
def test_stream_headers_and_framing(c: Checks):
    client, mgr, bus, rid, raw, meta, evs = _ensure_streamed_run()
    status, ctype, xab = meta
    c.chk("stream -> 200 text/event-stream",
          status == 200 and ctype.startswith("text/event-stream"), ctype)
    c.chk("stream disables proxy buffering", xab == "no")

    # walk the wire format: messages are [event:/id:/data:] triplets separated by
    # blank lines; ': keep-alive' comments may appear between them
    i, messages, framing_ok = 0, 0, True
    while i < len(raw):
        if raw[i] == "" or raw[i].startswith(":"):
            i += 1
            continue
        if (raw[i].startswith("event: runtime") and i + 2 < len(raw)
                and raw[i + 1].startswith("id: evt_")
                and raw[i + 2].startswith("data: ")):
            messages += 1
            i += 3
        else:
            framing_ok = False
            break
    c.chk("SSE framing: 'event: runtime' + 'id: evt_*' + 'data: {json}' per message",
          framing_ok and messages >= 10, raw[:6])


@section
def test_stream_delivers_whole_run(c: Checks):
    client, mgr, bus, rid, raw, meta, evs = _ensure_streamed_run()
    types = [e["event_type"] for e in evs]
    ids = [e["event_id"] for e in evs]
    c.chk("stream receives the whole run: run_started first",
          len(evs) > 10 and types[0] == "run_started", (len(evs), types[:1]))
    c.chk("run completion is delivered then the stream CLOSES",
          types[-1] in ("run_completed", "run_failed") and types[-1] == "run_completed",
          types[-1])
    c.chk("every event carries an event_id",
          all(ids) and all(i.startswith("evt_") for i in ids))
    c.chk("event ordering preserved (ids strictly increasing)",
          ids == sorted(ids) and len(set(ids)) == len(ids))
    c.chk("run reaches completed after streaming",
          wait_terminal(client, rid)["status"] == "completed")

    hist = client.get("/api/runs/%s/events" % rid).json()["events"]
    c.chk("streamed events == full event history (no loss)",
          ids == [e["event_id"] for e in hist])


@section
def test_stream_replay_after_completion(c: Checks):
    client, mgr, bus, rid, raw, meta, evs = _ensure_streamed_run()
    ids = [e["event_id"] for e in evs]
    evs2 = stream_events(client, "/api/runs/%s/stream" % rid)
    c.chk("streaming a finished run replays the full history and closes",
          [e["event_id"] for e in evs2] == ids)


@section
def test_stream_resume_with_cursor(c: Checks):
    client, mgr, bus, rid, raw, meta, evs = _ensure_streamed_run()
    ids = [e["event_id"] for e in evs]
    mid = ids[9]
    evs3 = stream_events(client, "/api/runs/%s/stream?after_event_id=%s" % (rid, mid))
    c.chk("resume via ?after_event_id starts strictly after the cursor",
          [e["event_id"] for e in evs3] == ids[10:], [e["event_id"] for e in evs3][:1])
    c.chk("resume sends no duplicates and no gaps",
          sorted(set(ids)) == sorted(set([e["event_id"] for e in evs3] + ids[:10])))

    evs4 = stream_events(client, "/api/runs/%s/stream" % rid, headers={"Last-Event-ID": mid})
    c.chk("resume via Last-Event-ID header identical to query-param resume",
          [e["event_id"] for e in evs4] == [e["event_id"] for e in evs3])
    evs5 = stream_events(client, "/api/runs/%s/stream" % rid, headers={"Last-Event-ID": ids[-1]})
    c.chk("resume from the terminal event yields an empty stream",
          evs5 == [], [e["event_id"] for e in evs5][:3])


@section
def test_failure_path_stream(c: Checks):
    client, *_ = _ensure_streamed_run()
    rid2 = client.post("/api/runs", json={"case_id": "bm-noev-001"}).json()["run_id"]
    evs6 = stream_events(client, "/api/runs/%s/stream" % rid2)
    types6 = [e["event_type"] for e in evs6]
    c.chk("needs_review run still terminates with run_completed + closes",
          types6[-1] == "run_completed" and evs6[-1]["status"] == "needs_review",
          (types6[-1], evs6[-1].get("status")))


def main():
    return run_sections(SECTIONS, "webui_test_sse_log.txt", "RUNTIME SSE")


if __name__ == "__main__":
    sys.exit(main())
