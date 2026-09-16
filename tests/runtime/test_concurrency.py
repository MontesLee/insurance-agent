"""Web UI Phase 1.1 — concurrency & event-attribution tests.

Guards the two Phase 1 audit findings and the tap-registration bug they exposed:

  M-1  a case with an ACTIVE run must reject POST /api/runs with 409 and must
       never start a second run (trace routing is keyed by case_id — a second
       run would mis-attribute the first run's events);
  M-2  the TraceEventAdapter must be run-scoped (task ids like TASK-001 repeat
       across runs, so a shared adapter cross-contaminates stage attribution);
  TAP  concurrent runs must each register a DISTINCT trace sink (equal bound
       methods collapse in trace.add_sink and would double every event).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_concurrency.py`.
Exit 0 = all checks pass.
"""
from __future__ import annotations

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, make_client, run_sections, wait_terminal  # noqa: E402

from runtime import events as ev  # noqa: E402

SECTIONS = []
_CACHE: dict = {}


def section(fn):
    SECTIONS.append(fn)
    return fn


def _events(client, rid):
    return client.get("/api/runs/%s/events" % rid).json()["events"]


def _ensure_parallel():
    """Run three different cases concurrently once; cache results for the sections."""
    if "par" not in _CACHE:
        client, mgr, bus = make_client()
        posts = [("bm-complete-001", client.post("/api/runs", json={"case_id": "bm-complete-001"})),
                 ("bm-complete-002", client.post("/api/runs", json={"case_id": "bm-complete-002"})),
                 ("bm-complete-003", client.post("/api/runs", json={"case_id": "bm-complete-003"}))]
        runs = [wait_terminal(client, r.json()["run_id"]) for _, r in posts]
        evs = [_events(client, r.json()["run_id"]) for _, r in posts]
        _CACHE["par"] = (client, mgr, bus, posts, runs, evs)
    return _CACHE["par"]


# --------------------------------------------------------------------------- #
# Test 1 — same case concurrent run is REJECTED (M-1)
# --------------------------------------------------------------------------- #
@section
def test_same_case_concurrent_run_rejected(c: Checks):
    client, mgr, bus = make_client()
    r1 = client.post("/api/runs", json={"case_id": "bm-noev-001"})
    c.chk("first POST /api/runs -> 201", r1.status_code == 201, (r1.status_code, r1.text))
    rid = r1.json()["run_id"]

    r2 = client.post("/api/runs", json={"case_id": "bm-noev-001"})
    body = r2.json()
    c.chk("second POST for the SAME case -> 409", r2.status_code == 409, r2.status_code)
    c.chk("409 body is the exact contract shape",
          body.get("error") == "case_already_running" and body.get("run_id") == rid
          and body.get("case_id") == "bm-noev-001", body)
    c.chk("no second run was created (registry holds exactly one run)",
          len(mgr._runs) == 1, sorted(mgr._runs))
    c.chk("the case slot still points at the first run",
          mgr._active.get("bm-noev-001") == rid, mgr._active)

    # Run A is unaffected by the rejected POST
    runA = wait_terminal(client, rid)
    c.chk("run A completes normally after the 409", runA["status"] == "needs_review",
          runA["status"])
    evs = _events(client, rid)
    c.chk("run A has exactly one run_started / one terminal event",
          [e["event_type"] for e in evs].count("run_started") == 1
          and [e["event_type"] for e in evs][-1] in ("run_completed", "run_failed"))

    # once A is finished the case slot is released and the case can run again
    r3 = client.post("/api/runs", json={"case_id": "bm-noev-001"})
    c.chk("after terminal status, the same case can run again -> 201",
          r3.status_code == 201, r3.status_code)
    runB = wait_terminal(client, r3.json()["run_id"])
    c.chk("the follow-up run is a fresh, independent run",
          runB["run_id"] != rid and runB["event_count"] > 0, runB)


# --------------------------------------------------------------------------- #
# Test 2 — different cases CAN run concurrently (M-1 must not over-block)
# --------------------------------------------------------------------------- #
@section
def test_different_cases_run_in_parallel(c: Checks):
    client, mgr, bus, posts, runs, evs = _ensure_parallel()
    c.chk("all three concurrent POSTs accepted (201, no 409)",
          all(r.status_code == 201 for _, r in posts),
          [(case, r.status_code) for case, r in posts])
    c.chk("all three runs completed", all(x["status"] == "completed" for x in runs),
          [x["status"] for x in runs])

    # overlap proof: every run started before the FIRST completion landed
    first_done = min(x["completed_at"] for x in runs)
    c.chk("runs genuinely overlapped in time",
          all(x["started_at"] < first_done for x in runs),
          [(x["run_id"], x["started_at"], x["completed_at"]) for x in runs])

    rids = [r.json()["run_id"] for _, r in posts]
    cases = [case for case, _ in posts]
    c.chk("each run's events all carry that run's run_id",
          all(all(e["run_id"] == rid for e in es) for rid, es in zip(rids, evs)))
    # event_ids are per-run cursors (evt_000001... in every run by design), so
    # disjointness is (run_id, event_id) pairs: no pair may repeat across the union
    c.chk("run topics are disjoint (no (run_id, event_id) pair appears twice)",
          len({(e["run_id"], e["event_id"]) for es in evs for e in es})
          == sum(len(es) for es in evs))


