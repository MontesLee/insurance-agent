"""LLM candidate adapter (Phase 28.A-2 / ADR-019 rule 1).

**LLM may PROPOSE, the deterministic layer decides.** This adapter turns any
LLMProvider-protocol object (runtime/agent/model.py — OpenAI-compatible or
FakeLLM) into the `llm_candidate` callable consumed by
runtime.intent.classifier.classify() — and NOTHING else:

  * it has NO knowledge of agents, workflows, tools, skills or the router;
  * an output containing `agent` / `workflow` / `decision_source` / `tool` /
    `skill` keys is REJECTED before leaving this module (the forbidden
    powers do not exist in the candidate contract at all);
  * the candidate carries at most {intent, confidence, explanation,
    evidence} — exactly the advisory shape ADR-019 allows;
  * on timeout or provider failure the adapter RAISES, and the classifier
    degrades to the rule path (fail-closed; shadow can never break a turn);
  * on a REJECTED output shape it returns None (classifier reason
    `llm:invalid_proposal`).

Privacy: the candidate prompt sends the user message + a short context tail
to the provider — the SAME provider that already serves the full chat turn
in agent mode, so no new data exposure. The model's `explanation` may echo
user text and is therefore NEVER stored in shadow records or events (the
hash-only discipline of runtime/intent/shadow.py is unchanged).

Runtime enablement is env-gated and OFF by default:
    INSURANCE_AGENT_INTENT_LLM=1                    (enable)
    INSURANCE_AGENT_INTENT_LLM_TIMEOUT=4.0          (seconds; also
                                                     configurable via
                                                     config/intent-rules.yaml
                                                     llm_candidate.timeout_seconds)

This module is intentionally NOT imported by runtime/intent/__init__.py —
importing `runtime.intent` stays LLM-provider-free.
"""
from __future__ import annotations

import json
import os
import threading
from typing import Callable, Optional

# ADR-019/28.A-2 spec: the ONLY keys an LLM candidate may carry. Anything
# else in the response is a contract violation -> rejected.
ALLOWED_KEYS = frozenset({"intent", "confidence", "explanation", "evidence"})

# Powers the LLM must never have (ADR-019 rule 2 / spec Rule 3). A response
# carrying ANY of these keys is rejected outright — before intent reading.
FORBIDDEN_KEYS = ("agent", "workflow", "decision_source", "tool", "skill",
                  "action", "step")

ENABLE_ENV = "INSURANCE_AGENT_INTENT_LLM"
TIMEOUT_ENV = "INSURANCE_AGENT_INTENT_LLM_TIMEOUT"

# one-line behavioral descriptions embedded in the (advisory) prompt; the
# vocabulary itself is interpolated from the rules file (single source).
_INTENT_HINTS = {
    "insurance_qa": "insurance concept / knowledge / difference question",
    "product_qa": "question about a SPECIFIC insurance product",
    "insurance_plan": "request to plan / configure insurance coverage",
    "modify_existing_plan": "request to MODIFY a plan already discussed",
    "unknown_insurance_intent": "none of the above / out of domain",
}

_SYSTEM_PROMPT = (
    "You are an insurance intent classification assistant. Classify the "
    "user's LATEST message into exactly one intent from this frozen "
    "vocabulary:\n%(vocab)s\n"
    "Respond with STRICT JSON only, no markdown fence, exactly these keys: "
    '{"intent": "<vocabulary value>", "confidence": <number 0.0-1.0>, '
    '"explanation": "<short reason>", "evidence": ["<short quote>"]}. '
    "You MUST NOT include any other key. You never select agents, "
    "workflows, tools or actions.")


def enabled(env: Optional[dict] = None) -> bool:
    """Runtime toggle for LLM candidates (default OFF — rules-only shadow)."""
    e = os.environ if env is None else env
    return str(e.get(ENABLE_ENV, "")).strip().lower() in ("1", "true", "yes")


def timeout_seconds(env: Optional[dict] = None, rules: Optional[dict] = None
                    ) -> float:
    """Candidate call budget: env override > rules file > 4.0s hard default."""
    e = os.environ if env is None else env
    raw = str(e.get(TIMEOUT_ENV, "")).strip()
    if raw:
        try:
            return max(0.5, float(raw))
        except ValueError:
            pass
    if rules is None:
        try:
            from runtime.intent.classifier import load_rules
            rules = load_rules()
        except Exception:  # noqa: BLE001 — rules unreadable is not our failure
            rules = {}
    try:
        return max(0.5, float((rules.get("llm_candidate") or {})
                              .get("timeout_seconds", 4.0)))
    except (TypeError, ValueError):
        return 4.0


