"""PostgreSQL task queue store — Phase 26A.

PostgreSQL is the ONLY queue and the ONLY task-state authority (no
Redis, no second queue). Every mutation is a single compare-and-set
statement guarded by (task_id, lease_id, status, lease validity), so:

  * a worker holding a stale/expired/superseded lease can NEVER write
  * two workers can never both hold a valid lease on one task
  * terminal states can never be re-executed or overwritten
  * a duplicate completion is a visible no-op, never a second result

Claim atomicity (26A-06/07): the claim is ONE statement —
UPDATE ... WHERE task_id IN (SELECT ... FOR UPDATE SKIP LOCKED) —
selection, lease assignment and attempt increment happen in the same
transaction; there is no SELECT-then-UPDATE window.

Connection injection: like KnowledgeRegistryStore, the connect factory
is injected; this module imports nothing from the business layers.
"""
from __future__ import annotations

import json
import time
from typing import Callable, Optional

from . import model

QUEUE_DDL = """
CREATE TABLE IF NOT EXISTS queue_tasks (
    task_id            VARCHAR(120) PRIMARY KEY,
    project_id         VARCHAR(64),
    run_id             VARCHAR(120),
    case_id            VARCHAR(64),
    task_type          VARCHAR(64) NOT NULL,
    skill_id           VARCHAR(120),
    payload            JSONB NOT NULL DEFAULT '{}',
    status             VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    attempt            INTEGER NOT NULL DEFAULT 0,
    max_attempts       INTEGER NOT NULL DEFAULT 3,
    lease_id           VARCHAR(80),
    lease_owner        VARCHAR(240),
    lease_acquired_at  TIMESTAMPTZ,
    lease_expires_at   TIMESTAMPTZ,
    heartbeat_at       TIMESTAMPTZ,
    idempotency_key    VARCHAR(240),
    result             JSONB,
    retry_reason       TEXT,
    request_id         VARCHAR(64),
    correlation_id     VARCHAR(64),
    trace_id           VARCHAR(64),
    worker_id          VARCHAR(120),
    worker_instance_id VARCHAR(160),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_qt_claim
    ON queue_tasks(status, created_at);
CREATE INDEX IF NOT EXISTS idx_qt_expiry
    ON queue_tasks(lease_expires_at)
    WHERE status IN ('LEASED', 'RUNNING');
"""


class QueueError(RuntimeError):
    """Queue-layer failure (fail-closed; never guessed around)."""


class LeaseRejected(QueueError):
    """The writer does not hold the CURRENT VALID lease — stale,
    mismatched, or expired authority. The write is refused."""


class IllegalTransition(QueueError):
    """The requested state change is not in the state machine."""


class OutcomeUnknown(QueueError):
    """26A-17: the database result of a critical write could not be
    determined (connection lost mid-flight). The caller MUST treat the
    task as RECOVERY_REQUIRED and re-read state before acting — never
    assume success or failure."""


