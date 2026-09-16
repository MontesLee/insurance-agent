"""Web UI Phase 1 — API tests (runtime/server.py).

Drives the FastAPI layer through real runs of the existing orchestrator:
  * health / cases / create-run / get-run / get-events;
  * a full COMPLETED case and a repair-exhausted NEEDS_REVIEW case;
  * the event vocabulary actually covered by a run (run/stage/eval/repair/artifact/
    checkpoint/tool);
  * the safety contract: events carry ids/statuses only — no secrets, no artifact
    payloads, no oversized messages.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_server.py`.
Exit 0 = all checks pass.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, make_client, run_sections, wait_terminal  # noqa: E402

from runtime import events as ev  # noqa: E402

SECTIONS = []
_CACHE: dict = {}


def section(fn):
    SECTIONS.append(fn)
    return fn


FORBIDDEN_KEYS = {"api_key", "apikey", "token", "access_token", "secret", "password",
                  "authorization", "prompt", "system_prompt"}


def _audit_events(evs):
    """Return a list of problems found in the event stream (empty = clean)."""
    problems = []
    for e in evs:
        blob = json.dumps(e, ensure_ascii=False).lower()
        for k in FORBIDDEN_KEYS:
            if '"%s"' % k in blob or '"%s":' % k in blob:
                problems.append("%s leaks key %s" % (e.get("event_id"), k))
        if len(e.get("message") or "") > 600:
            problems.append("%s message too long" % e.get("event_id"))
        if e.get("event_type") not in ev.EVENT_TYPES:
            problems.append("%s unknown type %s" % (e.get("event_id"), e.get("event_type")))
        for f in ("event_id", "run_id", "timestamp", "event_type"):
            if not e.get(f):
                problems.append("%s missing %s" % (e.get("event_id"), f))
        if json.dumps(e.get("data") or {}).count('"payload"'):
            problems.append("%s carries payload content" % e.get("event_id"))
    return problems


def _ensure_happy():
    """Run bm-complete-001 once and cache (client, rid, run, events) for the sections."""
    if "happy" not in _CACHE:
        client, mgr, bus = make_client()
        rid = client.post("/api/runs", json={"case_id": "bm-complete-001"}).json()["run_id"]
        run = wait_terminal(client, rid)
        evs = client.get("/api/runs/%s/events" % rid).json()["events"]
        _CACHE["happy"] = (client, mgr, bus, rid, run, evs)
    return _CACHE["happy"]


@section
def test_health_and_cases(c: Checks):
    client, *_ = _ensure_happy()
    r = client.get("/api/health")
    c.chk("GET /api/health -> 200 ok", r.status_code == 200 and r.json()["status"] == "ok")
    c.chk("health exposes bus stats", "bus" in r.json() and "runs" in r.json()["bus"])

    r = client.get("/api/cases")
    cases = r.json()["cases"]
    c.chk("GET /api/cases -> non-empty catalog", r.status_code == 200 and len(cases) > 0)
    c.chk("case entries are metadata only (id/category/desc/kb)",
          all(set(x) == {"id", "category", "desc", "kb"} for x in cases[:5]))


@section
def test_create_run_validation(c: Checks):
    client, *_ = _ensure_happy()
    client2, *_ = make_client()
    r = client2.post("/api/runs", json={"case_id": "bm-complete-001"})
    body = r.json()
    c.chk("POST /api/runs -> 201 with run_id/case_id/status",
          r.status_code == 201 and body["case_id"] == "bm-complete-001"
          and body["run_id"].startswith("run_")
          and body["status"] in ("queued", "running"), body)

    r = client.post("/api/runs", json={"case_id": "does-not-exist"})
    c.chk("POST /api/runs unknown case -> 404 + available list",
          r.status_code == 404 and "available" in r.json()["detail"]
          and "bm-complete-001" in r.json()["detail"]["available"])


@section
def test_happy_path_run_completes(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    c.chk("run reaches a terminal status",
          run["status"] not in ("queued", "running", None), run["status"])
    c.chk("bm-complete-001 completes", run["status"] == "completed", run["status"])
    c.chk("run metadata carries result_status / timestamps / event_count",
          run["result_status"] == "COMPLETED" and run["started_at"] and run["completed_at"]
          and run["event_count"] > 0, run)
    c.chk("run metadata tracks a current_stage", run["current_stage"] is not None, run)


@section
def test_get_run_endpoints(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    c.chk("GET /api/runs/{id} returns the Run",
          client.get("/api/runs/%s" % rid).json()["run_id"] == rid)
    c.chk("GET /api/runs unknown id -> 404",
          client.get("/api/runs/run_nope").status_code == 404)


@section
def test_events_endpoint_shape_and_coverage(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    r = client.get("/api/runs/%s/events" % rid)
    payload = r.json()
    c.chk("GET /api/runs/{id}/events -> run_id + count + events",
          r.status_code == 200 and payload["run_id"] == rid
          and payload["count"] == len(payload["events"]))
    types = [e["event_type"] for e in evs]
    c.chk("first event is run_started, last is run_completed",
          types[0] == "run_started" and types[-1] == "run_completed", (types[0], types[-1]))
    ids = [e["event_id"] for e in evs]
    c.chk("event ids strictly monotonic", ids == sorted(ids) and len(set(ids)) == len(ids))

    covered = set(types)
    needed = {"run_started", "run_completed",
              "stage_started", "stage_completed",
              "eval_started", "eval_passed",
              "artifact_created", "checkpoint_created",
              "tool_started", "tool_completed"}
    c.chk("event coverage: run/stage/eval/artifact/checkpoint/tool lifecycles present",
          needed <= covered, sorted(needed - covered))

    stages_seen = {e["stage"] for e in evs if e.get("stage")}
    c.chk("all 8 workflow stages appear in the stream", len(stages_seen) == 8, stages_seen)
    evals = [e for e in evs if e["event_type"] in ("eval_passed", "eval_failed")]
    c.chk("eval events carry eval_id + artifact linkage",
          all(e.get("eval_id") for e in evals), [e.get("eval_id") for e in evals][:5])
    arts = [e for e in evs if e["event_type"] == "artifact_created"]
    c.chk("artifact events carry artifact_id only (never content)",
          all(e.get("artifact_id") for e in arts)
          and all("payload" not in json.dumps(e["data"]) for e in arts))
    tools = [e for e in evs if e["event_type"].startswith("tool_")]
    c.chk("tool events identify the evidence provider",
          all(t["data"].get("tool") == "knowledge-search" for t in tools) and len(tools) >= 2)


@section
def test_safety_audit(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    problems = _audit_events(evs)
    c.chk("safety audit: no secrets / no payload content / capped messages / valid types",
          not problems, problems[:3])


@section
def test_events_replay_cursor(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    ids = [e["event_id"] for e in evs]
    mid = ids[9]
    r = client.get("/api/runs/%s/events?after_event_id=%s" % (rid, mid))
    tail = r.json()["events"]
    c.chk("events?after_event_id resumes strictly after the cursor",
          [e["event_id"] for e in tail] == ids[10:], (mid, tail[:1]))
    c.chk("events unknown run -> 404",
          client.get("/api/runs/run_nope/events").status_code == 404)


@section
def test_needs_review_path(c: Checks):
    client, *_ = _ensure_happy()
    if "noev" not in _CACHE:
        rid2 = client.post("/api/runs", json={"case_id": "bm-noev-001"}).json()["run_id"]
        run2 = wait_terminal(client, rid2)
        evs2 = client.get("/api/runs/%s/events" % rid2).json()["events"]
        _CACHE["noev"] = (rid2, run2, evs2)
    rid2, run2, evs2 = _CACHE["noev"]
    c.chk("bm-noev-001 ends needs_review", run2["status"] == "needs_review", run2["status"])
    types2 = [e["event_type"] for e in evs2]
    c.chk("failure path shows eval_failed -> repair_started -> repair_completed -> repair_exhausted",
          all(t in types2 for t in ("eval_failed", "repair_started", "repair_completed",
                                    "repair_exhausted", "stage_failed")),
          sorted(set(types2)))
    c.chk("failure path terminal is run_completed with status=needs_review",
          types2[-1] == "run_completed"
          and evs2[-1].get("status") == "needs_review", evs2[-1].get("status"))
    problems2 = _audit_events(evs2)
    c.chk("safety audit holds on the failure path too", not problems2, problems2[:3])


@section
def test_waiting_path(c: Checks):
    client, *_ = _ensure_happy()
    rid3 = client.post("/api/runs", json={"case_id": "bm-insufficient-001"}).json()["run_id"]
    run3 = wait_terminal(client, rid3)
    c.chk("insufficient-information case parks the run in waiting (client answers pending)",
          run3["status"] == "waiting", run3["status"])


@section
def test_run_isolation(c: Checks):
    client, mgr, bus, rid, run, evs = _ensure_happy()
    if "noev" not in _CACHE:
        test_needs_review_path(c)
    rid2, run2, evs2 = _CACHE["noev"]
    c.chk("each run streams on its own topic (no cross-run leakage)",
          all(e["run_id"] == rid for e in evs) and all(e["run_id"] == rid2 for e in evs2))


def main():
    return run_sections(SECTIONS, "webui_test_server_log.txt", "RUNTIME SERVER")


if __name__ == "__main__":
    sys.exit(main())
