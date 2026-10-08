"""Consumer content hygiene (Phase 28.K.25-S1).

K.25-RV found internal artifact IDs (ART-009) reaching consumer-visible
text: planning tool results carry ART-xxx into the LLM context, and the
model echoes them in generated answers (a K.7-era content-level path).

Two layers, one shared pattern set:

  * SOURCE hygiene — the LLM-facing tool-result projection drops
    internal identifiers entirely (the model never sees them, so it
    cannot repeat them). Internal runtime state (tool_history, events,
    artifact registry) keeps the real IDs untouched.
  * DELIVERY hygiene — a pure sanitizer applied to text as it crosses
    the consumer boundary (finish/ask messages, K.22 validated chunks).
    Replacement wording stays natural; parenthetical wrappers around a
    bare ID collapse to nothing so sentences do not become malformed.

Patterns are DELIBERATELY narrow (STOP-4/STOP-5 guard): an ASCII
ART-/EVAL- token needs a word boundary + hyphen + suffix (never matches
SMART-1 style prose or product codes like P001); run_/chat_/evt_/appr_
identifiers need an 8+ hex/alnum tail. Amounts, dates, clause numbers
and normal abbrevizations are structurally out of scope.
"""
from __future__ import annotations

import re

# narrow, evidence-based internal identifier shapes (see artifact_registry
# "ART-%03d", events evt_ prefix, run/chat hex16 ids)
_ART_EVAL = re.compile(r"(\(?[（(]\s*)?\b(ART|EVAL)-[0-9A-Za-z]{1,12}\b\.?(\s*[)）])?", re.IGNORECASE)
_RUNLIKE = re.compile(r"\b(?:run|chat|evt|appr|agentcase)_[0-9a-zA-Z]{8,}\b")


def _art_sub(m: re.Match) -> str:
    _open, body, _close = m.group(1), m.group(2), m.group(3)
    # a parenthetical wrapper around a bare ID collapses entirely;
    # a bare ID becomes natural wording
    if _open or _close:
        return ""
    return "相关结果" if body.upper().startswith("ART") else "校验记录"


def sanitize_consumer_text(text: str) -> str:
    """Pure function: consumer-safe text (internal identifiers removed).
    Never raises; non-string input passes through unchanged."""
    if not isinstance(text, str) or not text:
        return text
    out = _ART_EVAL.sub(_art_sub, text)
    out = _RUNLIKE.sub("本次处理", out)
    return out


def strip_internal_ids_for_llm(obj):
    """Source hygiene: recursively remove internal identifier KEYS from a
    structure destined for the LLM context (values like summaries stay).
    Returns a new dict; the caller's original is untouched."""
    if isinstance(obj, dict):
        return {k: strip_internal_ids_for_llm(v) for k, v in obj.items()
                if k not in ("artifact_id", "eval_id", "approval_id",
                             "run_id", "case_id")}
    if isinstance(obj, list):
        return [strip_internal_ids_for_llm(v) for v in obj]
    return obj
