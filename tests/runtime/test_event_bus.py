"""Web UI Phase 1 — Event Bus tests (runtime/event_bus.py).

Asserts the non-blocking contract:
  * publish/subscribe delivery, multiple subscribers, ordering;
  * unsubscribed / disconnected / slow / broken subscribers never affect the publisher;
  * bus-internal failures are swallowed (the bus is never a single point of failure);
  * history replay with after_event_id (the SSE resume primitive);
  * run termination wakes every subscriber (stream close).

Dual-mode: `pytest tests/runtime -q` or `python tests/runtime/test_event_bus.py`.
Exit 0 = all checks pass.
"""
from __future__ import annotations

import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

from runtime import event_bus as eb  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def ev(i, etype="stage_started"):
    return {"event_id": "evt_%06d" % i, "run_id": "r1", "event_type": etype,
            "timestamp": "2026-09-15T18:20:01Z", "data": {}}


@section
def test_publish_subscribe_delivery(c: Checks):
    bus = eb.EventBus()
    sub = bus.subscribe("r1")
    bus.publish("r1", ev(1))
    bus.publish("r1", ev(2))
    c.chk("publish->subscribe: events delivered",
          sub.get(timeout=1)["event_id"] == "evt_000001"
          and sub.get(timeout=1)["event_id"] == "evt_000002")

    s2, s3 = bus.subscribe("r1"), bus.subscribe("r1")
    bus.publish("r1", ev(3))
    got = [s2.get(timeout=1)["event_id"], s3.get(timeout=1)["event_id"]]
    c.chk("multiple subscribers each receive the event",
          got == ["evt_000003", "evt_000003"], got)

    eb.EventBus.unsubscribe(s2)
    bus.publish("r1", ev(4))
    try:
        s2.get(timeout=0.2)
        got_after_unsub = True
    except Exception:  # queue.Empty
        got_after_unsub = False
    c.chk("unsubscribed subscriber receives nothing", not got_after_unsub)
    c.chk("other subscribers unaffected by the disconnect",
          s3.get(timeout=1)["event_id"] == "evt_000004")


@section
def test_ordering_preserved(c: Checks):
    bus = eb.EventBus()
    s = bus.subscribe("ro")
    for i in range(1, 101):
        bus.publish("ro", ev(i))
    ids = [s.get(timeout=1)["event_id"] for _ in range(100)]
    c.chk("ordering preserved under 100 rapid publishes",
          ids == ["evt_%06d" % i for i in range(1, 101)])


@section
def test_slow_or_broken_subscriber_never_blocks_publisher(c: Checks):
    bus = eb.EventBus()
    slow = bus.subscribe("rslow")
    for _ in range(eb.SUBSCRIBER_QUEUE_SIZE):   # fill the queue completely
        bus.publish("rslow", ev(1))
    t0 = time.perf_counter()
    bus.publish("rslow", ev(2))                 # queue full -> must drop, not block
    dt = time.perf_counter() - t0
    c.chk("full subscriber queue does not block publish", dt < 0.5, "%.3fs" % dt)
    c.chk("overflow counted as dropped for that subscriber", slow.dropped >= 1, slow.dropped)
    c.chk("dropped event still recorded in history",
          any(e["event_id"] == "evt_000002" for e in bus.events_for("rslow")))

    class _BrokenQueue:
        def put_nowait(self, item):
            raise RuntimeError("subscriber exploded")

    bus4 = eb.EventBus()
    broken = bus4.subscribe("rb")
    broken.queue = _BrokenQueue()
    try:
        bus4.publish("rb", ev(1))
        ok, err = True, None
    except Exception as e:  # noqa: BLE001
        ok, err = False, e
    c.chk("a raising subscriber never crashes publish", ok, err)
    c.chk("event still lands in history despite broken subscriber",
          bus4.events_for("rb") == [ev(1)])


@section
def test_bus_internal_failure_swallowed(c: Checks):
    class _BrokenHist(dict):
        def setdefault(self, *a, **k):
            raise RuntimeError("history exploded")

    bus5 = eb.EventBus()
    bus5._history = _BrokenHist()
    try:
        bus5.publish("rbroken", ev(1))
        ok, err = True, None
    except Exception as e:  # noqa: BLE001
        ok, err = False, e
    c.chk("bus-internal failure swallowed by publish", ok, err)

    bus6 = eb.EventBus()
    bus6.publish("ronly", ev(1))
    c.chk("run with zero subscribers still records history",
          bus6.events_for("ronly") == [ev(1)])
    c.chk("run not marked done", not bus6.is_run_done("ronly"))


@section
def test_history_replay_cursor(c: Checks):
    bus7 = eb.EventBus()
    for i in range(1, 6):
        bus7.publish("rr", ev(i))
    c.chk("events_for returns full history", len(bus7.events_for("rr")) == 5)
    tail = bus7.events_for("rr", after_event_id="evt_000002")
    c.chk("after_event_id resumes strictly after the cursor",
          [e["event_id"] for e in tail] == ["evt_000003", "evt_000004", "evt_000005"], tail)
    c.chk("unknown cursor returns nothing (never re-sends everything)",
          bus7.events_for("rr", after_event_id="evt_999999") == [])


@section
def test_terminal_event_closes_streams(c: Checks):
    bus8 = eb.EventBus()
    sa, sb_ = bus8.subscribe("rt"), bus8.subscribe("rt")
    bus8.publish("rt", ev(1))
    bus8.publish("rt", ev(2, "run_completed"))
    got_a = [sa.get(timeout=1), sa.get(timeout=1)]
    got_b = [sb_.get(timeout=1), sb_.get(timeout=1)]
    c.chk("terminal event delivered to all subscribers",
          got_a[-1]["event_type"] == "run_completed"
          and got_b[-1]["event_type"] == "run_completed")
    c.chk("subscribers receive the CLOSED sentinel after the terminal event",
          sa.get(timeout=1) is eb.CLOSED and sb_.get(timeout=1) is eb.CLOSED)
    c.chk("run marked done", bus8.is_run_done("rt"))

    bus9 = eb.EventBus()
    sc = bus9.subscribe("rf")
    bus9.finish("rf")
    c.chk("finish() wakes subscribers even without a terminal event",
          sc.get(timeout=1) is eb.CLOSED and sc.closed)


@section
def test_concurrent_publishers(c: Checks):
    bus10 = eb.EventBus()
    sd = bus10.subscribe("rc")

    def _worker(n):
        for i in range(50):
            bus10.publish("rc", ev(n * 1000 + i))

    threads = [threading.Thread(target=_worker, args=(k,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    received = []
    while True:
        try:
            received.append(sd.get(timeout=0.2)["event_id"])
        except Exception:  # queue.Empty
            break
    hist_ids = [e["event_id"] for e in bus10.events_for("rc")]
    c.chk("concurrent publishers: history has every event exactly once",
          len(hist_ids) == len(set(hist_ids)) == 200, len(hist_ids))
    c.chk("concurrent publishers: subscriber got every event (no loss)",
          sorted(received) == sorted(hist_ids), (len(received), len(hist_ids)))

    st = bus10.stats()
    c.chk("stats reports runs and published totals",
          st["runs"] == 1 and st["published_total"] == 200, st)


def main():
    return run_sections(SECTIONS, "webui_test_event_bus_log.txt", "RUNTIME EVENT BUS")


if __name__ == "__main__":
    sys.exit(main())
