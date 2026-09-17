"""Specialist Agent Executor (Phase 5.1).

Gives each Specialist Agent a REAL execution loop:
  - own system prompt (from Agent Registry)
  - own tool boundary (filtered from the global Tool Registry)
  - LLM-driven tool calling (reuses runtime/agent/model.py provider)
  - structured output validated against the Artifact Contract

> Agent = Executor, not Controller (§2). The Harness retains absolute
> control over lifecycle, eval, repair, and checkpoint.

Integration: the Harness calls `execute()` instead of `_execute_stage()`
when a task has an `assigned_agent` and a provider is configured.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from runtime.agents import registry as agent_registry
from runtime.agents.registry import get as get_agent
from runtime.planner import registry as planner_registry

MAX_AGENT_STEPS = 8


class AgentExecutionResult:
    """Compatible with _execute_stage's return format."""

    def __init__(self, outcome: str, eval_rec: Optional[dict] = None,
                 reasons: Optional[list] = None, artifact: Any = None,
                 error_code: str = ""):
        self.outcome = outcome          # "OK" | "NEEDS_REVIEW" | "AGENT_FAILED"
        self.eval_rec = eval_rec
        self.reasons = reasons or []
        self.artifact = artifact
        self.error_code = error_code

    def get(self, key, default=None):
        return {"outcome": self.outcome, "eval": self.eval_rec,
                "reasons": self.reasons, "error_code": self.error_code}.get(key, default)


