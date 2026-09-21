"""Distributed task model — Phase 26A.

The queue's task is a NEW, parallel entity: it references (project,
run, case, skill) but never replaces the in-case task model
(runtime/tasks.py keeps its single-write-path mirror). Business
Skills never see queue concepts.

State machine (every transition explicit; illegal transitions are
refused at the store layer via compare-and-set SQL):

    PENDING ──claim──► LEASED ──start──► RUNNING ──succeed──► SUCCEEDED ✝
       ▲                  │                 │        └──fail──► FAILED
       │                  ├─ lease expired ─┤                    │
       ├──── release ─────┘                 │      retry (attempt<max)
       ├◄─ LEASE_EXPIRED ◄──────────────────┘        │
       └◄──────────── FAILED (retry requeue) ────────┘
    PENDING/LEASED/RUNNING ──cancel──► CANCELLED ✝

✝ terminal. LEASE_EXPIRED never jumps straight to SUCCEEDED (expiry
is a loss of authority, not a result). Execution semantics are
honestly AT-LEAST-ONCE + idempotent completion + stale-lease
rejection — exactly-once is NOT claimed (Phase 26A §34).
"""
from __future__ import annotations

import uuid

PENDING = "PENDING"
LEASED = "LEASED"
RUNNING = "RUNNING"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
LEASE_EXPIRED = "LEASE_EXPIRED"
CANCELLED = "CANCELLED"

ALL_STATES = (PENDING, LEASED, RUNNING, SUCCEEDED, FAILED,
              LEASE_EXPIRED, CANCELLED)
TERMINAL_STATES = (SUCCEEDED, CANCELLED)

# from -> {allowed to}; enforced by TaskQueueStore compare-and-set
TRANSITIONS = {
    PENDING: {LEASED, CANCELLED},
    LEASED: {RUNNING, PENDING, LEASE_EXPIRED, CANCELLED},
    RUNNING: {SUCCEEDED, FAILED, PENDING, LEASE_EXPIRED, CANCELLED},
    FAILED: {PENDING},                       # explicit retry requeue
    LEASE_EXPIRED: {PENDING, CANCELLED},
    SUCCEEDED: set(),
    CANCELLED: set(),
}


def transition_allowed(cur: str, to: str) -> bool:
    return to in TRANSITIONS.get(cur, set())


def new_task_id(task_type: str = "task") -> str:
    return "qt_%s_%s" % ("".join(ch for ch in task_type.lower()
                                 if ch.isalnum())[:16] or "task",
                         uuid.uuid4().hex[:16])


def new_lease_id() -> str:
    return "lease_%s" % uuid.uuid4().hex[:20]


def new_worker_instance_id(worker_id: str) -> str:
    """One identity per actual worker PROCESS lifetime. Deliberately
    NOT hostname/pid/thread-id alone: worker_id (logical) + fresh
    random component, so restarts and concurrent instances of the
    same logical worker are distinguishable."""
    return "wi_%s_%s" % (worker_id, uuid.uuid4().hex[:12])


def idempotency_key(task_id: str, attempt: int) -> str:
    """One logical execution attempt = (task_id, attempt). Terminal
    results are keyed on this so duplicate completions cannot create
    a second business result."""
    return "%s#%d" % (task_id, attempt)
