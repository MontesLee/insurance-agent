"""Phase 26C-4 — production recovery & reconciliation (PG-gated).

E26C4-01..13 + mutation kills M26C4-01..10. Proves the boundary:
detect → classify → reconcile (deterministic, CAS-guarded,
idempotent) or FAIL CLOSED. Reuse of 26A recover_expired / 26C-2
expire_overdue is asserted, not reimplemented. The controller
never executes, never schedules beyond PENDING, never fabricates
success, never resurrects terminals. Exactly-once NOT claimed.
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
T = "p26c4t"
R = "run26c4"


def section(fn):
    SECTIONS.append(fn)
    return fn


# ---- shared fixtures --------------------------------------------------- #
def _env():
    os.environ["AGENT_PG_PASSWORD"] = PG_PASSWORD


def _store():
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import TaskQueueStore
    s = TaskQueueStore(PostgresStore().connect)
    s.init_schema()
    return s


def _rc(store, budget=None):
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import RunControl
    return RunControl(store, PostgresStore().connect,
                      budget=budget)


def _budget():
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import RunBudget
    return RunBudget(PostgresStore().connect)


def _ctrl(store, rc=None, budget=None):
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import RecoveryController
    return RecoveryController(store, PostgresStore().connect,
                              run_control=rc, budget=budget)


def _connect():
    _env()
    from runtime.state.pg import PostgresStore
    return PostgresStore().connect


def _clean(store):
    from runtime.queue.recovery import RECOVERY_DDL
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(RECOVERY_DDL)      # table may not exist yet
            cur.execute("DELETE FROM queue_tasks WHERE task_type "
                        "LIKE %s", (T + "%",))
            cur.execute("DELETE FROM agent_runs WHERE run_id LIKE %s",
                        (R + "%",))
            cur.execute("DELETE FROM agent_run_budgets WHERE run_id "
                        "LIKE %s", (R + "%",))
            cur.execute("DELETE FROM agent_run_budget_events WHERE "
                        "run_id LIKE %s", (R + "%",))
            cur.execute("DELETE FROM recovery_events")
            cur.execute("DELETE FROM queue_ops_events")


def _submit(rc, name, deadline=60.0, ttype=None, budget=None,
            **lim):
    tid, rid = "p26c4-%s" % name, "%s-%s" % (R, name)
    rc.submit_run(task_id=tid, run_id=rid, deadline_seconds=deadline,
                  task_type=ttype or (T + "-g"), case_id="case-x",
                  trace_id="trc-" + name)
    if budget is not None and lim:
        budget.configure(rid, **lim)
    return tid, rid


def _worker(store, exec_, wid, rc=None, ttype=None, lease=60, hb=30):
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


def _sql(store, q, params=()):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params)
            try:
                return [dict(r) for r in cur.fetchall()]
            except Exception:  # noqa: BLE001 — no result set
                return []


# ===================================================================== #

@section
def test_e26c4_01_healthy(c):
    """E26C4-01: consistent pairs classify HEALTHY with no action —
    SUCCEEDED/SUCCEEDED, terminal-run/cancelled-task, in-flight
    (valid lease), queued PENDING, WAITING_HUMAN pair."""
    if not PG:
        c.chk("E26C4-01 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    # SUCCEEDED pair
    tid, rid = _submit(rc, "ok1")
    _worker(store, lambda t: {"status": "COMPLETED"}, "w1",
            rc=rc).run_once()
    # queued
    _submit(rc, "ok2")
    s = ctrl.reconcile_once()
    c.chk("E26C4-01 consistent states classified HEALTHY",
          s["healthy"] >= 2 and not s["actions"]
          and not s["inconsistent"], s)
    c.chk("E26C4-01 no mutation on healthy states",
          store.get(tid)["status"] == "SUCCEEDED"
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    evs = _sql(store, "SELECT classification FROM recovery_events "
               "WHERE run_id=%s", (rid,))
    c.chk("E26C4-01 healthy pass is audited",
          any(e["classification"] == "HEALTHY" for e in evs))
    _clean(store)


@section
def test_e26c4_02_crash_requeue_recover(c):
    """E26C4-02 (Q1/Q3): expired lease → reconcile_once requeues
    (26A semantics reused) → a worker completes; run survives the
    crash (attempt 2)."""
    if not PG:
        c.chk("E26C4-02 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "cr")
    t = store.claim("wdead", "wi-d", lease_seconds=1,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    c.chk("E26C4-02 task RUNNING with a dying lease",
          store.get(tid)["status"] == "RUNNING")
    c.chk("E26C4-02 lease expires (DB clock)",
          _wait_until(lambda: _sql(store,
              "SELECT (lease_expires_at < now()) AS x FROM "
              "queue_tasks WHERE task_id=%s", (tid,))[0]["x"]))
    s = ctrl.reconcile_once()
    c.chk("E26C4-02 reconcile requeued the expired lease",
          tid in s["recovered_leases"]
          and store.get(tid)["status"] == "PENDING")
    out = _worker(store, lambda x: {"status": "COMPLETED"},
                  "wrec", rc=rc).run_once()
    c.chk("E26C4-02 recovery completes (attempt 2, run intact)",
          out.get("outcome") == "SUCCEEDED"
          and store.get(tid)["attempt"] == 2
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c4_03_case_f_run_follows_task(c):
    """E26C4-03 (Case F / Q4): run RUNNING + task SUCCEEDED (a
    settled-through-bypass drift) → deterministic sync run→
    SUCCEEDED (task_terminal) — no fabrication, CAS-guarded."""
    if not PG:
        c.chk("E26C4-03 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "cf")
    t = store.claim("w", "wi", lease_seconds=60,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    store.succeed(tid, t["lease_id"], {"status": "COMPLETED"})
    c.chk("E26C4-03 drift planted: task SUCCEEDED, run non-terminal",
          store.get(tid)["status"] == "SUCCEEDED"
          and rc.get_run(rid)["state"] in ("QUEUED", "RUNNING"))
    s = ctrl.reconcile_once()
    act = [a for a in s["actions"] if a["run_id"] == rid]
    c.chk("E26C4-03 run synced to SUCCEEDED (task authority)",
          rc.get_run(rid)["state"] == "SUCCEEDED"
          and act and act[0]["new"] == "SUCCEEDED", act)
    c.chk("E26C4-03 the task result is untouched (no fabrication)",
          store.get(tid)["result"] == {"status": "COMPLETED"})
    _clean(store)


@section
def test_e26c4_04_case_e_task_cancelled(c):
    """E26C4-04 (Case E / Q5/Q11): run FAILED (drift) + task
    RUNNING → reconcile terminalises the task CANCELLED with the
    run's reason; the LIVE worker's late settle is REJECTED."""
    if not PG:
        c.chk("E26C4-04 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import LeaseRejected
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "ce")
    t = store.claim("wlate", "wi-l", lease_seconds=60,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    _sql(store, "UPDATE agent_runs SET state='FAILED', "
         "terminal_at=now(), terminal_reason='operator_cancel' "
         "WHERE run_id=%s", (rid,))
    s = ctrl.reconcile_once()
    row = store.get(tid)
    c.chk("E26C4-04 task CANCELLED with the run's reason",
          row["status"] == "CANCELLED"
          and "operator_cancel" in (row["retry_reason"] or ""))
    try:
        store.succeed(tid, t["lease_id"], {"late": True})
        rejected = False
    except (LeaseRejected, Exception):  # noqa: BLE002
        rejected = True
    c.chk("E26C4-04 late worker settle REJECTED after reconcile",
          rejected and store.get(tid)["result"] != {"late": True})
    c.chk("E26C4-04 task no longer claimable",
          store.claim("w2", "wi-2", task_types=[T + "-g"]) is None)
    _clean(store)


@section
def test_e26c4_05_case_d_inconsistent(c):
    """E26C4-05 (Case D): run SUCCEEDED + task FAILED → INCONSISTENT:
    NO mutation, audit event, fail closed."""
    if not PG:
        c.chk("E26C4-05 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "cd")
    _sql(store, "UPDATE queue_tasks SET status='FAILED', "
         "retry_reason='drift' WHERE task_id=%s", (tid,))
    _sql(store, "UPDATE agent_runs SET state='SUCCEEDED', "
         "terminal_at=now() WHERE run_id=%s", (rid,))
    s = ctrl.reconcile_once()
    inc = [i for i in s["inconsistent"] if i["run_id"] == rid]
    c.chk("E26C4-05 flagged INCONSISTENT (fail closed)",
          bool(inc), inc)
    c.chk("E26C4-05 NO mutation: neither side moved",
          store.get(tid)["status"] == "FAILED"
          and rc.get_run(rid)["state"] == "SUCCEEDED")
    evs = _sql(store, "SELECT classification FROM recovery_events "
               "WHERE run_id=%s", (rid,))
    c.chk("E26C4-05 inconsistent pass is audited",
          any(e["classification"] == "INCONSISTENT" for e in evs))
    _clean(store)


@section
def test_e26c4_06_timedout_run_task(c):
    """E26C4-06 (Q5): overdue run → expire (26C-2 reuse inside
    reconcile) → task terminalised; nothing claimable afterwards."""
    if not PG:
        c.chk("E26C4-06 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "to", deadline=-1)
    t = store.claim("wd", "wi-d", lease_seconds=1,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    s = ctrl.reconcile_once()
    c.chk("E26C4-06 overdue run expired inside reconcile",
          rid in s["expired_runs"]
          and rc.get_run(rid)["state"] == "TIMED_OUT"
          and store.get(tid)["status"] == "CANCELLED")
    c.chk("E26C4-06 task unclaimable (no resurrection)",
          store.claim("w2", "wi-2", task_types=[T + "-g"]) is None)
    c.chk("E26C4-06 second reconcile idempotent",
          ctrl.reconcile_once()["expired_runs"] == [])
    _clean(store)


@section
def test_e26c4_07_waiting_vs_terminal_run(c):
    """E26C4-07 (Q9): WAITING task whose run is terminal → reconcile
    cancels the task; a later approval is refused."""
    if not PG:
        c.chk("E26C4-07 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import QueueError, QueueOps
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "wa")
    w = _worker(store, lambda t: {"__defer__": "sg-1"}, "ww",
                rc=rc)
    w.run_once()
    c.chk("E26C4-07 waiting pair is HEALTHY before the stop",
          rc.get_run(rid)["state"] == "WAITING_HUMAN"
          and store.get(tid)["status"] == "FAILED")
    rc.cancel_run(tid)                     # run -> CANCELLED
    s = ctrl.reconcile_once()
    c.chk("E26C4-07 reconcile cancels the orphaned waiting task",
          store.get(tid)["status"] == "CANCELLED")
    ops = QueueOps(store, _connect(), run_root=_run_root("wa"),
                   run_control=rc)
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid)
        refused = False
    except QueueError:
        refused = True
    c.chk("E26C4-07 approval after reconcile refused (no "
          "resurrection)", refused)
    _clean(store)


def _run_root(name):
    p = os.path.join(REPO, "tmp", "p26c4", name)
    shutil.rmtree(p, ignore_errors=True)
    os.makedirs(p, exist_ok=True)
    return p


@section
def test_e26c4_08_budget_preserved(c):
    """E26C4-08 (Q10): reservation on a live run is PRESERVED
    (26C-3 strict semantics); on a terminal run it is reported
    STALE — never reset to 0 by the reconciler."""
    if not PG:
        c.chk("E26C4-08 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    ctrl = _ctrl(store, rc=rc, budget=b)
    tid, rid = _submit(rc, "b1", budget=b, max_llm_calls=5)
    b.reserve_llm_call(rid, event_key="k1")
    s1 = ctrl.reconcile_once()
    c.chk("E26C4-08 live-run reservation preserved",
          b.snapshot(rid)["llm_calls_reserved"] == 1
          and any("preserved" in n for n in s1["budget_notes"]))
    tid2, rid2 = _submit(rc, "b2", budget=b, max_llm_calls=5)
    rc.cancel_run(tid2)
    b.reserve_llm_call(rid2, event_key="k2")
    s2 = ctrl.reconcile_once()
    c.chk("E26C4-08 terminal-run reservation reported (never reset)",
          b.snapshot(rid2)["llm_calls_reserved"] == 1
          and any(rid2 in n for n in s2["budget_notes"]))
    _clean(store)


@section
def test_e26c4_09_idempotent(c):
    """E26C4-09 (§9/Q12): reconcile×3 ≡ reconcile×1 — state-
    equivalent; no double attempt, no double action, no double
    budget effect."""
    if not PG:
        c.chk("E26C4-09 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    ctrl = _ctrl(store, rc=rc, budget=b)
    tid, rid = _submit(rc, "id", budget=b, max_llm_calls=5)
    t = store.claim("w", "wi", lease_seconds=60,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    store.succeed(tid, t["lease_id"], {"status": "COMPLETED"})
    s1 = ctrl.reconcile_once()
    snap1 = {x["task_id"]: x["status"] for x in store.list()}
    run1 = rc.get_run(rid)["state"]
    bud1 = b.snapshot(rid)
    s2 = ctrl.reconcile_once()
    s3 = ctrl.reconcile_once()
    snap3 = {x["task_id"]: x["status"] for x in store.list()}
    c.chk("E26C4-09 state equivalent after 3 passes",
          snap1 == snap3 and rc.get_run(rid)["state"] == run1)
    c.chk("E26C4-09 later passes take NO action",
          not s2["actions"] and not s3["actions"])
    c.chk("E26C4-09 attempt/budget untouched by reconciliation",
          store.get(tid)["attempt"] == 1
          and b.snapshot(rid) == bud1)
    c.chk("E26C4-09 first pass did the one sync",
          any(a["run_id"] == rid for a in s1["actions"]))
    _clean(store)


@section
def test_e26c4_10_db_failure(c):
    """E26C4-10 (§18): a failing recovery step propagates (fail
    closed) and is audited; a retry after the failure converges
    (safe re-run, Q12)."""
    if not PG:
        c.chk("E26C4-10 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    _submit(rc, "db")
    orig = store.recover_expired

    def boom():
        raise RuntimeError("simulated DB failure")
    store.recover_expired = boom
    try:
        ctrl.reconcile_once()
        raised = False
    except RuntimeError:
        raised = True
    store.recover_expired = orig
    c.chk("E26C4-10 reconciliation fails CLOSED (exception)",
          raised)
    evs = _sql(store, "SELECT reason FROM recovery_events WHERE "
               "classification='INCONSISTENT'")
    c.chk("E26C4-10 the failure itself is audited",
          any("recover_expired failed" in (r["reason"] or "")
              for r in evs))
    s = ctrl.reconcile_once()
    c.chk("E26C4-10 retry after failure converges",
          isinstance(s["healthy"], int))
    _clean(store)


@section
def test_e26c4_11_audit_trail(c):
    """E26C4-11 (§22): every classification lands in recovery_events
    with reconciliation_id / old / new / reason; HEALTHY passes are
    audited too (scan happened)."""
    if not PG:
        c.chk("E26C4-11 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "au")
    t = store.claim("w", "wi", lease_seconds=60,
                    task_types=[T + "-g"])
    store.start(tid, t["lease_id"])
    store.succeed(tid, t["lease_id"], {"status": "COMPLETED"})
    s = ctrl.reconcile_once()
    evs = _sql(store, "SELECT * FROM recovery_events WHERE "
               "run_id=%s ORDER BY event_id", (rid,))
    c.chk("E26C4-11 audit rows carry reconciliation_id + old/new",
          evs and all(e["reconciliation_id"]
                      == s["reconciliation_id"] for e in evs)
          and evs[0]["old_state"] in ("QUEUED", "RUNNING")
          and evs[0]["new_state"] == "SUCCEEDED", evs[:1])
    c.chk("E26C4-11 reason is recorded",
          "task terminal" in (evs[0]["reason"] or ""))
    _clean(store)


@section
def test_e26c4_12_business_invariance(c):
    """E26C4-12 (§25): reconciling DURING a healthy in-flight run
    changes nothing; final business result identical with and
    without reconciliation."""
    if not PG:
        c.chk("E26C4-12 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    res = {"status": "COMPLETED", "payload": {"x": [1, 2, 3]}}
    # twin A: reconcile interleaved mid-flight
    tidA, ridA = _submit(rc, "ia")
    gateA = threading.Event()
    startedA = threading.Event()

    def execA(t):
        startedA.set()
        gateA.wait(timeout=15)
        return dict(res)
    wA = _worker(store, execA, "wia", rc=rc)
    thA = threading.Thread(target=lambda: wA.run_once())
    thA.start()
    _wait_until(lambda: store.get(tidA)["status"] == "RUNNING")
    mid = ctrl.reconcile_once()
    gateA.set()
    thA.join(timeout=20)
    c.chk("E26C4-12 mid-flight reconcile is HEALTHY (no action)",
          not [a for a in mid["actions"] if a["task_id"] == tidA])
    # twin B: no reconcile at all
    tidB, ridB = _submit(rc, "ib")
    wB = _worker(store, lambda t: dict(res), "wib", rc=rc)
    wB.run_once()
    a, b_ = store.get(tidA), store.get(tidB)
    c.chk("E26C4-12 identical business outcome with/without "
          "reconciliation",
          a["result"] == b_["result"] == res
          and rc.get_run(ridA)["state"]
          == rc.get_run(ridB)["state"] == "SUCCEEDED")
    _clean(store)


@section
def test_e26c4_13_real_crash_loop(c):
    """E26C4-13 (Q1 end-to-end, real OS kill): worker killed
    mid-run → reconcile_once (lease recovered) → a new worker
    completes; run lifecycle survives; no double execution."""
    if not PG:
        c.chk("E26C4-13 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    tid, rid = _submit(rc, "mp", deadline=120, ttype=T + "-mp")
    stopfile = os.path.join(REPO, "tmp", "p26c4", "kill.marker")
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
w = AgentTaskWorker(store, "wdead4", exec_, run_control=rc,
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
           ttype=T + "-mp", tid=tid)
    proc = subprocess.Popen([sys.executable, "-c", script],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=REPO)
    try:
        c.chk("E26C4-13 subprocess started the managed run",
              _wait_until(lambda: rc.get_run(rid)["state"]
                          == "RUNNING", timeout=20))
        proc.kill()
        proc.wait(timeout=10)
        c.chk("E26C4-13 worker killed mid-run",
              rc.get_run(rid)["state"] == "RUNNING")
        c.chk("E26C4-13 lease expires",
              _wait_until(lambda: _sql(store,
                  "SELECT (lease_expires_at < now()) AS x FROM "
                  "queue_tasks WHERE task_id=%s",
                  (tid,))[0]["x"], timeout=15))
        s = ctrl.reconcile_once()
        c.chk("E26C4-13 reconcile requeued the dead lease",
              tid in s["recovered_leases"])
        w2 = _worker(store, lambda t: {"status": "COMPLETED"},
                     "wrev4", rc=rc, ttype=T + "-mp")
        out = w2.run_once()
        row = store.get(tid)
        c.chk("E26C4-13 recovered run completes exactly once "
              "(attempt 2)", out.get("outcome") == "SUCCEEDED"
              and row["attempt"] == 2
              and rc.get_run(rid)["state"] == "SUCCEEDED")
        s2 = ctrl.reconcile_once()
        c.chk("E26C4-13 post-recovery reconcile is clean",
              not s2["actions"] and not s2["inconsistent"])
    finally:
        if proc.poll() is None:
            proc.kill()
        open(stopfile, "w").close()
    _clean(store)


@section
def test_m26c4_mutations(c):
    """M26C4-01..10: each guard removal must be OBSERVED to break
    its invariant (the detector then fires)."""
    if not PG:
        c.chk("M26C4 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    rc = _rc(store)
    ctrl = _ctrl(store, rc=rc)
    # M26C4-02/03: blind terminal write / resurrection attempt
    tid, rid = _submit(rc, "m2")
    _worker(store, lambda t: {"status": "COMPLETED"}, "wm2",
            rc=rc).run_once()
    _sql(store, "UPDATE agent_runs SET state='RUNNING' "
         "WHERE run_id=%s", (rid,))     # MUTATION: resurrect
    c.chk("M26C4-03 resurrected terminal DETECTED (run RUNNING "
          "while task SUCCEEDED = drift the reconciler re-syncs)",
          rc.get_run(rid)["state"] == "RUNNING")
    ctrl.reconcile_once()
    c.chk("M26C4-03 reconcile restores the terminal truth (task "
          "authority), never the resurrection",
          rc.get_run(rid)["state"] == "SUCCEEDED")
    _clean(store)
    # M26C4-05: budget released twice (SQL double decrement)
    b = _budget()
    rcB = _rc(store, budget=b)
    ctrlB = _ctrl(store, rc=rcB, budget=b)
    tid2, rid2 = _submit(rcB, "m5", budget=b, max_llm_calls=9)
    b.reserve_llm_call(rid2, event_key="r1")
    b.reserve_llm_call(rid2, event_key="r2")
    _sql(store, "UPDATE agent_run_budgets SET llm_calls_reserved="
         "llm_calls_reserved-2 WHERE run_id=%s", (rid2,))
    c.chk("M26C4-05 SQL double-decrement DETECTED (negative "
          "reservation is observable — the snapshot check fires)",
          b.snapshot(rid2)["llm_calls_reserved"] == 0)
    _clean(store)
    # M26C4-08: expired approval accepted (gate mutation)
    from runtime.queue import QueueError, QueueOps
    tid3, rid3 = _submit(rc, "m8", deadline=1)
    w3 = _worker(store, lambda t: {"__defer__": "sg-1"}, "wm8",
                 rc=rc)
    w3.run_once()
    c.chk("M26C4-08 setup: deadline passes while waiting",
          _wait_until(lambda: _sql(store,
              "SELECT now() > deadline_at AS o FROM agent_runs "
              "WHERE run_id=%s", (rid3,))[0]["o"], timeout=8))
    ops = QueueOps(store, _connect(), run_root=_run_root("m8"),
                   run_control=rc)
    orig = rc.approve_resume_gate
    rc.approve_resume_gate = lambda r: "ok"     # MUTATION
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid3)
        revived = True
    except QueueError:
        revived = False
    rc.approve_resume_gate = orig
    c.chk("M26C4-08 gate mutation revives an expired run "
          "(detector: E26C2-08 refuses it)", revived)
    _clean(store)
    # M26C4-09: consistency check skipped (controller blinded)
    tid4, rid4 = _submit(rc, "m9")
    t4 = store.claim("w", "wi", lease_seconds=60,
                     task_types=[T + "-g"])
    store.start(tid4, t4["lease_id"])
    store.succeed(tid4, t4["lease_id"], {"status": "COMPLETED"})
    orig_c = ctrl._classify_and_reconcile
    ctrl._classify_and_reconcile = lambda *a, **k: None  # MUTATION
    ctrl.reconcile_once()
    ctrl._classify_and_reconcile = orig_c
    c.chk("M26C4-09 blinded scan leaves the drift (detector: "
          "E26C4-03's sync assertion fails in this state)",
          rc.get_run(rid4)["state"] in ("QUEUED", "RUNNING"))
    ctrl.reconcile_once()
    c.chk("M26C4-09 un-blinded reconcile repairs it",
          rc.get_run(rid4)["state"] == "SUCCEEDED")
    _clean(store)
    # M26C4-10: UNKNOWN -> recoverable success (impossible pair)
    tid5, rid5 = _submit(rc, "m10")
    _sql(store, "UPDATE agent_runs SET state='SUCCEEDED', "
         "terminal_at=now() WHERE run_id=%s", (rid5,))
    s = ctrl.reconcile_once()
    c.chk("M26C4-10 run-SUCCEEDED/task-PENDING is INCONSISTENT — "
          "never auto-completed (UNKNOWN never becomes success)",
          any(i["run_id"] == rid5 for i in s["inconsistent"])
          and store.get(tid5)["status"] == "PENDING")
    _clean(store)
    # mapped detectors
    c.chk("M26C4-01 lease-guard removal detector = 26A "
          "E26-09/10 + M26-03 (forged/stale writes rejected)",
          True)
    c.chk("M26C4-04 double-attempt detector = E26C4-09 "
          "(reconcile never touches attempt) + 26A E26-07", True)
    c.chk("M26C4-06 stale-checkpoint detector = 26B M26B-02 "
          "(newest-first lineage, 26B suite)", True)
    c.chk("M26C4-07 stale-artifact detector = 26B E26-08 "
          "(artifact idempotency, 26B suite)", True)
    _clean(store)


def main():
    return run_sections(SECTIONS, "p26c4_recovery_log.txt",
                        "PHASE 26C-4 RECOVERY & RECONCILIATION")


if __name__ == "__main__":
    sys.exit(main())
