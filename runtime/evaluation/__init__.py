"""Runtime-side evaluation INFRASTRUCTURE (Phase 28.B4).

Distinct from the top-level evaluation/ package (the deterministic eval
ENGINE, ADR-004 territory — untouched): this namespace hosts test
harnesses that CONSUME the running system. Nothing here is ever on the
production execution path; modules are imported by tests/CLI only.
"""
