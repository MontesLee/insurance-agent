"""Production metrics abstraction — Phase 25D/25E.

In-process counters + latency histograms behind one facade. NO values
are fabricated: anything unmeasured is recorded as the string
"UNKNOWN" (HG25-09/10 — e.g. LLM token counts when the provider does
not report usage stay UNKNOWN, never 0).

Percentiles are computed from the actual observations (min / median /
p95 / max — never an average alone). Persistence is a JSON snapshot
file the operator pulls (Phase 25 deliberately adds NO PostgreSQL
schema — §15).

Observation-only: recording a metric cannot change business results.
"""
from __future__ import annotations

import json
import os
import threading
import time
from typing import Optional

UNKNOWN = "UNKNOWN"

_lock = threading.RLock()   # reentrant: snapshot() calls stats() while held


def _pct(sorted_xs: list, p: float) -> float:
    if not sorted_xs:
        return UNKNOWN
    k = max(0, min(len(sorted_xs) - 1,
                   int(round(p / 100 * (len(sorted_xs) - 1)))))
    return round(sorted_xs[k], 3)


class Latency:
    """Ring-buffered observations (bounded memory: last 2048)."""

    __slots__ = ("_xs", "_cap")

    def __init__(self, cap: int = 2048):
        self._xs = []
        self._cap = cap

    def observe(self, ms: float) -> None:
        try:
            v = float(ms)
        except (TypeError, ValueError):
            return                       # unmeasurable stays unrecorded
        with _lock:
            if len(self._xs) >= self._cap:
                self._xs = self._xs[-self._cap // 2:]
            self._xs.append(v)

    def stats(self) -> dict:
        with _lock:
            xs = sorted(self._xs)
        if not xs:
            return {"count": 0, "min": UNKNOWN, "median": UNKNOWN,
                    "p95": UNKNOWN, "max": UNKNOWN}
        return {"count": len(xs), "min": _pct(xs, 0),
                "median": _pct(xs, 50), "p95": _pct(xs, 95),
                "max": _pct(xs, 100)}


class MetricsRegistry:
    """The metric vocabulary of Phase 25 §7/§8. Counters are
    name-open (new names must pass declare() first — no typo-born
    phantom metrics); latencies are declared up front."""

    COUNTERS = (
        # requests
        "requests_total", "requests_success_total",
        "requests_failed_total", "requests_cancelled_total",
        # tasks
        "tasks_total", "tasks_success_total", "tasks_failed_total",
        "tasks_retried_total", "tasks_aborted_total",
        # skills
        "skill_calls_total", "skill_success_total",
        "skill_failure_total",
        # knowledge
        "knowledge_search_total", "knowledge_search_success_total",
        "knowledge_search_failure_total",
        "knowledge_abstention_total", "knowledge_governance_denied_total",
        # llm
        "llm_calls_total", "llm_success_total", "llm_failure_total",
        "llm_timeout_total", "llm_rate_limit_total",
        # persistence
        "persistence_reads_total", "persistence_writes_total",
        "persistence_failures_total", "transaction_failures_total",
    )

    LATENCIES = ("request_duration", "task_duration", "skill_duration",
                 "knowledge_duration", "llm_duration",
                 "persistence_duration")

    def __init__(self):
        self._counters = {n: 0 for n in self.COUNTERS}
        # label dims keep the vocabulary small: per-skill counters live
        # under skill.* keyed by skill name
        self._labeled: dict = {}
        self._latencies = {n: Latency() for n in self.LATENCIES}
        self._tokens: dict = {}          # provider -> total or UNKNOWN
        self._start = time.time()

    # ---- counters ---------------------------------------------------- #
    def inc(self, name: str, by: int = 1, **labels) -> None:
        if name not in self._counters:
            # declared vocabulary only — unknown names are a BUG, not a
            # silent metric; record it visibly instead of inventing it
            with _lock:
                self._counters.setdefault("_unknown_names_total", 0)
                self._counters["_unknown_names_total"] += 1
                self._counters.setdefault("_unknown:%s" % name, 0)
                self._counters["_unknown:%s" % name] += 1
            return
        if labels:
            key = tuple(sorted(labels.items()))
            with _lock:
                self._labeled.setdefault((name, key), 0)
                self._labeled[(name, key)] += by
        else:
            with _lock:
                self._counters[name] += by

    # ---- latencies ----------------------------------------------------- #
    def observe(self, name: str, ms: float) -> None:
        lat = self._latencies.get(name)
        if lat is None:
            return
        lat.observe(ms)

    def timeit(self, name: str):
        """Context manager: t = metrics.timeit("skill_duration");
        with t: ... — records wall ms on exit."""
        return _Timer(self, name)

    # ---- honest UNKNOWNs ------------------------------------------------ #
    def record_tokens(self, provider: str, usage) -> None:
        """LLM token accounting: a provider that reports no usage is
        UNKNOWN forever — never coerced to 0 (HG25-10)."""
        total = None
        if isinstance(usage, dict):
            v = usage.get("total_tokens")
            if isinstance(v, (int, float)) and v >= 0:
                total = v
        elif isinstance(usage, (int, float)) and usage >= 0:
            total = usage
        with _lock:
            cur = self._tokens.get(provider)
            if total is None or cur == UNKNOWN:
                # a missed measurement makes the RUNNING TOTAL unknowable
                self._tokens[provider] = UNKNOWN
            elif isinstance(cur, (int, float)):
                self._tokens[provider] = cur + total
            else:
                self._tokens[provider] = total

    # ---- output ---------------------------------------------------------- #
    def snapshot(self) -> dict:
        with _lock:
            counters = dict(self._counters)
            labeled = {("%s{%s}" % (n, ",".join(
                "%s=%s" % kv for kv in k))): v
                for (n, k), v in sorted(self._labeled.items())}
            lat = {n: self._latencies[n].stats() for n in self.LATENCIES}
            tokens = dict(self._tokens)
        return {
            "uptime_s": round(time.time() - self._start, 1),
            "counters": counters,
            "labeled": labeled,
            "latency_ms": lat,
            "llm_tokens": tokens,
        }

    def dump(self, path: str) -> dict:
        snap = self.snapshot()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False, indent=1)
        return snap


class _Timer:
    def __init__(self, reg: MetricsRegistry, name: str):
        self._reg = reg
        self._name = name
        self._t0 = None

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._t0 is not None:
            self._reg.observe(self._name,
                              (time.perf_counter() - self._t0) * 1000)
        return False


_default: Optional[MetricsRegistry] = None


def default_metrics() -> MetricsRegistry:
    global _default
    if _default is None:
        _default = MetricsRegistry()
    return _default


def set_default_metrics(reg: Optional[MetricsRegistry]) -> None:
    global _default
    _default = reg
