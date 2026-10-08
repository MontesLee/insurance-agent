"""Shadow-mode recorder for the Intent Layer + Router (Phase 28.A-1 + 28.A-2).

Shadow semantics: classify + route are RECORDED ONLY. The real execution
path (the existing chat agent) is untouched — every record carries
actual_execution="existing-agent" until the router goes authoritative
in a later, separately authorized phase.

Phase 28.A-2 additions: each record carries the classification latency,
the deterministic RESOLVER outcome (derived from IntentResult fields —
the frozen schema itself is never extended), the rule reason codes
(metadata only), and — after the post-run annotate — a deterministic
disagreement typing `mismatch_type` (see mismatch_types()).

Records are local diagnostics under tmp/intent-shadow/*.jsonl — they are
NOT the event system (that is runtime/events.py, unchanged contract) and
NOT a second run store. Privacy: records carry a message hash + length +
a 24-char head for local debugging; the full message never enters the
event bus (events are metadata only, runtime/events.py:9-12), and LLM
candidate explanations are never stored either.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Iterator, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
DEFAULT_DIR = os.path.join(REPO_ROOT, "tmp", "intent-shadow")

# legacy chat-agent intent enum (runtime/agent/schemas.py:20-25) -> v1
# intent. Canonical home (report.py re-exports): used to compare the old
# prompt-owned classification against the shadow classification.
LEGACY_TO_INTENT = {
    "GENERAL_KNOWLEDGE": "insurance_qa",
    "GENERAL_GUIDANCE": "insurance_qa",
    "PRODUCT_LOOKUP": "product_qa",
    "CLIENT_ADVISORY": "insurance_plan",
    "TASK_EXECUTION": "modify_existing_plan",
}

MISMATCH_TYPES = ("intent_difference", "confidence_difference",
                  "missing_context")

_lock = threading.Lock()


def _shadow_dir() -> str:
    return os.environ.get("INSURANCE_AGENT_INTENT_SHADOW_DIR", DEFAULT_DIR)


def _shadow_file() -> str:
    return os.path.join(_shadow_dir(), "shadow.jsonl")


def resolver_outcome(intent_result: dict) -> str:
    """Which deterministic branch decided (derived; schema untouched).

    rule_fast_path      rules matched, routed as-is
    rule_clarify        rules matched but forced clarification (modify w/o
                        active case — ADR-019 M1)
    llm_accepted        no rule hit; LLM proposal accepted by the resolver
    llm_floor_clarify   LLM proposal for a high-risk intent below the HD-1
                        floor -> clarification, never auto-route
    fail_closed_unknown nothing matched / candidate unusable -> unknown
    schema_gate_degrade internal result failed the final schema gate
    """
    reasons = list(intent_result.get("reason_codes") or [])
    if "schema_validation_failed" in reasons:
        return "schema_gate_degrade"
    if intent_result.get("intent_id") == "unknown_insurance_intent":
        return "fail_closed_unknown"
    if intent_result.get("confidence_source") == "llm":
        return ("llm_floor_clarify"
                if intent_result.get("clarification_required")
                else "llm_accepted")
    if intent_result.get("clarification_required"):
        return "rule_clarify"
    return "rule_fast_path"


def _calibration_floor() -> float:
    """The single externalized floor (config/intent-rules.yaml thresholds)."""
    try:
        from runtime.intent.classifier import load_rules
        return float(load_rules().get("thresholds", {})
                     .get("high_risk_llm_min_confidence", 0.75))
    except Exception:  # noqa: BLE001 — rules unreadable -> schema default
        return 0.75


def mismatch_types(rec: dict, floor: Optional[float] = None) -> list:
    """Deterministic disagreement typing for ONE annotated record.

    Vocabulary (28.A-2 spec): intent_difference / confidence_difference /
    missing_context. Empty list = agreement, or NOT COMPARABLE (no legacy
    classification was captured for the run — an annotate coverage gap,
    reported separately, never counted as agreement).

      intent_difference   legacy (mapped to v1) differs from the shadow
                          classification, or maps to nothing
      missing_context     the shadow result forced clarification because the
                          active-case context was absent (M1)
      confidence_difference same intent on both sides, but the shadow
                          confidence comes from an LLM proposal below the
                          externalized floor (the legacy path executed where
                          the resolver would have clarified)
    """
    raw = rec.get("legacy_intent")
    if raw is None:
        return []
    legacy = LEGACY_TO_INTENT.get(raw)
    predicted = rec.get("predicted_intent")
    out = []
    if legacy is None or legacy != predicted:
        out.append("intent_difference")
    reasons = rec.get("reason_codes") or []
    if rec.get("clarification_required") and (
            "context:active_case_missing" in reasons or
            (predicted == "modify_existing_plan")):
        out.append("missing_context")
    f = floor if floor is not None else _calibration_floor()
    if (legacy is not None and legacy == predicted
            and rec.get("confidence_source") == "llm"
            and isinstance(rec.get("confidence"), (int, float))
            and rec["confidence"] < f):
        out.append("confidence_difference")
    return out


def record(run_id: str, chat_id: Optional[str], text: str,
           intent_result: dict, route: dict,
           actual_execution: str = "existing-agent",
           latency_ms: Optional[int] = None,
           slice_decision: Optional[dict] = None,
           file: Optional[str] = None) -> dict:
    """Append one shadow record; returns the record (for tests/reports).

    latency_ms: total classify+route wall time (caller-measured). Metadata
    only — reason codes are rule ids, never message content.
    slice_decision (28.B4 gray observation): {"slice": knowledge-qa|
    product-qa, "fired": bool, "reason": flag_off|fired|
    clarification_required|not_registry_lookup} — WHY the production
    slice did or did not take this turn (metadata; run-level, no PII).
    """
    rec = {
        "ts": _now_iso(),
        "run_id": run_id,
        "chat_id": chat_id,
        "message_sha1": hashlib.sha1((text or "").encode("utf-8")).hexdigest(),
        "message_len": len(text or ""),
        "message_head": (text or "")[:24],
        "predicted_intent": intent_result["intent_id"],
        "predicted_agent": route["agent_id"],
        "decision_source": route["decision_source"],
        "confidence": intent_result["confidence"],
        "confidence_source": intent_result["confidence_source"],
        "clarification_required": intent_result["clarification_required"],
        "reason_codes": list(intent_result.get("reason_codes") or []),
        "resolver": resolver_outcome(intent_result),
        "latency_ms": latency_ms,
        "actual_execution": actual_execution,
        "slice_decision": slice_decision,
        "legacy_intent": None,
        "legacy_action": None,
        "mismatch_type": None,
    }
    path = file or _shadow_file()
    with _lock:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def annotate(run_id: str, file: Optional[str] = None, **fields) -> bool:
    """Fill post-run facts into the LAST record of this run (legacy intent
    from the agent's own decision, final action) and type the disagreement.

    Recording only — annotate can never change execution; it writes local
    diagnostics. Returns True if a record was updated.
    """
    path = file or _shadow_file()
    with _lock:
        if not os.path.exists(path):
            return False
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
        updated = False
        for i in range(len(lines) - 1, -1, -1):
            try:
                rec = json.loads(lines[i])
            except json.JSONDecodeError:
                continue
            if rec.get("run_id") == run_id:
                rec.update({k: v for k, v in fields.items() if v is not None})
                rec["mismatch_type"] = mismatch_types(rec)
                lines[i] = json.dumps(rec, ensure_ascii=False) + "\n"
                updated = True
                break
        if updated:
            with open(path, "w", encoding="utf-8") as fh:
                fh.writelines(lines)
        return updated


def iter_records(file: Optional[str] = None) -> Iterator[dict]:
    path = file or _shadow_file()
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
