"""Compatibility shim (Phase 28.C-2) — the citation gate moved to the
shared home runtime/grounding/gate.py. Kept so every 28.C-1 import path
(runtime.qa_agent.gate ...) and test keeps working unchanged."""
from runtime.grounding.gate import (  # noqa: F401
    RULES_PATH,
    check,
    extract_citations,
    is_fact_sentence,
    load_rules,
    split_sentences,
)
