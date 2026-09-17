"""Planner — converts a user's request into a validated Task Graph.

> Planner produces UNTRUSTED plans → Validator makes them TRUSTED → Harness executes.

The Planner does NOT execute tasks, call skills, or touch CaseState (§2).
It uses the existing LLMProvider to generate a structured plan, validates it
against the Task Registry, and returns a TaskGraph that the Harness accepts.

Malformed output → bounded retry ≤2 → NEEDS_REVIEW (§12). Never a silent
deterministic fallback (§22).
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Callable, Optional

from runtime.agent.model import LLMProvider
from runtime.planner import prompts, registry, schemas, validator

MAX_PLANNER_RETRIES = 2


class PlannerResult:
    def __init__(self, status: str, graph: Optional[dict] = None,
                 errors: Optional[list] = None, attempts: int = 0,
                 provider: str = "", model: str = ""):
        self.status = status        # "planned" | "needs_review"
        self.graph = graph          # validated TaskGraph dict or None
        self.errors = errors or []
        self.attempts = attempts
        self.provider = provider
        self.model = model

    @property
    def ok(self) -> bool:
        return self.status == "planned"


def plan(provider: LLMProvider, request: str,
         context: Optional[dict] = None,
         emit: Optional[Callable[[str, dict], None]] = None) -> PlannerResult:
    """Generate + validate a Task Graph for the given request."""
    emit = emit or (lambda t, d: None)
    emit("planner_started", {"request": request[:200]})

    prompt = prompts.build_planner_prompt(request, context)
    errors: list = []
    graph: Optional[dict] = None

    for attempt in range(1, MAX_PLANNER_RETRIES + 2):  # 1 + 2 retries = 3 max
        emit("graph_validation_started", {"attempt": attempt})
        try:
            raw = provider.generate(
                [{"role": "system", "content": prompt},
                 {"role": "user", "content": request}],
                tools=[])
            text = (raw.text or "").strip()
            # strip markdown fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                if text.endswith("```"):
                    text = text[:-3]
                text = text.strip()

            parsed = json.loads(text)
        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            errors.append("attempt %d: JSON parse error: %s" % (attempt, str(e)[:120]))
            emit("graph_validation_failed", {"attempt": attempt,
                                             "error": "json_parse",
                                             "detail": str(e)[:120]})
            continue

        # schema validation
        from jsonschema import Draft7Validator
        v = Draft7Validator(schemas.TASK_GRAPH_SCHEMA)
        schema_errs = sorted(v.iter_errors(parsed), key=lambda e: list(e.path))
        if schema_errs:
            errors.append("attempt %d: schema error: %s"
                          % (attempt, "; ".join(e.message[:80] for e in schema_errs[:3])))
            emit("graph_validation_failed", {"attempt": attempt,
                                             "error": "schema",
                                             "detail": schema_errs[0].message[:120]})
            continue

        # graph validation (registry + DAG + artifact + eval)
        ok, validation_errors = validator.validate_graph(parsed)
        if not ok:
            errors.extend("attempt %d: %s" % (attempt, e) for e in validation_errors)
            emit("graph_validation_failed", {"attempt": attempt,
                                             "error": "graph",
                                             "detail": "; ".join(validation_errors[:3])[:160]})
            continue

        # SUCCESS: normalize into the final TaskGraph
        graph = _normalize(parsed, request)
        emit("graph_validation_passed", {"attempt": attempt,
                                         "task_count": len(graph["tasks"])})
        emit("planner_completed", {"graph_id": graph["graph_id"],
                                   "task_count": len(graph["tasks"]),
                                   "attempts": attempt})
        return PlannerResult("planned", graph=graph, attempts=attempt,
                             provider=provider.name, model=provider.model)

    # all attempts exhausted
    emit("planner_failed", {"attempts": MAX_PLANNER_RETRIES + 1,
                            "errors": errors[:5]})
    return PlannerResult("needs_review", errors=errors,
                         attempts=MAX_PLANNER_RETRIES + 1,
                         provider=provider.name, model=provider.model)


def _normalize(parsed: dict, source_request: str) -> dict:
    """Convert LLM output into the canonical TaskGraph shape."""
    tasks = []
    for t in parsed["tasks"]:
        tt = t["task_type"]
        reg = registry.get(tt) or {}
        tasks.append({
            "task_id": t["task_id"],
            "task_type": tt,
            "description": t.get("description", reg.get("description", "")),
            "dependencies": t.get("dependencies") or [],
            # filled from the TRUSTED Registry, not from LLM output
            "input_artifacts": reg.get("required_inputs", []),
            "expected_artifacts": reg.get("produced_artifacts", []),
            "required_eval": reg.get("required_eval", []),
            "status": "PLANNED",
            "max_attempts": 3,
        })

    depended = {d for t in tasks for d in t["dependencies"]}
    return {
        "graph_id": "graph_%s" % uuid.uuid4().hex[:8],
        "planner_version": "v0.1",
        "tasks": tasks,
        "entry_tasks": [t["task_id"] for t in tasks if not t["dependencies"]],
        "terminal_tasks": [t["task_id"] for t in tasks if t["task_id"] not in depended],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source_request": source_request[:500],
    }


# --------------------------------------------------------------------------- #
# FakePlannerProvider — deterministic, for tests (no LLM)
# --------------------------------------------------------------------------- #
class FakePlannerProvider:
    """Returns a pre-built graph (or error script). For tests/CI only."""

    def __init__(self, graphs: list):
        """graphs: list of dicts to return in order (each is the LLM response text
        as a JSON string, or an Exception to raise)."""
        self.name = "fake_planner"
        self.model = "fake-planner"
        self._graphs = list(graphs)
        self.calls = 0

    def generate(self, messages, tools):
        self.calls += 1
        if not self._graphs:
            raise RuntimeError("fake planner exhausted")
        item = self._graphs.pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, str):
            from runtime.agent.model import LLMResponse
            return LLMResponse(text=item, tool_calls=[])
        return item  # already an LLMResponse-like
