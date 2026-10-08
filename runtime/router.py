"""Deterministic Router (Phase 28.A-1 / ADR-020 APPROVED).

The Router does exactly three things: LOOKUP, VALIDATE, DISPATCH.

    validated IntentResult  ->  route()  ->  RouterDecision (schema-valid)

What the Router is FORBIDDEN from (ADR-020 + ARCHITECTURE_PRINCIPLES P3):
    * insurance business logic        (no product/risk/client semantics)
    * workflow orchestration          (it knows ZERO stages/steps/skills)
    * knowledge retrieval             (no WeKnora / Catalog / KnowledgeService)
    * product recommendation
    * LLM involvement — decision_source has NO llm value (schema-enforced);
      an LLM can never produce a RouterDecision because the contract
      structurally excludes it (see schema/router-decision.schema.json)

Module boundary (import discipline, CI-checkable): this module imports
ONLY jsonschema (validation) + the agent registry contract. It never
imports the intent classifier, the orchestrator, any LLM provider, or
any skill.
"""
from __future__ import annotations

import json
import os
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTENT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                  "intent-result.schema.json")
ROUTER_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                  "router-decision.schema.json")

_intent_validator = None
_router_validator = None


def _validators():
    global _intent_validator, _router_validator
    if _intent_validator is None:
        from jsonschema import Draft7Validator
        with open(INTENT_SCHEMA_PATH, encoding="utf-8") as fh:
            _intent_validator = Draft7Validator(json.load(fh))
        with open(ROUTER_SCHEMA_PATH, encoding="utf-8") as fh:
            _router_validator = Draft7Validator(json.load(fh))
    return _intent_validator, _router_validator


def route(intent_result: dict, registry: dict) -> dict:
    """Route a validated IntentResult to a declared agent.

    registry: the load_registry() snapshot from runtime/agent_registry
    (intent_agent_map + agents). Fail-closed everywhere:
      * invalid IntentResult            -> fallback (conversation agent)
      * clarification_required          -> fallback (clarify, never guess)
      * unknown intent                  -> fallback
      * intent with no declared agent   -> fallback
    NEVER a default to a business agent.
    """
    iv, rv = _validators()
    errors = [e.message for e in iv.iter_errors(intent_result)]
    valid = not errors
    fallback_id = registry["intent_agent_map"].get("unknown_insurance_intent")
    table = registry["intent_agent_map"]

    if not valid:
        # an invalid IntentResult routes as unknown (fail-closed). The raw
        # intent value is NOT echoed into the decision — the RouterDecision
        # vocabulary is the frozen v1 enum and a bogus value must not leak
        # into a contract-valid document. The verbatim errors are kept.
        decision = _decision("unknown_insurance_intent", fallback_id,
                             "fallback", False,
                             errors[:5] + [str(intent_result.get("intent_id"))[:80]])
    elif intent_result.get("clarification_required"):
        decision = _decision(intent_result["intent_id"], fallback_id,
                             "fallback", True,
                             ["clarification_required"])
    elif intent_result["intent_id"] == "unknown_insurance_intent":
        decision = _decision("unknown_insurance_intent", fallback_id,
                             "fallback", True, ["intent:unknown"])
    else:
        agent_id = table.get(intent_result["intent_id"])
        if agent_id is None:
            decision = _decision(intent_result["intent_id"], fallback_id,
                                 "fallback", True,
                                 ["intent:not_declared_in_registry"])
        else:
            decision = _decision(intent_result["intent_id"], agent_id,
                                 "registry_lookup", True, [])

    # self-check: our own output must satisfy the contract (programming
    # error otherwise — fail loud so tests/CI catch it immediately)
    out_errors = [e.message for e in rv.iter_errors(decision)]
    if out_errors:
        raise ValueError("RouterDecision violates contract: %s" % out_errors)
    return decision


def _decision(intent_id, agent_id, source, valid, errors) -> dict:
    return {
        "intent_id": intent_id,
        "agent_id": agent_id,
        "decision_source": source,
        "validation_result": {
            "valid": bool(valid),
            "errors": list(errors),
        },
    }
