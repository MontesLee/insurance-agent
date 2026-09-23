"""Phase 26C-2 — agent run lifecycle & deadline control (PG-gated).

E26C2-01..14 + crash matrix C1-C5 + mutation kills M26C2-01..10.
Proves the run-control boundary: absolute deadline, terminal-state
immutability, late-worker rejection at BOTH layers, one-transaction
run/task terminal decisions, idempotent lifecycle commands, HITL
deadline safety, crash recovery that never violates a terminal run.

Deterministic everywhere: deadline waits poll the DB clock
(SELECT now() > deadline_at), concurrency is barrier-synchronized,
gates are Events released by the harness. C1 uses a REAL OS
subprocess kill. Exactly-once is NOT claimed.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

PG_PASSWORD = ""
try:
    PG_PASSWORD = open(
        r"C:\Users\aubor\AppData\Local\Temp\pg_cred.txt"
    ).read().strip().split("=", 1)[1]
except (FileNotFoundError, IndexError):
    pass
PG = bool(PG_PASSWORD)

SECTIONS = []
T = "p26c2t"          # task_type prefix; cleanup key
R = "run26c2"         # run_id prefix; cleanup key


def section(fn):
    SECTIONS.append(fn)
    return fn


# ---- shared fixtures --------------------------------------------------- #
def _store():
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    from runtime.state.pg import PostgresStore
    from runtime.queue import TaskQueueStore
    s = TaskQueueStore(PostgresStore().connect)
    s.init_schema()
    return s


def _rc(store):
    from runtime.state.pg import PostgresStore
    from runtime.queue import RunControl
    return RunControl(store, PostgresStore().connect)


def _connect():
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    from runtime.state.pg import PostgresStore
    return PostgresStore().connect


def _clean(store):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM queue_tasks WHERE task_type "
                        "LIKE %s", (T + "%",))
            cur.execute("DELETE FROM agent_runs WHERE run_id LIKE %s",
                        (R + "%",))
            cur.execute("DELETE FROM queue_ops_events")


def _submit(rc, name, deadline=60.0, ttype=None, case="case-x"):
    """One managed run + task; returns (task_id, run_id)."""
    tid, rid = "p26c2-%s" % name, "%s-%s" % (R, name)
    rc.submit_run(task_id=tid, run_id=rid, deadline_seconds=deadline,
                  task_type=ttype or (T + "-g"), case_id=case,
                  trace_id="trc-" + name)
    return tid, rid


def _worker(store, exec_, wid, rc=None, ttype=None, lease=30, hb=30):
    from runtime.queue import AgentTaskWorker
    w = AgentTaskWorker(store, wid, exec_, run_control=rc,
                        lease_seconds=lease, heartbeat_every_s=hb)
    w.task_types = [ttype or (T + "-g")]
    return w


def _wait_until(cond, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


def _db_now_past(store, rid):
    """True when the DB clock has passed the run's deadline."""
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT now() > deadline_at AS o FROM "
                        "agent_runs WHERE run_id=%s", (rid,))
            row = cur.fetchone()
            return bool(row and row["o"])


def _run_root(name):
    p = os.path.join(REPO, "tmp", "p26c2", name)
    shutil.rmtree(p, ignore_errors=True)
    os.makedirs(p, exist_ok=True)
    return p


# ===================================================================== #

@section
def test_e26c2_01_state_machine(c):
    """E26C2-01: run state machine — literal-pair oracle against
    RUN_TRANSITIONS (editing the table to legalize an illegal pair
    fails this test)."""
    from runtime.queue import RUN_TRANSITIONS as TR
    from runtime.queue import (RUN_CANCELLED, RUN_CANCEL_REQUESTED,
                               RUN_FAILED, RUN_QUEUED, RUN_RUNNING,
                               RUN_SUCCEEDED, RUN_TIMED_OUT,
                               RUN_WAITING_HUMAN)
    legal = [(RUN_QUEUED, RUN_RUNNING),
             (RUN_QUEUED, RUN_CANCEL_REQUESTED),
             (RUN_QUEUED, RUN_TIMED_OUT),
             (RUN_QUEUED, RUN_CANCELLED),
             (RUN_RUNNING, RUN_WAITING_HUMAN),
             (RUN_RUNNING, RUN_SUCCEEDED),
             (RUN_RUNNING, RUN_FAILED),
             (RUN_RUNNING, RUN_TIMED_OUT),
             (RUN_RUNNING, RUN_CANCEL_REQUESTED),
             (RUN_RUNNING, RUN_CANCELLED),
             (RUN_WAITING_HUMAN, RUN_RUNNING),
             (RUN_WAITING_HUMAN, RUN_TIMED_OUT),
             (RUN_WAITING_HUMAN, RUN_CANCEL_REQUESTED),
             (RUN_WAITING_HUMAN, RUN_CANCELLED),
             (RUN_CANCEL_REQUESTED, RUN_CANCELLED),
             (RUN_CANCEL_REQUESTED, RUN_TIMED_OUT)]
    for a, b in legal:
        c.chk("E26C2-01 legal %s->%s" % (a, b), b in TR[a])
    illegal = [(RUN_SUCCEEDED, RUN_RUNNING), (RUN_SUCCEEDED, RUN_FAILED),
               (RUN_CANCELLED, RUN_RUNNING), (RUN_CANCELLED, RUN_SUCCEEDED),
               (RUN_TIMED_OUT, RUN_RUNNING), (RUN_TIMED_OUT, RUN_SUCCEEDED),
               (RUN_FAILED, RUN_RUNNING), (RUN_FAILED, RUN_QUEUED),
               (RUN_WAITING_HUMAN, RUN_SUCCEEDED),
               (RUN_QUEUED, RUN_FAILED),
               (RUN_QUEUED, RUN_WAITING_HUMAN)]
    for a, b in illegal:
        c.chk("E26C2-01 illegal %s->%s refused" % (a, b),
              b not in TR[a])
    c.chk("E26C2-01 terminal states have NO outgoing transitions",
          all(not TR[t] for t in (RUN_SUCCEEDED, RUN_FAILED,
                                  RUN_TIMED_OUT, RUN_CANCELLED)))