class TaskQueueStore:
    """Authoritative PostgreSQL queue (state machine + leases)."""

    def __init__(self, connect: Callable):
        self._connect = connect
        # mutation-testing seam: tests may set False to simulate the
        # M26-01 defect (SKIP LOCKED removed) and prove detection
        self._skip_locked = True

    def init_schema(self) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(QUEUE_DDL)

    # ---- enqueue ---------------------------------------------------- #
    def enqueue(self, *, task_id: str, task_type: str,
                payload: Optional[dict] = None,
                project_id: str = "", run_id: str = "", case_id: str = "",
                skill_id: str = "", max_attempts: int = 3,
                request_id: str = "", correlation_id: str = "",
                trace_id: str = "") -> dict:
        """Idempotent enqueue: an existing task_id is returned as-is
        (never duplicated, never reset)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO queue_tasks
                        (task_id, project_id, run_id, case_id, task_type,
                         skill_id, payload, status, attempt, max_attempts,
                         idempotency_key, request_id, correlation_id,
                         trace_id, updated_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'PENDING',0,%s,%s,%s,%s,%s,
                            now())
                    ON CONFLICT (task_id) DO NOTHING
                """, (task_id, project_id or None, run_id or None,
                      case_id or None, task_type, skill_id or None,
                      json.dumps(payload or {}, ensure_ascii=False),
                      max_attempts,
                      model.idempotency_key(task_id, 1),
                      request_id, correlation_id, trace_id))
                return self._get(cur, task_id)

    # ---- claim (atomic: select+lease+attempt in ONE statement) ----- #
    def claim(self, worker_id: str, worker_instance_id: str,
              lease_seconds: float = 30.0,
              task_types: Optional[list] = None) -> Optional[dict]:
        """Claim ONE claimable task. Claimable = PENDING, or
        LEASED/RUNNING whose lease has expired (crash recovery — the
        expiry is requeue-visible via recover_expired/lease columns).
        SELECT ... FOR UPDATE SKIP LOCKED + lease assignment + attempt
        increment is a single atomic statement: N competing workers can
        never produce two valid leases for one task."""
        skip = "SKIP LOCKED" if self._skip_locked else ""
        type_filter = "AND task_type = ANY(%s)" if task_types else ""
        sql = """
            UPDATE queue_tasks SET
                status = 'LEASED',
                lease_id = %s,
                lease_owner = %s || '/' || %s,
                lease_acquired_at = now(),
                lease_expires_at = now() + (%s || ' seconds')::interval,
                heartbeat_at = now(),
                attempt = attempt + 1,
                worker_id = %s,
                worker_instance_id = %s,
                idempotency_key = task_id || '#' || (attempt+1)::text,
                retry_reason = NULL,
                updated_at = now()
            WHERE task_id = (
                SELECT task_id FROM queue_tasks
                WHERE status = 'PENDING'
                   OR (status IN ('LEASED','RUNNING')
                       AND lease_expires_at < now())
                {type_filter}
                ORDER BY created_at
                FOR UPDATE {skip} LIMIT 1
            )
            RETURNING *
        """.format(type_filter=type_filter, skip=skip)
        params = [model.new_lease_id(), worker_id, worker_instance_id,
                  lease_seconds, worker_id, worker_instance_id]
        if task_types:
            params.append(list(task_types))
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    row = cur.fetchone()
                    return self._row(row) if row else None
        except Exception as e:  # noqa: BLE001 — DB failure is fail-closed
            raise QueueError("claim failed (fail closed): %s"
                             % str(e)[:160]) from e

    # ---- lease-guarded transitions ------------------------------------ #
    def start(self, task_id: str, lease_id: str) -> dict:
        return self._guarded(task_id, lease_id, """
            UPDATE queue_tasks SET status='RUNNING', updated_at=now()
            WHERE task_id=%s AND lease_id=%s AND status='LEASED'
              AND lease_expires_at > now()
        """, (task_id, lease_id), to_state="RUNNING")

    def heartbeat(self, task_id: str, lease_id: str,
                  extend_seconds: float = 30.0) -> dict:
        """Only the CURRENT lease owner may heartbeat; a mismatched or
        expired lease is refused (26A-11)."""
        return self._guarded(task_id, lease_id, """
            UPDATE queue_tasks SET
                lease_expires_at = now() + (%s || ' seconds')::interval,
                heartbeat_at = now(), updated_at=now()
            WHERE task_id=%s AND lease_id=%s
              AND status IN ('LEASED','RUNNING')
              AND lease_expires_at > now()
        """, (extend_seconds, task_id, lease_id), to_state=None)

    def succeed(self, task_id: str, lease_id: str,
                result: Optional[dict] = None) -> dict:
        """RUNNING + valid lease -> SUCCEEDED. A duplicate completion
        (already SUCCEEDED with the same idempotency key) is a visible
        NO-OP (never a second result); a stale lease is REJECTED."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, idempotency_key FROM "
                            "queue_tasks WHERE task_id=%s", (task_id,))
                row = cur.fetchone()
                if not row:
                    raise QueueError("task %s not found" % task_id)
                if row["status"] == model.SUCCEEDED:
                    return {"outcome": "DUPLICATE_SUCCESS",
                            "task_id": task_id, "changed": False}
                cur.execute("""
                    UPDATE queue_tasks SET
                        status='SUCCEEDED', result=%s, updated_at=now()
                    WHERE task_id=%s AND lease_id=%s AND status='RUNNING'
                      AND lease_expires_at > now()
                """, (json.dumps(result or {}, ensure_ascii=False),
                      task_id, lease_id))
                if cur.rowcount != 1:
                    self._reject(cur, task_id, lease_id)
                return {"outcome": "SUCCEEDED", "task_id": task_id,
                        "changed": True}

    def fail(self, task_id: str, lease_id: str, reason: str,
             retry: bool = True) -> dict:
        """RUNNING + valid lease -> FAILED. When retry is allowed and
        attempts remain, the same transaction requeues the task
        (FAILED -> PENDING); at max_attempts the task stays FAILED
        (bounded retry, 26A-18)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, attempt, max_attempts FROM "
                            "queue_tasks WHERE task_id=%s", (task_id,))
                row = cur.fetchone()
                if not row:
                    raise QueueError("task %s not found" % task_id)
                if row["status"] == model.SUCCEEDED:
                    return {"outcome": "DUPLICATE_SUCCESS",
                            "task_id": task_id, "changed": False}
                cur.execute("""
                    UPDATE queue_tasks SET
                        status='FAILED', retry_reason=%s, updated_at=now()
                    WHERE task_id=%s AND lease_id=%s AND status='RUNNING'
                      AND lease_expires_at > now()
                """, (reason[:400], task_id, lease_id))
                if cur.rowcount != 1:
                    self._reject(cur, task_id, lease_id)
                if retry and row["attempt"] < row["max_attempts"]:
                    cur.execute("""
                        UPDATE queue_tasks SET status='PENDING',
                            lease_id=NULL, lease_owner=NULL,
                            lease_expires_at=NULL, updated_at=now()
                        WHERE task_id=%s AND status='FAILED'
                    """, (task_id,))
                    return {"outcome": "FAILED_REQUEUED",
                            "task_id": task_id, "changed": True}
                return {"outcome": "FAILED", "task_id": task_id,
                        "changed": True}

    def release(self, task_id: str, lease_id: str) -> dict:
        """Graceful-shutdown path: give the task back (LEASED/RUNNING
        -> PENDING) so another worker can take it immediately."""
        return self._guarded(task_id, lease_id, """
            UPDATE queue_tasks SET
                status='PENDING', lease_id=NULL, lease_owner=NULL,
                lease_expires_at=NULL, updated_at=now()
            WHERE task_id=%s AND lease_id=%s
              AND status IN ('LEASED','RUNNING')
              AND lease_expires_at > now()
        """, (task_id, lease_id), to_state="PENDING")

    # ---- operator / recovery ------------------------------------------- #
    def recover_expired(self) -> list:
        """Lease-expiry crash recovery (26A-10): LEASED/RUNNING with an
        expired lease transitions through LEASE_EXPIRED (recorded, so
        expiry is visible and can NEVER become SUCCEEDED by itself)
        and is immediately requeued to PENDING in the same
        transaction. Returns the recovered task ids."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE queue_tasks SET
                        status='PENDING', lease_id=NULL, lease_owner=NULL,
                        lease_expires_at=NULL,
                        retry_reason = COALESCE(retry_reason,
                                                'lease_expired'),
                        updated_at=now()
                    WHERE status IN ('LEASED','RUNNING')
                      AND lease_expires_at < now()
                    RETURNING task_id
                """)
                return [r["task_id"] for r in cur.fetchall()]

    def cancel(self, task_id: str) -> dict:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE queue_tasks SET status='CANCELLED',
                        updated_at=now()
                    WHERE task_id=%s AND status IN
                        ('PENDING','LEASED','RUNNING','LEASE_EXPIRED',
                         'FAILED')
                """, (task_id,))
                if cur.rowcount != 1:
                    raise IllegalTransition(
                        "cancel refused for %s (terminal or missing)"
                        % task_id)
                return {"outcome": "CANCELLED", "task_id": task_id}

    # ---- reads ---------------------------------------------------------- #
    def get(self, task_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                return self._get(cur, task_id)

    def list(self, status: Optional[str] = None,
             limit: int = 100) -> list:
        with self._connect() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute("SELECT * FROM queue_tasks "
                                "WHERE status=%s ORDER BY created_at "
                                "LIMIT %s", (status, limit))
                else:
                    cur.execute("SELECT * FROM queue_tasks "
                                "ORDER BY created_at LIMIT %s", (limit,))
                return [self._row(r) for r in cur.fetchall()]

    # ---- internals -------------------------------------------------------- #
    def _get(self, cur, task_id):
        cur.execute("SELECT * FROM queue_tasks WHERE task_id=%s",
                    (task_id,))
        row = cur.fetchone()
        return self._row(row) if row else None

    def _guarded(self, task_id, lease_id, sql, params, to_state):
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    if cur.rowcount != 1:
                        self._reject(cur, task_id, lease_id)
                    return self._get(cur, task_id) or {
                        "task_id": task_id, "status": to_state}
        except Exception as e:
            if isinstance(e, (LeaseRejected, IllegalTransition)):
                raise
            raise OutcomeUnknown(
                "critical write outcome UNKNOWN for %s (connection "
                "lost? treat as RECOVERY_REQUIRED and re-read): %s"
                % (task_id, str(e)[:120])) from e

    def _reject(self, cur, task_id, lease_id):
        """Distinguish WHY the guarded write missed (fail-closed
        diagnostics; never a silent skip). Lease validity is decided
        by the DATABASE clock (now()), never by Python-side string
        comparison."""
        cur.execute("SELECT status, lease_id, "
                    "(lease_expires_at > now()) AS lease_valid "
                    "FROM queue_tasks WHERE task_id=%s", (task_id,))
        row = cur.fetchone()
        if not row:
            raise QueueError("task %s not found" % task_id)
        if row["lease_id"] != lease_id:
            raise LeaseRejected(
                "%s: lease %r is not current (held: %r) — stale worker "
                "write REJECTED" % (task_id, lease_id[:12],
                                    (row["lease_id"] or "")[:12]))
        if row["lease_valid"] is False:
            raise LeaseRejected(
                "%s: lease %r EXPIRED — write REJECTED" %
                (task_id, lease_id[:12]))
        raise IllegalTransition(
            "%s: state %r refuses this write" % (task_id,
                                                 row["status"]))

    @staticmethod
    def _row(r) -> dict:
        if not r:
            return {}
        d = dict(r)
        for k in ("lease_acquired_at", "lease_expires_at",
                  "heartbeat_at", "created_at", "updated_at"):
            if d.get(k) is not None:
                d[k] = str(d[k])
        return d
