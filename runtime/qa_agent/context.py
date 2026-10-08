"""Compatibility shim (Phase 28.C-2) — AnswerContext construction moved
to the shared home runtime/grounding/context.py. Kept so every 28.C-1
import path (runtime.qa_agent.context ...) and test keeps working
unchanged."""
from runtime.grounding.context import (  # noqa: F401
    SCHEMA_PATH,
    anchor,
    grounded,
    not_attempted_retrieval,
    refused,
    validate,
    validate_intent,
    validator,
)