def max_context_messages(rules: Optional[dict] = None) -> int:
    try:
        if rules is None:
            from runtime.intent.classifier import load_rules
            rules = load_rules()
        return max(0, int((rules.get("llm_candidate") or {})
                          .get("max_context_messages", 4)))
    except Exception:  # noqa: BLE001
        return 4


def parse_candidate(raw: Optional[str]) -> Optional[tuple]:
    """Validate a raw model response into a candidate, or REJECT (None).

    Rejection reasons (all -> None, never an exception):
      * not JSON / not an object;
      * any FORBIDDEN key present (agent/workflow/decision_source/...);
      * any key outside ALLOWED_KEYS;
      * intent missing/not a str; confidence missing/out of [0,1]/not a
        number; explanation/evidence of the wrong shape.
    """
    if not raw or not isinstance(raw, str):
        return None
    text = raw.strip()
    # strip a markdown fence if the model added one despite instructions
    if text.startswith("```"):
        text = text.strip("`")
        if text[:4].lower() == "json":
            text = text[4:]
        text = text.strip()
    # extract the outermost JSON object if any prose surrounds it
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        doc = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
    if not isinstance(doc, dict):
        return None
    if any(k in doc for k in FORBIDDEN_KEYS):
        return None                      # forbidden power -> rejected
    if not set(doc) <= ALLOWED_KEYS:
        return None                      # unknown extra key -> rejected
    intent = doc.get("intent")
    confidence = doc.get("confidence")
    if not isinstance(intent, str) or not intent.strip():
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    if not 0.0 <= float(confidence) <= 1.0:
        return None
    explanation = doc.get("explanation")
    if explanation is not None and not isinstance(explanation, str):
        return None
    evidence = doc.get("evidence")
    if evidence is not None and (not isinstance(evidence, list) or
                                 not all(isinstance(x, str) for x in evidence)):
        return None
    return intent.strip(), float(confidence)


def _build_messages(message: str, context: list, rules: dict) -> list:
    vocab = rules.get("vocabulary") or []
    hints = "\n".join("- %s: %s" % (v, _INTENT_HINTS.get(v, ""))
                      for v in vocab)
    lines = ["Conversation so far (most recent last):"]
    tail = [str(c) for c in (context or []) if c][-max_context_messages(rules):]
    for c in tail:
        lines.append("  | %s" % c[:160])          # bounded echo, advisory only
    lines.append("Latest message to classify:")
    lines.append("  >>> %s" % message)
    return [
        {"role": "system", "content": _SYSTEM_PROMPT % {"vocab": hints}},
        {"role": "user", "content": "\n".join(lines)},
    ]


def make_candidate(provider, timeout: Optional[float] = None,
                   rules: Optional[dict] = None,
                   thread_factory: Optional[Callable] = None) -> Callable:
    """Build the `llm_candidate` callable for classify().

    provider: ANY object satisfying the LLMProvider protocol
    (`.generate(messages, tools)`); this module never constructs one and
    never imports a provider class. thread_factory: test seam (defaults to
    threading.Thread) so the watchdog is unit-testable without sleeping.
    """
    from runtime.intent.classifier import load_rules
    r = rules or load_rules()
    budget = timeout if timeout is not None else timeout_seconds(rules=r)
    spawn = thread_factory or (lambda target: threading.Thread(
        target=target, daemon=True, name="intent-llm-candidate"))

    def candidate(message: str, context: list) -> Optional[tuple]:
        messages = _build_messages(message, context, r)
        box: dict = {}

        def _call():
            try:
                box["resp"] = provider.generate(messages, [])
            except Exception as exc:  # noqa: BLE001 — surfaced below
                box["err"] = exc

        t = spawn(_call)
        t.start()
        t.join(budget)
        if "resp" in box:
            return parse_candidate(box["resp"].text)   # None == rejected
        if t.is_alive():
            raise RuntimeError("llm_candidate_unavailable: timeout(%.1fs)"
                               % budget)
        raise RuntimeError("llm_candidate_unavailable: %s"
                           % repr(box.get("err", "no response"))[:160])

    return candidate
