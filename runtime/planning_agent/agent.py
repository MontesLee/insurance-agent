"""Insurance Planning Agent — behavior unit, M3 slice (Phase 28.D).

Registry agent `insurance-planning-agent`'s v1 runtime behavior: the
EXISTING chat tool-stack MOUNTED on the planning registry entry
(migration plan §11/28.B; ADR-025 M3; contract
docs/production/phase-28d-planning-slice-contract.md).

What this unit does (and deliberately nothing more):
  1. CONTRACT GUARD — re-verify the routing input (validated
     IntentResult; intent in {insurance_plan, modify_existing_plan};
     no pending clarification — M1: modify without an active case was
     already forced to clarification upstream and never reaches here);
     guard failure => return None => the caller falls back to the
     legacy path (fail-closed, no guessing).
  2. EXECUTE — run the caller-injected spine execution (the identical
     run_agent_turn tool-loop over the SAME CaseState/ToolContext/
     artifact registry/eval engine). Exceptions DURING execution
     PROPAGATE unchanged so crash semantics stay byte-identical to the
     legacy path (E1 equivalence requirement).

Forbidden by contract (§6) and absent by construction: re-classifying
intent, routing to another agent, inventing insurance facts, bypassing
the evidence gates, invoking any hidden execution runtime, touching
governance. The spine, artifacts, events and evaluations are the
EXISTING ones — this module adds IDENTITY + GUARD, not a second
runtime.
"""
from __future__ import annotations

import os
from typing import Callable, Optional

SLICE_ENV = "INSURANCE_AGENT_PLAN_SLICE"

PLANNING_INTENTS = ("insurance_plan", "modify_existing_plan")


def planning_slice_enabled(env: Optional[dict] = None) -> bool:
    """Feature flag for the planning slice — DEFAULT OFF (M3 contract
    §4; gray-enable only after E1 + rollback + regression GREEN)."""
    e = os.environ if env is None else env
    return str(e.get(SLICE_ENV, "0")).strip().lower() in ("1", "true",
                                                          "yes", "on")


def guard_ok(intent_result) -> bool:
    """Contract guard: the routing input must be a validated IntentResult
    for a planning intent with no pending clarification."""
    if not isinstance(intent_result, dict):
        return False
    from runtime.grounding import context as gctx
    if gctx.validate_intent(intent_result):
        return False
    if intent_result.get("intent_id") not in PLANNING_INTENTS:
        return False
    if intent_result.get("clarification_required"):
        return False
    return True


def run_planning_turn(intent_result, execute: Callable,
                      conversation_context: Optional[list] = None):
    """Run ONE planning turn as the planning agent.

    execute: the caller-injected spine execution (legacy
    run_agent_turn over the prepared CaseState/ToolContext). Returns
    execute()'s outcome; returns None when the contract guard fails
    (caller falls back to the legacy path — never a guess, never a
    re-route). Exceptions from execute() propagate unchanged (legacy
    crash semantics).
    """
    if not guard_ok(intent_result):
        return None
    return execute()
