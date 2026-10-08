"""Insurance Intent Layer (Phase 28.A-1 / ADR-019 APPROVED).

Public API:
    classify(...)      -> schema-valid IntentResult (deterministic-first)
    load_rules()       -> externalized rules (config/intent-rules.yaml)

Shadow-mode companions:
    runtime.intent.shadow        — shadow records (JSONL, tmp/intent-shadow/)
    runtime.intent.report        — corpus runner + shadow statistics report
    runtime.intent.llm_candidate — OPTIONAL env-gated LLM proposal adapter
                                   (ADR-019 rule 1; advisory only). NOT
                                   imported here, so importing this package
                                   stays LLM-provider-free.

The deterministic Router lives in runtime/router.py (ADR-020) and the
configuration-based Agent Registry loader in runtime/agent_registry.py
(ADR-021). This package never dispatches, never selects workflows or
tools, and never imports an LLM provider.
"""
from runtime.intent.classifier import (  # noqa: F401
    IntentRulesError,
    UNKNOWN,
    classify,
    load_rules,
)
