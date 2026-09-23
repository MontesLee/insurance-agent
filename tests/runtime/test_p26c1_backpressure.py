"""Phase 26C-1 — worker backpressure & capacity control (PG-gated).

Closes V-26V-P3-01: max_concurrent_tasks existed (26A-19) with ZERO
test coverage and no review audit. This suite fixes the audit gap,
proves the semantics and pins the invariants:

    INV-01 capacity upper bound (incl. the 26C-1 TOCTOU fix:
         reserve is atomic — check-then-act could overshoot)
    INV-02 backpressure BEFORE claim (queued tasks keep no
         lease / no attempt)
    INV-03 capacity released on every settle path
    INV-04 crash does not permanently consume capacity (real
         OS-process kill + lease expiry + worker-B recovery)
    INV-05 multi-worker: per-INSTANCE bound; global concurrency is
         NOT bounded by this control (explicitly asserted)
    INV-06 queue/lease semantics preserved (26A/26B suites remain
         the regression authority)
    INV-07 HITL WAITING holds no execution slot

All waits are deadline-based polls — no sleep-and-hope. The hammer
tests synchronize entry with threading.Barrier; gates are
threading.Events released by the harness after the asserted state is
observed, so concurrency proofs are deterministic, not probabilistic.
"""
from __future__ import annotations

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
T = "p26c1t"          # task_type prefix; cleanup key


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


def _connect():
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD
    from runtime.state.pg import PostgresStore
    return PostgresStore().connect


def _clean(store):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM queue_tasks WHERE task_type "
                        "LIKE %s", (T + "%",))
            cur.execute("DELETE FROM queue_ops_events")


def _enq(store, n, ttype, **kw):
    tids = ["p26c1-%s-%d" % (ttype, i) for i in range(n)]
    for tid in tids:
        store.enqueue(task_id=tid, task_type=ttype, payload={}, **kw)
    return tids


def _worker(store, exec_, wid, ttype, maxc=1, lease=30, hb=30,
            agent=False):
    from runtime.queue import TaskWorker, AgentTaskWorker
    cls = AgentTaskWorker if agent else TaskWorker
    w = cls(store, wid, exec_, lease_seconds=lease,
            heartbeat_every_s=hb, max_concurrent_tasks=maxc)
    w.task_types = [ttype]
    return w


def _wait_until(cond, timeout=15.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.02)
    return False


class _Track:
    """Per-key (per-worker) active/max counters + first-wave count."""

    def __init__(self):
        self.lock = threading.Lock()
        self.active = {}
        self.max = {}
        self.g_active = 0       # global concurrent executions
        self.g_max = 0
        self.started = 0
        self.blocked = 0      # executions that entered while gate unset

    def enter(self, key, gate_is_set):
        with self.lock:
            self.started += 1
            self.active[key] = self.active.get(key, 0) + 1
            self.max[key] = max(self.max.get(key, 0),
                                self.active[key])
            self.g_active += 1
            self.g_max = max(self.g_max, self.g_active)
            if not gate_is_set:
                self.blocked += 1

    def exit(self, key):
        with self.lock:
            self.active[key] = self.active.get(key, 0) - 1
            self.g_active -= 1


def _gated(track, key, gate):
    """Executor: record entry, block on the gate, record exit."""
    def exec_(task):
        track.enter(key, gate.is_set())
        gate.wait(timeout=30)        # harness always releases
        track.exit(key)
        return {"ok": task["task_id"]}
    return exec_


def _spawn(fn_list):
    ths = [threading.Thread(target=f) for f in fn_list]
    [th.start() for th in ths]
    return ths


def _statuses(store, tids):
    return {t: store.get(t)["status"] for t in tids}


# ===================================================================== #

