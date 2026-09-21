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

__all__ = [
    "ALL_STATES", "CANCELLED", "FAILED", "LEASED", "LEASE_EXPIRED",
    "PENDING", "RUNNING", "SUCCEEDED", "TERMINAL_STATES", "TRANSITIONS",
    "idempotency_key", "new_lease_id", "new_task_id",
    "new_worker_instance_id", "transition_allowed",
    "IllegalTransition", "LeaseRejected", "OutcomeUnknown", "QueueError",
    "TaskQueueStore", "TaskWorker",
]
