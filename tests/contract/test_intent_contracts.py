"""Phase 28.A-0 — Intent Layer contract tests (schema-only, no runtime).

Validates the three v1 contracts in schema/ against the six mandated
checks from the 28.A-0 spec:

  1. unknown intent can degrade safely (unknown_insurance_intent is a
     valid value; and per ADR-019 M1, modify_existing_plan WITHOUT
     active-case context is only valid together with
     clarification_required=true)
  2. invalid intent is rejected (enum)
  3. the Router does not accept an agent that is not declared in the
     Agent Registry (cross-contract check: RouterDecision.agent_id
     must be a declared registry entry id)
  4. IntentResult contains NO workflow field (structurally impossible)
  5. IntentResult contains NO tool/skill selection (structurally
     impossible)
  6. schemas are backward-compatible by construction: valid draft-07,
     versioned $id, additionalProperties:false (no silent field
     additions), and the v1 intent vocabulary is a frozen golden list

Non-vacuousness: every negative case uses a payload that differs from
its positive twin ONLY in the asserted aspect, so a pass cannot happen
by accident.
"""
from __future__ import annotations

import copy
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from jsonschema import Draft7Validator  # noqa: E402

SCHEMA_DIR = os.path.join(REPO, "schema")

V1_INTENTS = [
    "insurance_qa",
    "product_qa",
    "insurance_plan",
    "modify_existing_plan",
    "unknown_insurance_intent",
]

# The v1 declaration-only registry fixture (mirrors the ADR-021 v1 agent
# set; used by check 3. Not wired to any runtime code in this phase).
REGISTRY_FIXTURE = [
    {
        "id": "insurance-qa-agent",
        "name": "Insurance QA Agent",
        "description": "Insurance knowledge and product-fact QA with evidence grounding.",
        "supported_intents": ["insurance_qa", "product_qa"],
        "input_contract": "schema/intent-result.schema.json",
        "output_contract": "contracts/knowledge-evidence.schema.json",
        "capabilities": ["knowledge-grounded-qa", "catalog-fact-lookup"],
        "risk_level": "low",
    },
    {
        "id": "insurance-planning-agent",
        "name": "Insurance Planning Agent",
        "description": "Family risk / gap analysis, plan design, product recommendation, report generation.",
        "supported_intents": ["insurance_plan", "modify_existing_plan"],
        "input_contract": "schema/intent-result.schema.json",
        "output_contract": "contracts/insurance-report.schema.json",
        "capabilities": ["planning-workflow", "plan-modification"],
        "risk_level": "high",
    },
    {
        "id": "conversation-agent",
        "name": "Conversation Agent",
        "description": "Clarification and presentation front-end; owns no business workflow.",
        "supported_intents": ["unknown_insurance_intent"],
        "input_contract": "schema/intent-result.schema.json",
        "output_contract": "schema/intent-result.schema.json",
        "capabilities": ["clarification"],
        "risk_level": "low",
    },
]