# --------------------------------------------------------------------------- #
# Test 3 — TraceEventAdapter state is NOT shared between runs (M-2)
# --------------------------------------------------------------------------- #
@section
def test_adapter_state_not_shared(c: Checks):
    adapter_a, adapter_b = ev.TraceEventAdapter(), ev.TraceEventAdapter()

    def rec(task_id, **kw):
        base = {"trace_id": "TRACE-X", "case_id": "c1", "task_id": task_id,
                "skill": "s", "event": None, "attempt": None, "input_artifacts": [],
                "output_artifact": None, "eval_status": None, "duration_ms": None,
                "timestamp": "2026-09-15T18:20:01Z", "detail": None}
        base.update(kw)
        return base

    # same task_id, DIFFERENT stage in each run (task ids repeat across runs)
    adapter_a.to_event(rec("TASK-001", event="TASK_CREATED", detail="stage=solution"),
                       "run_A", 1)
    adapter_b.to_event(rec("TASK-001", event="TASK_CREATED", detail="stage=report-generation"),
                       "run_B", 1)
    c.chk("adapters hold separate internal tables",
          adapter_a._task_stage is not adapter_b._task_stage
          and adapter_a._task_stage != adapter_b._task_stage,
          (adapter_a._task_stage, adapter_b._task_stage))

    # a TASK_FAILED with no stage= in detail resolves through each run's own table
    fa = adapter_a.to_event(rec("TASK-001", event="TASK_FAILED", eval_status="FAIL",
                                detail="EVAL_FAIL: x"), "run_A", 2)
    fb = adapter_b.to_event(rec("TASK-001", event="TASK_FAILED", eval_status="FAIL",
                                detail="EVAL_FAIL: x"), "run_B", 2)
    c.chk("run A resolves its own stage (solution)",
          fa is not None and fa.stage == "solution" and fa.run_id == "run_A", fa)
    c.chk("run B resolves its own stage (report-generation)",
          fb is not None and fb.stage == "report-generation" and fb.run_id == "run_B", fb)
    c.chk("teaching adapter B did not change adapter A's mapping",
          adapter_a._task_stage == {"TASK-001": "solution"}, adapter_a._task_stage)


# --------------------------------------------------------------------------- #
# Test 4 — provenance holds under concurrency (run_id AND case_id per event)
# --------------------------------------------------------------------------- #
@section
def test_provenance_under_concurrency(c: Checks):
    client, mgr, bus, posts, runs, evs = _ensure_parallel()
    cases = [case for case, _ in posts]
    rids = [r.json()["run_id"] for _, r in posts]

    for case, rid, es in zip(cases, rids, evs):
        c.chk("%s: every event.run_id == %s" % (case, rid),
              all(e["run_id"] == rid for e in es),
              [e["event_id"] for e in es if e["run_id"] != rid][:3])
        c.chk("%s: every event.case_id == %s (no cross-case attribution)" % (case, case),
              all(e.get("case_id") == case for e in es),
              [(e["event_id"], e.get("case_id")) for e in es if e.get("case_id") != case][:3])

    # no duplicated content from double tap-registration: a concurrent run must
    # produce exactly as many events as the same case run alone
    solo_client, _, _ = make_client()
    solo_rid = solo_client.post("/api/runs", json={"case_id": "bm-complete-001"}).json()["run_id"]
    solo = wait_terminal(solo_client, solo_rid)
    solo_events = _events(solo_client, solo_rid)
    par_events = evs[0]
    c.chk("concurrent run event count == solo run event count (no tap double-dispatch)",
          len(par_events) == len(solo_events) == solo["event_count"],
          (len(par_events), len(solo_events), solo["event_count"]))

    # structural integrity per run
    workflow_stages = {"client-intake", "requirement-analysis", "risk-analysis",
                       "coverage-gap-analysis", "solution", "product-candidate-provider",
                       "product-recommendation", "report-generation"}
    for case, rid, es in zip(cases, rids, evs):
        ids = [e["event_id"] for e in es]
        c.chk("%s: event ids contiguous and unique" % case,
              ids == ["evt_%06d" % i for i in range(1, len(es) + 1)], ids[:3] + ids[-3:])
        types = [e["event_type"] for e in es]
        c.chk("%s: exactly one run_started and one terminal event" % case,
              types.count("run_started") == 1
              and sum(1 for t in types if t in ("run_completed", "run_failed")) == 1)
        stages = {e["stage"] for e in es if e.get("stage")}
        c.chk("%s: stage names all belong to the workflow" % case,
              stages <= workflow_stages, stages - workflow_stages)


def main():
    return run_sections(SECTIONS, "webui_test_concurrency_log.txt", "RUNTIME CONCURRENCY")


if __name__ == "__main__":
    sys.exit(main())
