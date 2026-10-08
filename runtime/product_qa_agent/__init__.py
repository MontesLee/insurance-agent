"""Insurance Product QA Agent package (Phase 28.C-2 / ADR-022).

Public API:
    run_product_qa_turn(...)      -> AnswerContext (schema-valid, fail-closed)
    product_qa_slice_enabled()    -> feature flag (DEFAULT OFF, spec Step 3)

The product-facts behavior unit of registry agent insurance-qa-agent
(product_qa intent). Owns: product fact lookup, product clause
explanation, product information QA. Forbidden: recommendations, plan
design, coverage calculation, sales advice (planning agent's domain).
Evidence: deterministic version-pinned CATALOG record + governed WeKnora
evidence qualifying for the product (linked doc or named product);
missing parameters fail closed (ruling D6).
"""
from runtime.product_qa_agent.agent import (  # noqa: F401
    system_prompt,
    product_qa_slice_enabled,
    run_product_qa_turn,
)
