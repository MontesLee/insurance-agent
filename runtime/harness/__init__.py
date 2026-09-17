"""Long-Running Agent Harness V0.1 (Phase 3).

Layering (spec §13):
    Agent  = 决策 / 执行智能 (runtime/agent/)
    Harness = 可靠执行基础设施 (this module)

The Harness does NOT make insurance decisions. It manages:
    WHEN to execute / WHAT task / dependency / status / PASS/FAIL / recovery.

Everything below REUSES the existing deterministic runtime:
    tasks.py (task model) → orchestrator._execute_stage (eval+repair)
    → checkpoint.py (persistence) → store.py (disk) → events.py (observability)

V0.1 persistence = JSON files under a harness root (no Redis/Postgres/Celery).
"""
from runtime.harness.harness import (LongRunningHarness, Project,
                                     load_project, list_projects,
                                     HARNESS_TASK_EVENTS)

__all__ = ["LongRunningHarness", "Project", "load_project", "list_projects",
           "HARNESS_TASK_EVENTS"]
