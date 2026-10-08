"""Insurance QA Agent package (Phase 28.C-1 / ADR-022 APPROVED).

Public API:
    run_qa_turn(...)     -> AnswerContext (schema-valid, fail-closed)
    qa_slice_enabled()   -> ops kill-switch for the production slice
    build_gateway(...)   -> LLM Gateway wiring (owner ruling D2)

Companions:
    runtime.qa_agent.gate    — evidence closure gate (deterministic code)
    runtime.qa_agent.context — AnswerContext builders + validation

This package never routes (Router decides), never owns workflow
knowledge, never registers artifacts (ruling D1: AnswerContext is a
run-scoped record), and never touches WeKnora except through
KnowledgeService.
"""
from runtime.qa_agent.agent import (  # noqa: F401
    system_prompt,
    build_gateway,
    qa_slice_enabled,
    run_qa_turn,
)
