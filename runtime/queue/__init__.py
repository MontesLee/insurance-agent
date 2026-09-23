"""runtime.queue — PostgreSQL-backed distributed task queue (26A).

PostgreSQL is the ONLY queue and the ONLY task-state authority.
Workers are stateless executors with injected executors — business
skills stay queue-agnostic. Execution semantics are AT-LEAST-ONCE +
idempotent completion + stale-lease rejection (exactly-once is NOT
claimed).
"""
from .model import (ALL_STATES, CANCELLED, FAILED, LEASED, LEASE_EXPIRED,
                    PENDING, RUNNING, SUCCEEDED, TERMINAL_STATES,
                    TRANSITIONS, idempotency_key, new_lease_id,
                    new_task_id, new_worker_instance_id,
                    transition_allowed)
from .store import (IllegalTransition, LeaseRejected, OutcomeUnknown,
                    QueueError, TaskQueueStore)
from .worker import TaskWorker
from .agent_runtime import (AgentTaskWorker, defer_reason,
                            make_agent_executor, parse_defer_reason)
from .ops import OpsDenied, QueueOps
from .run_control import (
    CANCELLED as RUN_CANCELLED,
    FAILED as RUN_FAILED,
    QUEUED as RUN_QUEUED,
    RUNNING as RUN_RUNNING,
    SUCCEEDED as RUN_SUCCEEDED,
    TIMED_OUT as RUN_TIMED_OUT,
    WAITING_HUMAN as RUN_WAITING_HUMAN,
    CANCEL_REQUESTED as RUN_CANCEL_REQUESTED,
    RUN_TERMINAL, RUN_TRANSITIONS, IllegalRunTransition, RunControl)
from .budget import UNKNOWN as BUDGET_UNKNOWN, BudgetExceeded, \
    RunBudget
from .recovery import RecoveryController

__all__ = [
    "ALL_STATES", "CANCELLED", "FAILED", "LEASED", "LEASE_EXPIRED",
    "PENDING", "RUNNING", "SUCCEEDED", "TERMINAL_STATES", "TRANSITIONS",
    "idempotency_key", "new_lease_id", "new_task_id",
    "new_worker_instance_id", "transition_allowed",
    "IllegalTransition", "LeaseRejected", "OutcomeUnknown", "QueueError",
    "TaskQueueStore", "TaskWorker", "AgentTaskWorker", "defer_reason",
    "make_agent_executor", "parse_defer_reason", "OpsDenied", "QueueOps",
    "RUN_CANCELLED", "RUN_FAILED", "RUN_QUEUED", "RUN_RUNNING",
    "RUN_SUCCEEDED", "RUN_TIMED_OUT", "RUN_WAITING_HUMAN",
    "RUN_CANCEL_REQUESTED", "RUN_TERMINAL", "RUN_TRANSITIONS",
    "IllegalRunTransition", "RunControl",
    "BUDGET_UNKNOWN", "BudgetExceeded", "RunBudget",
    "RecoveryController",
]
