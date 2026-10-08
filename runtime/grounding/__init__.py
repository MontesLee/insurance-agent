"""Shared grounding capabilities (Phase 28.C-2 extraction from 28.C-1).

Public surface (consumed by runtime/qa_agent and runtime/product_qa_agent):
    runtime.grounding.gate     — evidence citation-closure gate (deterministic)
    runtime.grounding.context  — AnswerContext builders + closed-schema validation
    runtime.grounding.loop     — gateway wiring + grounded-generation attempts loop

This package owns NO retrieval (agents assemble evidence), NO routing,
NO artifact registration, and never touches knowledge/ (KnowledgeService
is the only evidence path) or runtime/llm/ (the gateway is consumed
as-is). runtime/qa_agent/{gate,context}.py remain as compatibility
shims so every 28.C-1 import path keeps working unchanged.
"""
from runtime.grounding.gate import (  # noqa: F401
    check,
    extract_citations,
    is_fact_sentence,
    load_rules,
    split_sentences,
)
