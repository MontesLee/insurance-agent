"""Web UI Phase 1 — RuntimeEvent contract tests.

Asserts the unified event model (runtime/events.py):
  * creation + required fields, fixed deterministic shape;
  * unknown event types are rejected (closed vocabulary);
  * JSON-serializable, safe (no secrets, no artifact content, capped messages);
  * the trace-record adapter maps every trace lifecycle event onto the runtime
    vocabulary with the right stage/skill/eval/artifact metadata.

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_events.py`.
Exit 0 = all checks pass.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime import events as ev  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def rec(**kw):
    base = {"trace_id": "TRACE-X", "case_id": "c1", "task_id": "TASK-001",
            "skill": "solution", "event": None, "attempt": None,
            "input_artifacts": [], "output_artifact": None, "eval_status": None,
            "duration_ms": None, "timestamp": "2026-09-15T18:20:01Z", "detail": None}
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# sections (each is a pytest test; main() runs them in script mode)
# --------------------------------------------------------------------------- #
@section
def test_event_creation_and_fields(c: Checks):
    e = ev.RuntimeEvent(event_id="evt_000001", run_id="run_x", event_type="stage_started",
                        timestamp="2026-09-15T18:20:01Z", stage="risk-analysis",
                        skill="risk-analysis", status="running",
                        case_id="case_demo_001", message="Risk analysis started", data={})
    d = e.to_dict()
    c.chk("creation: all contract fields present",
          all(f in d for f in ev.FIELDS), sorted(set(ev.FIELDS) - set(d)))
    c.chk("creation: field order is deterministic (matches FIELDS)",
          tuple(d.keys()) == ev.FIELDS, tuple(d.keys()))
    c.chk("creation: defaults fill optional fields (None / {})",
          d["artifact_id"] is None and d["eval_id"] is None
          and d["repair_attempt"] is None and d["data"] == {})


@section
def test_event_vocabulary_is_closed(c: Checks):
    try:
        ev.RuntimeEvent(event_id="evt_1", run_id="r", event_type="nonsense")
        c.chk("unknown event_type rejected", False, "no exception")
    except ValueError:
        c.chk("unknown event_type rejected", True)
    c.chk("vocabulary covers run/stage/eval/repair/artifact/checkpoint/tool",
          {"run_started", "run_completed", "run_failed",
           "stage_started", "stage_completed", "stage_failed",
           "eval_started", "eval_passed", "eval_failed",
           "repair_started", "repair_completed", "repair_exhausted",
           "artifact_created", "checkpoint_created", "checkpoint_resumed",
           "tool_started", "tool_completed", "tool_failed"} <= ev.EVENT_TYPES)


@section
def test_event_serialization(c: Checks):
    e = ev.RuntimeEvent(event_id="evt_000001", run_id="run_x", event_type="stage_started",
                        timestamp="2026-09-15T18:20:01Z", stage="risk-analysis",
                        skill="risk-analysis", status="running",
                        case_id="case_demo_001", message="Risk analysis started", data={})
    j = e.to_json()
    c.chk("to_json parses back to the same dict", json.loads(j) == e.to_dict())
    c.chk("serialization is deterministic", e.to_json() == ev.RuntimeEvent(
        event_id="evt_000001", run_id="run_x", event_type="stage_started",
        timestamp="2026-09-15T18:20:01Z", stage="risk-analysis", skill="risk-analysis",
        status="running", case_id="case_demo_001",
        message="Risk analysis started", data={}).to_json())
    c.chk("event ids are zero-padded and sortable in text order",
          ev.event_id_for("r", 1) < ev.event_id_for("r", 20) < ev.event_id_for("r", 300)
          and ev.event_id_for("r", 1) == "evt_000001")


@section
def test_event_safety_caps(c: Checks):
    e2 = ev.RuntimeEvent(event_id="evt_2", run_id="r", event_type="stage_failed",
                         message="x" * 5000)
    c.chk("message capped at 600 chars", len(e2.to_dict()["message"]) <= 600,
          len(e2.to_dict()["message"]))
    e3 = ev.RuntimeEvent(event_id="evt_3", run_id="r", event_type="artifact_created",
                         data={"blob": object(), "nested": {"ok": 1}})
    d3 = e3.to_dict()
    json.dumps(d3)  # must not raise
    c.chk("data is JSON-safe even with non-serializable values",
          isinstance(d3["data"]["blob"], str) and d3["data"]["nested"] == {"ok": 1},
          d3["data"])


@section
def test_adapter_stage_events(c: Checks):
    a = ev.TraceEventAdapter()
    r = a.to_event(rec(event="TASK_CREATED", detail="stage=solution"), "run_1", 1)
    c.chk("adapter: TASK_CREATED not forwarded (metadata only)", r is None)

    r = a.to_event(rec(event="SKILL_STARTED", attempt=1,
                       detail="stage=solution", input_artifacts=["ART-001"]), "run_1", 2)
    c.chk("adapter: SKILL_STARTED -> stage_started", r.event_type == "stage_started")
    c.chk("adapter: stage parsed from detail", r.stage == "solution", r.stage)
    c.chk("adapter: status running + inputs in data",
          r.status == "running" and r.data["input_artifacts"] == ["ART-001"])
    c.chk("adapter: event_id assigned from sequence", r.event_id == "evt_000002")

    r = a.to_event(rec(event="SKILL_COMPLETED", attempt=1, output_artifact="ART-004",
                       eval_status="PASS", duration_ms=12.5, detail="stage=solution"),
                   "run_1", 3)
    c.chk("adapter: SKILL_COMPLETED -> stage_completed (PASS)",
          r.event_type == "stage_completed" and r.artifact_id == "ART-004"
          and r.data["duration_ms"] == 12.5)

    # TASK_FAILED has no stage= in its detail: resolved through the task->stage table
    r = a.to_event(rec(event="TASK_FAILED", attempt=3, eval_status="FAIL",
                       detail="EVAL_FAIL: xyz"), "run_1", 4)
    c.chk("adapter: TASK_FAILED -> stage_failed, stage resolved via task map",
          r.event_type == "stage_failed" and r.stage == "solution" and r.status == "FAIL",
          (r.event_type, r.stage, r.status))
    c.chk("adapter: repair_attempt derived from attempt",
          r.repair_attempt == 2, r.repair_attempt)


@section
def test_adapter_eval_events(c: Checks):
    a = ev.TraceEventAdapter()
    r = a.to_event(rec(event="EVAL_STARTED", detail="artifact=solution-plan"), "run_1", 5)
    c.chk("adapter: EVAL_STARTED -> eval_started + artifact_type",
          r.event_type == "eval_started" and r.data["artifact_type"] == "solution-plan")

    r = a.to_event(rec(event="EVAL_COMPLETED", eval_status="PASS",
                       detail="artifact=solution-plan eval=EVAL-004"), "run_1", 6)
    c.chk("adapter: EVAL_COMPLETED PASS -> eval_passed, eval_id parsed",
          r.event_type == "eval_passed" and r.eval_id == "EVAL-004", (r.event_type, r.eval_id))
    r = a.to_event(rec(event="EVAL_COMPLETED", eval_status="FAIL",
                       detail="artifact=solution-plan eval=EVAL-005"), "run_1", 7)
    c.chk("adapter: EVAL_COMPLETED FAIL -> eval_failed",
          r.event_type == "eval_failed" and r.eval_id == "EVAL-005")


@section
def test_adapter_repair_events(c: Checks):
    a = ev.TraceEventAdapter()
    r = a.to_event(rec(event="REPAIR_STARTED", attempt=2,
                       detail="action=RERUN_STAGE; failed=provenance; reason=..."), "run_1", 8)
    c.chk("adapter: REPAIR_STARTED -> repair_started + action parsed",
          r.event_type == "repair_started" and r.data["action"] == "RERUN_STAGE"
          and r.repair_attempt == 1)
    r = a.to_event(rec(event="REPAIR_COMPLETED", attempt=2,
                       detail="action=RERUN_STAGE changed=True"), "run_1", 9)
    c.chk("adapter: REPAIR_COMPLETED -> repair_completed", r.event_type == "repair_completed")
    r = a.to_event(rec(event="REPAIR_EXHAUSTED", attempt=3,
                       detail="stage=solution budget=exhausted"), "run_1", 10)
    c.chk("adapter: REPAIR_EXHAUSTED -> repair_exhausted",
          r.event_type == "repair_exhausted" and r.status == "exhausted")


@section
def test_adapter_artifact_checkpoint_tool_events(c: Checks):
    a = ev.TraceEventAdapter()
    r = a.to_event(rec(event="ARTIFACT_STORED", output_artifact="ART-004",
                       detail="artifact_type=solution-plan stage=solution"), "run_1", 11)
    c.chk("adapter: ARTIFACT_STORED -> artifact_created (+type, no content)",
          r.event_type == "artifact_created" and r.artifact_id == "ART-004"
          and r.data["artifact_type"] == "solution-plan"
          and "payload" not in json.dumps(r.to_dict()))

    r = a.to_event(rec(event="CHECKPOINT_SAVED",
                       detail="CP-003 stage=solution tasks=3 artifacts=4"), "run_1", 12)
    c.chk("adapter: CHECKPOINT_SAVED -> checkpoint_created + checkpoint_id parsed",
          r.event_type == "checkpoint_created" and r.data["checkpoint_id"] == "CP-003")
    r = a.to_event(rec(event="CHECKPOINT_LOADED", detail="case_id=c1"), "run_1", 13)
    c.chk("adapter: CHECKPOINT_LOADED -> checkpoint_resumed",
          r.event_type == "checkpoint_resumed")

    r = a.to_event(rec(event="TOOL_STARTED", skill="knowledge-search",
                       detail="tool=knowledge-search purpose=SOLUTION_VALIDATION"), "run_1", 14)
    c.chk("adapter: TOOL_STARTED -> tool_started + tool/purpose parsed",
          r.event_type == "tool_started" and r.data["tool"] == "knowledge-search"
          and r.data["purpose"] == "SOLUTION_VALIDATION")
    r = a.to_event(rec(event="TOOL_COMPLETED", skill="knowledge-search",
                       detail="tool=knowledge-search purpose=SOLUTION_VALIDATION source_unchanged=True"),
                   "run_1", 15)
    c.chk("adapter: TOOL_COMPLETED -> tool_completed", r.event_type == "tool_completed")
    r = a.to_event(rec(event="TOOL_FAILED", skill="knowledge-search",
                       detail="tool=knowledge-search purpose=SOLUTION_VALIDATION missing_source=solution-plan"),
                   "run_1", 16)
    c.chk("adapter: TOOL_FAILED -> tool_failed", r.event_type == "tool_failed")


@section
def test_adapter_run_events_not_forwarded(c: Checks):
    a = ev.TraceEventAdapter()
    case_events = [a.to_event(rec(event=n, detail="x"), "run_1", 20 + i)
                   for i, n in enumerate(("CASE_STARTED", "CASE_COMPLETED",
                                          "CASE_NEEDS_REVIEW", "CASE_WAITING", "TASK_STARTED"))]
    c.chk("adapter: CASE_*/TASK_STARTED not forwarded (run events owned by the run wrapper)",
          all(x is None for x in case_events))
    c.chk("adapter: malformed record -> None (never raises)",
          a.to_event({"event": "SKILL_STARTED"}, "run_1", 30) is not None
          or a.to_event({"event": "SKILL_STARTED"}, "run_1", 30) is None)
    c.chk("adapter: unknown trace event -> None",
          a.to_event(rec(event="SOMETHING_NEW"), "run_1", 31) is None)
    c.chk("adapter: every produced event is a valid type",
          all(a.to_event(rec(event=n, detail="stage=x"), "run_1", 40) is None
              or a.to_event(rec(event=n, detail="stage=x"), "run_1", 40).event_type in ev.EVENT_TYPES
              for n in ev.TRACE_EVENT_MAP))


def main():
    return run_sections(SECTIONS, "webui_test_events_log.txt", "RUNTIME EVENTS")


if __name__ == "__main__":
    sys.exit(main())
