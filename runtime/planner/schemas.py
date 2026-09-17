"""Planner schemas — JSON Schema for the LLM's structured plan output.

The LLM must return STRICT JSON matching TASK_GRAPH_SCHEMA. Anything else
is malformed → bounded retry (≤2) → NEEDS_REVIEW (§11/§12).
"""
from __future__ import annotations

TASK_SCHEMA = {
    "type": "object",
    "required": ["task_id", "task_type"],
    "properties": {
        "task_id": {"type": "string", "pattern": "^task_[a-z0-9_]+$",
                    "maxLength": 40},
        "task_type": {"type": "string",
                      "enum": list(__import__("runtime.planner.registry",
                                              fromlist=["TASK_REGISTRY"]).TASK_REGISTRY.keys())},
        "description": {"type": "string", "maxLength": 200},
        "dependencies": {"type": "array", "items": {"type": "string"},
                         "maxItems": 10},
    },
    "additionalProperties": False,
}

TASK_GRAPH_SCHEMA = {
    "type": "object",
    "required": ["tasks"],
    "properties": {
        "tasks": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "items": TASK_SCHEMA,
        },
    },
    "additionalProperties": False,
}
