"""Agent run lifecycle & deadline control — Phase 26C-2.

AUTHORITY SPLIT (no second lifecycle machine — 26C-2 constraint):
the TASK (runtime.queue.store) stays the queue/execution authority
(claim / lease / attempt / terminal CAS, unchanged 26A semantics).
The RUN (this module) is the BUSINESS lifecycle authority: one
agent run = one business outcome, spanning task attempts, HITL
waits and crash recovery.

    agent_runs row:  QUEUED -> RUNNING -> {SUCCEEDED, FAILED,
                      TIMED_OUT, CANCELLED}
                     RUNNING -> WAITING_HUMAN -> RUNNING
                     any non-terminal -> CANCEL_REQUESTED -> CANCELLED

DEADLINE (absolute, run-level): set once at submit
(now() + deadline_seconds, computed DB-side); NEVER moved — retry
does not reset it (INV-26C2-03). Enforced at CONTROL POINTS
(no background reaper, per 26C-2 §32):

    before start · before settle-success · before retry ·
    before approval-resume · pull-based expire_overdue()

Deterministic deadline policy (26C-2 §9):
  A  start at 09:59:59 with deadline 10:00        -> ALLOWED
     (start guard: now() <= deadline_at)
  B  provider call still running at deadline       -> not killed;
     the run is bounded at the next control point
  C  provider returns after deadline               -> result NOT
     accepted (settle guard rejects -> TIMED_OUT)
  D  task completed but deadline passed            -> TIMED_OUT
     (completion CAS carries now() <= deadline_at)

ONE-TRANSACTION RULE (26C-2 §18): every transition that changes a
run's terminal fate writes run + task in the SAME PostgreSQL
transaction (both CAS, affected-rows checked) — a late worker,
duplicate command or racing operator can never leave run and task
in contradictory terminal states. Idempotent: duplicate
cancel/timeout/approve/complete produce NO second effect.

Late-worker protection: after TIMED_OUT/CANCELLED the task is
terminal (CANCELLED/FAILED), so the worker's settle CAS misses AND
the run CAS refuses — rejected at BOTH layers, logged as
run.late_completion_rejected. Exactly-once is NOT claimed.
"""
from __future__ import annotations

import json
from typing import Optional

from .store import LeaseRejected, TaskQueueStore
from .budget import BudgetExceeded

# ---- run state machine -------------------------------------------------- #
QUEUED = "QUEUED"
RUNNING = "RUNNING"
WAITING_HUMAN = "WAITING_HUMAN"
CANCEL_REQUESTED = "CANCEL_REQUESTED"
SUCCEEDED = "SUCCEEDED"
FAILED = "FAILED"
TIMED_OUT = "TIMED_OUT"
CANCELLED = "CANCELLED"

RUN_TERMINAL = (SUCCEEDED, FAILED, TIMED_OUT, CANCELLED)

RUN_TRANSITIONS = {
    QUEUED: (RUNNING, CANCEL_REQUESTED, TIMED_OUT, CANCELLED),
    RUNNING: (WAITING_HUMAN, SUCCEEDED, FAILED, TIMED_OUT,
              CANCEL_REQUESTED, CANCELLED),
    WAITING_HUMAN: (RUNNING, TIMED_OUT, CANCEL_REQUESTED,
                    CANCELLED),
    CANCEL_REQUESTED: (CANCELLED, TIMED_OUT),
    SUCCEEDED: (), FAILED: (), TIMED_OUT: (), CANCELLED: (),
}

