"""Agent Registry loader — configuration based, read-only (ADR-021 APPROVED).

Single source of truth for agent declarations:
    config/agent-registry.json   (the declarations, versioned in git)
    schema/agent-registry.schema.json  (the entry contract, frozen v1)

Startup discipline (fail-closed):
    load_registry() validates every entry against the schema, checks id
    uniqueness, checks supported_intents against the frozen v1 intent
    vocabulary (read from schema/intent-result.schema.json — the single
    vocabulary source), derives the intent->agent routing table, and
    REFUSES (raises RegistryValidationError) on any violation — an
    invalid registry must stop the server, not limp up.

FORBIDDEN (ADR-021 ruling): runtime dynamic registration. This module
exposes no register/mutate API at all; the only write path is editing
config/agent-registry.json (a code change, reviewed + versioned).
"""
from __future__ import annotations

import copy
import json
import os
from typing import Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_PATH = os.path.join(REPO_ROOT, "config", "agent-registry.json")
ENTRY_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                 "agent-registry.schema.json")
INTENT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                  "intent-result.schema.json")


class RegistryValidationError(RuntimeError):
    """Invalid registry declaration — startup must fail closed."""


def _intent_vocabulary() -> set:
    with open(INTENT_SCHEMA_PATH, encoding="utf-8") as fh:
        schema = json.load(fh)
    return set(schema["properties"]["intent_id"]["enum"])


def _entry_validator():
    from jsonschema import Draft7Validator
    with open(ENTRY_SCHEMA_PATH, encoding="utf-8") as fh:
        return Draft7Validator(json.load(fh))


def load_registry(path: Optional[str] = None, refresh: bool = False) -> dict:
    """Load + validate the registry. Returns a read-only snapshot dict:

        {"registry_version": int, "agents": [entry, ...],
         "intent_agent_map": {intent -> agent_id}}

    Caller gets deep copies — no mutation path back into this module.
    """
    src = path or REGISTRY_PATH
    with open(src, encoding="utf-8") as fh:
        doc = json.load(fh)

    agents = doc.get("agents")
    if not isinstance(agents, list) or not agents:
        raise RegistryValidationError("%s: 'agents' must be a non-empty list" % src)

    vocab = _intent_vocabulary()
    validator = _entry_validator()
    seen_ids: set = set()
    intent_map: dict = {}

    for i, entry in enumerate(agents):
        errs = [e.message for e in validator.iter_errors(entry)]
        if errs:
            raise RegistryValidationError(
                "%s: agents[%d] violates agent-registry.schema.json: %s"
                % (src, i, "; ".join(errs[:3])))
        agent_id = entry["id"]
        if agent_id in seen_ids:
            raise RegistryValidationError("%s: duplicate agent id %r" % (src, agent_id))
        seen_ids.add(agent_id)
        outside = set(entry["supported_intents"]) - vocab
        if outside:
            raise RegistryValidationError(
                "%s: agent %r declares intents outside the frozen v1 "
                "vocabulary: %s" % (src, agent_id, sorted(outside)))
        for intent in entry["supported_intents"]:
            if intent in intent_map:
                raise RegistryValidationError(
                    "%s: intent %r claimed by both %r and %r — the router "
                    "table must be unambiguous" % (src, intent,
                                                   intent_map[intent], agent_id))
            intent_map[intent] = agent_id

    if "unknown_insurance_intent" not in intent_map:
        raise RegistryValidationError(
            "%s: no agent serves unknown_insurance_intent — the fail-closed "
            "clarification path must have a declared target" % src)

    return {
        "registry_version": doc.get("registry_version", 1),
        "agents": copy.deepcopy(agents),
        "intent_agent_map": dict(intent_map),
    }


def fallback_agent(registry: dict) -> str:
    """The declared target for the fail-closed clarification path."""
    return registry["intent_agent_map"]["unknown_insurance_intent"]


# module-level snapshot for process lifetime (configuration based: one
# load at startup; refresh only via restart — no runtime dynamic registry)
_SNAPSHOT: Optional[dict] = None


def default_registry() -> dict:
    global _SNAPSHOT
    if _SNAPSHOT is None:
        _SNAPSHOT = load_registry()
    return _SNAPSHOT