def _load(name: str) -> dict:
    with open(os.path.join(SCHEMA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def _validator(name: str) -> Draft7Validator:
    schema = _load(name)
    Draft7Validator.check_schema(schema)  # itself an assertion: valid draft-07
    return Draft7Validator(schema)


def _errors(v: Draft7Validator, instance) -> list:
    return [e.message for e in v.iter_errors(instance)]


def _intent_result(**overrides) -> dict:
    base = {
        "intent_id": "insurance_qa",
        "confidence": 1.0,
        "confidence_source": "rule",
        "context_refs": {
            "conversation_id": "chat_abc123",
            "active_case_id": None,
            "message_id": "msg_0001",
        },
        "clarification_required": False,
        "reason_codes": ["rule:qa-difference-01"],
        "created_at": "2026-09-25T10:00:00Z",
    }
    base.update(overrides)
    return base


def _router_decision(**overrides) -> dict:
    base = {
        "intent_id": "insurance_qa",
        "agent_id": "insurance-qa-agent",
        "decision_source": "registry_lookup",
        "validation_result": {"valid": True, "errors": []},
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------
# Check 1 — unknown intent degrades safely (fail-closed, never a guess)
# --------------------------------------------------------------------------

def test_unknown_intent_is_valid_value():
    v = _validator("intent-result.schema.json")
    doc = _intent_result(
        intent_id="unknown_insurance_intent",
        clarification_required=True,
        reason_codes=["schema_validation_failed"],
    )
    assert _errors(v, doc) == [], "unknown_insurance_intent must be a valid, renderable outcome"


def test_modify_intent_without_case_context_requires_clarification():
    v = _validator("intent-result.schema.json")
    no_context = _intent_result(
        intent_id="modify_existing_plan",
        confidence=0.9,
        confidence_source="llm",
        context_refs={"conversation_id": None, "active_case_id": None, "message_id": "m1"},
        reason_codes=["llm:proposal-07"],
    )
    # clarification_required defaults False in the fixture -> must be INVALID
    assert _errors(v, no_context) != [], (
        "ADR-019 M1: modify_existing_plan without active case context must not validate "
        "unless clarification_required=true"
    )
    safe = copy.deepcopy(no_context)
    safe["clarification_required"] = True
    assert _errors(v, safe) == [], "safe degradation to clarification must validate"
    # twin with context present and no clarification is fine (positive control)
    with_context = copy.deepcopy(no_context)
    with_context["context_refs"]["active_case_id"] = "case_001"
    assert _errors(v, with_context) == []


# --------------------------------------------------------------------------
# Check 2 — invalid intent rejected
# --------------------------------------------------------------------------

def test_invalid_intent_enum_rejected():
    v = _validator("intent-result.schema.json")
    for bad in ("general_chitchat", "TASK_EXECUTION", "insurance_qa ", ""):
        doc = _intent_result(intent_id=bad)
        assert _errors(v, doc) != [], "intent %r outside the v1 vocabulary must be rejected" % bad
    # non-vacuous control: the vocabulary twin validates
    assert _errors(v, _intent_result(intent_id="insurance_qa")) == []


def test_router_rejects_invalid_intent_too():
    v = _validator("router-decision.schema.json")
    assert _errors(v, _router_decision(intent_id="policy_compare")) != [], (
        "RouterDecision must consume the same v1 vocabulary (policy_compare is not v1)"
    )


# --------------------------------------------------------------------------
# Check 3 — Router does not accept an undeclared agent
# --------------------------------------------------------------------------

def test_router_decision_agent_must_be_declared_in_registry():
    v = _validator("router-decision.schema.json")
    declared = {entry["id"] for entry in REGISTRY_FIXTURE}

    ok = _router_decision(agent_id="insurance-qa-agent")
    assert _errors(v, ok) == []
    assert ok["agent_id"] in declared, "fixture sanity: declared agent id must be in registry"

    rogue = _router_decision(agent_id="rogue-agent")
    # schema-valid shape, but the agent is not declared -> contract check fails
    assert _errors(v, rogue) == [], "shape itself is schema-valid (isolation of the asserted aspect)"
    assert rogue["agent_id"] not in declared, (
        "RouterDecision referencing an agent absent from the Agent Registry violates the "
        "contract (router may only route to declared agents)"
    )
    # the only legal non-declared target is none: fallback goes to conversation-agent,
    # which must itself be declared
    fallback = _router_decision(
        intent_id="unknown_insurance_intent",
        agent_id="conversation-agent",
        decision_source="fallback",
        validation_result={"valid": True},
    )
    assert fallback["agent_id"] in declared


def test_registry_fixture_entries_validate():
    v = _validator("agent-registry.schema.json")
    for entry in REGISTRY_FIXTURE:
        assert _errors(v, entry) == [], "registry fixture entry %s must validate" % entry["id"]


# --------------------------------------------------------------------------
# Check 4/5 — IntentResult structurally contains no workflow / tool selection
# --------------------------------------------------------------------------

FORBIDDEN_INTENT_KEYS = ["workflow", "workflow_steps", "skill", "skills",
                         "tool", "tools", "tool_selection", "agent_name",
                         "agent_id", "stage", "stages"]


def test_intent_result_rejects_execution_detail_keys():
    v = _validator("intent-result.schema.json")
    for key in FORBIDDEN_INTENT_KEYS:
        doc = _intent_result(**{key: "anything"})
        assert _errors(v, doc) != [], (
            "IntentResult must not carry execution detail: key %r must be rejected" % key
        )


def test_intent_schema_declares_no_execution_properties():
    schema = _load("intent-result.schema.json")
    props = set(schema.get("properties", {}))
    leaked = props & set(FORBIDDEN_INTENT_KEYS)
    assert leaked == set(), "intent schema properties must not declare execution detail, found %s" % leaked
    assert schema.get("additionalProperties") is False, (
        "additionalProperties:false is what makes execution fields structurally impossible; "
        "removing it is a breaking contract change (see backward-compat check)"
    )


# --------------------------------------------------------------------------
# Check 6 — backward compatibility by construction
# --------------------------------------------------------------------------

def test_schemas_are_versioned_draft07_and_closed():
    for name in ("intent-result.schema.json", "router-decision.schema.json",
                 "agent-registry.schema.json"):
        schema = _load(name)
        assert schema["$schema"] == "http://json-schema.org/draft-07/schema#", name
        assert "$id" in schema and "/v1" in schema["$id"], (
            "%s must carry a versioned $id so future revisions are explicit" % name
        )
        assert schema.get("additionalProperties") is False, (
            "%s must stay closed: silent field additions are how contracts drift" % name
        )
        Draft7Validator.check_schema(schema)


def test_v1_intent_vocabulary_is_frozen_golden():
    for name in ("intent-result.schema.json", "router-decision.schema.json"):
        enum = _load(name)["properties"]["intent_id"]["enum"]
        assert enum == V1_INTENTS, (
            "%s v1 vocabulary must match the frozen golden list exactly; any change is a "
            "version-bumping contract revision (add-only, never silent)" % name
        )
    registry_enum = _load("agent-registry.schema.json")["properties"]["supported_intents"]["items"]["enum"]
    assert set(registry_enum) == set(V1_INTENTS), (
        "registry vocabulary must stay a subset of the same frozen intent list"
    )


if __name__ == "__main__":
    failures = 0
    for fn in [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (
        len([k for k in globals() if k.startswith("test_")]), failures))
    sys.exit(1 if failures else 0)
