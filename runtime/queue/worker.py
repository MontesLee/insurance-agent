"""Task worker — Phase 26A (26A-13).

A worker is a STATELESS execution unit: ownership, lease authority
and terminal truth all live in PostgreSQL. The worker only:

    claim() -> start() -> [ adopt trace context -> execute -> ]
    succeed() / fail() / release()

The EXECUTOR is injected (`executor(task) -> dict`): business skills
and agent logic stay untouched and queue-agnostic — they never see
worker/lease/queue concepts.

Backpressure (26A-19, audited 26C-1): max_concurrent_tasks caps the
CONCURRENT ACTIVE EXECUTIONS of ONE worker instance (worker-local —
global concurrency is NOT bounded by it). The slot is reserved
atomically BEFORE the claim: a worker at capacity does not claim, so
queued tasks keep status PENDING with no lease/attempt consumed.

Graceful shutdown (26A-20): SIGTERM (or request_stop()) stops new
claims; the in-flight task runs to a safe point, heartbeats, then
completes — or is RELEASED so the lease path can recover it. A task
is never silently lost.

Observability (26A-12): every execution adopts the task's stored
request/correlation/trace ids and logs with worker_id,
worker_instance_id, task_id, lease_id, attempt, trace_id — stderr/file
only; stdout stays product-only (Phase 25.1 invariant).
"""
from __future__ import annotations

import signal
import threading
import time
from typing import Callable, Optional

from . import model
from .store import LeaseRejected, OutcomeUnknown, TaskQueueStore


