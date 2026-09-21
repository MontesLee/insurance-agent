"""runtime.obs — the Phase 25 observability core.

context   → unified trace ids (request/correlation/trace/project/
            case/task/skill/tool), contextvar-scoped
log       → JSONL structured logging with redaction by construction
errors    → deterministic error taxonomy (retryable / safe_to_retry /
            operator_action / user_visible)
metrics   → counters + latency histograms, UNKNOWN-honest
health    → liveness (process) vs readiness (workload, mode-aware)
diagnostics → read-only, secret-free runtime snapshot

The whole package is OBSERVATION-ONLY: it must never change business
results (verified by test_p25_business_invariance).
"""
from .context import (TraceContext, attach_context, current, span,
                      start_request, use_context)
from .log import JsonlLogger, default_logger, log, set_default_logger
from .errors import (ALL_CLASSES, ClassifiedError, classify,
                     governance_denial, abstention)
from .metrics import UNKNOWN, default_metrics, set_default_metrics
from .health import liveness, readiness
from .diagnostics import snapshot as diagnostics_snapshot

__all__ = [
    "TraceContext", "attach_context", "current", "span", "start_request",
    "use_context", "JsonlLogger", "default_logger", "log",
    "set_default_logger", "ALL_CLASSES", "ClassifiedError", "classify",
    "governance_denial", "abstention", "UNKNOWN", "default_metrics",
    "set_default_metrics", "liveness", "readiness",
    "diagnostics_snapshot",
]