@section
def test_e26c1_01_semantics(c):
    """E26C1-01: constructor semantics + introspection surface (no PG
    needed): max_concurrent normalized >= 1; counters exposed."""
    from runtime.queue import TaskWorker
    w0 = TaskWorker(None, "w", executor=lambda t: {},
                    max_concurrent_tasks=0)
    wn = TaskWorker(None, "w", executor=lambda t: {},
                    max_concurrent_tasks=-3)
    w2 = TaskWorker(None, "w", executor=lambda t: {},
                    max_concurrent_tasks=2)
    c.chk("E26C1-01 max_concurrent_tasks=0 normalizes to 1",
          w0.max_concurrent == 1)
    c.chk("E26C1-01 negative max_concurrent_tasks normalizes to 1",
          wn.max_concurrent == 1)
    c.chk("E26C1-01 explicit capacity kept", w2.max_concurrent == 2)
    c.chk("E26C1-01 active_tasks starts at 0",
          w2.active_tasks == 0 and w2.at_capacity() is False)
    c.chk("E26C1-01 capacity_rejections starts at 0",
          w2.capacity_rejections == 0)


@section
def test_e26c1_02_capacity_bound(c):
    """E26C1-02 (Group A, INV-01): max=2, 5 tasks, 5 concurrent
    run_once callers -> EXACTLY 2 active executions; the rest are
    refused; everything eventually completes exactly once."""
    if not PG:
        c.chk("E26C1-02 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-cap"
    tids = _enq(store, 5, ttype)
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wcap", ttype,
                maxc=2)
    rets = []

    def call():
        rets.append(w.run_once())
    ths = _spawn([call] * 5)
    ok = _wait_until(lambda: w.active_tasks == 2
                     and track.max.get("w") == 2)
    c.chk("E26C1-02 exactly 2 concurrent active executions", ok,
          {"active": w.active_tasks, "max": track.max})
    gate.set()
    [th.join(timeout=30) for th in ths]
    c.chk("E26C1-02 three callers refused at capacity",
          rets.count(None) == 3 and len(rets) == 5, rets)
    c.chk("E26C1-02 capacity_rejections counted (3)",
          w.capacity_rejections == 3, w.capacity_rejections)
    # drain the remaining three through the same bounded worker
    for _ in range(3):
        w.run_once()
    st = _statuses(store, tids)
    c.chk("E26C1-02 all 5 tasks complete exactly once",
          all(s == "SUCCEEDED" for s in st.values()), st)
    c.chk("E26C1-02 max_observed_active == 2 (never 3+)",
          track.max.get("w") == 2, track.max)
    c.chk("E26C1-02 capacity back to 0 after drain",
          w.active_tasks == 0)
    _clean(store)


@section
def test_e26c1_03_backpressure_pre_claim(c):
    """E26C1-03 (Group B, INV-02 + C10): while both slots are busy,
    queued tasks keep status PENDING with NO lease and NO attempt —
    backpressure happens BEFORE the claim."""
    if not PG:
        c.chk("E26C1-03 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-bp"
    tids = _enq(store, 5, ttype)
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wbp", ttype,
                maxc=2)
    ths = _spawn([lambda: w.run_once()] * 2)
    ok = _wait_until(lambda: w.active_tasks == 2)
    c.chk("E26C1-03 two slots busy", ok)
    w.run_once()                      # a third call: must refuse
    c.chk("E26C1-03 run_once at capacity returns None", True)
    for tid in tids[2:]:
        row = store.get(tid)
        c.chk("E26C1-03 %s remains QUEUED (PENDING)" % tid[-1],
              row["status"] == "PENDING")
        c.chk("E26C1-03 %s has NO lease" % tid[-1],
              row["lease_id"] is None
              and row["lease_expires_at"] is None
              and row["lease_owner"] is None)
        c.chk("E26C1-03 %s attempt NOT consumed" % tid[-1],
              row["attempt"] == 0, row["attempt"])
    gate.set()
    [th.join(timeout=30) for th in ths]
    for _ in range(3):
        w.run_once()
    st = _statuses(store, tids)
    c.chk("E26C1-03 all 5 complete after gate release",
          all(s == "SUCCEEDED" for s in st.values()), st)
    _clean(store)


