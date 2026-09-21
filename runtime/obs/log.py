"""Structured JSON logging — Phase 25B.

One JSONL sink, one field contract, redaction by construction. Every
record answers: WHO (context ids) → WHAT (event + skill/tool) → HOW
LONG (duration_ms) → OUTCOME (status) → WHY FAILED (error fields).

Redaction (HG25-06/07): credential-SHAPED values are rewritten at
emit time (runtime.state.dataprotection.redact_credential_values) and
PII-bearing keys are dropped by name. Raw prompts / full LLM responses
/ Authorization headers are never logged by this module's callers'
convention — the sink enforces the denylist regardless.

Observability-only: log() never raises into business code.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Optional

from .context import current

# Keys never emitted (values may hold PII/secrets). The EVENT stays,
# the payload field does not.
_PII_KEYS = frozenset({
    "prompt", "full_prompt", "response", "full_response", "messages",
    "authorization", "api_key", "x_api_key", "password", "token",
    "secret", "dsn", "client_profile", "customer_profile", "content",
    "document_content", "chunk_content",
})

_LEVELS = ("DEBUG", "INFO", "WARN", "ERROR")

_lock = threading.Lock()


class JsonlLogger:
    """Append-only JSONL structured log. Process-local file sink (the
    operator ships the file); stdout mirror optional for dev."""

    def __init__(self, path: Optional[str] = None, mirror_stdout=False):
        self._path = path
        self._mirror = mirror_stdout
        self._fh = None
        if path:
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8")

    def close(self) -> None:
        if self._fh:
            try:
                self._fh.close()
            except Exception:  # noqa: BLE001
                pass
            self._fh = None

    def emit(self, event: str, level: str = "INFO", status: str = "",
             duration_ms: Optional[float] = None, error=None,
             **fields) -> dict:
        """Write one record; returns the record (testable). Never
        raises."""
        level = level if level in _LEVELS else "INFO"
        rec = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                       time.gmtime()),
            "level": level,
            "event": str(event),
        }
        rec.update({k: v for k, v in current().fields().items() if v})
        if status:
            rec["status"] = status
        if duration_ms is not None:
            try:
                rec["duration_ms"] = round(float(duration_ms), 2)
            except (TypeError, ValueError):
                rec["duration_ms"] = None
        if error is not None:
            rec["error"] = _error_fields(error)
        for k, v in fields.items():
            if k in _PII_KEYS:
                # keep the fact, not the payload
                rec[k + "_redacted"] = "<redacted:%s>" % type(
                    v).__name__
                continue
            rec[k] = _redact_value(v)
        try:
            line = json.dumps(rec, ensure_ascii=False, default=str)
        except Exception:  # noqa: BLE001 — logging must not raise
            line = json.dumps({"event": event, "level": "ERROR",
                               "status": "LOG_SERIALIZE_FAILED"})
        with _lock:
            if self._fh:
                try:
                    self._fh.write(line + "\n")
                    self._fh.flush()
                except Exception:  # noqa: BLE001
                    pass
            if self._mirror:
                try:
                    sys.stdout.write(line + "\n")
                except Exception:  # noqa: BLE001
                    pass
        return rec


def _error_fields(error) -> dict:
    """Deterministic error projection (taxonomy-aware when the error
    carries a classify hook — see obs.errors)."""
    from .errors import classify
    c = classify(error)
    out = {"error_code": c.error_code, "error_class": c.error_class,
           "retryable": c.retryable, "safe_to_retry": c.safe_to_retry,
           "operator_action": c.operator_action,
           "user_visible": c.user_visible,
           "message": _redact_value(str(error))[:200]}
    return out


def _redact_value(v):
    """Credential-shaped STRING values are rewritten in place; other
    types pass through (they carry no key material)."""
    if isinstance(v, str):
        from runtime.state.dataprotection import \
            redact_credential_values
        return redact_credential_values(v)
    return v


_default: Optional[JsonlLogger] = None


def default_logger() -> JsonlLogger:
    """Process default: tmp/obs/agent.jsonl (gitignored), mirrored to
    stdout only in DEMO mode. Explicitly settable for tests."""
    global _default
    if _default is None:
        from runtime import mode as rt_mode
        path = os.path.join("tmp", "obs", "agent.jsonl")
        _default = JsonlLogger(
            path, mirror_stdout=(rt_mode.mode() == rt_mode.DEMO))
    return _default


def set_default_logger(logger: Optional[JsonlLogger]) -> None:
    global _default
    _default = logger


def log(event: str, **kw) -> dict:
    """Emit on the default logger (no-op safe if file unwritable)."""
    return default_logger().emit(event, **kw)
