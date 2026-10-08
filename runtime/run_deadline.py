"""Run lifecycle deadline configuration (Phase 28.K.24 — L1/L2).

28.K.23 established: local LLM/Tool timeouts exist, but a Run has NO
independent lifetime ceiling, and the agent-loop's provider calls use a
PER-READ httpx timeout that slow-drip streaming can extend indefinitely.
This module centralizes the two knobs that close those gaps:

  * run deadline      — ABSOLUTE monotonic ceiling over the WHOLE run
                        (every stage/tool/generation shares it; retries
                        never re-arm it; enforced by a supervisor that
                        owns the terminal transition, independent of the
                        worker thread).
  * generation wall   — per-call wall-clock ceiling for agent-loop
                        provider calls (generate/stream_generate), the
                        same thread+join watchdog pattern as the QA
                        adapter (28.B5.1). Clamped by the run's
                        REMAINING budget so a retry can never outlive
                        the run deadline.

Values (env-overridable, deployment config — not legal/business rules):

  RUN_DEADLINE_S      default 900s. Derivation: QA worst-case bounded
                      wall ≈ 360s (90s × 2 gateway × 2 regen);
                      observed full planning chains (intake→report)
                      300-600s (K.7/K.8 gates); +headroom for repair
                      loops → 900s covers every legitimate observed path
                      while guaranteeing finiteness.
  GENERATION_WALL_S   default 240s per agent-loop provider call.
                      Observed live generations 16-60s; QA attempts are
                      separately bounded at 90s by their own watchdog;
                      240s is generous for long streamed answers while
                      killing the slow-drip-forever case.
  MIN_RETRY_BUDGET_S  default 5s — a retry is only STARTED when at
                      least this much run budget remains (a retry that
                      cannot possibly finish is not started).
"""
from __future__ import annotations

import os

RUN_DEADLINE_ENV = "INSURANCE_AGENT_RUN_DEADLINE_S"
GENERATION_WALL_ENV = "INSURANCE_AGENT_GENERATION_WALL_S"
MIN_RETRY_BUDGET_ENV = "INSURANCE_AGENT_MIN_RETRY_BUDGET_S"

_DEFAULT_RUN_DEADLINE_S = 900.0
_DEFAULT_GENERATION_WALL_S = 240.0
_DEFAULT_MIN_RETRY_BUDGET_S = 5.0


def run_deadline_s() -> float:
    try:
        return float(os.environ.get(RUN_DEADLINE_ENV, "")
                     or _DEFAULT_RUN_DEADLINE_S)
    except ValueError:
        return _DEFAULT_RUN_DEADLINE_S


def generation_wall_s() -> float:
    try:
        return float(os.environ.get(GENERATION_WALL_ENV, "")
                     or _DEFAULT_GENERATION_WALL_S)
    except ValueError:
        return _DEFAULT_GENERATION_WALL_S


def min_retry_budget_s() -> float:
    try:
        return float(os.environ.get(MIN_RETRY_BUDGET_ENV, "")
                     or _DEFAULT_MIN_RETRY_BUDGET_S)
    except ValueError:
        return _DEFAULT_MIN_RETRY_BUDGET_S


def generation_budget(deadline_at: float | None) -> float:
    """Wall-clock budget for ONE agent-loop provider call:
    min(configured generation wall, remaining run budget). Raises
    TimeoutError when the remaining budget is below the minimum retry
    floor (do not start a call that cannot finish)."""
    from runtime.llm.types import TimeoutError as LLMTimeout

    budget = generation_wall_s()
    if deadline_at is not None:
        budget = min(budget, deadline_at - _mono())
    if budget < min_retry_budget_s():
        raise LLMTimeout(
            "run deadline budget exhausted (remaining %.1fs < floor "
            "%.1fs)" % (budget, min_retry_budget_s()))
    return budget


def _mono() -> float:
    import time
    return time.monotonic()
