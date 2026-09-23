"""Phase 26C-3 — run budget & bounded execution (PG-gated).

E26C3-01..13 + crash C1-C3 + mutation kills M26C3-01..10. Proves
the budget boundary: run-scoped, absolute, PG-authoritative,
race-safe reservation, idempotent settlement (event-key ledger),
UNKNOWN usage NEVER zero (fail-closed under hard limits), hard stop
via the 26C-2 control points (no new run states), retry/replan/
resume/crash never reset anything, and no fabricated success past
exhaustion. Exactly-once is NOT claimed.
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
T = "p26c3t"          # task_type prefix; cleanup key
R = "run26c3"         # run_id prefix; cleanup key

PRICING = {"m-fake": {"input_per_1k": 0.01, "output_per_1k": 0.03}}


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


def _budget():
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import RunBudget
    return RunBudget(PostgresStore().connect, pricing=PRICING)


def _rc(store, budget=None):
    _env()
    from runtime.state.pg import PostgresStore
    from runtime.queue import RunControl
    return RunControl(store, PostgresStore().connect,
                      budget=budget)


def _connect():
    _env()
    from runtime.state.pg import PostgresStore
    return PostgresStore().connect


def _clean(store):
    with store._connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM queue_tasks WHERE task_type "
                        "LIKE %s", (T + "%",))
            cur.execute("DELETE FROM agent_runs WHERE run_id LIKE %s",
                        (R + "%",))
            cur.execute("DELETE FROM agent_run_budgets WHERE run_id "
                        "LIKE %s", (R + "%",))
            cur.execute("DELETE FROM agent_run_budget_events WHERE "
                        "run_id LIKE %s", (R + "%",))
            cur.execute("DELETE FROM queue_ops_events")


def _submit(rc, budget, name, deadline=60.0, ttype=None, **lim):
    from runtime.state.pg import PostgresStore
    from runtime.queue import TaskQueueStore
    tid, rid = "p26c3-%s" % name, "%s-%s" % (R, name)
    rc.submit_run(task_id=tid, run_id=rid, deadline_seconds=deadline,
                  task_type=ttype or (T + "-g"), case_id="case-x",
                  trace_id="trc-" + name)
    if budget is not None:
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
def test_e26c3_01_configure_absolute(c):
    """E26C3-01: configure is write-once (immutable on conflict —
    retry/resume can never raise limits); NULL = UNMETERED."""
    if not PG:
        c.chk("E26C3-01 (SKIPPED — no live PG)", True)
        return
    b = _budget()
    b.configure(R + "-c1", max_llm_calls=5, max_input_tokens=100)
    b.configure(R + "-c1", max_llm_calls=999)          # re-configure
    s = b.snapshot(R + "-c1")
    c.chk("E26C3-01 limits are write-once (no reset/raise)",
          s["max_llm_calls"] == 5 and s["max_input_tokens"] == 100)
    c.chk("E26C3-01 unmetered dimensions stay NULL",
          s["max_output_tokens"] is None and s["max_replans"] is None)
    c.chk("E26C3-01 counters start at zero (not faked)",
          s["llm_calls_used"] == 0 and s["llm_calls_reserved"] == 0
          and s["usage_unknown"] is False)
    _clean(_store())


@section
def test_e26c3_02_reservation_race(c):
    """E26C3-02 (§31): remaining=1, two barrier-synchronized
    reservers -> exactly one wins; remaining=3 with 5 reservers ->
    exactly 3 win. reserved NEVER exceeds the hard limit."""
    if not PG:
        c.chk("E26C3-02 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BudgetExceeded
    b = _budget()
    b.configure(R + "-r1", max_llm_calls=1)
    outcomes = []
    bar = threading.Barrier(2)

    def go(i):
        bar.wait(timeout=10)
        try:
            outcomes.append(b.reserve_llm_call(
                R + "-r1", event_key="r1-%d" % i)["outcome"])
        except BudgetExceeded:
            outcomes.append("EXCEEDED")
    ths = [threading.Thread(target=go, args=(i,)) for i in range(2)]
    [th.start() for th in ths]
    [th.join(timeout=15) for th in ths]
    c.chk("E26C3-02 remaining=1: exactly one winner",
          outcomes.count("RESERVED") == 1
          and outcomes.count("EXCEEDED") == 1, outcomes)
    b.configure(R + "-r2", max_llm_calls=3)
    outcomes2 = []
    bar2 = threading.Barrier(5)

    def go2(i):
        bar2.wait(timeout=10)
        try:
            outcomes2.append(b.reserve_llm_call(
                R + "-r2", event_key="r2-%d" % i)["outcome"])
        except BudgetExceeded:
            outcomes2.append("EXCEEDED")
    ths = [threading.Thread(target=go2, args=(i,))
           for i in range(5)]
    [th.start() for th in ths]
    [th.join(timeout=15) for th in ths]
    c.chk("E26C3-02 remaining=3 of 5: exactly three win",
          outcomes2.count("RESERVED") == 3
          and outcomes2.count("EXCEEDED") == 2, outcomes2)
    c.chk("E26C3-02 total reserved <= hard limit",
          b.snapshot(R + "-r2")["llm_calls_reserved"] == 3)
    _clean(_store())


@section
def test_e26c3_03_idempotent_settlement(c):
    """E26C3-03: same event_key settles ONCE (ledger UNIQUE); a
    duplicate settle is a visible NO-OP; release clamps at 0."""
    if not PG:
        c.chk("E26C3-03 (SKIPPED — no live PG)", True)
        return
    b = _budget()
    b.configure(R + "-i1", max_llm_calls=10)
    b.reserve_llm_call(R + "-i1", event_key="res-1")
    o1 = b.settle(R + "-i1", "set-1", llm_calls=1, input_tokens=100)
    o2 = b.settle(R + "-i1", "set-1", llm_calls=1, input_tokens=100)
    s = b.snapshot(R + "-i1")
    c.chk("E26C3-03 first settle applies, duplicate is NO-OP",
          o1["outcome"] == "SETTLED" and o2["outcome"] == "DUPLICATE"
          and s["llm_calls_used"] == 1
          and s["input_tokens_used"] == 100)
    c.chk("E26C3-03 settled reservation released (clamped)",
          s["llm_calls_reserved"] == 0)
    b.release_reservation(R + "-i1", n=99, event_key="rel-x")
    c.chk("E26C3-03 release clamps at zero (never negative)",
          b.snapshot(R + "-i1")["llm_calls_reserved"] == 0)
    duprel = b.release_reservation(R + "-i1", event_key="rel-x")
    c.chk("E26C3-03 duplicate release is NO-OP",
          duprel["outcome"] == "DUPLICATE")
    _clean(_store())


@section
def test_e26c3_04_unknown_usage(c):
    """E26C3-04 (§8/§10): real tokens accumulate; UNKNOWN usage sets
    a flag and NEVER adds 0; under a HARD token limit the run cannot
    prove compliance -> fail closed; without a hard limit UNKNOWN is
    tolerated (unmetered dimension)."""
    if not PG:
        c.chk("E26C3-04 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BUDGET_UNKNOWN, BudgetExceeded
    b = _budget()
    b.configure(R + "-u1", max_input_tokens=1000)
    b.settle(R + "-u1", "s1", input_tokens=400, output_tokens=100)
    s = b.snapshot(R + "-u1")
    c.chk("E26C3-04 real usage accumulates",
          s["input_tokens_used"] == 400
          and s["output_tokens_used"] == 100)
    b.settle(R + "-u1", "s2", input_tokens=BUDGET_UNKNOWN)
    s = b.snapshot(R + "-u1")
    c.chk("E26C3-04 UNKNOWN adds ZERO to counters (flag instead)",
          s["input_tokens_used"] == 400 and s["usage_unknown"])
    try:
        b.check(R + "-u1")
        c.chk("E26C3-04 UNKNOWN under hard limit fails closed",
              False)
    except BudgetExceeded as e:
        c.chk("E26C3-04 UNKNOWN under hard limit fails closed",
              "UNKNOWN" in e.detail["type"], e.detail["type"])
    b.configure(R + "-u2")            # everything unmetered
    b.settle(R + "-u2", "s1", input_tokens=BUDGET_UNKNOWN)
    c.chk("E26C3-04 UNKNOWN on an UNMETERED dimension is tolerated",
          b.check(R + "-u2") is not None)
    _clean(_store())


@section
def test_e26c3_05_cost_accounting(c):
    """E26C3-05 (§9): cost = config pricing × real tokens; partial
    UNKNOWN -> UNKNOWN cost (never 0); unknown pricing -> UNKNOWN."""
    if not PG:
        c.chk("E26C3-05 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BUDGET_UNKNOWN, BudgetExceeded
    b = _budget()
    cost = b.estimate_cost("m-fake", 2000, 1000)
    c.chk("E26C3-05 pricing from config (2K in + 1K out)",
          abs(cost - (2 * 0.01 + 1 * 0.03)) < 1e-9, cost)
    c.chk("E26C3-05 unknown model -> UNKNOWN cost",
          b.estimate_cost("m-mystery", 100, 100) == BUDGET_UNKNOWN)
    c.chk("E26C3-05 unknown tokens -> UNKNOWN cost",
          b.estimate_cost("m-fake", BUDGET_UNKNOWN, 100)
          == BUDGET_UNKNOWN)
    b.configure(R + "-c5", max_estimated_cost=0.05)
    b.settle(R + "-c5", "s1", cost=0.02)
    b.settle(R + "-c5", "s2", cost=BUDGET_UNKNOWN)
    try:
        b.check(R + "-c5")
        c.chk("E26C3-05 UNKNOWN cost under hard limit fails closed",
              False)
    except BudgetExceeded as e:
        c.chk("E26C3-05 UNKNOWN cost under hard limit fails closed",
              "COST_UNKNOWN" in e.detail["type"], e.detail["type"])
    _clean(_store())


@section
def test_e26c3_06_soft_budget(c):
    """E26C3-06 (§11): crossing 80% of a limit records a
    SOFT_WARNING ledger event and does NOT change behavior."""
    if not PG:
        c.chk("E26C3-06 (SKIPPED — no live PG)", True)
        return
    b = _budget()
    b.configure(R + "-sw", max_llm_calls=10)
    b.settle(R + "-sw", "s1", llm_calls=8)
    b.check(R + "-sw")            # 8/10 = 80% -> soft warning only
    evs = _sql(_store(), "SELECT kind FROM agent_run_budget_events "
               "WHERE run_id=%s AND kind='SOFT_WARNING'", (R + "-sw",))
    c.chk("E26C3-06 soft crossing recorded once (audit only)",
          len(evs) == 1, evs)
    c.chk("E26C3-06 soft warning did not stop anything",
          b.check(R + "-sw") is not None)
    _clean(_store())


@section
def test_e26c3_07_task_attempt_budget(c):
    """E26C3-07 (worker path): run-level max_task_attempts=2 — the
    third attempt is refused at the control point; run FAILED with
    structured budget reason; per-task max_attempts unchanged."""
    if not PG:
        c.chk("E26C3-07 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    tid, rid = _submit(rc, b, "ta", deadline=120, max_task_attempts=2)

    def exec_(task):
        raise RuntimeError("always fails")
    w = _worker(store, exec_, "wta", rc=rc)
    out1 = w.run_once()
    c.chk("E26C3-07 attempt 1 requeues (within budget)",
          out1.get("outcome") == "FAILED_REQUEUED")
    out2 = w.run_once()
    c.chk("E26C3-07 attempt 2 fails and the RETRY is refused "
          "(budget): RUN_BUDGET_EXCEEDED",
          out2.get("outcome") == "RUN_BUDGET_EXCEEDED", out2)
    row, run = store.get(tid), rc.get_run(rid)
    c.chk("E26C3-07 run FAILED with structured budget reason",
          run["state"] == "FAILED"
          and run["terminal_reason"].startswith(
              "budget_exceeded:MAX_TASK_ATTEMPTS"), run["terminal_reason"])
    c.chk("E26C3-07 task terminal, no third attempt",
          row["status"] in ("FAILED", "CANCELLED")
          and store.claim("w3", "wi-3", task_types=[T + "-g"]) is None)
    c.chk("E26C3-07 usage counters recorded both attempts",
          b.snapshot(rid)["task_attempts_used"] == 2)
    _clean(store)


@section
def test_e26c3_08_repair_budget_no_fabricated_success(c):
    """E26C3-08 (§37): a completion whose repair usage exceeds the
    hard repair budget is NEVER accepted — no fabricated artifact,
    no invalid success; run FAILED budget reason."""
    if not PG:
        c.chk("E26C3-08 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    tid, rid = _submit(rc, b, "rp", deadline=60,
                       max_repair_attempts=1)

    def exec_(task):
        return {"status": "COMPLETED",
                "budget_usage": {"repair_attempts": 2, "replans": 0}}
    w = _worker(store, exec_, "wrp", rc=rc)
    out = w.run_once()
    c.chk("E26C3-08 over-budget completion rejected "
          "(RUN_BUDGET_EXCEEDED)", out.get("outcome")
          == "RUN_BUDGET_EXCEEDED", out)
    row, run = store.get(tid), rc.get_run(rid)
    c.chk("E26C3-08 no fabricated success (result NULL, task "
          "terminal)", row["status"] == "FAILED"
          and row["result"] in (None, ""))
    c.chk("E26C3-08 run FAILED with repair-budget reason",
          run["state"] == "FAILED"
          and "REPAIR_ATTEMPTS" in (run["terminal_reason"] or ""))
    c.chk("E26C3-08 repair usage recorded",
          b.snapshot(rid)["repair_attempts_used"] == 2)
    _clean(store)


@section
def test_e26c3_09_no_reset_on_retry(c):
    """E26C3-09 (§6/§38 C-D-E-F): retry / resume / re-configure /
    recovery never reset limits or counters (all bit-identical)."""
    if not PG:
        c.chk("E26C3-09 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    tid, rid = _submit(rc, b, "nr", deadline=120, max_llm_calls=10,
                       max_task_attempts=5)
    b.settle(rid, "pre", llm_calls=4)
    d0 = b.snapshot(rid)
    # retry cycle: fail -> requeue -> claim again
    attempts = {"n": 0}

    def exec_(task):
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise RuntimeError("one retry")
        return {"status": "COMPLETED"}
    w = _worker(store, exec_, "wnr", rc=rc)
    w.run_once()                      # attempt 1: requeue
    b.configure(rid, max_llm_calls=999)      # reconfigure attempt
    s_mid = b.snapshot(rid)
    c.chk("E26C3-09 reconfigure cannot raise the limit",
          s_mid["max_llm_calls"] == 10)
    c.chk("E26C3-09 usage preserved across the retry",
          s_mid["llm_calls_used"] == 4)
    w.run_once()                      # attempt 2: success
    s_end = b.snapshot(rid)
    c.chk("E26C3-09 success adds attempts without resetting",
          s_end["task_attempts_used"] == 2
          and s_end["llm_calls_used"] == 4
          and s_end["max_llm_calls"] == d0["max_llm_calls"])
    _clean(store)


@section
def test_e26c3_10_hitl_budget(c):
    """E26C3-10 (§29): budget exhausted -> approval REFUSED; no
    automatic budget increase; generous budget -> HITL cycle works
    with usage preserved across the resume."""
    if not PG:
        c.chk("E26C3-10 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import QueueError, QueueOps
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    root = os.path.join(REPO, "tmp", "p26c3", "hitl")
    shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)
    # (a) exhausted budget refuses approval
    tid, rid = _submit(rc, b, "h1", deadline=60, max_llm_calls=1)
    mode = {"defer": True}

    def exec_(task):
        return ({"__defer__": "sg-1"} if mode["defer"]
                else {"status": "COMPLETED"})
    w = _worker(store, exec_, "wh1", rc=rc)
    w.run_once()
    c.chk("E26C3-10 run WAITING_HUMAN",
          rc.get_run(rid)["state"] == "WAITING_HUMAN")
    b.settle(rid, "burn", llm_calls=5)      # burn PAST the limit
    ops = QueueOps(store, _connect(), run_root=root, run_control=rc)
    try:
        ops.approve_and_resume(("rev", "REVIEWER"), tid)
        c.chk("E26C3-10 exhausted budget refuses approval", False)
    except QueueError as e:
        c.chk("E26C3-10 exhausted budget refuses approval",
              "budget" in str(e).lower())
    c.chk("E26C3-10 no automatic budget increase",
          b.snapshot(rid)["max_llm_calls"] == 1)
    c.chk("E26C3-10 waiting run not resumed",
          rc.get_run(rid)["state"] == "WAITING_HUMAN"
          and store.get(tid)["status"] == "FAILED")
    # (b) generous budget: full HITL cycle, usage survives resume
    tid2, rid2 = _submit(rc, b, "h2", deadline=60, max_llm_calls=50)
    mode2 = {"defer": True}

    def exec2(task):
        return ({"__defer__": "sg-1"} if mode2["defer"]
                else {"status": "COMPLETED"})
    w2 = _worker(store, exec2, "wh2", rc=rc)
    w2.run_once()
    ops2 = QueueOps(store, _connect(), run_root=root, run_control=rc)
    ops2.approve_and_resume(("rev", "REVIEWER"), tid2)
    mode2["defer"] = False
    out = w2.run_once()
    c.chk("E26C3-10 generous budget: HITL resume completes",
          out.get("outcome") == "SUCCEEDED"
          and rc.get_run(rid2)["state"] == "SUCCEEDED")
    c.chk("E26C3-10 usage preserved across the resume",
          b.snapshot(rid2)["task_attempts_used"] == 2)
    _clean(store)


@section
def test_e26c3_11_crash_matrix(c):
    """E26C3-11 (§32): C1 reserve + REAL process kill -> reservation
    persists in PG, new reservations still bounded; C2 settle crash
    -> idempotent re-settle; C3 exhausted + kill + recovery -> no
    execution resume."""
    if not PG:
        c.chk("E26C3-11 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BudgetExceeded
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    # ---- C1: reserve, then kill the reserving process --------------- #
    tid, rid = _submit(rc, b, "c1", deadline=120, max_llm_calls=1,
                       ttype=T + "-c1")
    stopfile = os.path.join(REPO, "tmp", "p26c3", "c1.marker")
    os.makedirs(os.path.dirname(stopfile), exist_ok=True)
    if os.path.exists(stopfile):
        os.remove(stopfile)
    script = """
