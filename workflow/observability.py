"""Observability + Trace Viewer (Step 4 Phase 9 / Phase 11).

Turns a finished CaseState (or its `trace.jsonl`) into the numbers and the timeline an
engineer or an interviewer actually wants:

  * how many skill calls did one case cost?  (which skill dominates the latency?)
  * how many repairs, how many knowledge-search calls?
  * what happened, in order, with timings — rendered as readable Markdown.

Deliberately dependency-free: no tracing infrastructure, just the Execution Trace that
Phase 2 already writes (spec §22 "JSONL / local trace 即可").
"""
from __future__ import annotations

import json
import os
from collections import OrderedDict

# stage-level milestones we show in the timeline (one line per meaningful event)
TIMELINE_EVENTS = {
    "SKILL_COMPLETED", "TASK_FAILED", "REPAIR_STARTED", "REPAIR_COMPLETED",
    "CHECKPOINT_SAVED", "CHECKPOINT_LOADED", "CASE_STARTED", "CASE_WAITING",
    "CASE_COMPLETED", "CASE_NEEDS_REVIEW",
}


def load_trace(case_dir: str) -> list:
    """Read `<case_dir>/trace.jsonl` (the case dir that holds case_state.json)."""
    p = case_dir
    if os.path.isdir(case_dir):
        p = os.path.join(case_dir, "trace.jsonl")
    with open(p, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def summarize(state: dict) -> dict:
    """Agent-level cost/performance summary for one case."""
    trace = state.get("trace") or []
    per_skill = OrderedDict()
    events = {}
    for r in trace:
        ev = r.get("event")
        events[ev] = events.get(ev, 0) + 1
        skill = r.get("skill")
        if ev == "SKILL_STARTED" and skill:
            s = per_skill.setdefault(skill, {"calls": 0, "completed": 0, "failed": 0,
                                             "total_ms": 0.0, "max_ms": 0.0})
            s["calls"] += 1
        elif ev == "SKILL_COMPLETED" and skill:
            s = per_skill.setdefault(skill, {"calls": 0, "completed": 0, "failed": 0,
                                             "total_ms": 0.0, "max_ms": 0.0})
            s["completed"] += 1
            ms = r.get("duration_ms")
            if isinstance(ms, (int, float)):
                s["total_ms"] = round(s["total_ms"] + ms, 2)
                s["max_ms"] = max(s["max_ms"], round(ms, 2))
        elif ev == "TASK_FAILED" and skill:
            s = per_skill.setdefault(skill, {"calls": 0, "completed": 0, "failed": 0,
                                             "total_ms": 0.0, "max_ms": 0.0})
            s["failed"] += 1

    services = state.get("services") or {}
    service_calls = {k: (v or {}).get("calls", 0) for k, v in services.items()}

    tasks = state.get("tasks") or []
    repairs = sum(max(0, (t.get("attempt") or 1) - 1) for t in tasks)
    executed_skills = sum(v["calls"] for v in per_skill.values())
    # seeded `executor: provided` stages are not executed locally: they still count as a
    # stage in the chain (the client conversation happened upstream), but cost 0 calls here.
    provided_skills = sum(1 for v in per_skill.values()
                          if v["calls"] == 0 and v["completed"] > 0)
    total_stages = executed_skills + provided_skills
    total_skill_calls = total_stages + sum(service_calls.values())

    return {
        "case_id": state.get("case_id"),
        "status": state.get("status"),
        "skill_calls": executed_skills,
        "provided_skills": provided_skills,
        "total_stages": total_stages,
        "service_calls": service_calls,
        "total_skill_calls": total_skill_calls,
        "knowledge_search_calls": service_calls.get("knowledge-search", 0),
        "repairs": repairs,
        "repairs_attempted": repairs,
        "artifacts": len(state.get("artifact_registry") or {}),
        "evals": len(state.get("evaluations") or []),
        "checkpoints": len(state.get("checkpoints") or []),
        "per_skill": per_skill,
        "events": events,
        "wall_span": _wall_span(trace),
    }


def _wall_span(trace: list) -> str:
    if not trace:
        return "0s"
    from datetime import datetime
    try:
        t0 = datetime.fromisoformat(trace[0]["timestamp"])
        t1 = datetime.fromisoformat(trace[-1]["timestamp"])
        return "%.2fs" % (t1 - t0).total_seconds()
    except Exception:  # noqa: BLE001
        return "?"


def render_summary_text(state: dict) -> str:
    s = summarize(state)
    lines = []
    lines.append("Case %s  status=%s  wall=%s" % (s["case_id"], s["status"], s["wall_span"]))
    lines.append("Stage calls: %d executed + %d provided(upstream) = %d stages"
                 % (s["skill_calls"], s["provided_skills"], s["total_stages"]))
    if s["service_calls"]:
        lines.append("Service calls: %s" % ", ".join("%s=%d" % (k, v)
                                                     for k, v in s["service_calls"].items()))
    lines.append("Total skill invocations for this case: %d" % s["total_skill_calls"])
    lines.append("Repairs: %d   Artifacts: %d   Evals: %d   Checkpoints: %d"
                 % (s["repairs"], s["artifacts"], s["evals"], s["checkpoints"]))
    lines.append("")
    lines.append("%-28s %5s %5s %5s %10s" % ("skill", "call", "done", "fail", "total_ms"))
    for skill, v in s["per_skill"].items():
        lines.append("%-28s %5d %5d %5d %10.2f"
                     % (skill, v["calls"], v["completed"], v["failed"], v["total_ms"]))
    return "\n".join(lines)


def render_trace_markdown(state: dict, title: str = None) -> str:
    """A human-readable timeline — the 'Trace Viewer' output (spec §25)."""
    trace = state.get("trace") or []
    s = summarize(state)
    case_id = state.get("case_id")
    out = []
    out.append("# %s" % (title or ("%s TRACE" % case_id)))
    out.append("")
    out.append("- case_id: `%s`" % case_id)
    out.append("- final status: **%s**" % state.get("status"))
    out.append("- total skill calls: **%d** (incl. %d knowledge-search)"
               % (s["total_skill_calls"], s["knowledge_search_calls"]))
    out.append("- repairs: **%d**" % s["repairs"])
    out.append("")
    out.append("| time | event | skill | dur(ms) | detail |")
    out.append("|---|---|---|---|---|")
    t0 = trace[0]["timestamp"] if trace else None
    for r in trace:
        if r["event"] not in TIMELINE_EVENTS:
            continue
        out.append("| %s | `%s` | %s | %s | %s |" % (
            _rel(r.get("timestamp"), t0), r["event"], r.get("skill") or "-",
            r.get("duration_ms") if isinstance(r.get("duration_ms"), (int, float)) else "-",
            (str(r.get("detail") or "")[:80]).replace("|", "/")))
    return "\n".join(out)


def _rel(ts: str, t0: str) -> str:
    if not ts or not t0:
        return ts or "-"
    from datetime import datetime
    try:
        return "%.2fs" % (datetime.fromisoformat(ts) - datetime.fromisoformat(t0)).total_seconds()
    except Exception:  # noqa: BLE001
        return ts
