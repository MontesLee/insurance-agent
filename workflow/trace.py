"""Execution Trace (Step 4 Phase 2).

A structured, queryable record of every agent action. It complements the older
append-only `state["events"]` log with the spec §4 fields so the trace can answer
"why did this case not recommend a product?" at a glance (spec §6).

Each record carries:
    trace_id, case_id, task_id, skill, event, attempt,
    input_artifacts, output_artifact, eval_status, duration_ms, timestamp, detail

Records are stored in `state["trace"]` (so they checkpoint with the case) and, when a
case directory is registered, mirrored line-by-line to `<case_dir>/trace.jsonl`.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Optional

# spec §5 event vocabulary
EVENTS = {
    "CASE_STARTED", "TASK_CREATED", "TASK_STARTED", "SKILL_STARTED", "SKILL_COMPLETED",
    "EVAL_STARTED", "EVAL_COMPLETED", "REPAIR_STARTED", "REPAIR_COMPLETED",
    "CHECKPOINT_SAVED", "CHECKPOINT_LOADED", "TASK_FAILED", "CASE_WAITING",
    "CASE_COMPLETED", "CASE_NEEDS_REVIEW",
}

# case_id -> case directory (NOT stored in state, to keep the CaseState schema clean
# and avoid collisions when several cases run in one process, e.g. the E2E harness).
_CASE_DIRS: dict = {}

# Optional live sink (Step 4 Phase 10): a callable invoked with each record as it is
# emitted, so the Demo CLI can show progress in real time. Never affects execution.
_SINK = None


def set_sink(fn) -> None:
    global _SINK
    _SINK = fn


def clear_sink() -> None:
    global _SINK
    _SINK = None


def register_case(case_id: str, case_dir: str) -> None:
    _CASE_DIRS[case_id] = case_dir


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def emit(state, event, *, case_id=None, task_id=None, skill=None, attempt=None,
         input_artifacts=None, output_artifact=None, eval_status=None,
         duration_ms=None, detail=None):
    """Append one structured trace record. Safe to call anywhere: failures never break the run."""
    rec = {
        "trace_id": "TRACE-" + uuid.uuid4().hex[:8].upper(),
        "case_id": case_id or state.get("case_id"),
        "task_id": task_id,
        "skill": skill,
        "event": event,
        "attempt": attempt,
        "input_artifacts": list(input_artifacts or []),
        "output_artifact": output_artifact,
        "eval_status": eval_status,
        "duration_ms": duration_ms,
        "timestamp": _now_iso(),
        "detail": detail,
    }
    state.setdefault("trace", []).append(rec)
    cd = _CASE_DIRS.get(state.get("case_id"))
    if cd:
        try:
            os.makedirs(cd, exist_ok=True)
            with open(os.path.join(cd, "trace.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
    if _SINK is not None:
        try:
            _SINK(rec)
        except Exception:
            pass
    return rec


def dump_jsonl(state, case_dir: str) -> None:
    """Rewrite the full trace as <case_dir>/trace.jsonl (idempotent; used once a dir is known)."""
    tr = state.get("trace") or []
    try:
        os.makedirs(case_dir, exist_ok=True)
        with open(os.path.join(case_dir, "trace.jsonl"), "w", encoding="utf-8") as f:
            for r in tr:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    except Exception:
        pass


def timer():
    """Return a small helper to measure duration_ms."""
    class _T:
        def __init__(self):
            self._t = time.perf_counter()
        def ms(self) -> Optional[float]:
            return round((time.perf_counter() - self._t) * 1000.0, 2)
    return _T()
