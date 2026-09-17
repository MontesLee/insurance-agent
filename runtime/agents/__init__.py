"""Multi-Agent V0.1 (Phase 5).

Specialist Agents execute tasks; the Harness retains absolute control over
lifecycle, dependencies, eval, and recovery (§2/§10/§27).

    Planner → Task Graph → Agent Assignment → Harness → Specialist Agent
                                                             ↓
                                                          Artifact
                                                             ↓
                                                             Eval
"""
from runtime.agents.registry import (AGENT_REGISTRY, TASK_AGENT_MAP,
                                     agent_for_task, get, is_valid_agent,
                                     can_execute, allowed_tools,
                                     validate_assignment)

__all__ = [
    "AGENT_REGISTRY", "TASK_AGENT_MAP", "agent_for_task", "get",
    "is_valid_agent", "can_execute", "allowed_tools", "validate_assignment",
]
