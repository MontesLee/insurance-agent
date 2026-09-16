"""Runtime Events — the unified event contract for observers (Web UI Phase 1).

One event model shared by everything that watches a run:

    Existing Runtime -> trace.emit() -> trace records -> TraceEventAdapter
                                                              |
    trace.jsonl  (replay / debug) <---------------------------+----> Event Bus -> SSE -> React UI

The event is METADATA ONLY. It never carries artifact content, prompts, secrets or
client-identifying values — ids, statuses, counters and short messages only. The full
artifacts stay in CaseState / the artifact registry; the full execution record stays in
`state["trace"]` / `trace.jsonl`. An observer that wants detail follows the ids.

Design rule (spec: "UI 是 Runtime 的观察者，而不是 Runtime 的主人"):
    publishing an event can never influence execution — the adapter is a pure function of
    the trace record, and the bus swallows every failure (see runtime/event_bus.py).
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

# --------------------------------------------------------------------------- #
# event vocabulary
# --------------------------------------------------------------------------- #
EVENT_TYPES = frozenset({
    # run lifecycle
    "run_started", "run_completed", "run_failed",
    # stage lifecycle
    "stage_started", "stage_completed", "stage_failed",
    # eval lifecycle
    "eval_started", "eval_passed", "eval_failed",
    # repair lifecycle
    "repair_started", "repair_completed", "repair_exhausted",
    # artifacts
    "artifact_created",
    # checkpoints
    "checkpoint_created", "checkpoint_resumed",
    # tool / shared-service lifecycle (knowledge-search Evidence Provider)
    "tool_started", "tool_completed", "tool_failed",
})

# events after which a run's stream is closed
RUN_TERMINAL_TYPES = frozenset({"run_completed", "run_failed"})

# message cap: events are telemetry, not logs — long eval reasons are truncated
_MESSAGE_LIMIT = 600

# stable field order for to_dict() (deterministic serialization)
FIELDS = (
    "event_id", "run_id", "timestamp", "event_type", "stage", "skill", "status",
    "case_id", "artifact_id", "eval_id", "repair_attempt", "message", "data",
)


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def event_id_for(run_id: str, seq: int) -> str:
    """Monotonic, zero-padded, per-run event id — the SSE resume cursor."""
    return "evt_%06d" % seq


# --------------------------------------------------------------------------- #
# sanitization helpers
# --------------------------------------------------------------------------- #
def _clean_str(val: Any, limit: int = _MESSAGE_LIMIT) -> Optional[str]:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _json_safe(val: Any, depth: int = 0) -> Any:
    """Coerce anything into JSON-serializable scalars/containers (defensive)."""
    if depth > 6:
        return _clean_str(val, 120)
    if isinstance(val, dict):
        return {str(k): _json_safe(v, depth + 1) for k, v in list(val.items())[:64]}
    if isinstance(val, (list, tuple)):
        return [_json_safe(v, depth + 1) for v in list(val)[:64]]
    if isinstance(val, (str, int, float, bool)) or val is None:
        return val
    return _clean_str(val, 200)


class RuntimeEvent:
    """One observable thing that happened during a run. Immutable value object."""

    __slots__ = FIELDS

    def __init__(self, event_id: str, run_id: str, event_type: str, *,
                 timestamp: Optional[str] = None, stage: Optional[str] = None,
                 skill: Optional[str] = None, status: Optional[str] = None,
                 case_id: Optional[str] = None, artifact_id: Optional[str] = None,
                 eval_id: Optional[str] = None, repair_attempt: Optional[int] = None,
                 message: Optional[str] = None, data: Optional[dict] = None):
        if event_type not in EVENT_TYPES:
            raise ValueError("unknown event_type: %r (known: %s)"
                             % (event_type, sorted(EVENT_TYPES)))
        self.event_id = event_id
        self.run_id = run_id
        self.timestamp = timestamp or now_iso()
        self.event_type = event_type
        self.stage = stage
        self.skill = skill
        self.status = status
        self.case_id = case_id
        self.artifact_id = artifact_id
        self.eval_id = eval_id
        self.repair_attempt = repair_attempt
        self.message = _clean_str(message)
        self.data = _json_safe(dict(data or {}))

    def to_dict(self) -> dict:
        """Deterministic, JSON-serializable dict (all declared fields, fixed order)."""
        return {f: getattr(self, f) for f in FIELDS}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=False)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "RuntimeEvent(%s %s run=%s stage=%s)" % (
            self.event_id, self.event_type, self.run_id, self.stage)


# --------------------------------------------------------------------------- #
# trace record -> RuntimeEvent
# --------------------------------------------------------------------------- #
# Which trace events become runtime events. CASE_* run-level records are NOT mapped:
# the run wrapper (runtime/server.py RunManager) emits run_started / run_completed /
# run_failed exactly once per run, with the true final status — a trace CASE_* record
# cannot know whether the wrapper will pause-and-approve and continue.
TRACE_EVENT_MAP = {
    "SKILL_STARTED": "stage_started",
    "SKILL_COMPLETED": "stage_completed",
    "TASK_FAILED": "stage_failed",
    "EVAL_STARTED": "eval_started",
    "EVAL_COMPLETED": None,          # -> eval_passed | eval_failed (by eval_status)
    "REPAIR_STARTED": "repair_started",
    "REPAIR_COMPLETED": "repair_completed",
    "REPAIR_EXHAUSTED": "repair_exhausted",
    "ARTIFACT_STORED": "artifact_created",
    "CHECKPOINT_SAVED": "checkpoint_created",
    "CHECKPOINT_LOADED": "checkpoint_resumed",
    "TOOL_STARTED": "tool_started",
    "TOOL_COMPLETED": "tool_completed",
    "TOOL_FAILED": "tool_failed",
}

# detail-string extracts. The formats are those runtime/orchestrator.py emits; the
# parser is defensive (None when absent) so a wording change degrades gracefully.
_RE_STAGE = re.compile(r"(?:^|[\s;])stage=([A-Za-z0-9_.\-]+)")
_RE_ARTIFACT_TYPE = re.compile(r"artifact_type=([A-Za-z0-9_.\-]+)")
_RE_EVAL = re.compile(r"(?:^|[\s;])eval=([A-Za-z0-9_\-]+)")
_RE_ARTIFACT = re.compile(r"(?:^|[\s;])artifact=([A-Za-z0-9_.\-]+)")
_RE_ACTION = re.compile(r"action=([A-Za-z0-9_\-]+)")
_RE_CHECKPOINT = re.compile(r"(?:^|[\s])(CP-[0-9]+)")
_RE_TOOL = re.compile(r"tool=([A-Za-z0-9_.\-]+)")
_RE_PURPOSE = re.compile(r"purpose=([A-Za-z0-9_\-]+)")


def _find(pattern: re.Pattern, detail: Optional[str]) -> Optional[str]:
    if not detail:
        return None
    m = pattern.search(detail)
    if not m:
        return None
    val = m.group(1)
    return None if val == "None" else val   # guard against "stage=%s" % None slips


class TraceEventAdapter:
    """Stateful mapper: trace records in, RuntimeEvents out.

    Stateless mapping except for the task_id -> stage_id table learned from
    TASK_CREATED records (which carry `stage=` in their detail), so stage can be
    resolved for records that only carry a task_id (e.g. TASK_FAILED).
    """

    def __init__(self):
        self._task_stage: dict = {}

    def to_event(self, rec: dict, run_id: str, seq: int) -> Optional[RuntimeEvent]:
        """Convert one trace record. Returns None when the record is not observer-relevant."""
        try:
            return self._to_event(rec, run_id, seq)
        except Exception:  # noqa: BLE001 — observability must never break the run
            return None

    def _to_event(self, rec: dict, run_id: str, seq: int) -> Optional[RuntimeEvent]:
        ev_name = rec.get("event")
        detail = rec.get("detail")
        task_id = rec.get("task_id")

        if ev_name == "TASK_CREATED":
            stage = _find(_RE_STAGE, detail)
            if task_id and stage:
                self._task_stage[task_id] = stage
            return None

        event_type = TRACE_EVENT_MAP.get(ev_name)
        if event_type is None and ev_name != "EVAL_COMPLETED":
            return None  # CASE_* / TASK_STARTED etc. are not forwarded (see map comment)

        stage = _find(_RE_STAGE, detail) or self._task_stage.get(task_id)
        skill = rec.get("skill")
        attempt = rec.get("attempt") if isinstance(rec.get("attempt"), int) else None
        common = {
            "event_id": event_id_for(run_id, seq),
            "run_id": run_id,
            "timestamp": rec.get("timestamp") or now_iso(),
            "stage": stage,
            "skill": skill,
            "case_id": rec.get("case_id"),
            "message": _clean_str(detail),
            "data": {"trace_id": rec.get("trace_id")},
        }

        if ev_name == "SKILL_STARTED":
            return RuntimeEvent(event_type="stage_started", status="running",
                                repair_attempt=(attempt - 1) if attempt and attempt > 1 else None,
                                data={**common["data"],
                                      "attempt": attempt,
                                      "input_artifacts": list(rec.get("input_artifacts") or [])},
                                **_kw(common))
        if ev_name == "SKILL_COMPLETED":
            return RuntimeEvent(event_type="stage_completed",
                                status=rec.get("eval_status") or "PASS",
                                artifact_id=rec.get("output_artifact"),
                                repair_attempt=(attempt - 1) if attempt and attempt > 1 else None,
                                data={**common["data"],
                                      "attempt": attempt,
                                      "duration_ms": rec.get("duration_ms")},
                                **_kw(common))
        if ev_name == "TASK_FAILED":
            return RuntimeEvent(event_type="stage_failed",
                                status=rec.get("eval_status") or "ERROR",
                                repair_attempt=(attempt - 1) if attempt and attempt > 1 else None,
                                data={**common["data"], "attempt": attempt},
                                **_kw(common))
        if ev_name == "EVAL_STARTED":
            return RuntimeEvent(event_type="eval_started", status="running",
                                artifact_id=rec.get("output_artifact"),
                                data={**common["data"],
                                      "artifact_type": _find(_RE_ARTIFACT, detail)},
                                **_kw(common))
        if ev_name == "EVAL_COMPLETED":
            passed = (rec.get("eval_status") == "PASS")
            return RuntimeEvent(event_type="eval_passed" if passed else "eval_failed",
                                status=rec.get("eval_status"),
                                eval_id=_find(_RE_EVAL, detail),
                                artifact_id=rec.get("output_artifact"),
                                data={**common["data"],
                                      "artifact_type": _find(_RE_ARTIFACT, detail)},
                                **_kw(common))
        if ev_name == "REPAIR_STARTED":
            return RuntimeEvent(event_type="repair_started", status="running",
                                repair_attempt=(attempt - 1) if attempt else None,
                                data={**common["data"], "action": _find(_RE_ACTION, detail)},
                                **_kw(common))
        if ev_name == "REPAIR_COMPLETED":
            return RuntimeEvent(event_type="repair_completed", status="completed",
                                repair_attempt=(attempt - 1) if attempt else None,
                                data={**common["data"], "action": _find(_RE_ACTION, detail)},
                                **_kw(common))
        if ev_name == "REPAIR_EXHAUSTED":
            return RuntimeEvent(event_type="repair_exhausted", status="exhausted",
                                repair_attempt=(attempt - 1) if attempt else None,
                                **_kw(common))
        if ev_name == "ARTIFACT_STORED":
            return RuntimeEvent(event_type="artifact_created", status="created",
                                artifact_id=rec.get("output_artifact"),
                                data={**common["data"],
                                      "artifact_type": _find(_RE_ARTIFACT_TYPE, detail)},
                                **_kw(common))
        if ev_name == "CHECKPOINT_SAVED":
            return RuntimeEvent(event_type="checkpoint_created", status="saved",
                                data={**common["data"],
                                      "checkpoint_id": _find(_RE_CHECKPOINT, detail)},
                                **_kw(common))
        if ev_name == "CHECKPOINT_LOADED":
            return RuntimeEvent(event_type="checkpoint_resumed", status="resumed",
                                **_kw(common))
        if ev_name in ("TOOL_STARTED", "TOOL_COMPLETED", "TOOL_FAILED"):
            status = {"TOOL_STARTED": "running", "TOOL_COMPLETED": "completed",
                      "TOOL_FAILED": "failed"}[ev_name]
            return RuntimeEvent(event_type={"TOOL_STARTED": "tool_started",
                                            "TOOL_COMPLETED": "tool_completed",
                                            "TOOL_FAILED": "tool_failed"}[ev_name],
                                status=status,
                                data={**common["data"],
                                      "tool": _find(_RE_TOOL, detail),
                                      "purpose": _find(_RE_PURPOSE, detail)},
                                **_kw(common))
        return None


def _kw(common: dict) -> dict:
    """Positional-arg helper: the shared fields every mapped event carries."""
    return {k: v for k, v in common.items() if k not in ("data",)}
