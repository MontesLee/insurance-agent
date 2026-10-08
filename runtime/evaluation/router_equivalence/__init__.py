"""B4 Behavior Equivalence Gate (Phase 28.B4 / ADR-025 M0, PROPOSED).

Implementation of docs/production/architecture/router-equivalence-gate-
design.md: run golden cases through the REAL server twice (legacy flags
vs candidate flags), capture six observation dimensions, and judge:

    E1 byte equivalence   planning-class: normalized artifacts,
                          evaluations and event chains must be IDENTICAL
    E2 contract equiv.    QA-class: candidate-side invariants (schema,
                          grounding status, evidence closure, refusal
                          behavior, safety probes) — answer WORDING is
                          deliberately not compared

The gate never enables Router authority, never modifies business
execution semantics, and never writes to the artifact registry.
Per-case verdict: PASS | RED (never silent-skip, never hide mismatch).
"""
from runtime.evaluation.router_equivalence.models import (  # noqa: F401
    CaseResult, GateReport, GoldenCase, SideCapture, load_cases)
from runtime.evaluation.router_equivalence.runner import (  # noqa: F401
    run_case, run_gate)
