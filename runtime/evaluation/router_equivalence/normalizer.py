"""B4 normalization (Phase 28.B4) — make two runs of the SAME behavior
comparable by removing only what is provably volatile.

Rules (router-equivalence-gate-design.md §3):
  * ADDITIVE telemetry event types are stripped from BOTH sides:
    intent_classified / qa_answered + the contract-reserved grounding_
    started / grounding_completed / route_selected. (Both sides emit
    intent_classified today; stripping symmetrically keeps the legacy
    event chain the comparison surface.)
  * volatile scalar keys are dropped recursively (timestamps, ids,
    latencies) via a WHITELIST — new payload fields are compared unless
    registered here, so unknown drift surfaces instead of hiding.
"""
from __future__ import annotations

import hashlib
import json
import re

# event types that are additive telemetry, not execution semantics
ADDITIVE_EVENT_TYPES = frozenset({
    "intent_classified", "qa_answered", "grounding_started",
    "grounding_completed", "route_selected",
})

# full ISO datetimes EMBEDDED IN STRING VALUES (e.g. the report's
# "生成时间：<now>" line) are generation stamps, not semantics — and
# their second resolution makes them a race between the two sides.
# Bare dates (2026-09-25) are NOT touched: effective windows are
# semantic content.
_ISO_STAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?")

# scalar keys whose values are volatile across runs (never semantics)
VOLATILE_KEYS = frozenset({
    "event_id", "timestamp", "created_at", "generated_at", "retrieved_at",
    "started_at", "completed_at", "ts", "latency_ms", "duration_ms",
    "run_id", "case_id", "chat_id", "request_id", "correlation_id",
    "artifact_id", "eval_id", "response_id", "message_id", "usage",
    "answer_len", "reason_codes", "trace_id",
})


def normalize(value):
    """Recursive volatile-strip. Dicts: drop VOLATILE_KEYS; lists: keep
    order (execution order is semantics); strings: scrub embedded ISO
    generation stamps; everything else verbatim."""
    if isinstance(value, dict):
        return {k: normalize(v) for k, v in sorted(value.items())
                if k not in VOLATILE_KEYS}
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, str):
        return _ISO_STAMP.sub("TS", value)
    return value


def normalize_events(events: list) -> list:
    out = []
    for e in events:
        if not isinstance(e, dict):
            continue
        if e.get("event_type") in ADDITIVE_EVENT_TYPES:
            continue
        out.append(normalize(e))
    return out


def stable_hash(normalized) -> str:
    return hashlib.sha256(json.dumps(
        normalized, ensure_ascii=False, sort_keys=True,
        separators=(",", ":")).encode("utf-8")).hexdigest()
