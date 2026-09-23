"""Production recovery & reconciliation — Phase 26C-4.

A minimal, PULL-BASED controller (no daemon, no scheduler, no
execution): it INSPECTS durable state, CLASSIFIES it, and applies
DETERMINISTIC, CAS-guarded, idempotent reconciliation — or fails
closed. It never plans, never executes agents/skills/LLM, never
fabricates artifacts or successes.

    reconcile_once()
      1. reuse 26A recover_expired()        (expired leases → PENDING)
      2. reuse 26C-2 expire_overdue()       (overdue runs → TIMED_OUT
                                             + task terminalised)
      3. run/task consistency scan          (the 26C-4 boundary)

Classification (per PHASE_26C4_AUDIT.md):
  HEALTHY      consistent / in-flight with a valid lease — no action
  RECOVERABLE  deterministic one-way sync (task is the EXECUTION
               authority; a non-terminal run follows its terminal
               task; a terminal run terminalises its non-terminal
               task as CANCELLED with the run's reason — NEVER as
               SUCCEEDED)
  STALE        old worker/lease/attempt — existing CAS rejects;
               surfaced in events when observed
  INCONSISTENT run SUCCEEDED with task not SUCCEEDED, or task
               SUCCEEDED with a non-success terminal run — NO
               mutation, audit event, fail closed
  UNKNOWN      not provable from durable state — fail closed
               (this build has no actionable UNKNOWN beyond
               INCONSISTENT; the class exists for future
               filesystem-level checks)

Every action is ONE CAS/transaction: a crash mid-reconcile (Q12)
is safely retried — reconcile();reconcile();reconcile() ≡
reconcile() (state-equivalent; the audit trail is append-only by
design). Audit rows land in recovery_events + obs (stderr only —
product stdout is untouched, Phase 25.1).

Exactly-once execution is NOT claimed; terminal states are NEVER
resurrected (all writes are state-guarded CAS).
"""
from __future__ import annotations

import time
import uuid
from typing import Optional

