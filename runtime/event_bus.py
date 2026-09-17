"""Event Bus — non-blocking publish/subscribe for RuntimeEvents (Web UI Phase 1).

Contract with the runtime (the design principle "observability must be non-blocking"):

  * ``publish()`` NEVER raises and NEVER blocks — every internal failure is swallowed
    (stderr note only). The bus cannot become a single point of failure for the agent.
  * A run with zero subscribers works identically (events still land in history, the
    orchestrator does not care). The Web UI can be closed; the agent still runs.
  * Subscribers receive events through bounded queues: a slow consumer drops events
    instead of blocking the publisher, and can resync from history via ``after_event_id``
    (every event keeps a monotonic per-run ``event_id``).
  * History is retained per run (bounded) so page refresh / replay / resume works after
    the fact, and so SSE reconnection never re-sends the whole stream.

This is deliberately NOT a message broker: one process, in-memory, thread-safe.
"""
from __future__ import annotations

import queue
import sys
import threading
from typing import Optional

# a run is bounded (tens of events); the cap only exists to bound memory if a
# pathological run (or a bug) ever produced an unbounded number of records.
MAX_HISTORY_PER_RUN = 10_000

# per-subscriber queue bound; beyond it events are dropped for THAT subscriber
# (flagged ``dropped``), retrievable from history on resync.
SUBSCRIBER_QUEUE_SIZE = 1024

# sentinel pushed to every subscriber queue when the run is finished (public: the SSE
# layer compares received items against it)
CLOSED = object()

RUN_TERMINAL_TYPES = ("run_completed", "run_failed")


class Subscription:
    """One live observer of one run."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.queue: "queue.Queue" = queue.Queue(maxsize=SUBSCRIBER_QUEUE_SIZE)
        self.dropped = 0          # events dropped because this subscriber was slow
        self.closed = False       # set on unsubscribe or on run termination

    def get(self, timeout: Optional[float] = None):
        """Next event dict, the CLOSED sentinel, or raise queue.Empty on timeout."""
        return self.queue.get(timeout=timeout)


class EventBus:
    def __init__(self):
        self._lock = threading.Lock()
        self._history: dict = {}       # run_id -> [event dict, ...]
        self._subs: dict = {}          # run_id -> [Subscription, ...]
        self._done: dict = {}          # run_id -> terminal event dict (or True)
        self._publish_count = 0        # stats only

    # ------------------------------------------------------------------ #
    # publish side (called from the run's worker thread)
    # ------------------------------------------------------------------ #
    def publish(self, run_id: str, event: dict) -> None:
        """Append to history and fan out to subscribers. Never raises, never blocks."""
        try:
            self._publish_count += 1
            with self._lock:
                hist = self._history.setdefault(run_id, [])
                if len(hist) < MAX_HISTORY_PER_RUN:
                    hist.append(event)
                # prune dead subscriptions lazily; a disconnected observer must not
                # cost the runtime anything beyond this list comprehension
                subs = [s for s in self._subs.get(run_id, ()) if not s.closed]
                if subs or run_id in self._subs:
                    self._subs[run_id] = subs
                terminal = event.get("event_type") in RUN_TERMINAL_TYPES
                if terminal:
                    self._done[run_id] = event
            for sub in subs:
                try:
                    sub.queue.put_nowait(event)
                except Exception:  # queue.Full or a broken queue: drop for THIS subscriber
                    sub.dropped += 1
            if terminal:
                self._close_subscribers(run_id)
        except Exception as e:  # noqa: BLE001 — the bus must never break the runtime
            print("[event_bus] publish failed (ignored): %r" % e, file=sys.stderr)

    def publish_transient(self, run_id: str, event: dict) -> None:
        """Fan out to LIVE subscribers WITHOUT appending to history.

        Used for high-frequency, replay-irrelevant payloads (e.g. streaming
        text deltas): they appear in open SSE streams, never in
        GET /events replay, resume cursors or durable observability records."""
        try:
            with self._lock:
                subs = [s for s in self._subs.get(run_id, ()) if not s.closed]
            for sub in subs:
                try:
                    sub.queue.put_nowait(event)
                except Exception:  # noqa: BLE001 — drop for THIS subscriber only
                    sub.dropped += 1
        except Exception as e:  # noqa: BLE001 — the bus must never break the runtime
            print("[event_bus] publish_transient failed (ignored): %r" % e, file=sys.stderr)

    def finish(self, run_id: str) -> None:
        """Mark the run finished even when no terminal event was published (defensive)."""
        try:
            with self._lock:
                self._done.setdefault(run_id, True)
            self._close_subscribers(run_id)
        except Exception as e:  # noqa: BLE001
            print("[event_bus] finish failed (ignored): %r" % e, file=sys.stderr)

    def _close_subscribers(self, run_id: str) -> None:
        with self._lock:
            subs = [s for s in self._subs.get(run_id, ()) if not s.closed]
        for sub in subs:
            try:
                sub.queue.put_nowait(CLOSED)
            except Exception:  # noqa: BLE001 — full queue: terminal event is in history
                pass
            sub.closed = True

    # ------------------------------------------------------------------ #
    # subscribe side (called from SSE handlers / test observers)
    # ------------------------------------------------------------------ #
    def subscribe(self, run_id: str) -> Subscription:
        with self._lock:
            sub = Subscription(run_id)
            self._subs.setdefault(run_id, []).append(sub)
            return sub

    @staticmethod
    def unsubscribe(sub: Subscription) -> None:
        """Idempotent. A disconnecting subscriber never affects the run."""
        sub.closed = True

    # ------------------------------------------------------------------ #
    # history / replay
    # ------------------------------------------------------------------ #
    def events_for(self, run_id: str, after_event_id: Optional[str] = None) -> list:
        """All events of a run, optionally strictly after ``after_event_id``."""
        with self._lock:
            hist = list(self._history.get(run_id, ()))
        if not after_event_id:
            return hist
        try:
            idx = next(i for i, e in enumerate(hist) if e.get("event_id") == after_event_id)
            return hist[idx + 1:]
        except StopIteration:
            return []  # unknown cursor: nothing new (never re-send everything)

    def is_run_done(self, run_id: str) -> bool:
        with self._lock:
            return run_id in self._done

    def event_count(self, run_id: str) -> int:
        with self._lock:
            return len(self._history.get(run_id, ()))

    def stats(self) -> dict:
        with self._lock:
            return {
                "runs": len(self._history),
                "published_total": self._publish_count,
                "open_subscriptions": sum(len(v) for v in self._subs.values()),
            }

    # ------------------------------------------------------------------ #
    # test / ops helpers
    # ------------------------------------------------------------------ #
    def clear_run(self, run_id: str) -> None:
        with self._lock:
            self._history.pop(run_id, None)
            self._subs.pop(run_id, None)
            self._done.pop(run_id, None)

    def reset(self) -> None:
        with self._lock:
            self._history.clear()
            self._subs.clear()
            self._done.clear()
            self._publish_count = 0


# module-level default bus: one process, one bus. The runtime never imports this
# module directly — only observers (server / tests) do.
default_bus = EventBus()