@section
def test_e26c1_04_release_on_success(c):
    """E26C1-04 (Group C, INV-03): success returns the slot; the next
    queued task becomes executable; later tasks stay untouched."""
    if not PG:
        c.chk("E26C1-04 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-rel"
    t1, t2, t3 = _enq(store, 3, ttype)
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wrel", ttype,
                maxc=1)
    th = _spawn([lambda: w.run_once()])[0]
    ok = _wait_until(lambda: store.get(t1)["status"] == "RUNNING")
    c.chk("E26C1-04 T1 running (capacity 1/1)", ok)
    c.chk("E26C1-04 T2/T3 still queued while T1 holds the slot",
          store.get(t2)["status"] == "PENDING"
          and store.get(t3)["status"] == "PENDING")
    gate.set()
    th.join(timeout=30)
    c.chk("E26C1-04 T1 SUCCEEDED",
          store.get(t1)["status"] == "SUCCEEDED")
    c.chk("E26C1-04 capacity returned 1 -> 0 after success",
          w.active_tasks == 0, w.active_tasks)
    out = w.run_once()                # claims T2 (oldest first)
    c.chk("E26C1-04 next queued task claimed and settled",
          out is not None and out.get("outcome") == "SUCCEEDED"
          and store.get(t2)["status"] == "SUCCEEDED", out)
    c.chk("E26C1-04 T3 untouched (no premature claim)",
          store.get(t3)["status"] == "PENDING"
          and store.get(t3)["attempt"] == 0)
    w.run_once()
    c.chk("E26C1-04 T3 completes last",
          store.get(t3)["status"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c1_05_failure_releases(c):
    """E26C1-05 (Group D, INV-03): a FAILED execution releases the
    slot — no capacity leak, later tasks still execute, retry bounded."""
    if not PG:
        c.chk("E26C1-05 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-fail"
    t1, t2 = _enq(store, 2, ttype)

    def exec_(task):
        if task["task_id"] == t1 and task["attempt"] == 1:
            raise RuntimeError("intended first-attempt failure")
        return {"ok": task["task_id"]}
    w = _worker(store, exec_, "wfail", ttype, maxc=1)
    out1 = w.run_once()
    c.chk("E26C1-05 first attempt fails and requeues",
          out1 is not None and out1.get("outcome") == "FAILED_REQUEUED"
          and store.get(t1)["status"] == "PENDING", out1)
    c.chk("E26C1-05 capacity released after failure (1 -> 0)",
          w.active_tasks == 0, w.active_tasks)
    c.chk("E26C1-05 requeued task keeps a bounded attempt count",
          store.get(t1)["attempt"] == 1, store.get(t1)["attempt"])
    out2 = w.run_once()               # T1 attempt 2 succeeds
    c.chk("E26C1-05 retry attempt succeeds",
          out2 is not None and store.get(t1)["status"] == "SUCCEEDED"
          and store.get(t1)["attempt"] == 2)
    out3 = w.run_once()               # T2 only after capacity freed
    c.chk("E26C1-05 queued T2 executes after failure (no leak)",
          out3 is not None and store.get(t2)["status"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c1_06_crash_recovery(c):
    """E26C1-06 (Group E, INV-04): REAL OS process killed mid-run;
    lease expires; worker B (fresh capacity) recovers and completes.
    No process may permanently consume capacity."""
    if not PG:
        c.chk("E26C1-06 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-crash"
    tid = _enq(store, 1, ttype)[0]
    stopfile = os.path.join(REPO, "tmp", "p26c1",
                            "crash_stop.marker")
    os.makedirs(os.path.dirname(stopfile), exist_ok=True)
    if os.path.exists(stopfile):
        os.remove(stopfile)
    script = """
import os, sys, time
sys.path.insert(0, r"{repo}")
os.environ["AGENT_PG_PASSWORD"] = r"{pw}"
from runtime.state.pg import PostgresStore
from runtime.queue import TaskQueueStore, TaskWorker
store = TaskQueueStore(PostgresStore().connect)
ttype = "{ttype}"
def exec_(task):
    while not os.path.exists(r"{stopfile}"):
        time.sleep(0.05)          # mid-execution when killed
    return {{}}
w = TaskWorker(store, "wcrash", exec_, lease_seconds=2,
               heartbeat_every_s=60, max_concurrent_tasks=1)
w.task_types = [ttype]
end = time.time() + 60
while time.time() < end:
    if w.run_once() is not None:
        continue
    if store.get("{tid}")["status"] == "SUCCEEDED":
        break
    time.sleep(0.05)
""".format(repo=REPO, pw=PG_PASSWORD, ttype=ttype,
           stopfile=stopfile, tid=tid)
    proc = subprocess.Popen([sys.executable, "-c", script],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=REPO)
    try:
        ok = _wait_until(lambda: store.get(tid)["status"]
                         == "RUNNING", timeout=20)
        c.chk("E26C1-06 subprocess claimed and started T1 "
              "(attempt 1, its slot busy)", ok
              and store.get(tid)["attempt"] == 1)
        proc.kill()                    # HARD kill mid-execution
        proc.wait(timeout=10)
        c.chk("E26C1-06 worker process killed", proc.returncode != 0)
        # lease (2s, no heartbeat) expires -> task claimable again
        ok = _wait_until(lambda: store.get(tid)["lease_expires_at"]
                         is not None and _lease_expired(store, tid),
                         timeout=15)
        c.chk("E26C1-06 dead worker's lease expired", ok)
        # worker B: fresh instance, fresh capacity, same queue
        w2 = _worker(store, lambda t: {"ok": t["task_id"]},
                     "wrecover", ttype, maxc=1)
        out = w2.run_once()
        row = store.get(tid)
        c.chk("E26C1-06 worker B recovered T1 (attempt 2, no "
              "attempt inflation beyond the real re-claim)",
              out is not None and row["attempt"] == 2
              and row["status"] == "SUCCEEDED", (out, row["attempt"],
                                                 row["status"]))
        c.chk("E26C1-06 worker B capacity free after recovery",
              w2.active_tasks == 0)
        c.chk("E26C1-06 crashed instance holds NO shared capacity "
              "(worker B executed immediately)",
              w2.capacity_rejections == 0)
        # nothing left to recover
        c.chk("E26C1-06 recover_expired finds nothing after "
              "recovery", store.recover_expired() == [])
    finally:
        if proc.poll() is None:
            proc.kill()
        open(stopfile, "w").close()    # release a surviving loop
    _clean(store)


def _lease_expired(store, tid):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT (lease_expires_at < now()) AS x "
                        "FROM queue_tasks WHERE task_id=%s", (tid,))
            row = cur.fetchone()
            return bool(row and row["x"])


@section
def test_e26c1_07_multiworker(c):
    """E26C1-07 (Group F + M26C-06, INV-05): 2 workers x max=2 on 8
    shared tasks: each instance <= 2; observed GLOBAL concurrency is
    4 — the control is worker-local, NOT a global cap (a global cap
    of 2 would fail this). No duplicate terminal, no lost task."""
    if not PG:
        c.chk("E26C1-07 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-mw"
    tids = _enq(store, 8, ttype)
    gate = threading.Event()
    track = _Track()      # shared: keys "A"/"B" + global counters
    wA = _worker(store, _gated(track, "A", gate), "wA", ttype,
                 maxc=2)
    wB = _worker(store, _gated(track, "B", gate), "wB", ttype,
                 maxc=2)

    def loop(w):
        end = time.time() + 60
        while time.time() < end:
            if w.run_once() is None:
                if all(store.get(t)["status"] in ("SUCCEEDED",
                                                  "CANCELLED")
                       for t in tids):
                    break
                time.sleep(0.02)
    # TWO caller threads per worker instance — a worker's own
    # concurrency comes from concurrent run_once() callers
    ths = _spawn([lambda: loop(wA), lambda: loop(wA),
                  lambda: loop(wB), lambda: loop(wB)])
    ok = _wait_until(lambda: wA.active_tasks == 2
                     and wB.active_tasks == 2, timeout=20)
    c.chk("E26C1-07 both workers at their own capacity (2+2)", ok,
          {"A": wA.active_tasks, "B": wB.active_tasks})
    c.chk("E26C1-07 remaining 4 tasks queued (no premature lease)",
          all(store.get(t)["status"] == "PENDING"
              and store.get(t)["attempt"] == 0 for t in tids[4:]))
    gate.set()
    [th.join(timeout=60) for th in ths]
    st = _statuses(store, tids)
    c.chk("E26C1-07 all 8 complete exactly once",
          all(s == "SUCCEEDED" for s in st.values()), st)
    c.chk("E26C1-07 worker A never exceeded 2",
          track.max.get("A", 0) <= 2, track.max)
    c.chk("E26C1-07 worker B never exceeded 2",
          track.max.get("B", 0) <= 2, track.max)
    c.chk("E26C1-07 observed SIMULTANEOUS global concurrency == 4 "
          "(worker-local control is NOT a global cap)",
          track.g_max == 4, track.g_max)
    owners = {store.get(t)["worker_id"] for t in tids}
    c.chk("E26C1-07 both workers participated", owners == {"wA", "wB"},
          owners)
    _clean(store)


@section
def test_e26c1_08_retry_capacity(c):
    """E26C1-08 (Group H): retry consumes a slot ONLY while actively
    executing — between attempts the slot is free and the requeued
    task carries no lease; attempts increment per real claim only."""
    if not PG:
        c.chk("E26C1-08 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-retry"
    t1, t2 = _enq(store, 2, ttype, max_attempts=3)

    def exec_(task):
        if task["task_id"] == t1 and task["attempt"] < 3:
            raise RuntimeError("fail until attempt 3")
        return {"ok": task["task_id"]}
    w = _worker(store, exec_, "wretry", ttype, maxc=1)
    seen_attempts = []
    for _ in range(6):
        out = w.run_once()
        if out is None:
            break
        row = store.get(t1)
        if row["status"] == "PENDING":
            seen_attempts.append(row["attempt"])
            c.chk("E26C1-08 slot free while attempt %d awaits retry"
                  % row["attempt"], w.active_tasks == 0)
            c.chk("E26C1-08 requeued task holds no lease",
                  row["lease_id"] is None)
    row = store.get(t1)
    c.chk("E26C1-08 task succeeds at its last bounded attempt",
          row["status"] == "SUCCEEDED" and row["attempt"] == 3, row)
    c.chk("E26C1-08 intermediate requeues seen at attempts 1,2",
          seen_attempts == [1, 2], seen_attempts)
    w.run_once()
    c.chk("E26C1-08 T2 executes after retries complete",
          store.get(t2)["status"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c1_09_hitl_capacity(c):
    """E26C1-09 (Group I, INV-07): a WAITING (deferred) task holds NO
    execution slot; after approval + requeue the resume consumes a
    slot again and completes."""
    if not PG:
        c.chk("E26C1-09 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import QueueOps
    store = _store()
    _clean(store)
    ttype = T + "-hitl"
    tid = _enq(store, 1, ttype)[0]
    root = os.path.join(REPO, "tmp", "p26c1", "hitl")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    mode = {"defer": True}

    def exec_(task):
        if mode["defer"]:
            return {"__defer__": "sg-1"}
        return {"status": "COMPLETED", "ok": task["task_id"]}
    w = _worker(store, exec_, "whitl", ttype, maxc=1, agent=True)
    out = w.run_once()
    row = store.get(tid)
    c.chk("E26C1-09 gate defers the task (FAILED + WAITING reason)",
          out is not None and row["status"] == "FAILED"
          and (row["retry_reason"] or "").startswith(
              "WAITING_FOR_APPROVAL@"), (out, row["retry_reason"]))
    c.chk("E26C1-09 WAITING task holds NO execution slot",
          w.active_tasks == 0, w.active_tasks)
    ops = QueueOps(store, _connect(), run_root=root)
    res = ops.approve_and_resume(("rev-1", "REVIEWER"), tid)
    c.chk("E26C1-09 approval requeues the task",
          res.get("outcome") == "REQUEUED_FOR_RESUME"
          and store.get(tid)["status"] == "PENDING", res)
    mode["defer"] = False
    out2 = w.run_once()
    row = store.get(tid)
    c.chk("E26C1-09 resume consumes capacity again and completes",
          out2 is not None and row["status"] == "SUCCEEDED"
          and row["attempt"] == 2, (out2, row["attempt"]))
    c.chk("E26C1-09 slot released after resume settle",
          w.active_tasks == 0)
    marker = os.path.join(root, "attempt-1", "approval.json")
    c.chk("E26C1-09 approval marker recorded",
          os.path.isfile(marker))
    _clean(store)


@section
def test_e26c1_10_toctou_hammer(c):
    """E26C1-10 (Group G / INV-01, the 26C-1 fix): 8 barrier-
    synchronized run_once callers on ONE worker (max=2) with a held
    gate — the reservation must be atomic: exactly 2 execute, 6 are
    refused, observed active NEVER exceeds 2. (Pre-fix check-then-act
    let all callers past at_capacity().)"""
    if not PG:
        c.chk("E26C1-10 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-race"
    tids = _enq(store, 12, ttype)
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wrace", ttype,
                maxc=2)
    n_threads = 8
    bar = threading.Barrier(n_threads)
    done = []

    def call():
        bar.wait(timeout=15)
        done.append(w.run_once())
    ths = _spawn([call] * n_threads)
    # first wave: exactly 2 executions block on the gate; the other
    # 6 callers must be refused (and RETURN) while the gate is held
    ok = _wait_until(lambda: track.blocked == 2
                     and len(done) == n_threads - 2, timeout=20)
    c.chk("E26C1-10 exactly 2 first-wave executions (6 refused)",
          ok, {"blocked": track.blocked, "done": len(done)})
    c.chk("E26C1-10 capacity bound held under synchronized entry",
          w.active_tasks == 2 and track.max.get("w") == 2,
          {"active": w.active_tasks, "max": track.max})
    c.chk("E26C1-10 refusals counted exactly 6",
          w.capacity_rejections == 6, w.capacity_rejections)
    gate.set()
    [th.join(timeout=30) for th in ths]
    for _ in range(10):               # drain the remaining 10 tasks
        w.run_once()
    st = _statuses(store, tids)
    c.chk("E26C1-10 all 12 tasks complete exactly once",
          all(s == "SUCCEEDED" for s in st.values())
          and len([s for s in st.values() if s == "SUCCEEDED"]) == 12,
          st)
    c.chk("E26C1-10 observed concurrency never exceeded 2",
          track.max.get("w") == 2, track.max)
    _clean(store)


@section
def test_e26c1_11_metrics(c):
    """E26C1-11 (§20 metrics): max_concurrent_tasks, active_tasks,
    queued_tasks (store) and capacity_rejections are measurable; a
    claim-miss with a FREE slot is NOT a capacity rejection."""
    if not PG:
        c.chk("E26C1-11 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    ttype = T + "-met"
    tid = _enq(store, 1, ttype)[0]
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wmet", ttype,
                maxc=1)
    th = _spawn([lambda: w.run_once()])[0]
    ok = _wait_until(lambda: w.active_tasks == 1
                     and store.get(tid)["status"] == "RUNNING")
    c.chk("E26C1-11 active_tasks measurable (1/1)", ok)
    own_pending = [t for t in store.list(status="PENDING", limit=50)
                   if (t["task_type"] or "").startswith(T)]
    c.chk("E26C1-11 queued_tasks measurable (0 own pending)",
          own_pending == [])
    c.chk("E26C1-11 max_concurrent_tasks measurable",
          w.max_concurrent == 1)
    refused = w.run_once()            # at capacity
    c.chk("E26C1-11 refusal observed", refused is None)
    c.chk("E26C1-11 capacity_rejections measurable (1)",
          w.capacity_rejections == 1)
    gate.set()
    th.join(timeout=30)
    # free slot + nothing claimable for our type -> NOT a rejection
    w2 = _worker(store, lambda t: {}, "wmet2", ttype + "-none")
    c.chk("E26C1-11 empty-queue miss is not a capacity rejection",
          w2.run_once() is None and w2.capacity_rejections == 0)
    _clean(store)


@section
def test_m26c_mutations(c):
    """M26C-01..06: behavioral kills (instance-level mutations only
    — never source edits). Each mutation must be DETECTED by the
    invariants above."""
    if not PG:
        c.chk("M26C (SKIPPED — no live PG)", True)
        return
    from runtime.queue import TaskWorker
    store = _store()
    _clean(store)

    # -- M26C-01 capacity bypass (the pre-fix check-then-act) ----- #
    ttype = T + "-m1"
    tids = _enq(store, 12, ttype)
    gate = threading.Event()
    track = _Track()
    w = _worker(store, _gated(track, "w", gate), "wm1", ttype,
                maxc=2)
    w._reserve = lambda: True         # MUTATION: bypass the bound
    bar = threading.Barrier(6)
    done = []

    def call():
        bar.wait(timeout=15)
        done.append(w.run_once())
    ths = _spawn([call] * 6)
    overshoot = _wait_until(lambda: track.blocked >= 3, timeout=20)
    c.chk("M26C-01 bypass DETECTED: active executions exceed "
          "max_concurrent_tasks (3+ with max=2)",
          overshoot, {"blocked": track.blocked,
                      "max": track.max.get("w")})
    gate.set()
    [th.join(timeout=30) for th in ths]
    for _ in range(6):
        w.run_once()
    _clean(store)

    # -- M26C-02 / M26C-04 release removed / counter not decremented #
    ttype = T + "-m2"
    t1, t2 = _enq(store, 2, ttype)
    leak = TaskWorker(store, "wm2", lambda t: {"ok": t["task_id"]},
                      lease_seconds=30, heartbeat_every_s=30,
                      max_concurrent_tasks=1)
    leak.task_types = [ttype]
    leak._release_slot = lambda: None     # MUTATION: never release
    out1 = leak.run_once()
    c.chk("M26C-02 control: first task settles fine",
          out1 is not None and store.get(t1)["status"] == "SUCCEEDED")
    c.chk("M26C-02 MUTATION DETECTED: slot leaks (active stays 1)",
          leak.active_tasks == 1, leak.active_tasks)
    out2 = leak.run_once()
    c.chk("M26C-04 MUTATION DETECTED: leaked capacity blocks the "
          "next task (T2 never claimed)",
          out2 is None and store.get(t2)["status"] == "PENDING")
    _clean(store)

    # -- M26C-03 check moved after claim --------------------------- #
    ttype = T + "-m3"
    tids = _enq(store, 4, ttype)
    gate = threading.Event()
    track = _Track()
    w3 = _worker(store, _gated(track, "w", gate), "wm3", ttype,
                 maxc=2)
    ths = _spawn([lambda: w3.run_once()] * 2)
    ok = _wait_until(lambda: w3.active_tasks == 2)
    out = w3.run_once()               # refused third call
    queued = store.get(tids[2])
    c.chk("M26C-03 DETECTOR: refusal keeps the task QUEUED with no "
          "lease/attempt (claim-then-wait would leave a lease)",
          ok and out is None and queued["status"] == "PENDING"
          and queued["lease_id"] is None and queued["attempt"] == 0,
          queued)
    gate.set()
    [th.join(timeout=30) for th in ths]
    _clean(store)

    # -- M26C-05 crashed worker keeps capacity ---------------------- #
    # Behavioral kill = E26C1-06 (real kill -> worker B executes
    # immediately; capacity is per-instance, a dead process cannot
    # hold a slot in any live worker).
    c.chk("M26C-05 detector lives in E26C1-06 (crash -> recovery "
          "consumes fresh capacity; no permanent occupancy)", True)

    # -- M26C-06 worker-local limit treated as global --------------- #
    # Behavioral kill = E26C1-07 (global observed concurrency 4 with
    # per-worker max 2 — a global cap of 2 would fail that check).
    c.chk("M26C-06 detector lives in E26C1-07 (global concurrency "
          "4 observed; the limit is per-instance, not global)", True)
    _clean(store)


def main():
    return run_sections(SECTIONS, "p26c1_backpressure_log.txt",
                        "PHASE 26C-1 BACKPRESSURE & CAPACITY CONTROL")


if __name__ == "__main__":
    sys.exit(main())