RECOVERY_DDL = """
CREATE TABLE IF NOT EXISTS recovery_events (
    event_id           BIGSERIAL PRIMARY KEY,
    reconciliation_id  VARCHAR(64) NOT NULL,
    classification     VARCHAR(20) NOT NULL,
    run_id             VARCHAR(120),
    task_id            VARCHAR(120),
    worker_id          VARCHAR(120),
    old_state          VARCHAR(40),
    new_state          VARCHAR(40),
    reason             TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

_NON_TERM_RUN = "('QUEUED','RUNNING','WAITING_HUMAN'," \
                "'CANCEL_REQUESTED')"

# task status -> run state (the task is the execution authority)
_TASK_TO_RUN = {
    "SUCCEEDED": "SUCCEEDED",
    "FAILED": "FAILED",        # refined to WAITING_HUMAN when the
                               # task carries a WAITING reason
    "CANCELLED": "CANCELLED",
}


class RecoveryController:
    """Inspect → classify → reconcile. Wraps (never changes) the
    26A/26B/26C-1/2/3 semantics; adds ONLY the consistency scan."""

    def __init__(self, store, connect, run_control=None,
                 budget=None, observability=True):
        self.store = store
        self._connect = connect
        self.run_control = run_control    # optional (26C-2)
        self.budget = budget              # optional (26C-3, reporting)
        self._obs = observability
        with connect() as conn:
            with conn.cursor() as cur:
                cur.execute(RECOVERY_DDL)

    # ---- entry point --------------------------------------------------- #
    def reconcile_once(self, limit: int = 100) -> dict:
        """One pull-based pass. Returns a summary dict. Any DB
        failure propagates (fail closed — never assume success);
        re-running is idempotent."""
        rid = "rec-%s" % uuid.uuid4().hex[:12]
        summary = {"reconciliation_id": rid, "recovered_leases": [],
                   "expired_runs": [], "actions": [], "healthy": 0,
                   "inconsistent": [], "stale_observed": 0,
                   "budget_notes": []}
        # 1. expired leases (26A semantics, reused verbatim)
        try:
            summary["recovered_leases"] = \
                self.store.recover_expired()
        except Exception as e:  # noqa: BLE001 — fail closed
            self._audit(rid, "INCONSISTENT", "", "", "",
                        "", "", "recover_expired failed: %s"
                        % str(e)[:120])
            raise
        # 2. overdue runs (26C-2, reused verbatim)
        if self.run_control is not None:
            try:
                summary["expired_runs"] = \
                    self.run_control.expire_overdue(limit=limit)
            except Exception as e:  # noqa: BLE001 — fail closed
                self._audit(rid, "INCONSISTENT", "", "", "",
                            "", "", "expire_overdue failed: %s"
                            % str(e)[:120])
                raise
        # 3. run/task consistency scan (the 26C-4 boundary)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT r.run_id, r.state AS run_state,
                           r.terminal_reason,
                           t.task_id, t.status AS task_status,
                           t.retry_reason, t.worker_id,
                           (t.lease_expires_at > now()) AS lease_ok
                    FROM agent_runs r
                    JOIN queue_tasks t ON t.task_id = r.task_id
                    ORDER BY r.created_at
                    LIMIT %s
                """, (limit,))
                rows = [dict(r) for r in cur.fetchall()]
        for row in rows:
            self._classify_and_reconcile(rid, row, summary)
        self._budget_notes(rid, summary)
        self._log("recovery.pass", rid=rid, **{
            k: (len(v) if isinstance(v, list) else v)
            for k, v in summary.items()
            if k != "reconciliation_id"})
        return summary

    # ---- classification + deterministic actions ------------------------- #
    def _classify_and_reconcile(self, rid, row, summary) -> None:
        run_id = row["run_id"]
        task_id = row["task_id"]
        rs, ts = row["run_state"], row["task_status"]
        run_terminal = rs in ("SUCCEEDED", "FAILED", "TIMED_OUT",
                              "CANCELLED")
        # HEALTHY pairs
        if rs == "SUCCEEDED" and ts == "SUCCEEDED":
            summary["healthy"] += 1
            self._audit(rid, "HEALTHY", run_id, task_id,
                        row["worker_id"], rs, rs,
                        "run+task SUCCEEDED")
            return
        if run_terminal and ts == "CANCELLED":
            summary["healthy"] += 1
            self._audit(rid, "HEALTHY", run_id, task_id,
                        row["worker_id"], rs, ts,
                        "terminal run + cancelled task")
            return
        if not run_terminal and ts in ("PENDING", "LEASED",
                                       "RUNNING"):
            # in flight (a valid lease) or freshly requeued —
            # healthy unless the lease expired, which step 1/2
            # already handled
            if ts in ("LEASED", "RUNNING") and row["lease_ok"]:
                summary["healthy"] += 1
                self._audit(rid, "HEALTHY", run_id, task_id,
                            row["worker_id"], rs, ts,
                            "in flight (valid lease)")
            else:
                summary["healthy"] += 1   # PENDING — queued work
                self._audit(rid, "HEALTHY", run_id, task_id,
                            row["worker_id"], rs, ts, "queued")
            return
        # INCONSISTENT (fail closed — never mutate)
        if rs == "SUCCEEDED" and ts != "SUCCEEDED":
            self._inconsistent(rid, row, summary,
                               "run SUCCEEDED but task %s — "
                               "impossible via API; corruption/"
                               "bypass suspected" % ts)
            return
        if ts == "SUCCEEDED" and rs in ("FAILED", "TIMED_OUT",
                                        "CANCELLED"):
            self._inconsistent(rid, row, summary,
                               "task SUCCEEDED but run %s — late "
                               "success bypassed the run layer" % rs)
            return
        # RECOVERABLE: run non-terminal + task terminal → run
        # follows the task (execution authority), CAS-guarded
        if not run_terminal and ts in _TASK_TO_RUN:
            target = _TASK_TO_RUN[ts]
            if ts == "FAILED" and (row["retry_reason"] or "") \
                    .startswith("WAITING_FOR_APPROVAL"):
                target = "WAITING_HUMAN"
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE agent_runs SET state=%s,
                            terminal_at = CASE WHEN %s IN
                                ('SUCCEEDED','FAILED','TIMED_OUT',
                                 'CANCELLED') THEN now()
                                ELSE terminal_at END,
                            terminal_reason = CASE WHEN %s IN
                                ('SUCCEEDED','FAILED','TIMED_OUT',
                                 'CANCELLED')
                                THEN 'task_terminal_reconciled'
                                ELSE terminal_reason END,
                            updated_at=now()
                        WHERE run_id=%s AND state IN %s
                    """ % ("%s", "%s", "%s", "%s", _NON_TERM_RUN),
                        (target, target, target, run_id))
                    changed = cur.rowcount == 1
            self._audit(rid, "RECOVERABLE", run_id, task_id,
                        row["worker_id"], rs,
                        target if changed else rs,
                        "task terminal (%s) -> run synced%s"
                        % (ts, "" if changed else " (already)"))
            summary["actions"].append(
                {"run_id": run_id, "task_id": task_id,
                 "classification": "RECOVERABLE",
                 "old": rs, "new": target if changed else rs,
                 "changed": changed})
            return
        # RECOVERABLE: run terminal (non-success) + task
        # non-terminal → task CANCELLED with the run's reason
        # (exactly what the one-txn stop would have co-written);
        # a late worker's settle is then rejected by the task CAS
        if run_terminal and rs != "SUCCEEDED" \
                and ts in ("PENDING", "LEASED", "RUNNING",
                           "FAILED"):
            reason = ("run_terminal_reconciled:%s"
                      % (row["terminal_reason"] or rs))[:400]
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE queue_tasks SET status='CANCELLED',
                            retry_reason=%s, updated_at=now()
                        WHERE task_id=%s AND status IN
                            ('PENDING','LEASED','RUNNING',
                             'FAILED')
                    """, (reason, task_id))
                    changed = cur.rowcount == 1
            self._audit(rid, "RECOVERABLE", run_id, task_id,
                        row["worker_id"], ts,
                        "CANCELLED" if changed else ts,
                        "run terminal (%s) -> task cancelled%s"
                        % (rs, "" if changed else " (already)"))
            summary["actions"].append(
                {"run_id": run_id, "task_id": task_id,
                 "classification": "RECOVERABLE", "old": ts,
                 "new": "CANCELLED" if changed else ts,
                 "changed": changed})
            return
        # everything else (e.g. WAITING_HUMAN run + FAILED task
        # waiting) is a consistent HITL pair
        summary["healthy"] += 1
        self._audit(rid, "HEALTHY", run_id, task_id,
                    row["worker_id"], rs, ts, "consistent pair")

    def _inconsistent(self, rid, row, summary, why):
        summary["inconsistent"].append(
            {"run_id": row["run_id"], "task_id": row["task_id"],
             "run_state": row["run_state"],
             "task_status": row["task_status"], "reason": why})
        self._audit(rid, "INCONSISTENT", row["run_id"],
                    row["task_id"], row["worker_id"],
                    row["run_state"], row["task_status"], why)
        self._log("recovery.inconsistent", level="ERROR", rid=rid,
                  run_id=row["run_id"], task_id=row["task_id"],
                  run_state=row["run_state"],
                  task_status=row["task_status"], reason=why)

    # ---- budget reporting (26C-3 semantics preserved) ------------------- #
    def _budget_notes(self, rid, summary):
        if self.budget is None:
            return
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT b.run_id, b.llm_calls_reserved,
                           r.state AS run_state
                    FROM agent_run_budgets b
                    JOIN agent_runs r ON r.run_id = b.run_id
                    WHERE b.llm_calls_reserved > 0
                """)
                rows = [dict(x) for x in cur.fetchall()]
        for x in rows:
            note = ("reservation %d on run %s (%s) — preserved "
                    "(26C-3 strict fail-closed; never reset without "
                    "durable evidence)"
                    % (x["llm_calls_reserved"], x["run_id"],
                       x["run_state"]))
            summary["budget_notes"].append(note)
            self._audit(rid, "STALE" if x["run_state"] in
                        ("SUCCEEDED", "FAILED", "TIMED_OUT",
                         "CANCELLED") else "HEALTHY",
                        x["run_id"], "", "", "RESERVED",
                        "RESERVED", note)

    # ---- audit / obs ------------------------------------------------------ #
    def _audit(self, rid, classification, run_id, task_id,
               worker_id, old_state, new_state, reason):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO recovery_events
                        (reconciliation_id, classification, run_id,
                         task_id, worker_id, old_state, new_state,
                         reason)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (rid, classification, run_id or None,
                      task_id or None, worker_id or None,
                      str(old_state or "")[:40],
                      str(new_state or "")[:40],
                      (reason or "")[:400]))

    def _log(self, event, level="INFO", rid="", **kw):
        if not self._obs:
            return
        try:
            import runtime.obs as obs
            obs.log(event, level=level,
                    reconciliation_id=rid, **kw)
        except Exception:  # noqa: BLE001 — observation only
            pass