class TaskWorker:
    def __init__(self, store: TaskQueueStore, worker_id: str,
                 executor: Callable[[dict], dict],
                 lease_seconds: float = 30.0,
                 heartbeat_every_s: float = 10.0,
                 max_concurrent_tasks: int = 1,
                 task_types: Optional[list] = None):
        self.store = store
        self.worker_id = worker_id
        self.worker_instance_id = model.new_worker_instance_id(worker_id)
        self.executor = executor
        self.lease_seconds = lease_seconds
        self.heartbeat_every_s = heartbeat_every_s
        self.max_concurrent = max(1, max_concurrent_tasks)
        self.task_types = task_types        # claim filter (isolation)
        self._stop = threading.Event()
        self._inflight = 0
        self._capacity_rejections = 0
        self._at_capacity_edge = False
        self._lock = threading.Lock()
        self._installed_handler = None

    # ---- lifecycle ---------------------------------------------------- #
    def install_signal_handlers(self):
        """SIGTERM -> graceful stop (POSIX/Windows-safe best effort)."""
        def _h(signum, frame):
            self.request_stop("signal:%s" % signum)
        try:
            self._installed_handler = signal.signal(signal.SIGTERM, _h)
            signal.signal(signal.SIGINT, _h)
        except (ValueError, OSError):
            pass    # not the main thread / unsupported platform
        return self

    def request_stop(self, reason: str = "operator"):
        self._stop.set()
        self._log("worker.stop_requested", status="OK",
                  reason=reason)

    @property
    def stopping(self) -> bool:
        return self._stop.is_set()

    def at_capacity(self) -> bool:
        with self._lock:
            return self._inflight >= self.max_concurrent

    def _reserve(self) -> bool:
        """Atomically reserve ONE execution slot (26C-1): the capacity
        check and the increment happen under a SINGLE lock
        acquisition. A check-then-act split (at_capacity() here,
        increment after the claim) let two concurrent run_once()
        callers both pass the check and overshoot max_concurrent_tasks."""
        with self._lock:
            if self._inflight >= self.max_concurrent:
                self._capacity_rejections += 1
                return False
            self._inflight += 1
            self._at_capacity_edge = False
            return True

    def _release_slot(self) -> None:
        with self._lock:
            self._inflight -= 1

    @property
    def active_tasks(self) -> int:
        """Executions currently holding a slot on THIS instance."""
        with self._lock:
            return self._inflight

    @property
    def capacity_rejections(self) -> int:
        """run_once() refusals due to full capacity (26C-1 metric)."""
        return self._capacity_rejections

    # ---- one task ------------------------------------------------------ #
    def run_once(self) -> Optional[dict]:
        """Claim + execute + settle ONE task. Returns the settle
        outcome dict, or None when no task was claimable / at
        capacity / stopping. Capacity is reserved BEFORE the claim
        (26C-1): backpressure keeps tasks QUEUED — a task never takes
        a lease this worker cannot yet execute."""
        if self.stopping:
            return None
        if not self._reserve():
            self._log_capacity()
            return None
        try:
            task = self.store.claim(self.worker_id,
                                    self.worker_instance_id,
                                    lease_seconds=self.lease_seconds,
                                    task_types=self.task_types)
            if task is None:
                return None
            return self._execute(task)
        finally:
            self._release_slot()

    def _log_capacity(self):
        """Edge-triggered backpressure event (26C-1): log a capacity
        refusal ONCE per busy period — a polling loop sitting at
        capacity must not spam the obs sink."""
        with self._lock:
            if self._at_capacity_edge:
                return
            self._at_capacity_edge = True
        self._log("worker.backpressure", status="AT_CAPACITY",
                  reason="capacity_full",
                  max_capacity=self.max_concurrent,
                  active=self._inflight)

    def _execute(self, task: dict) -> dict:
        tid, lease = task["task_id"], task["lease_id"]
        try:
            self.store.start(tid, lease)
        except Exception as e:  # noqa: BLE001 — DB loss before execution
            self._log("task.start_failed", level="ERROR",
                      status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                      task_id=tid, lease_id=lease, error=e)
            return {"outcome": "RECOVERY_REQUIRED", "task_id": tid,
                    "changed": False}
        self._log("task.claimed", status="RUNNING", task_id=tid,
                  lease_id=lease, attempt=task["attempt"],
                  task_type=task["task_type"])
        # heartbeat thread: only the current lease owner may extend —
        # a rejected heartbeat means authority was lost; execution
        # continues to its safe point but CANNOT settle (stale lease)
        lost_lease = threading.Event()
        hb_stop = threading.Event()

        def _hb():
            while not hb_stop.wait(self.heartbeat_every_s):
                try:
                    self.store.heartbeat(tid, lease,
                                         self.lease_seconds)
                    self._log("task.heartbeat", status="OK",
                              task_id=tid, lease_id=lease)
                except LeaseRejected:
                    lost_lease.set()
                    self._log("task.heartbeat", level="ERROR",
                              status="LEASE_LOST", task_id=tid,
                              lease_id=lease)
                    return
                except Exception as e:  # noqa: BLE001 — transient DB
                    self._log("task.heartbeat", level="WARN",
                              status="UNAVAILABLE", task_id=tid,
                              error=e)
        hb = threading.Thread(target=_hb, daemon=True)
        hb.start()
        # ---- execute under the task's ADOPTED trace context -------- #
        t0 = time.perf_counter()
        outcome = None
        try:
            result = self._with_trace_context(task)
            outcome = self.store.succeed(tid, lease, result)
        except LeaseRejected as e:
            # lost authority mid-flight: NEVER overwrite the current
            # owner's truth — record and surface for recovery
            self._log("task.settle", level="ERROR",
                      status="STALE_LEASE_REJECTED", task_id=tid,
                      lease_id=lease, error=e)
            outcome = {"outcome": "STALE_REJECTED", "task_id": tid,
                       "changed": False}
        except OutcomeUnknown as e:
            self._log("task.settle", level="ERROR",
                      status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                      task_id=tid, lease_id=lease, error=e)
            outcome = {"outcome": "RECOVERY_REQUIRED", "task_id": tid,
                       "changed": False}
        except Exception as e:  # noqa: BLE001 — business failure
            try:
                outcome = self.store.fail(tid, lease,
                                          "%s: %s" % (type(e).__name__,
                                                      str(e)[:200]),
                                          retry=True)
            except LeaseRejected:
                outcome = {"outcome": "STALE_REJECTED",
                           "task_id": tid, "changed": False}
            except Exception as e2:  # noqa: BLE001 — settle-time DB loss
                # 26A-17: outcome UNKNOWN -> RECOVERY_REQUIRED, the
                # worker NEVER assumes success/failure and NEVER
                # crash-loops on a lost database connection
                outcome = {"outcome": "RECOVERY_REQUIRED",
                           "task_id": tid, "changed": False}
                self._log("task.settle", level="ERROR",
                          status="OUTCOME_UNKNOWN_RECOVERY_REQUIRED",
                          task_id=tid, lease_id=lease, error=e2)
            self._log("task.failed", level="ERROR", status="FAILED",
                      task_id=tid, lease_id=lease,
                      attempt=task["attempt"], error=e)
        finally:
            hb_stop.set()
            hb.join(timeout=2)
        ms = (time.perf_counter() - t0) * 1000
        self._log("task.settled", status=outcome.get("outcome", "?"),
                  duration_ms=ms, task_id=tid, lease_id=lease,
                  attempt=task["attempt"])
        return outcome

    def _with_trace_context(self, task: dict) -> dict:
        """Adopt the task's propagated ids and run the EXECUTOR under
        them (26A-12). A missing stored trace id gets a fresh one —
        recorded in the log, never guessed silently."""
        from runtime.obs import context as obs_ctx
        ctx = obs_ctx.TraceContext(
            request_id=task.get("request_id") or "",
            correlation_id=task.get("correlation_id") or "",
            trace_id=task.get("trace_id")
            or obs_ctx.new_id("trace"),
            project_id=task.get("project_id") or "",
            case_id=task.get("case_id") or "",
            task_id=task["task_id"],
            skill_name=task.get("skill_id") or "",
            tool_name="")
        with obs_ctx.use_context(ctx):
            return self.executor(task)

    # ---- graceful shutdown / drain -------------------------------------- #
    def shutdown_and_release(self, task: Optional[dict] = None):
        """26A-20: stop claiming; release the in-flight task (if the
        caller holds one) so another worker recovers it immediately —
        no silent loss."""
        self.request_stop("shutdown")
        if task and task.get("lease_id"):
            try:
                self.store.release(task["task_id"],
                                   task["lease_id"])
                self._log("task.released", status="PENDING",
                          task_id=task["task_id"])
            except Exception as e:  # noqa: BLE001 — lease will expire
                self._log("task.release_failed", level="WARN",
                          status="LEASE_EXPIRY_PATH", task_id=task
                          ["task_id"], error=e)

    def run_until_empty(self, idle_sleep_s: float = 0.05,
                        max_tasks: Optional[int] = None):
        """Claim/execute loop until the queue offers nothing (used by
        tests and batch workers). Respects stop + backpressure."""
        done = 0
        while not self.stopping and (max_tasks is None
                                     or done < max_tasks):
            out = self.run_once()
            if out is None:
                time.sleep(idle_sleep_s)
                # nothing claimable right now -> drain check
                if not self.store.list(status="PENDING", limit=1) \
                        and not self.store.list(status="RUNNING",
                                                limit=1):
                    break
                continue
            done += 1
        return done

    # ---- observability ------------------------------------------------ #
    def _log(self, event, level="INFO", status="", task_id="",
             lease_id="", attempt=None, **kw):
        """Worker log line: WHO (worker) / WHICH INSTANCE / WHICH TASK
        / WHICH LEASE / WHICH ATTEMPT / WHICH TRACE (26A-12). Goes to
        the obs sink (file/stderr) — NEVER stdout."""
        try:
            import runtime.obs as obs
            obs.log(event, level=level, status=status,
                    worker_id=self.worker_id,
                    worker_instance_id=self.worker_instance_id,
                    task_id=task_id, lease_id=lease_id,
                    attempt=attempt, **kw)
        except Exception:  # noqa: BLE001 — observation only
            pass
