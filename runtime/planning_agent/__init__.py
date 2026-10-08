"""Insurance Planning Agent package (Phase 28.D / M3, ADR-025 APPROVED).

Public API:
    planning_slice_enabled()   -> feature flag (DEFAULT OFF)
    run_planning_turn(...)     -> contract guard + spine execution mount

v1 behavior = the existing chat tool-stack mounted on the planning
registry entry (same spine, same artifacts, same evals; identity +
guard only). E1 equivalence against
tests/golden/planning-baseline.json is the M3 acceptance gate.
"""
from runtime.planning_agent.agent import (  # noqa: F401
    PLANNING_INTENTS,
    guard_ok,
    planning_slice_enabled,
    run_planning_turn,
)