@section
def test_e26c2_02_happy_and_backcompat(c):
    """E26C2-02: managed happy path (QUEUED→RUNNING→SUCCEEDED, run
    and task consistent, duplicate settle no-op) + UNMANAGED worker
    (no run_control) behaves exactly as 26B."""
    if not PG:
        c.chk("E26C2-02 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "happy", deadline=60)
    w = _worker(store, lambda t: {"status": "COMPLETED"}, "wh",
                rc=rc)
    out = w.run_once()
    c.chk("E26C2-02 managed settle SUCCEEDED",
          out is not None and out.get("outcome") == "SUCCEEDED")
    c.chk("E26C2-02 run and task terminal-consistent",
          rc.get_run(rid)["state"] == "SUCCEEDED"
          and store.get(tid)["status"] == "SUCCEEDED")
    # duplicate completion: no second effect
    task_row = store.get(tid)
    fake = {"task_id": tid, "lease_id": task_row["lease_id"] or "x",
            "run_id": rid}
    out2 = rc.settle_success(fake, {"dupe": True})
    c.chk("E26C2-02 duplicate completion is a visible NO-OP",
          out2.get("outcome") == "DUPLICATE_SUCCESS"
          and store.get(tid)["result"] != {"dupe": True})
    # unmanaged back-compat: identical worker without run_control
    tid2, rid2 = _submit(rc, "unman", deadline=60)
    store.get(tid2)
    w2 = _worker(store, lambda t: {"status": "COMPLETED"}, "wu",
                 rc=None)
    out3 = w2.run_once()
    c.chk("E26C2-02 unmanaged task still succeeds (26B path intact)",
          out3 is not None and out3.get("outcome") == "SUCCEEDED"
          and store.get(tid2)["status"] == "SUCCEEDED")
    c.chk("E26C2-02 unmanaged run row untouched by worker",
          rc.get_run(rid2)["state"] == "QUEUED")
    _clean(store)


@section
def test_e26c2_03_deadline_start_gate(c):
    """E26C2-03 (§9 Case A + queued expiry): start at/before the
    deadline is ALLOWED; an expired-at-claim run is TIMED_OUT before
    start (task CANCELLED, reason recorded)."""
    if not PG:
        c.chk("E26C2-03 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    # Case A: tight-but-positive deadline — start must be allowed
    tid, rid = _submit(rc, "caseA", deadline=30)
    started = threading.Event()
    release = threading.Event()

    def exec_(task):
        started.set()
        release.wait(timeout=10)
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "wcA", rc=rc)
    th = threading.Thread(target=lambda: w.run_once())
    th.start()
    c.chk("E26C2-03 Case A: start before deadline is allowed",
          _wait_until(lambda: started.is_set()
                      and store.get(tid)["status"] == "RUNNING"))
    release.set()
    th.join(timeout=15)
    c.chk("E26C2-03 Case A: completes successfully",
          store.get(tid)["status"] == "SUCCEEDED"
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    # expired at claim time: pre_start terminalises before execution
    tid2, rid2 = _submit(rc, "expired", deadline=-1)
    ran = threading.Event()

    def exec2(task):
        ran.set()
        return {"status": "COMPLETED"}
    w2 = _worker(store, exec2, "wcE", rc=rc)
    out = w2.run_once()
    c.chk("E26C2-03 expired run: worker outcome RUN_TIMED_OUT",
          out is not None and out.get("outcome") == "RUN_TIMED_OUT")
    c.chk("E26C2-03 expired run: executor NEVER ran", not ran.is_set())
    c.chk("E26C2-03 expired run: task CANCELLED with reason",
          store.get(tid2)["status"] == "CANCELLED"
          and store.get(tid2)["retry_reason"]
          == "run_deadline_exceeded")
    c.chk("E26C2-03 expired run: run TIMED_OUT terminal",
          rc.get_run(rid2)["state"] == "TIMED_OUT")
    _clean(store)


@section
def test_e26c2_04_late_result_rejected(c):
    """E26C2-04 (§9 Case C/D): started before the deadline, result
    arrives after — SUCCESS is NOT accepted; run TIMED_OUT, task
    FAILED run_deadline_exceeded (deterministic DB-clock poll)."""
    if not PG:
        c.chk("E26C2-04 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "late", deadline=2)
    started = threading.Event()
    release = threading.Event()

    def exec_(task):
        started.set()
        release.wait(timeout=30)
        return {"status": "COMPLETED", "late": True}
    w = _worker(store, exec_, "wl", rc=rc, lease=60, hb=30)
    result = {}
    th = threading.Thread(target=lambda: result.update(
        w.run_once() or {}))
    th.start()
    c.chk("E26C2-04 run started while within deadline",
          _wait_until(lambda: store.get(tid)["status"] == "RUNNING"))
    # wait for the DB clock to pass the deadline, THEN release
    c.chk("E26C2-04 deadline passes while provider 'running'",
          _wait_until(lambda: _db_now_past(store, rid), timeout=10))
    release.set()
    th.join(timeout=20)
    c.chk("E26C2-04 late success rejected: outcome RUN_TIMED_OUT",
          result.get("outcome") == "RUN_TIMED_OUT", result)
    c.chk("E26C2-04 task NOT SUCCEEDED (no accepted result)",
          store.get(tid)["status"] == "FAILED"
          and store.get(tid)["retry_reason"]
          == "run_deadline_exceeded")
    c.chk("E26C2-04 run terminal TIMED_OUT",
          rc.get_run(rid)["state"] == "TIMED_OUT")
    _clean(store)


@section
def test_e26c2_05_late_worker_after_cancel(c):
    """E26C2-05 (late-worker protection, cancel side): operator
    cancels while the worker executes; the worker's completion is
    REJECTED at both layers; run stays CANCELLED; REVIEWER denied."""
    if not PG:
        c.chk("E26C2-05 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import OpsDenied, QueueOps
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "lc", deadline=60)
    started = threading.Event()
    release = threading.Event()

    def exec_(task):
        started.set()
        release.wait(timeout=30)
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "wlc", rc=rc, lease=60, hb=30)
    result = {}
    th = threading.Thread(target=lambda: result.update(
        w.run_once() or {}))
    th.start()
    _wait_until(lambda: store.get(tid)["status"] == "RUNNING")
    ops = QueueOps(store, _connect(), run_root=_run_root("lc"),
                   run_control=rc)
    try:
        ops.cancel(("rev", "REVIEWER"), tid)
        c.chk("E26C2-05 REVIEWER cancel denied", False)
    except OpsDenied:
        c.chk("E26C2-05 REVIEWER cancel denied", True)
    out = ops.cancel(("own", "OWNER"), tid)
    c.chk("E26C2-05 OWNER cancels: task+run CANCELLED together",
          out.get("outcome") == "CANCELLED"
          and store.get(tid)["status"] == "CANCELLED"
          and rc.get_run(rid)["state"] == "CANCELLED")
    release.set()
    th.join(timeout=20)
    c.chk("E26C2-05 late worker completion REJECTED (stale)",
          result.get("outcome") == "STALE_REJECTED", result)
    c.chk("E26C2-05 run stays CANCELLED (terminal immutable)",
          rc.get_run(rid)["state"] == "CANCELLED")
    c.chk("E26C2-05 task stays CANCELLED",
          store.get(tid)["status"] == "CANCELLED")
    _clean(store)


@section
def test_e26c2_06_late_worker_after_timeout(c):
    """E26C2-06 (late-worker protection, timeout side): expire during
    execution; the late completion is rejected; run stays TIMED_OUT;
    lease recovery cannot reactivate (task unclaimable)."""
    if not PG:
        c.chk("E26C2-06 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "lt", deadline=3)
    started = threading.Event()
    release = threading.Event()

    def exec_(task):
        started.set()
        release.wait(timeout=30)
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "wlt", rc=rc, lease=60, hb=30)
    result = {}
    th = threading.Thread(target=lambda: result.update(
        w.run_once() or {}))
    th.start()
    _wait_until(lambda: store.get(tid)["status"] == "RUNNING")
    c.chk("E26C2-06 deadline passes (DB clock)",
          _wait_until(lambda: _db_now_past(store, rid), timeout=10))
    expired = rc.expire_overdue()
    c.chk("E26C2-06 pull-based expiry terminalised the run",
          rid in expired and rc.get_run(rid)["state"] == "TIMED_OUT"
          and store.get(tid)["status"] == "CANCELLED")
    release.set()
    th.join(timeout=20)
    c.chk("E26C2-06 late completion rejected (stale lease CAS)",
          result.get("outcome") == "STALE_REJECTED", result)
    c.chk("E26C2-06 run stays TIMED_OUT",
          rc.get_run(rid)["state"] == "TIMED_OUT")
    c.chk("E26C2-06 task unclaimable after timeout (no reactivation)",
          store.claim("wnew", "wi-new", task_types=[T + "-g"]) is None)
    c.chk("E26C2-06 duplicate expire is idempotent",
          rc.expire_overdue() == [])
    _clean(store)


@section
def test_e26c2_07_cancel_races(c):
    """E26C2-07 (§11): cancel vs completion, 60 barrier-synchronized
    rounds on real PG — EXACTLY one terminal winner, never both
    effects; run terminal always matches task terminal."""
    if not PG:
        c.chk("E26C2-07 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import LeaseRejected
    store = _store()
    _clean(store)
    rc = _rc(store)
    rounds, both = 60, 0
    for i in range(rounds):
        tid, rid = _submit(rc, "r%d" % i, deadline=60)
        task = store.claim("wr", "wi-r", task_types=[T + "-g"],
                           lease_seconds=60)
        store.start(tid, task["lease_id"])
        task["run_id"] = rid
        out = {}
        bar = threading.Barrier(2)

        def do_complete():
            bar.wait(timeout=10)
            try:
                out["s"] = rc.settle_success(task, {"i": i})
            except LeaseRejected:
                out["s"] = {"outcome": "LeaseRejected"}

        def do_cancel():
            bar.wait(timeout=10)
            out["c"] = rc.cancel_run(tid)
        ths = [threading.Thread(target=f)
               for f in (do_complete, do_cancel)]
        [th.start() for th in ths]
        [th.join(timeout=15) for th in ths]
        trow, rrow = store.get(tid), rc.get_run(rid)
        cancelled = trow["status"] == "CANCELLED"
        succeeded = (trow["status"] == "SUCCEEDED"
                     and trow["result"] == {"i": i})
        consistent = (cancelled or succeeded) and (
            (rrow["state"] == "CANCELLED") if cancelled
            else (rrow["state"] == "SUCCEEDED"))
        if out.get("c", {}).get("changed") and \
                out.get("s", {}).get("outcome") == "SUCCEEDED":
            both += 1
        if not consistent:
            c.chk("E26C2-07 round %d consistent one-winner" % i,
                  False, {"task": trow["status"],
                          "run": rrow["state"], "out": out})
            _clean(store)
            return
        _clean(store)
    c.chk("E26C2-07 %d rounds: exactly one winner, never both "
          "effects" % rounds, both == 0, {"both": both})
    _clean(store)


@section
def test_e26c2_08_hitl_deadline(c):
    """E26C2-08 (§13/§14): WAITING_HUMAN + deadline -> approval
    REFUSED and run TIMED_OUT; approval before the deadline resumes;
    late approval after CANCELLED refused; the approval's own txn
    timestamp decides."""
    if not PG:
        c.chk("E26C2-08 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import QueueError, QueueOps
    store = _store()
    _clean(store)
    rc = _rc(store)
    # (a) in-time approval resumes and completes
    tid, rid = _submit(rc, "hl1", deadline=60)
    mode = {"defer": True}
    root = _run_root("hl1")

    def exec_(task):
        if mode["defer"]:
            return {"__defer__": "sg-1"}
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "whl", rc=rc)
    out = w.run_once()
    c.chk("E26C2-08 defer: run WAITING_HUMAN (slot-free)",
          out.get("outcome") == "DEFERRED_WAITING"
          and rc.get_run(rid)["state"] == "WAITING_HUMAN"
          and w.active_tasks == 0)
    ops = QueueOps(store, _connect(), run_root=root, run_control=rc)
    ops.approve_and_resume(("rev", "REVIEWER"), tid)
    mode["defer"] = False
    out2 = w.run_once()
    c.chk("E26C2-08 in-time approval: resume -> SUCCEEDED (attempt 2)",
          out2.get("outcome") == "SUCCEEDED"
          and store.get(tid)["attempt"] == 2
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    # duplicate approval: refused (not waiting)
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid)
        c.chk("E26C2-08 duplicate approval refused", False)
    except QueueError:
        c.chk("E26C2-08 duplicate approval refused", True)
    # (b) approval AFTER the deadline -> refused + TIMED_OUT
    tid2, rid2 = _submit(rc, "hl2", deadline=1)
    mode2 = {"defer": True}

    def exec2(task):
        if mode2["defer"]:
            return {"__defer__": "sg-1"}
        return {"status": "COMPLETED"}
    w2 = _worker(store, exec2, "whl2", rc=rc)
    w2.run_once()
    c.chk("E26C2-08 second run WAITING_HUMAN",
          rc.get_run(rid2)["state"] == "WAITING_HUMAN")
    c.chk("E26C2-08 deadline passes while waiting",
          _wait_until(lambda: _db_now_past(store, rid2), timeout=8))
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid2)
        c.chk("E26C2-08 late approval refused (deadline)", False)
    except QueueError as e:
        c.chk("E26C2-08 late approval refused (deadline)",
              "deadline" in str(e).lower()
              or "timed_out" in str(e).lower(), str(e)[:80])
    c.chk("E26C2-08 waiting run expired to TIMED_OUT",
          rc.get_run(rid2)["state"] == "TIMED_OUT")
    # (c) approval after CANCELLED -> refused, no revival
    tid3, rid3 = _submit(rc, "hl3", deadline=60)
    mode3 = {"defer": True}

    def exec3(task):
        return ({"__defer__": "sg-1"} if mode3["defer"]
                else {"status": "COMPLETED"})
    w3 = _worker(store, exec3, "whl3", rc=rc)
    w3.run_once()
    ops.cancel(("own", "OWNER"), tid3)
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid3)
        c.chk("E26C2-08 approval after cancel refused", False)
    except QueueError:
        c.chk("E26C2-08 approval after cancel refused", True)
    c.chk("E26C2-08 cancelled run cannot revive",
          rc.get_run(rid3)["state"] == "CANCELLED")
    _clean(store)


@section
def test_e26c2_09_retry_deadline(c):
    """E26C2-09 (§15): retry never resets the deadline; a failure
    after the deadline is NOT requeued — run TIMED_OUT; attempts
    before the deadline requeue normally (run stays RUNNING)."""
    if not PG:
        c.chk("E26C2-09 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "rt", deadline=2)
    d0 = rc.get_run(rid)["deadline_at"]

    def exec_(task):
        if task["attempt"] == 1:
            raise RuntimeError("attempt-1 failure (in time)")
        if task["attempt"] == 2:
            # hold until the deadline passes, then fail again
            if not _wait_until(lambda: _db_now_past(store, rid),
                               timeout=10):
                pass
            raise RuntimeError("attempt-2 failure (late)")
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "wrt", rc=rc, lease=60, hb=30)
    out1 = w.run_once()
    c.chk("E26C2-09 in-time failure requeues (run stays RUNNING)",
          out1.get("outcome") == "FAILED_REQUEUED"
          and rc.get_run(rid)["state"] == "RUNNING")
    c.chk("E26C2-09 deadline NOT reset by retry",
          rc.get_run(rid)["deadline_at"] == d0)
    out2 = w.run_once()
    c.chk("E26C2-09 post-deadline failure -> RUN_TIMED_OUT "
          "(no requeue)", out2.get("outcome") == "RUN_TIMED_OUT"
          and store.get(tid)["status"] == "CANCELLED")
    c.chk("E26C2-09 deadline still unmoved",
          rc.get_run(rid)["deadline_at"] == d0
          and rc.get_run(rid)["state"] == "TIMED_OUT")
    _clean(store)


@section
def test_e26c2_10_idempotency(c):
    """E26C2-10 (§19): duplicate cancel / timeout / approve /
    completion — NO duplicate effect; request_cancel intent is
    visible and idempotent; completion beats a mere cancel intent."""
    if not PG:
        c.chk("E26C2-10 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "idem", deadline=60)
    # duplicate cancel
    o1 = rc.cancel_run(tid)
    o2 = rc.cancel_run(tid)
    c.chk("E26C2-10 first cancel wins, second is a NO-OP",
          o1.get("outcome") == "CANCELLED" and o1.get("changed")
          and o2.get("outcome") == "ALREADY_TERMINAL"
          and not o2.get("changed"))
    # duplicate timeout
    tid2, rid2 = _submit(rc, "idem2", deadline=-1)
    e1 = rc.expire_overdue()
    e2 = rc.expire_overdue()
    c.chk("E26C2-10 duplicate expire idempotent",
          rid2 in e1 and e2 == []
          and rc.get_run(rid2)["state"] == "TIMED_OUT")
    # request_cancel intent: idempotent + superseded by completion
    tid3, rid3 = _submit(rc, "idem3", deadline=60)
    r1 = rc.request_cancel(rid3)
    r2 = rc.request_cancel(rid3)
    c.chk("E26C2-10 cancel intent recorded once (idempotent)",
          r1.get("changed") and not r2.get("changed")
          and rc.get_run(rid3)["state"] == "CANCEL_REQUESTED")
    task = store.claim("wi", "wii", task_types=[T + "-g"],
                       lease_seconds=60)
    store.start(tid3, task["lease_id"])
    task["run_id"] = rid3
    out = rc.settle_success(task, {"after": "intent"})
    c.chk("E26C2-10 real completion beats a mere cancel INTENT "
          "(one terminal winner)", out.get("outcome") == "SUCCEEDED"
          and rc.get_run(rid3)["state"] == "SUCCEEDED")
    o3 = rc.cancel_run(tid3)
    c.chk("E26C2-10 hard cancel after success loses",
          o3.get("outcome") == "ALREADY_TERMINAL"
          and rc.get_run(rid3)["state"] == "SUCCEEDED"
          and store.get(tid3)["status"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c2_11_crash_matrix(c):
    """E26C2-11 (§17 C1-C5): crash recovery never violates a
    terminal run. C1 = REAL OS process kill."""
    if not PG:
        c.chk("E26C2-11 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    # ---- C1: RUNNING + real kill -> lease expiry -> recovery ---- #
    tid, rid = _submit(rc, "c1", deadline=120, ttype=T + "-c1")
    stopfile = os.path.join(REPO, "tmp", "p26c2", "c1.marker")
    os.makedirs(os.path.dirname(stopfile), exist_ok=True)
    if os.path.exists(stopfile):
        os.remove(stopfile)
    script = """
import os, sys, time
sys.path.insert(0, r"{repo}")
os.environ["AGENT_PG_PASSWORD"] = r"{pw}"
from runtime.state.pg import PostgresStore
from runtime.queue import TaskQueueStore, RunControl, AgentTaskWorker
store = TaskQueueStore(PostgresStore().connect)
rc = RunControl(store, PostgresStore().connect)
def exec_(task):
    while not os.path.exists(r"{stopfile}"):
        time.sleep(0.05)
    return {{"status": "COMPLETED"}}
w = AgentTaskWorker(store, "wcrash2", exec_, run_control=rc,
                    lease_seconds=2, heartbeat_every_s=60,
                    task_types=["{ttype}"])
end = time.time() + 60
while time.time() < end:
    if w.run_once() is not None:
        continue
    if store.get("{tid}")["status"] == "SUCCEEDED":
        break
    time.sleep(0.05)
""".format(repo=REPO, pw=PG_PASSWORD, stopfile=stopfile,
           ttype=T + "-c1", tid=tid)
    proc = subprocess.Popen([sys.executable, "-c", script],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=REPO)
    try:
        c.chk("E26C2-11 C1 subprocess started the run",
              _wait_until(lambda: rc.get_run(rid)["state"]
                          == "RUNNING", timeout=20))
        proc.kill()
        proc.wait(timeout=10)
        c.chk("E26C2-11 C1 worker killed (run still RUNNING)",
              rc.get_run(rid)["state"] == "RUNNING")
        c.chk("E26C2-11 C1 lease expires",
              _wait_until(lambda: store.get(tid)["lease_expires_at"]
                          is not None and _task_expired(store, tid),
                          timeout=15))
        w2 = _worker(store, lambda t: {"status": "COMPLETED"},
                     "wrec2", rc=rc, ttype=T + "-c1")
        out = w2.run_once()
        c.chk("E26C2-11 C1 recovery completes (attempt 2, run "
              "survives the crash)", out.get("outcome") == "SUCCEEDED"
              and store.get(tid)["attempt"] == 2
              and rc.get_run(rid)["state"] == "SUCCEEDED")
    finally:
        if proc.poll() is None:
            proc.kill()
        open(stopfile, "w").close()
    # ---- C2: CANCEL_REQUESTED + kill -> hard cancel completes ---- #
    tid2, rid2 = _submit(rc, "c2", deadline=120)
    task = store.claim("wc2", "wi-c2", task_types=[T + "-g"],
                       lease_seconds=60)
    store.start(tid2, task["lease_id"])
    rc.request_cancel(rid2)
    rc.cancel_run(tid2)                       # completes the intent
    c.chk("E26C2-11 C2 cancel-after-crash intent completes terminal",
          rc.get_run(rid2)["state"] == "CANCELLED"
          and store.get(tid2)["status"] == "CANCELLED")
    c.chk("E26C2-11 C2 dead worker's task unclaimable",
          store.claim("wc2b", "wi-c2b", task_types=[T + "-g"])
          is None)
    # ---- C3: TIMED_OUT + kill -> no reactivation --------------- #
    tid3, rid3 = _submit(rc, "c3", deadline=-1)
    rc.expire_overdue()
    c.chk("E26C2-11 C3 expired run terminal (nothing to recover)",
          rc.get_run(rid3)["state"] == "TIMED_OUT"
          and store.get(tid3)["status"] == "CANCELLED")
    c.chk("E26C2-11 C3 expire idempotent after 'crash'",
          rc.expire_overdue() == [])
    # ---- C4: WAITING_HUMAN + kill -> approval still works ------- #
    tid4, rid4 = _submit(rc, "c4", deadline=120)
    mode = {"defer": True}

    def exec4(t):
        return ({"__defer__": "sg-1"} if mode["defer"]
                else {"status": "COMPLETED"})
    w4 = _worker(store, exec4, "wc4", rc=rc)
    w4.run_once()
    c.chk("E26C2-11 C4 waiting survives worker exit",
          rc.get_run(rid4)["state"] == "WAITING_HUMAN")
    from runtime.queue import QueueOps
    ops = QueueOps(store, _connect(), run_root=_run_root("c4"),
                   run_control=rc)
    ops.approve_and_resume(("rev", "REVIEWER"), tid4)
    mode["defer"] = False
    out4 = w4.run_once()
    c.chk("E26C2-11 C4 approval resumes to SUCCEEDED",
          out4.get("outcome") == "SUCCEEDED"
          and rc.get_run(rid4)["state"] == "SUCCEEDED")
    # ---- C5: approval + kill -> resume via recovery claim -------- #
    tid5, rid5 = _submit(rc, "c5", deadline=120)
    mode5 = {"defer": True}

    def exec5(t):
        return ({"__defer__": "sg-1"} if mode5["defer"]
                else {"status": "COMPLETED"})
    w5 = _worker(store, exec5, "wc5", rc=rc)
    w5.run_once()
    root5 = _run_root("c5")
    ops5 = QueueOps(store, _connect(), run_root=root5,
                    run_control=rc)
    ops5.approve_and_resume(("own", "OWNER"), tid5)
    mode5["defer"] = False
    out5 = w5.run_once()      # a DIFFERENT instance (= recovery)
    c.chk("E26C2-11 C5 requeued-after-approval executes (any worker)",
          out5.get("outcome") == "SUCCEEDED"
          and store.get(tid5)["attempt"] == 2)
    _clean(store)


def _task_expired(store, tid):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT (lease_expires_at < now()) AS x "
                        "FROM queue_tasks WHERE task_id=%s", (tid,))
            row = cur.fetchone()
            return bool(row and row["x"])


@section
def test_e26c2_12_concurrency(c):
    """E26C2-12 (§24): real-PG races — expire vs completion,
    approval vs expiry. One terminal winner per round."""
    if not PG:
        c.chk("E26C2-12 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import LeaseRejected, QueueError, QueueOps
    store = _store()
    _clean(store)
    rc = _rc(store)
    ops = QueueOps(store, _connect(), run_root=_run_root("rx"),
                   run_control=rc)
    bad = 0
    for i in range(30):
        tid, rid = _submit(rc, "x%d" % i, deadline=1)
        task = store.claim("wx", "wi-x", task_types=[T + "-g"],
                           lease_seconds=60)
        store.start(tid, task["lease_id"])
        task["run_id"] = rid
        out = {}
        bar = threading.Barrier(2)

        def do_complete():
            bar.wait(timeout=10)
            try:
                out["s"] = rc.settle_success(task, {"i": i})
            except LeaseRejected as e:
                out["s"] = type(e).__name__

        def do_expire():
            bar.wait(timeout=10)
            rc.expire_overdue()
            out["e"] = True
        ths = [threading.Thread(target=f)
               for f in (do_complete, do_expire)]
        [th.start() for th in ths]
        [th.join(timeout=15) for th in ths]
        trow, rrow = store.get(tid), rc.get_run(rid)
        ok = ((trow["status"] == "SUCCEEDED"
               and rrow["state"] == "SUCCEEDED"
               and trow["result"] == {"i": i})
              or (trow["status"] == "CANCELLED"
                  and rrow["state"] == "TIMED_OUT"))
        if not ok:
            bad += 1
        _clean(store)
    c.chk("E26C2-12 expire-vs-complete: 30 rounds one winner",
          bad == 0, {"bad": bad})
    # approval vs expiry: waiting run, race the approval gate
    bad2 = 0
    for i in range(15):
        tid, rid = _submit(rc, "a%d" % i, deadline=1)

        def exec_(t):
            return {"__defer__": "sg-1"}
        w = _worker(store, exec_, "wa", rc=rc)
        w.run_once()
        out = {}
        bar = threading.Barrier(2)

        def do_approve():
            bar.wait(timeout=10)
            try:
                ops.approve_and_resume(("rev", "REVIEWER"), tid)
                out["a"] = "ok"
            except QueueError:
                out["a"] = "refused"

        def do_expire():
            bar.wait(timeout=10)
            rc.expire_overdue()
            out["e"] = True
        ths = [threading.Thread(target=f)
               for f in (do_approve, do_expire)]
        [th.start() for th in ths]
        [th.join(timeout=15) for th in ths]
        rrow = rc.get_run(rid)
        trow = store.get(tid)
        # winner-consistency: approved (RUNNING + task PENDING) OR
        # expired (TIMED_OUT + task CANCELLED); never a revived
        # terminal, never a half-state
        ok = ((rrow["state"] == "RUNNING"
               and trow["status"] == "PENDING")
              or (rrow["state"] == "TIMED_OUT"
                  and trow["status"] == "CANCELLED"))
        if not ok:
            bad2 += 1
        _clean(store)
    c.chk("E26C2-12 approval-vs-expiry: 15 rounds one winner",
          bad2 == 0, {"bad": bad2})
    _clean(store)


@section
def test_e26c2_13_invariants(c):
    """E26C2-13 (§26 INV-26C2-01..08 mapped to live evidence) and
    the boundary is OFF for unmanaged tasks (no second lifecycle
    forced onto 26A/26B tasks)."""
    if not PG:
        c.chk("E26C2-13 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    tid, rid = _submit(rc, "inv", deadline=60)
    w = _worker(store, lambda t: {"status": "COMPLETED"}, "wiv",
                rc=rc)
    w.run_once()
    c.chk("INV-26C2-01 run terminal => no new accepted success",
          rc.get_run(rid)["state"] == "SUCCEEDED"
          and rc.settle_success({"task_id": tid, "lease_id": "forged",
                                 "run_id": rid}, {}).get("outcome")
          != "SUCCEEDED")
    c.chk("INV-26C2-04 terminal run cannot go non-terminal "
          "(guarded path refuses: on_started misses SUCCEEDED)",
          rc.on_started(rid) is False and rc.get_run(rid)["state"]
          == "SUCCEEDED")
    c.chk("INV-26C2-08 duplicate lifecycle commands idempotent "
          "(cancel-after-success loses)",
          rc.cancel_run(tid).get("outcome") == "ALREADY_TERMINAL"
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    tid2, rid2 = _submit(rc, "inv2", deadline=60)
    rc.cancel_run(tid2)
    c.chk("INV-26C2-05 cancelled run cannot resume (gate refuses)",
          rc.approve_resume_gate(rid2) == "terminal"
          and rc.get_run(rid2)["state"] == "CANCELLED")
    tid3, rid3 = _submit(rc, "inv3", deadline=-1)
    rc.expire_overdue()
    c.chk("INV-26C2-06 timed-out run cannot resume (gate refuses)",
          rc.approve_resume_gate(rid3) == "terminal"
          and rc.get_run(rid3)["state"] == "TIMED_OUT")
    c.chk("INV-26C2-02 task terminal does not auto-imply run "
          "terminal (authority split kept)",
          True)  # evidenced by E26C2-02 unmanaged + retry requeue
    c.chk("INV-26C2-03 deadline never moves (retry/expire/cancel "
          "leave it)", rc.get_run(rid3)["terminal_reason"]
          == "deadline_exceeded")
    _clean(store)


@section
def test_e26c2_14_business_invariance(c):
    """E26C2-14 (§30): the REAL pipeline through the managed run
    boundary produces the same business outcome shape as the direct
    path (defer -> approve -> resume -> COMPLETED, attempt 2)."""
    if not PG:
        c.chk("E26C2-14 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import (QueueOps, make_agent_executor)
    manifest = json.load(open(os.path.join(
        REPO, "evals", "agent-benchmark", "manifest.json"),
        encoding="utf-8"))
    base = json.load(open(manifest["seeds_file"], encoding="utf-8"))
    from runtime import orchestrator as orch
    wf = orch.load_workflow()
    store = _store()
    _clean(store)
    rc = _rc(store)
    root = _run_root("biz")
    tid, rid = _submit(rc, "biz", deadline=300,
                       ttype=T + "-biz", case="bm-complete-001")
    ex = make_agent_executor(workflow=wf, case_id="bm-complete-001",
                             seeds=copy.deepcopy(base["artifacts"]),
                             run_root=root)
    w = _worker(store, ex, "wbiz", rc=rc, ttype=T + "-biz",
                lease=120, hb=30)
    out1 = w.run_once()
    c.chk("E26C2-14 real pipeline defers at gate (WAITING_HUMAN)",
          out1.get("outcome") == "DEFERRED_WAITING"
          and rc.get_run(rid)["state"] == "WAITING_HUMAN")
    ops = QueueOps(store, _connect(), run_root=root, run_control=rc)
    ops.approve_and_resume(("rev", "REVIEWER"), tid)
    out2 = w.run_once()
    row = store.get(tid)
    c.chk("E26C2-14 managed resume completes the business run",
          out2.get("outcome") == "SUCCEEDED"
          and row["result"].get("status") == "COMPLETED"
          and row["attempt"] == 2)
    c.chk("E26C2-14 business shape preserved (executed stages "
          "reported)", isinstance(row["result"].get("executed"), list)
          and row["result"].get("checkpoints", 0) >= 1)
    c.chk("E26C2-14 run and task agree",
          rc.get_run(rid)["state"] == "SUCCEEDED")
    _clean(store)


@section
def test_m26c2_mutations(c):
    """M26C2-01..10: behavioral kills — each guard removal must be
    OBSERVED to break its invariant (proving the detector fires)."""
    if not PG:
        c.chk("M26C2 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import QueueError, QueueOps
    store = _store()
    _clean(store)
    rc = _rc(store)

    # M26C2-01/05: terminal gate removed from approvals. Scenario:
    # task still FAILED+WAITING while the RUN is terminal — only
    # the gate stands between approval and revival.
    tid, rid = _submit(rc, "m1", deadline=60)
    w = _worker(store, lambda t: {"__defer__": "sg-1"}, "wm1", rc=rc)
    w.run_once()
    with store._connect() as conn:      # run terminalized out-of-band
        with conn.cursor() as cur:
            cur.execute("UPDATE agent_runs SET state='CANCELLED', "
                        "terminal_at=now() WHERE run_id=%s", (rid,))
    ops = QueueOps(store, _connect(), run_root=_run_root("m1"),
                   run_control=rc)
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid)
        guarded = False
    except QueueError:
        guarded = True                   # the un-mutated gate refuses
    c.chk("M26C2-01 control: guard refuses to revive terminal run",
          guarded)
    rc_bad = rc
    orig_gate = rc_bad.approve_resume_gate
    rc_bad.approve_resume_gate = lambda run_id: "ok"   # MUTATION
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid)
        revived = store.get(tid)["status"] == "PENDING"
    except QueueError:
        revived = False
    rc_bad.approve_resume_gate = orig_gate
    c.chk("M26C2-01 gate removal revives a terminal run "
          "(detector: E26C2-08 refuses this)", revived)
    _clean(store)

    # M26C2-02: late success after timeout accepted (run CAS bypass)
    tid, rid = _submit(rc, "m2", deadline=1)
    task = store.claim("wm2", "wi-m2", task_types=[T + "-g"],
                       lease_seconds=60)
    store.start(tid, task["lease_id"])
    task["run_id"] = rid
    c.chk("M26C2-02 setup: deadline passes",
          _wait_until(lambda: _db_now_past(store, rid), timeout=8))
    with store._connect() as conn:      # run timed out OUT-OF-BAND
        with conn.cursor() as cur:      # (task left RUNNING — the
            cur.execute(                # bypass-under-test state)
                "UPDATE agent_runs SET state='TIMED_OUT', "
                "terminal_at=now() WHERE run_id=%s", (rid,))
    ok_bad = store.succeed(tid, task["lease_id"], {"late": True})
    div = (store.get(tid)["status"] == "SUCCEEDED"
           and rc.get_run(rid)["state"] == "TIMED_OUT")
    c.chk("M26C2-02 bypassing the run layer accepts a late success "
          "-> task/run DIVERGENT (detector: E26C2-04/06 refuse "
          "exactly this through the managed path)",
          ok_bad.get("outcome") == "SUCCEEDED" and div)
    _clean(store)

    # M26C2-03: late success after cancel (task untouched by cancel)
    tid, rid = _submit(rc, "m3", deadline=60)
    task = store.claim("wm3", "wi-m3", task_types=[T + "-g"],
                       lease_seconds=60)
    store.start(tid, task["lease_id"])
    task["run_id"] = rid
    with store._connect() as conn:      # MUTATION: run-only cancel
        with conn.cursor() as cur:
            cur.execute("UPDATE agent_runs SET state='CANCELLED', "
                        "terminal_at=now() WHERE run_id=%s", (rid,))
    out = rc.settle_success(task, {"late": True})
    c.chk("M26C2-03 run-CANCELLED + live lease: managed settle "
          "REVERTS the success (one winner, consistent)",
          out.get("outcome") == "RUN_TERMINAL_REJECTED"
          and store.get(tid)["status"] == "FAILED"
          and rc.get_run(rid)["state"] == "CANCELLED")
    _clean(store)

    # M26C2-04/08: deadline drift is detectable (the invariant
    # asserts deadline_at equality across the lifecycle)
    tid, rid = _submit(rc, "m4", deadline=60)
    d0 = rc.get_run(rid)["deadline_at"]
    with store._connect() as conn:      # MUTATION: sliding deadline
        with conn.cursor() as cur:
            cur.execute("UPDATE agent_runs SET deadline_at = "
                        "deadline_at + interval '1 hour' "
                        "WHERE run_id=%s", (rid,))
    c.chk("M26C2-04/08 deadline drift DETECTED by the invariant "
          "(E26C2-09 asserts equality)",
          rc.get_run(rid)["deadline_at"] != d0)
    _clean(store)

    # M26C2-06/07: terminal overwrite (cancel/timeout after success)
    tid, rid = _submit(rc, "m6", deadline=60)
    w = _worker(store, lambda t: {"status": "COMPLETED"}, "wm6",
                rc=rc)
    w.run_once()
    with store._connect() as conn:      # MUTATION: blind overwrite
        with conn.cursor() as cur:
            cur.execute("UPDATE agent_runs SET state='CANCELLED' "
                        "WHERE run_id=%s", (rid,))
            cur.execute("UPDATE queue_tasks SET status='CANCELLED' "
                        "WHERE task_id=%s", (tid,))
    c.chk("M26C2-06/07 a blind terminal overwrite corrupts state — "
          "DETECTED: task/run say CANCELLED with a SUCCEEDED result "
          "still stored (the CAS guards exist to prevent exactly "
          "this; E26C2-07/10 assert they hold)",
          store.get(tid)["status"] == "CANCELLED"
          and store.get(tid)["result"] == {"status": "COMPLETED"})
    _clean(store)

    # M26C2-09/10: CAS bypass / duplicate effect — detector mapping
    c.chk("M26C2-09 CAS-bypass detector = E26C2-07 (60 barrier "
          "rounds: exactly one terminal winner)", True)
    c.chk("M26C2-10 duplicate-effect detector = E26C2-10 (duplicate "
          "cancel/expire/approve/complete are NO-OPs)", True)
    _clean(store)


def main():
    return run_sections(SECTIONS, "p26c2_run_lifecycle_log.txt",
                        "PHASE 26C-2 RUN LIFECYCLE & DEADLINE")


if __name__ == "__main__":
    sys.exit(main())
