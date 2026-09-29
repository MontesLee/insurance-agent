"""LLM shadow comparator (OD-11) — SHADOW ONLY.

Wraps any LLMProvider into an advisory claim-support judge. The
deterministic result NEVER reads this module's output at judgment time
(the evaluator records both and computes agreement afterwards). Strict
JSON contract; any deviation degrades to None (fail-closed, excluded
from agreement stats rather than guessed).
"""
from __future__ import annotations

import json
import os
from typing import Optional

ALLOWED = {"SUPPORTED", "PARTIALLY_SUPPORTED", "UNSUPPORTED",
           "NOT_APPLICABLE"}

_SYSTEM = (
    "You are an insurance claim-support auditor. Given ONE claim and "
    "the numbered EVIDENCE texts that already passed governance and "
    "relevance qualification, decide whether the EVIDENCE actually "
    "supports the CLAIM. Respond with STRICT JSON only: "
    '{"status": "SUPPORTED|PARTIALLY_SUPPORTED|UNSUPPORTED|'
    'NOT_APPLICABLE", "reason": "<short reason>", '
    '"evidence_idx": [<int>]}. NOT_APPLICABLE means the claim is not '
    "an externally verifiable insurance fact (user-provided fact, "
    "recommendation, deterministic calculation, model uncertainty, or "
    "planning analysis conclusion). Citation markers in the claim like "
    "[E1] are the model's OWN citations and are NOT evidence of "
    "support. Respond JSON only.")


def make_judge(provider):
    """provider: LLMProvider protocol object (runtime/agent/model.py)."""

    def judge(claim: str, evidence_texts: list) -> Optional[dict]:
        ev = "\n".join("[%d] %s" % (i + 1, t)
                       for i, t in enumerate(evidence_texts))
        msgs = [
            {"role": "system", "content": _SYSTEM},
            {"role": "user",
             "content": "CLAIM: %s\n\nEVIDENCE:\n%s" % (claim, ev)}]
        try:
            resp = provider.generate(msgs, [])
            raw = ((getattr(resp, "text", None) or getattr(resp, "content", None) or "")).strip()
            if raw.startswith("```"):
                raw = raw.strip("`")
                if raw.startswith("json"):
                    raw = raw[4:]
            obj = json.loads(raw)
            status = obj.get("status")
            if status not in ALLOWED:
                return None
            return {"status": status,
                    "reason": str(obj.get("reason", ""))[:200]}
        except Exception:  # noqa: BLE001 — shadow, fail-closed
            return None

    return judge


def llm_enabled(env=None) -> bool:
    e = os.environ if env is None else env
    return str(e.get("INSURANCE_AGENT_CLAIM_SHADOW_LLM", "")
               ).strip().lower() in ("1", "true", "yes")