class SpecialistAgentExecutor:
    """Executes a task through a Specialist Agent's own LLM loop."""

    def __init__(self, llm_provider=None):
        """llm_provider: LLMProvider instance (real or Fake). None = use env config."""
        self._provider = llm_provider

    def _get_provider(self):
        if self._provider is not None:
            return self._provider
        from runtime.agent.config import load_llm_config
        return load_llm_config().to_provider()

    def execute(self, *, agent_id: str, task: dict, project, case_state: dict,
                emit=None) -> AgentExecutionResult:
        """Execute one task as the assigned Specialist Agent."""
        emit = emit or (lambda t, d: None)
        task_type = task.get("task_type", "")
        task_id = task.get("task_id", "")

        # ---- 1. Load agent definition -------------------------------------- #
        agent_def = get_agent(agent_id)
        if agent_def is None:
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="AGENT_NOT_FOUND")
        ok_assign, assign_err = agent_registry.validate_assignment(task_type, agent_id)
        if not ok_assign:
            emit("agent_validation_failed", {"task_id": task_id,
                                             "agent_id": agent_id,
                                             "reason": assign_err[:160]})
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="AGENT_NOT_AUTHORIZED")

        # ---- 2. Get expected artifact contract ------------------------------ #
        planner_def = planner_registry.get(task_type)
        if planner_def is None:
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="TASK_TYPE_NOT_IN_PLANNER_REGISTRY")
        expected_artifacts = planner_def.get("produced_artifacts", [])
        stage_id = planner_def.get("stage_id", "")

        # ---- 3. Build agent-scoped tool registry ----------------------------- #
        from runtime.agent.tools import build_registry, ToolContext, validate_arguments
        full_registry = build_registry()
        allowed = agent_def.get("allowed_tools", [])
        scoped_tools = {name: full_registry[name] for name in allowed
                        if name in full_registry}
        if not scoped_tools:
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="NO_ALLOWED_TOOLS")

        # ---- 4. Get LLM provider --------------------------------------------- #
        try:
            provider = self._get_provider()
        except Exception as e:
            emit("agent_failed", {"task_id": task_id, "agent_id": agent_id,
                                  "reason": "LLM provider unavailable: %s" % str(e)[:100]})
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="LLM_PROVIDER_UNAVAILABLE")

        # ---- 5. Run the agent loop ------------------------------------------- #
        emit("agent_started", {"task_id": task_id, "agent_id": agent_id,
                               "task_type": task_type})
        system_prompt = agent_def["system_prompt"]
        context = self._build_context(case_state, task, scoped_tools,
                                      expected_artifacts)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": context},
            {"role": "user", "content": "Execute task: %s (%s)" % (task_id, task_type)},
        ]

        # Phase 5.2: skip_eval=True → Tool stores artifact WITHOUT running eval.
        # The Harness owns the eval boundary (eval runs after agent completes).
        ctx = ToolContext(case_state, case_state.get("_workflow", {}),
                          task_id, persist=lambda: None, skip_eval=True)
        t0 = time.perf_counter()

        for step in range(1, MAX_AGENT_STEPS + 1):
            emit("agent_step_started", {"step": step, "agent_id": agent_id,
                                        "task_id": task_id})
            try:
                response = provider.generate(messages, list(scoped_tools.values()))
            except Exception as e:
                emit("agent_failed", {"task_id": task_id, "agent_id": agent_id,
                                      "reason": "LLM error: %s" % str(e)[:100],
                                      "step": step})
                return AgentExecutionResult("AGENT_FAILED",
                                            error_code="LLM_ERROR")

            # no tool call = plain text answer (agent may finish with text)
            if not response.tool_calls:
                text = (response.text or "").strip()
                if not text:
                    return AgentExecutionResult("AGENT_FAILED",
                                                error_code="EMPTY_RESPONSE")
                # plain text is not a structured artifact → check if artifacts exist
                break

            call = response.tool_calls[0]
            tool_name = call.name

            # ---- tool authorization check (§8) ------------------------------ #
            if tool_name not in scoped_tools:
                emit("agent_validation_failed", {
                    "task_id": task_id, "agent_id": agent_id,
                    "tool": tool_name,
                    "reason": "TOOL_NOT_AUTHORIZED: %s not in %s allowed tools"
                              % (tool_name, agent_id)})
                messages.append({"role": "system", "content":
                                 "Tool %r is not authorized for agent %s. "
                                 "Allowed: %s" % (tool_name, agent_id,
                                                  sorted(scoped_tools))})
                continue

            tool = scoped_tools[tool_name]

            # ---- schema validation ------------------------------------------ #
            invalid = validate_arguments(tool, call.arguments)
            if invalid:
                messages.append({"role": "system", "content":
                                 "Arguments for %s failed schema validation: %s"
                                 % (tool_name, invalid)})
                continue

            # ---- execute ------------------------------------------------------ #
            emit("agent_tool_call", {"step": step, "agent_id": agent_id,
                                     "task_id": task_id, "tool": tool_name})
            result = tool.execute(call.arguments, ctx)
            status = result.get("status")
            emit("agent_tool_completed", {"step": step, "agent_id": agent_id,
                                          "task_id": task_id, "tool": tool_name,
                                          "status": status,
                                          "artifact_id": result.get("artifact_id")})

            if status == "needs_review":
                return AgentExecutionResult("NEEDS_REVIEW",
                                            reasons=[result.get("summary", "")[:200]])

            messages.append({"role": "assistant", "content": "",
                             "tool_calls": response.tool_calls})
            import json as _json
            messages.append({"role": "tool", "tool_call_id": call.id or tool_name,
                             "name": tool_name,
                             "content": _json.dumps(
                                 {k: v for k, v in result.items()
                                  if k in ("status", "summary", "artifact_id",
                                           "artifact_type", "eval_id")},
                                 ensure_ascii=False)[:2000]})
        else:
            # step limit exhausted
            emit("agent_failed", {"task_id": task_id, "agent_id": agent_id,
                                  "reason": "AGENT_STEP_LIMIT (%d)" % MAX_AGENT_STEPS})
            return AgentExecutionResult("AGENT_FAILED",
                                        error_code="AGENT_STEP_LIMIT")

        # ---- 6. Validate output against Artifact Contract (§11) -------------- #
        for art_type in expected_artifacts:
            if art_type not in (case_state.get("artifacts") or {}):
                emit("agent_validation_failed", {
                    "task_id": task_id, "agent_id": agent_id,
                    "reason": "AGENT_OUTPUT_INVALID: expected artifact %s not produced"
                              % art_type})
                return AgentExecutionResult("AGENT_FAILED",
                                            error_code="AGENT_OUTPUT_INVALID")

        # ---- 7. Artifact ready — Harness will run Eval (Phase 5.2 §6/§7) ------ #
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        emit("agent_output_validated", {"task_id": task_id, "agent_id": agent_id,
                                        "artifacts": expected_artifacts,
                                        "duration_ms": elapsed})
        emit("agent_completed", {"task_id": task_id, "agent_id": agent_id,
                                 "artifacts": expected_artifacts,
                                 "duration_ms": elapsed})

        # ARTIFACT_READY: the artifact exists but Eval has NOT been run.
        # The Harness is the eval owner — it calls ev.evaluate() after this.
        return AgentExecutionResult("ARTIFACT_READY",
                                    artifact=expected_artifacts,
                                    eval_rec=None)

    def _build_context(self, case_state: dict, task: dict,
                        scoped_tools: dict, expected_artifacts: list) -> str:
        """Agent-scoped context: only what this agent needs to see."""
        parts = []
        parts.append("Task: %s (type: %s)" % (task.get("task_id"),
                                               task.get("task_type")))
        if task.get("description"):
            parts.append("Description: %s" % task["description"])
        arts = case_state.get("artifacts") or {}
        if arts:
            parts.append("Available artifacts: %s" % ", ".join(sorted(arts.keys())))
        evals = case_state.get("evaluations") or []
        if evals:
            parts.append("Completed evals: %d" % len(evals))
        parts.append("Your allowed tools: %s" % ", ".join(sorted(scoped_tools)))
        parts.append("Expected output artifacts: %s" % ", ".join(expected_artifacts))
        parts.append("Call the appropriate tool to produce the expected artifact.")
        return "\n".join(parts)