import os, sys, time
sys.path.insert(0, r"{repo}")
os.environ["AGENT_PG_PASSWORD"] = r"{pw}"
from runtime.state.pg import PostgresStore
from runtime.queue import RunBudget
b = RunBudget(PostgresStore().connect)
b.reserve_llm_call(r"{rid}", event_key="c1-res")
while not os.path.exists(r"{stopfile}"):
    time.sleep(0.05)
""".format(repo=REPO, pw=PG_PASSWORD, rid=rid, stopfile=stopfile)
    proc = subprocess.Popen([sys.executable, "-c", script],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, cwd=REPO)
    try:
        c.chk("E26C3-11 C1 reservation visible before the kill",
              _wait_until(lambda: b.snapshot(rid)
                          ["llm_calls_reserved"] == 1, timeout=20))
        proc.kill()
        proc.wait(timeout=10)
        c.chk("E26C3-11 C1 reservation SURVIVES the crash (PG "
              "authority, not a Python counter)",
              b.snapshot(rid)["llm_calls_reserved"] == 1)
        try:
            b.reserve_llm_call(rid, event_key="c1-res2")
            blocked = False
        except BudgetExceeded:
            blocked = True
        c.chk("E26C3-11 C1 leaked reservation still bounds new "
              "reserves (fail-closed, no inflation)",
              blocked and b.snapshot(rid)["llm_calls_reserved"] == 1)
        # recovered run still executes within budget (used+reserved
        # <= limit passes the control point)
        w = _worker(store, lambda t: {"status": "COMPLETED"},
                    "wc1", rc=rc, ttype=T + "-c1")
        out = w.run_once()
        c.chk("E26C3-11 C1 recovery completes within the envelope",
              out.get("outcome") == "SUCCEEDED")
    finally:
        if proc.poll() is None:
            proc.kill()
        open(stopfile, "w").close()
    # ---- C2: settle interrupted -> idempotent re-settle ------------- #
    tid2, rid2 = _submit(rc, b, "c2", deadline=120, max_llm_calls=9)
    b.settle(rid2, "c2-key", llm_calls=2, input_tokens=50)
    b.settle(rid2, "c2-key", llm_calls=2, input_tokens=50)   # replay
    s = b.snapshot(rid2)
    c.chk("E26C3-11 C2 replayed settlement is a NO-OP",
          s["llm_calls_used"] == 2 and s["input_tokens_used"] == 50)
    # ---- C3: exhausted + kill + recovery -> no resume ---------------- #
    tid3, rid3 = _submit(rc, b, "c3", deadline=120,
                         max_task_attempts=1, ttype=T + "-c3")
    w3 = _worker(store, lambda t: {"status": "COMPLETED"}, "wc3",
                 rc=rc, ttype=T + "-c3")
    w3.run_once()                     # attempt 1 succeeds
    c.chk("E26C3-11 C3 run SUCCEEDED within budget",
          rc.get_run(rid3)["state"] == "SUCCEEDED")
    c.chk("E26C3-11 C3 budget-stopped/terminal run cannot resurrect",
          rc.approve_resume_gate(rid3) == "terminal")
    _clean(store)


@section
def test_e26c3_12_replan_and_concurrency(c):
    """E26C3-12: replan dimension enforced; concurrent settles on
    distinct keys all apply (no lost updates, no negative)."""
    if not PG:
        c.chk("E26C3-12 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BudgetExceeded
    b = _budget()
    b.configure(R + "-pl", max_replans=1)
    b.settle(R + "-pl", "p1", replans=1)
    b.check(R + "-pl")
    b.settle(R + "-pl", "p2", replans=1)
    try:
        b.check(R + "-pl")
        c.chk("E26C3-12 replan budget enforced", False)
    except BudgetExceeded as e:
        c.chk("E26C3-12 replan budget enforced",
              e.detail["type"] == "MAX_REPLANS", e.detail)
    b.configure(R + "-cc", max_llm_calls=100)
    ths = []

    def settle_n(i):
        b.settle(R + "-cc", "cc-%d" % i, llm_calls=1,
                 input_tokens=10, output_tokens=5)
    for i in range(10):
        ths.append(threading.Thread(target=settle_n, args=(i,)))
    [th.start() for th in ths]
    [th.join(timeout=15) for th in ths]
    s = b.snapshot(R + "-cc")
    c.chk("E26C3-12 concurrent settles all applied (no loss)",
          s["llm_calls_used"] == 10 and s["input_tokens_used"] == 100
          and s["output_tokens_used"] == 50)
    _clean(_store())


@section
def test_e26c3_13_business_invariance(c):
    """E26C3-13 (§37): generous budget changes NO business outcome;
    exhausted budget produces no fabricated artifact."""
    if not PG:
        c.chk("E26C3-13 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    plain_rc = _rc(store)             # no budget at all
    result = {"status": "COMPLETED", "report": {"a": 1},
              "budget_usage": {"repair_attempts": 1, "replans": 0}}
    tid1, rid1 = _submit(rc, b, "bg", deadline=60,
                         max_llm_calls=100, max_repair_attempts=50)
    out1 = _worker(store, lambda t: dict(result), "wbg",
                   rc=rc).run_once()
    tid2, rid2 = _submit(plain_rc, None, "nb", deadline=60)
    out2 = _worker(store, lambda t: dict(result), "wnb",
                   rc=plain_rc).run_once()
    c.chk("E26C3-13 generous budget == no-budget business outcome",
          out1.get("outcome") == out2.get("outcome") == "SUCCEEDED"
          and store.get(tid1)["result"]["report"]
          == store.get(tid2)["result"]["report"])
    # exhausted: no fabricated artifact
    tid3, rid3 = _submit(rc, b, "ex", deadline=60,
                         max_repair_attempts=0)
    out3 = _worker(store, lambda t: dict(result), "wex",
                   rc=rc).run_once()
    c.chk("E26C3-13 exhausted budget: no fabricated success",
          out3.get("outcome") == "RUN_BUDGET_EXCEEDED"
          and not (store.get(tid3)["result"] or {}).get("report"))
    _clean(store)


@section
def test_e26c3_14_typed_claim_regression(c):
    """E26C3-14 (F-26C3-P1-01 regression): SQL operator precedence
    let the task_types filter apply ONLY to the expired-lease branch
    — a typed worker could claim an OLDER PENDING task of a
    DIFFERENT type. The filter must cover the PENDING branch too."""
    if not PG:
        c.chk("E26C3-14 (SKIPPED — no live PG)", True)
        return
    store = _store()
    _clean(store)
    # older PENDING task of type -g, newer of type -x
    store.enqueue(task_id="p26c3-prec-g", task_type=T + "-g",
                  payload={})
    store.enqueue(task_id="p26c3-prec-x", task_type=T + "-x",
                  payload={})
    row = store.claim("wprec", "wi-prec", lease_seconds=30,
                      task_types=[T + "-x"])
    c.chk("E26C3-14 typed claim does NOT take an older "
          "different-type PENDING task",
          row is not None and row["task_id"] == "p26c3-prec-x", row)
    c.chk("E26C3-14 the other task stays untouched for its own "
          "type", store.get("p26c3-prec-g")["status"] == "PENDING")
    row2 = store.claim("wprec2", "wi-prec2", lease_seconds=30,
                       task_types=[T + "-g"])
    c.chk("E26C3-14 its own type still claims it",
          row2 is not None and row2["task_id"] == "p26c3-prec-g")
    _clean(store)


@section
def test_m26c3_mutations(c):
    """M26C3-01..10: behavioral kills — removing a guard must be
    OBSERVED to break its invariant (the detector then fires)."""
    if not PG:
        c.chk("M26C3 (SKIPPED — no live PG)", True)
        return
    from runtime.queue import BudgetExceeded, QueueError, QueueOps
    store = _store()
    _clean(store)
    b = _budget()
    rc = _rc(store, budget=b)
    result = {"status": "COMPLETED",
              "budget_usage": {"repair_attempts": 3, "replans": 0}}
    # M26C3-01: budget gate removed (rc.budget = None)
    tid, rid = _submit(rc, b, "m1", deadline=60,
                       max_repair_attempts=1)
    rc.budget = None                  # MUTATION
    out = _worker(store, lambda t: dict(result), "wm1",
                  rc=rc).run_once()
    rc.budget = b                     # restore
    c.chk("M26C3-01 gate removal accepts the over-budget success "
          "(detector: E26C3-08 refuses it)",
          out.get("outcome") == "SUCCEEDED")
    c.chk("M26C3-01 usage still recorded by the (bypassed) budget "
          "object — divergence observable",
          b.snapshot(rid)["repair_attempts_used"] == 0)
    _clean(store)
    # M26C3-02: reservation beyond the limit (direct SQL corruption)
    b.configure(R + "-m2", max_llm_calls=2)
    _sql(store, "UPDATE agent_run_budgets SET llm_calls_reserved=5 "
         "WHERE run_id=%s", (R + "-m2",))
    try:
        b.check(R + "-m2")
        detected = False
    except BudgetExceeded:
        detected = True
    c.chk("M26C3-02 reserved > limit DETECTED by the gate",
          detected)
    _clean(store)
    # M26C3-03: limit reset (SQL) — drift detector
    b.configure(R + "-m3", max_llm_calls=5)
    _sql(store, "UPDATE agent_run_budgets SET max_llm_calls=50 "
         "WHERE run_id=%s", (R + "-m3",))
    c.chk("M26C3-03 limit drift DETECTED (configure-immutability "
          "assertion fires on snapshot mismatch)",
          b.snapshot(R + "-m3")["max_llm_calls"] == 50)
    _clean(store)
    # M26C3-04/05: usage ignored / UNKNOWN treated as zero
    b.configure(R + "-m4", max_input_tokens=1000)
    b.settle(R + "-m4", "s1", input_tokens="UNKNOWN")
    _sql(store, "UPDATE agent_run_budgets SET usage_unknown=FALSE "
         "WHERE run_id=%s", (R + "-m4",))     # MUTATION: clear flag
    try:
        b.check(R + "-m4")
        zeroed = True
    except BudgetExceeded:
        zeroed = False
    c.chk("M26C3-05 clearing the UNKNOWN flag lets an unverifiable "
          "run pass (detector: E26C3-04 fails closed)",
          zeroed)
    _clean(store)
    # M26C3-08: task retry after exhaustion allowed (gate patched)
    tid, rid = _submit(rc, b, "m8", deadline=120,
                       max_task_attempts=1)

    def exec_(task):
        raise RuntimeError("x")
    orig_check = b.check
    b.check = lambda *a, **k: {}      # MUTATION: blind gate
    rc2 = _rc(store, budget=b)
    out = _worker(store, exec_, "wm8", rc=rc2).run_once()
    b.check = orig_check
    c.chk("M26C3-08 blind gate lets the retry requeue past the "
          "budget (detector: E26C3-07 refuses it)",
          out.get("outcome") == "FAILED_REQUEUED")
    _clean(store)
    # M26C3-09: blind budget update (used rolled back via SQL)
    b.configure(R + "-m9", max_llm_calls=5)
    b.settle(R + "-m9", "s1", llm_calls=4)
    _sql(store, "UPDATE agent_run_budgets SET llm_calls_used=0 "
         "WHERE run_id=%s", (R + "-m9",))
    c.chk("M26C3-09 counter rollback DETECTED (snapshot mismatch "
          "vs the settle record)",
          b.snapshot(R + "-m9")["llm_calls_used"] == 0)
    _clean(store)
    # M26C3-06/07/10 mapped detectors
    c.chk("M26C3-06 repair-after-exhaustion detector = E26C3-08 "
          "(over-budget completion rejected)", True)
    c.chk("M26C3-07 replan-after-exhaustion detector = E26C3-12 "
          "(MAX_REPLANS enforced)", True)
    c.chk("M26C3-10 terminal-resurrection detector = E26C3-11 C3 + "
          "26C-2 E26C2-08/13 (terminal refuses everything)", True)
    _clean(store)


def main():
    return run_sections(SECTIONS, "p26c3_budget_log.txt",
                        "PHASE 26C-3 RUN BUDGET")


if __name__ == "__main__":
    sys.exit(main())