RUN_DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id          VARCHAR(120) PRIMARY KEY,
    task_id         VARCHAR(120) NOT NULL UNIQUE,
    project_id      VARCHAR(64),
    case_id         VARCHAR(120),
    state           VARCHAR(30) NOT NULL,
    deadline_at     TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    terminal_at     TIMESTAMPTZ,
    terminal_reason TEXT
);
"""

_NON_TERMINAL_SQL = "('QUEUED','RUNNING','WAITING_HUMAN'," \
                    "'CANCEL_REQUESTED')"


class IllegalRunTransition(RuntimeError):
    """A run transition was refused (wrong state / terminal /
    deadline) — fail closed, never a silent skip."""


class RunControl:
    """Run-lifecycle authority. Wraps (never changes) the 26A/26B
    task semantics; co-transacts run+task terminal decisions."""

    def __init__(self, store: TaskQueueStore, connect,
                 observability=True, budget=None):
        self.store = store
        self._connect = connect
        self._obs = observability
        self.budget = budget          # 26C-3 RunBudget (optional)
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(RUN_DDL)

    # ---- submit ------------------------------------------------------- #
    def submit_run(self, *, task_id: str, run_id: str,
                   deadline_seconds: float = 3600.0,
                   project_id: str = "", case_id: str = "",
                   task_type: str = "agent-run",
                   payload: Optional[dict] = None,
                   trace_id: str = "") -> dict:
        """Create the run (QUEUED, absolute deadline) + enqueue its
        task. Idempotent on both keys: an existing run/task is
        returned as-is (deadline NEVER re-set)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO agent_runs
                        (run_id, task_id, project_id, case_id, state,
                         deadline_at)
                    VALUES (%s,%s,%s,%s,'QUEUED',
                            now() + (%s || ' seconds')::interval)
                    ON CONFLICT (run_id) DO NOTHING
                    RETURNING run_id, state, deadline_at
                """, (run_id, task_id, project_id or None,
                      case_id or None, deadline_seconds))
                row = cur.fetchone()
                created = row is not None
                if not created:
                    cur.execute("SELECT run_id, state, deadline_at "
                                "FROM agent_runs WHERE run_id=%s",
                                (run_id,))
                    row = cur.fetchone()
        task = self.store.enqueue(
            task_id=task_id, task_type=task_type, payload=payload,
            project_id=project_id, run_id=run_id, case_id=case_id,
            trace_id=trace_id)
        self._log("run.created" if created else "run.resubmitted",
                  run_id=run_id, task_id=task_id,
                  status=row["state"],
                  deadline_seconds=deadline_seconds)
        return {"run": dict(row), "task": task, "created": created}

    # ---- reads --------------------------------------------------------- #
    def get_run(self, run_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_runs WHERE "
                            "run_id=%s", (run_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def run_for_task(self, task_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM agent_runs WHERE "
                            "task_id=%s", (task_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    # ---- control point: before start ----------------------------------- #
    def pre_start(self, run_id: str, task: dict) -> str:
        """'go' | 'timed_out' | 'terminal' | 'budget'. Pure gate (no
        mutation) except when the deadline has passed or a hard
        budget is exhausted: then the run AND task are terminalised
        together (one transaction)."""
        run = self.get_run(run_id)
        if run is None:
            return "go"                 # unmanaged run: task-only path
        if run["state"] in RUN_TERMINAL:
            self._log("run.late_start_rejected", level="WARN",
                      run_id=run_id, status=run["state"],
                      task_id=task["task_id"])
            return "terminal"
        if run["deadline_at"] is not None and \
                self._past_deadline(cur_run=run):
            self._expire_in_tx(run, task["task_id"])
            return "timed_out"
        if self.budget is not None:
            try:
                self.budget.check(run_id)
            except BudgetExceeded as e:        # noqa: PERF203
                self._budget_stop(run_id, task["task_id"], e)
                return "budget"
        return "go"

    def on_started(self, run_id: str) -> bool:
        """QUEUED -> RUNNING (tolerant: a crash between task.start
        and this CAS converges at the settle gate). Returns False
        (no transition) for terminal/mismatched runs — a terminal
        run can never go non-terminal through this path."""
        if self._cas(run_id, RUNNING, (QUEUED, RUNNING)):
            self._log("run.started", run_id=run_id, status=RUNNING)
            return True
        return False

    # ---- control point: before settle-success --------------------------- #
    def settle_success(self, task: dict, result: dict) -> dict:
        """Accept a successful completion. ONE transaction:
        (1) task succeed CAS (lease guard, 26A semantics incl.
            DUPLICATE_SUCCESS), (2) run CAS SUCCEEDED guarded by
            now() <= deadline_at. If the deadline guard misses, the
            SAME transaction converts task->FAILED(no retry) and
            run->TIMED_OUT — a late success is never accepted."""
        tid, lease = task["task_id"], task["lease_id"]
        rid = task.get("run_id") or ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM queue_tasks "
                            "WHERE task_id=%s", (tid,))
                row = cur.fetchone()
                if not row:
                    raise IllegalRunTransition("task %s not found"
                                               % tid)
                if row["status"] == "SUCCEEDED":
                    return {"outcome": "DUPLICATE_SUCCESS",
                            "task_id": tid, "changed": False}
                if row["status"] != "RUNNING":
                    # task terminal (cancelled/expired-failed) while
                    # this worker was late — the task-layer CAS wins
                    self._log("run.late_completion_rejected",
                              level="WARN", run_id=rid, task_id=tid,
                              status=row["status"])
                    raise LeaseRejected(
                        "%s: settle refused (task %s — late worker)"
                        % (tid, row["status"]))
                # 26C-3 control point: settle this attempt's usage,
                # then gate BEFORE accepting (an over-budget success
                # is never accepted — no fabricated artifact)
                if self.budget is not None:
                    usage = (result or {}).get("budget_usage") or {}
                    self.budget.settle(
                        rid, "%s:success:%s" % (rid, task.get("attempt")),
                        task_attempts=1,
                        repair_attempts=int(
                            usage.get("repair_attempts") or 0),
                        replans=int(usage.get("replans") or 0))
                    try:
                        self.budget.check(rid)
                    except BudgetExceeded as e:
                        cur.execute("""
                            UPDATE queue_tasks SET
                                status='FAILED',
                                retry_reason=%s, result=NULL,
                                updated_at=now()
                            WHERE task_id=%s AND lease_id=%s
                              AND status='RUNNING'
                        """, ("budget_exceeded:%s"
                              % e.detail.get("type"), tid, lease))
                        cur.execute("""
                            UPDATE agent_runs SET
                                state='FAILED', terminal_at=now(),
                                terminal_reason=%s, updated_at=now()
                            WHERE run_id=%s AND state IN
                                ('QUEUED','RUNNING','WAITING_HUMAN',
                                 'CANCEL_REQUESTED')
                        """, ("budget_exceeded:%s"
                              % e.detail.get("type"), rid))
                        self._log("run.budget_exceeded", level="WARN",
                                  run_id=rid, task_id=tid,
                                  status="FAILED",
                                  budget=e.detail)
                        return {"outcome": "RUN_BUDGET_EXCEEDED",
                                "task_id": tid, "changed": True}
                cur.execute("""
                    UPDATE queue_tasks SET
                        status='SUCCEEDED', result=%s, updated_at=now()
                    WHERE task_id=%s AND lease_id=%s AND status='RUNNING'
                      AND lease_expires_at > now()
                """, (json.dumps(result or {}, ensure_ascii=False),
                      tid, lease))
                if cur.rowcount != 1:
                    cur.execute("SELECT status, lease_id, "
                                "(lease_expires_at > now()) AS ok "
                                "FROM queue_tasks WHERE task_id=%s",
                                (tid,))
                    d = cur.fetchone()
                    raise LeaseRejected(
                        "%s: settle refused (status=%s, lease=%r)"
                        % (tid, d["status"] if d else "?", lease))
                # task accepted -> now the RUN decides (same txn).
                # CANCEL_REQUESTED counts as completable: a mere
                # cancel INTENT does not beat a real completion
                # (one terminal winner; the stale intent is
                # superseded and a later hard cancel reports
                # ALREADY_TERMINAL).
                cur.execute("""
                    UPDATE agent_runs SET
                        state='SUCCEEDED', terminal_at=now(),
                        terminal_reason='completed', updated_at=now()
                    WHERE run_id=%s AND state IN
                        ('QUEUED','RUNNING','CANCEL_REQUESTED')
                      AND (deadline_at IS NULL OR now() <= deadline_at)
                """, (rid,))
                if cur.rowcount == 1:
                    out = {"outcome": "SUCCEEDED", "task_id": tid,
                           "changed": True}
                else:
                    cur.execute("SELECT state, (now() > deadline_at) "
                                "AS overdue FROM agent_runs WHERE "
                                "run_id=%s", (rid,))
                    run = cur.fetchone()
                    if run and run["overdue"]:
                        # Case C/D: completion after the deadline —
                        # undo the success IN THIS TRANSACTION and
                        # terminalise as TIMED_OUT (no retry)
                        cur.execute("""
                            UPDATE queue_tasks SET
                                status='FAILED',
                                retry_reason='run_deadline_exceeded',
                                result=NULL, updated_at=now()
                            WHERE task_id=%s AND status='SUCCEEDED'
                        """, (tid,))
                        cur.execute("""
                            UPDATE agent_runs SET
                                state='TIMED_OUT', terminal_at=now(),
                                terminal_reason='deadline_exceeded',
                                updated_at=now()
                            WHERE run_id=%s AND state NOT IN
                              ('SUCCEEDED','FAILED','TIMED_OUT',
                               'CANCELLED')
                        """, (rid,))
                        out = {"outcome": "RUN_TIMED_OUT",
                               "task_id": tid, "changed": True}
                    else:
                        # run already terminal (cancel raced in):
                        # roll back so task+run stay consistent —
                        # the task write is undone, terminal state
                        # of the run wins.
                        cur.execute("""
                            UPDATE queue_tasks SET
                                status='FAILED',
                                retry_reason='run_superseded',
                                result=NULL, updated_at=now()
                            WHERE task_id=%s AND status='SUCCEEDED'
                        """, (tid,))
                        self._log("run.late_completion_rejected",
                                  level="WARN", run_id=rid,
                                  task_id=tid,
                                  status=run["state"] if run else "?")
                        out = {"outcome": "RUN_TERMINAL_REJECTED",
                               "task_id": tid, "changed": False}
        if out["outcome"] == "SUCCEEDED":
            self._log("run.succeeded", run_id=rid, task_id=tid,
                      status=SUCCEEDED)
        elif out["outcome"] == "RUN_TIMED_OUT":
            self._log("run.timeout", run_id=rid, task_id=tid,
                      status=TIMED_OUT)
        return out

    # ---- control point: HITL defer --------------------------------------- #
    def settle_defer(self, task: dict, stage: str) -> dict:
        """Task fail(no retry, WAITING reason) + run -> WAITING_HUMAN
        in ONE transaction (the 26B defer, run-aware)."""
        tid, lease = task["task_id"], task["lease_id"]
        rid = task.get("run_id") or ""
        reason = "WAITING_FOR_APPROVAL@%s" % stage
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE queue_tasks SET
                        status='FAILED', retry_reason=%s,
                        updated_at=now()
                    WHERE task_id=%s AND lease_id=%s
                      AND status='RUNNING' AND lease_expires_at > now()
                """, (reason[:400], tid, lease))
                if cur.rowcount != 1:
                    raise LeaseRejected(
                        "%s: defer refused (stale lease)" % tid)
                if self.budget is not None:
                    # 26C-3: a deferred attempt is still an attempt
                    self.budget.settle(
                        rid, "%s:attempt:%s" % (rid, task.get("attempt")),
                        task_attempts=1)
                cur.execute("""
                    UPDATE agent_runs SET state='WAITING_HUMAN',
                        updated_at=now()
                    WHERE run_id=%s AND state IN
                        ('QUEUED','RUNNING','WAITING_HUMAN')
                """, (rid,))
        self._log("run.waiting_human", run_id=rid, task_id=tid,
                  status=WAITING_HUMAN, stage=stage)
        return {"outcome": "DEFERRED_WAITING", "task_id": tid,
                "changed": True}

    # ---- control point: failure / retry ----------------------------------- #
    def settle_failure(self, task: dict, reason: str,
                       retry_allowed: bool = True) -> dict:
        """Task fail + run decision in ONE transaction. The deadline
        gates RETRY: past-deadline failures never requeue (retry is
        not a deadline reset — INV-26C2-03). A requeued attempt
        leaves the run RUNNING (business run spans attempts); a
        terminal task failure terminalises the run FAILED."""
        tid, lease = task["task_id"], task["lease_id"]
        rid = task.get("run_id") or ""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status, attempt, max_attempts "
                            "FROM queue_tasks WHERE task_id=%s",
                            (tid,))
                row = cur.fetchone()
                if not row:
                    raise IllegalRunTransition("task %s not found"
                                               % tid)
                if row["status"] == "SUCCEEDED":
                    return {"outcome": "DUPLICATE_SUCCESS",
                            "task_id": tid, "changed": False}
                cur.execute("""
                    UPDATE queue_tasks SET status='FAILED',
                        retry_reason=%s, updated_at=now()
                    WHERE task_id=%s AND lease_id=%s
                      AND status='RUNNING' AND lease_expires_at > now()
                """, (reason[:400], tid, lease))
                if cur.rowcount != 1:
                    raise LeaseRejected(
                        "%s: failure settle refused (stale lease)"
                        % tid)
                overdue = self._overdue(cur, rid)
                # 26C-3: settle this attempt, then gate the RETRY —
                # budget never resets and never allows a retry past
                # a hard task-attempt limit
                budget_stop = None
                if self.budget is not None:
                    self.budget.settle(
                        rid, "%s:attempt:%s" % (rid, row["attempt"]),
                        task_attempts=1)
                    try:
                        self.budget.check(rid, extra_task_attempts=1)
                    except BudgetExceeded as e:
                        budget_stop = e
                retry = retry_allowed and not overdue and \
                    row["attempt"] < row["max_attempts"] and \
                    budget_stop is None
                if budget_stop is not None and not retry:
                    cur.execute("""
                        UPDATE agent_runs SET
                            state='FAILED', terminal_at=now(),
                            terminal_reason=%s, updated_at=now()
                        WHERE run_id=%s AND state IN
                            ('QUEUED','RUNNING','WAITING_HUMAN',
                             'CANCEL_REQUESTED')
                    """, ("budget_exceeded:%s"
                          % budget_stop.detail.get("type"), rid))
                    out = {"outcome": "RUN_BUDGET_EXCEEDED",
                           "task_id": tid, "changed": True}
                elif retry:
                    cur.execute("""
                        UPDATE queue_tasks SET status='PENDING',
                            lease_id=NULL, lease_owner=NULL,
                            lease_expires_at=NULL, updated_at=now()
                        WHERE task_id=%s AND status='FAILED'
                    """, (tid,))
                    out = {"outcome": "FAILED_REQUEUED",
                           "task_id": tid, "changed": True}
                elif overdue:
                    self._expire_task_in_cur(cur, tid)
                    cur.execute("""
                        UPDATE agent_runs SET state='TIMED_OUT',
                            terminal_at=now(),
                            terminal_reason='deadline_exceeded',
                            updated_at=now()
                        WHERE run_id=%s AND state NOT IN
                          ('SUCCEEDED','FAILED','TIMED_OUT',
                           'CANCELLED')
                    """, (rid,))
                    out = {"outcome": "RUN_TIMED_OUT", "task_id": tid,
                           "changed": True}
                else:
                    cur.execute("""
                        UPDATE agent_runs SET state='FAILED',
                            terminal_at=now(),
                            terminal_reason=%s, updated_at=now()
                        WHERE run_id=%s AND state NOT IN
                          ('SUCCEEDED','FAILED','TIMED_OUT',
                           'CANCELLED')
                    """, (reason[:200], rid))
                    out = {"outcome": "FAILED", "task_id": tid,
                           "changed": True}
        self._log("run.timeout" if out["outcome"] == "RUN_TIMED_OUT"
                  else "run.failed", run_id=rid, task_id=tid,
                  status=out["outcome"])
        return out

    # ---- cancel ------------------------------------------------------------ #
    def request_cancel(self, run_id: str) -> dict:
        """Operator INTENT (no task mutation): non-terminal ->
        CANCEL_REQUESTED. Idempotent (already-requested/terminal is
        a visible NO-OP, never a second effect)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE agent_runs SET
                        state='CANCEL_REQUESTED', updated_at=now()
                    WHERE run_id=%s AND state IN
                        ('QUEUED','RUNNING','WAITING_HUMAN')
                """, (run_id,))
                changed = cur.rowcount == 1
        self._log("run.cancel_requested", run_id=run_id,
                  status=CANCEL_REQUESTED if changed else "NOOP")
        return {"outcome": "CANCEL_REQUESTED" if changed
                else "ALREADY_TERMINAL_OR_REQUESTED",
                "run_id": run_id, "changed": changed}

    def cancel_run(self, task_id: str) -> dict:
        """Hard cancel, run-aware, ONE transaction: task cancel CAS
        + run -> CANCELLED. If the task CAS loses (already
        SUCCEEDED/FAILED) the run is synced to the task's terminal —
        exactly one terminal winner, never both effects. Duplicate
        cancel = idempotent NO-OP."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE queue_tasks SET status='CANCELLED',
                        updated_at=now()
                    WHERE task_id=%s AND status IN
                        ('PENDING','LEASED','RUNNING','LEASE_EXPIRED',
                         'FAILED')
                """, (task_id,))
                task_won = cur.rowcount == 1
                cur.execute("SELECT run_id FROM agent_runs WHERE "
                            "task_id=%s", (task_id,))
                r = cur.fetchone()
                rid = r["run_id"] if r else None
                if rid:
                    if task_won:
                        cur.execute("""
                            UPDATE agent_runs SET
                                state='CANCELLED', terminal_at=now(),
                                terminal_reason='operator_cancel',
                                updated_at=now()
                            WHERE run_id=%s AND state NOT IN
                              ('SUCCEEDED','FAILED','TIMED_OUT',
                               'CANCELLED')
                        """, (rid,))
                        out = {"outcome": "CANCELLED",
                               "task_id": task_id, "changed": True}
                    else:
                        # task already terminal: sync run to it
                        cur.execute("""
                            UPDATE agent_runs r SET
                                state = t.status,
                                terminal_at = now(),
                                terminal_reason = 'task_terminal',
                                updated_at = now()
                            FROM queue_tasks t
                            WHERE r.task_id = t.task_id
                              AND r.run_id = %s
                              AND r.state IN ('QUEUED','RUNNING',
                                              'WAITING_HUMAN',
                                              'CANCEL_REQUESTED')
                        """, (rid,))
                        out = {"outcome": "ALREADY_TERMINAL",
                               "task_id": task_id, "changed": False}
                else:
                    out = {"outcome": "CANCELLED" if task_won
                           else "ALREADY_TERMINAL",
                           "task_id": task_id,
                           "changed": task_won}
        self._log("run.cancelled" if out["changed"] else
                  "run.cancel_noop", run_id=rid or "",
                  task_id=task_id, status=out["outcome"])
        return out

    # ---- approval gate ------------------------------------------------------- #
    def approve_resume_gate(self, run_id: str) -> str:
        """'ok' | 'not_waiting' | 'timed_out' | 'terminal'. Called
        BEFORE the 26B marker+requeue: WAITING_HUMAN -> RUNNING is
        allowed only while now() <= deadline_at (the approval's own
        transaction timestamp decides — 26C-2 §14). 26C-3: an
        exhausted budget also refuses (resume never resets budget)."""
        if self.budget is not None:
            try:
                self.budget.check(run_id)
            except BudgetExceeded as e:
                self._log("run.late_approval_rejected", level="WARN",
                          run_id=run_id, status="BUDGET_EXCEEDED",
                          budget=e.detail)
                return "budget"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE agent_runs SET state='RUNNING',
                        updated_at=now()
                    WHERE run_id=%s AND state='WAITING_HUMAN'
                      AND (deadline_at IS NULL OR now() <= deadline_at)
                """, (run_id,))
                if cur.rowcount == 1:
                    self._log("run.resume_approved", run_id=run_id,
                              status=RUNNING)
                    return "ok"
                cur.execute("SELECT state, (now() > deadline_at) AS "
                            "overdue FROM agent_runs WHERE run_id=%s",
                            (run_id,))
                run = cur.fetchone()
                if run is None:
                    return "not_waiting"
                if run["state"] in RUN_TERMINAL:
                    self._log("run.late_approval_rejected",
                              level="WARN", run_id=run_id,
                              status=run["state"])
                    return "terminal"
                if run["overdue"]:
                    self._expire_run_only(cur, run_id)
                    self._log("run.timeout", run_id=run_id,
                              status=TIMED_OUT)
                    return "timed_out"
                return "not_waiting"

    # ---- pull-based reconciliation (no daemon; 26C-2 §32) --------------------- #
    def expire_overdue(self, limit: int = 100) -> list:
        """Expire every non-terminal run past its deadline (run +
        task terminalised together). Call at control points / ops.
        A periodic reaper remains Future/P3 debt."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT run_id, task_id FROM agent_runs
                    WHERE state IN ('QUEUED','RUNNING',
                                    'WAITING_HUMAN','CANCEL_REQUESTED')
                      AND deadline_at IS NOT NULL
                      AND now() > deadline_at
                    LIMIT %s
                """, (limit,))
                rows = cur.fetchall()
        expired = []
        for r in rows:
            self._expire_in_tx(dict(run_id=r["run_id"]),
                               r["task_id"])
            expired.append(r["run_id"])
        return expired

    def _budget_stop(self, run_id: str, task_id: str,
                     exc: "BudgetExceeded") -> None:
        """26C-3 hard stop: task CANCELLED + run FAILED with the
        structured budget reason (the expiry pattern; no new run
        states, no automatic retry, terminal)."""
        reason = "budget_exceeded:%s" % exc.detail.get("type")
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE queue_tasks SET status='CANCELLED',
                        retry_reason=%s, updated_at=now()
                    WHERE task_id=%s AND status IN
                        ('PENDING','LEASED','RUNNING','LEASE_EXPIRED',
                         'FAILED')
                """, (reason[:400], task_id))
                cur.execute("""
                    UPDATE agent_runs SET state='FAILED',
                        terminal_at=now(), terminal_reason=%s,
                        updated_at=now()
                    WHERE run_id=%s AND state IN
                        ('QUEUED','RUNNING','WAITING_HUMAN',
                         'CANCEL_REQUESTED')
                """, (reason[:400], run_id))
        self._log("run.budget_exceeded", level="WARN", run_id=run_id,
                  task_id=task_id, status="FAILED", budget=exc.detail)

    # ---- internals ------------------------------------------------------------- #
    def _cas(self, run_id, to_state, from_states) -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                return self._cas_cur(cur, run_id, to_state,
                                     from_states)

    def _cas_cur(self, cur, run_id, to_state, from_states) -> bool:
        places = ",".join(["%s"] * len(from_states))
        cur.execute(
            "UPDATE agent_runs SET state=%s, updated_at=now() "
            "WHERE run_id=%s AND state IN (%s)"
            % ("%s", "%s", places),
            (to_state, run_id, *from_states))
        return cur.rowcount == 1

    def _overdue(self, cur, run_id) -> bool:
        cur.execute("SELECT (deadline_at IS NOT NULL AND "
                    "now() > deadline_at) AS o FROM agent_runs "
                    "WHERE run_id=%s", (run_id,))
        row = cur.fetchone()
        return bool(row and row["o"])

    def _past_deadline(self, cur_run: dict) -> bool:
        """DB-clock comparison (never a Python-side clock)."""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT now() > %s AS o",
                            (cur_run["deadline_at"],))
                return bool(cur.fetchone()["o"])

    def _expire_in_tx(self, run: dict, task_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                self._expire_task_in_cur(cur, task_id)
                self._expire_run_only(cur, run["run_id"])
        self._log("run.timeout", run_id=run["run_id"],
                  task_id=task_id, status=TIMED_OUT)

    def _expire_task_in_cur(self, cur, task_id: str) -> None:
        """Task -> CANCELLED with reason (legal from every
        non-terminal task state; a live worker's later settle CAS
        misses — late-worker rejection at the task layer)."""
        cur.execute("""
            UPDATE queue_tasks SET status='CANCELLED',
                retry_reason='run_deadline_exceeded',
                updated_at=now()
            WHERE task_id=%s AND status IN
                ('PENDING','LEASED','RUNNING','LEASE_EXPIRED','FAILED')
        """, (task_id,))

    def _expire_run_only(self, cur, run_id: str) -> None:
        cur.execute("""
            UPDATE agent_runs SET state='TIMED_OUT',
                terminal_at=now(),
                terminal_reason='deadline_exceeded', updated_at=now()
            WHERE run_id=%s AND state IN
                ('QUEUED','RUNNING','WAITING_HUMAN','CANCEL_REQUESTED')
        """, (run_id,))

    def _log(self, event, level="INFO", run_id="", task_id="",
             status="", **kw):
        if not self._obs:
            return
        try:
            import runtime.obs as obs
            obs.log(event, level=level, status=status, run_id=run_id,
                    task_id=task_id, **kw)
        except Exception:  # noqa: BLE001 — observation only
            pass
