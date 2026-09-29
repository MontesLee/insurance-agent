"""Deterministic-first Insurance Intent classifier (Phase 28.A-1 / ADR-019).

Intent truth = schema + rules + runtime events. A prompt is NEVER an
intent source (ADR-019 rule 8, owner-approved 2026-09-25).

Pipeline (fixed, deterministic order — mirrors config/intent-rules.yaml):

    message (+ conversation context + active case context)
      -> rule classifier                       (signals from the rules file)
      -> LLM candidate (OPTIONAL, advisory)    (only when rules find nothing)
      -> deterministic resolver                (this module — always decides)
      -> IntentResult (schema/agent-registry... see schema/intent-result.schema.json)

Guarantees:
  * The OUTPUT ALWAYS validates against intent-result.schema.json; any
    internal failure degrades fail-closed to unknown_insurance_intent
    (never a guess, never an exception to the caller).
  * The LLM (when a candidate callable is supplied) can only PROPOSE an
    intent + confidence. It can never dispatch, choose a workflow, or
    select a tool — those powers do not exist in this module at all.
  * High-risk intents (insurance_plan, modify_existing_plan) proposed
    only by the LLM below the configured confidence floor are returned
    with clarification_required=true instead of auto-routing.
  * ADR-019 M1: modify_existing_plan without an active case context is
    only ever returned together with clarification_required=true (also
    enforced structurally by the schema's if/then).
"""
from __future__ import annotations

import hashlib
import os
import re
from typing import Callable, List, Optional

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
RULES_PATH = os.path.join(REPO_ROOT, "config", "intent-rules.yaml")
INTENT_SCHEMA_PATH = os.path.join(REPO_ROOT, "schema",
                                  "intent-result.schema.json")

UNKNOWN = "unknown_insurance_intent"

_rules_cache = None
_schema_validator = None


class IntentRulesError(RuntimeError):
    """Raised when the externalized rules file itself is invalid.

    Fail-closed: an invalid rules file is a configuration error, not a
    classification fallback — callers (tests/startup) must see it.
    """


def load_rules(path: Optional[str] = None, refresh: bool = False) -> dict:
    """Load (and cache) the externalized intent rules (config/intent-rules.yaml)."""
    global _rules_cache
    if _rules_cache is not None and not refresh and path is None:
        return _rules_cache
    import yaml  # noqa: WPS433 — same lazy import style as orchestrator.py:62
    with open(path or RULES_PATH, encoding="utf-8") as fh:
        rules = yaml.safe_load(fh)
    _validate_rules(rules, path or RULES_PATH)
    if path is None:
        _rules_cache = rules
    return rules


def _validate_rules(rules: dict, src: str) -> None:
    if not isinstance(rules, dict):
        raise IntentRulesError("%s: root must be a mapping" % src)
    vocab = rules.get("vocabulary")
    if not isinstance(vocab, list) or UNKNOWN not in vocab:
        raise IntentRulesError("%s: vocabulary must list %s" % (src, UNKNOWN))
    intents = rules.get("intents") or {}
    for key in ("insurance_plan", "modify_existing_plan"):
        sigs = (intents.get(key) or {}).get("signals")
        if not isinstance(sigs, list) or not sigs:
            raise IntentRulesError("%s: intents.%s.signals missing" % (src, key))


def _validator():
    global _schema_validator
    if _schema_validator is None:
        import json
        from jsonschema import Draft7Validator
        with open(INTENT_SCHEMA_PATH, encoding="utf-8") as fh:
            _schema_validator = Draft7Validator(json.load(fh))
    return _schema_validator


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _hits(text: str, signals: List[str]) -> List[str]:
    return [s for s in signals if s in text]


def _fallback_unknown(reasons: List[str], conversation_id, message_id,
                      active_case_id) -> dict:
    return {
        "intent_id": UNKNOWN,
        "confidence": 0.0,
        "confidence_source": "rule",
        "context_refs": {
            "conversation_id": conversation_id,
            "active_case_id": active_case_id,
            "message_id": message_id,
        },
        "clarification_required": True,
        "reason_codes": reasons[:5],
        "created_at": _now_iso(),
    }


def classify(message: str,
             conversation_context: Optional[List[str]] = None,
             conversation_id: Optional[str] = None,
             active_case_id: Optional[str] = None,
             message_id: Optional[str] = None,
             llm_candidate: Optional[Callable[[str, List[str]], tuple]] = None,
             rules: Optional[dict] = None,
             pending_clarification: bool = False) -> dict:
    """Classify one user message into a schema-valid IntentResult.

    llm_candidate: OPTIONAL callable(message, context) -> (intent, confidence).
    Advisory only — the deterministic resolver below always makes the final
    decision; on any candidate misbehaviour we degrade to unknown.
    """
    r = rules or load_rules()
    text = (message or "").strip()
    ctx = [str(c) for c in (conversation_context or []) if c]

    def build(intent, confidence, source, reasons, clarify) -> dict:
        return {
            "intent_id": intent,
            "confidence": confidence,
            "confidence_source": source,
            "context_refs": {
                "conversation_id": conversation_id,
                "active_case_id": active_case_id,
                "message_id": message_id,
            },
            "clarification_required": clarify,
            "reason_codes": reasons[:5] or ["rule:match"],
            "created_at": _now_iso(),
        }

    result = None
    markers = r.get("markers") or {}
    intents = r.get("intents") or {}
    thresholds = r.get("thresholds") or {}
    high_risk = set(thresholds.get("high_risk_intents") or
                    ["insurance_plan", "modify_existing_plan"])
    floor = float(thresholds.get("high_risk_llm_min_confidence", 0.75))

    product_id_hit = bool(re.search(markers.get("product_id_pattern") or r"P0\d{2}", text))
    # Phase 28.C-2: a CATALOG product name/id in the message is the
    # strongest specific-product reference (externalized versioned data —
    # the catalog — consumed read-only; fail-quiet to no-signal).
    catalog_hit = None
    try:
        from runtime.catalog_refs import find_product_in
        catalog_hit = find_product_in(text)
    except Exception:  # noqa: BLE001 — catalog unreadable = no signal
        catalog_hit = None
    has_anchor = product_id_hit or catalog_hit is not None or bool(
        _hits(text, markers.get("insurance_anchors") or []))
    # ADR-019 rule 7 (context signals, Phase 28.A-2): an ELLIPTICAL follow-up
    # (demonstrative / product id) may inherit the insurance-domain anchor
    # from recent conversation context. Evaluative-only phrasing NEVER
    # inherits — a mid-conversation "今天天气怎么样" must still degrade to
    # unknown. Switchable off via context.anchor_inheritance (rules file).
    inherit = bool((r.get("context") or {}).get("anchor_inheritance", True))
    context_anchor = inherit and any(
        _hits(str(c), markers.get("insurance_anchors") or []) for c in ctx)
    product_specific = ((has_anchor or context_anchor) and bool(
        _hits(text, markers.get("product_specific") or []))) \
        or product_id_hit or catalog_hit is not None
    product_evaluative = bool(_hits(text, markers.get("product_evaluative") or []))
    definition = bool(_hits(text, markers.get("definition_markers") or []))

    # 1. SPECIFIC product reference (demonstrative / product id / catalog
    #    name) — stays product QA even when phrased as a definition
    #    ("P001是什么产品"); insurance anchor required so out-of-domain
    #    text degrades to unknown (a catalog name IS the anchor)
    if product_specific:
        hit = _hits(text, markers.get("product_specific") or [])
        result = build("product_qa", 1.0, "rule",
                       ["rule:product_qa_specific:%s" % h for h in hit[:3]]
                       + (["rule:product_id_pattern"] if product_id_hit and not hit else [])
                       + (["rule:product_qa_catalog_name:%s" % catalog_hit["product_id"]]
                          if catalog_hit is not None and not hit
                          and not product_id_hit else [])
                       + (["context:anchor_inherited"]
                          if context_anchor and not has_anchor else []),
                       False)
    # 2. EVALUATIVE product phrasing — product QA unless a definition question
    #    ("等待期是什么意思" is a concept question, not a product lookup);
    #    anchor required ("今天天气怎么样" is not about insurance)
    elif product_evaluative and has_anchor and not definition:
        hit = _hits(text, markers.get("product_evaluative") or [])
        result = build("product_qa", 1.0, "rule",
                       ["rule:product_qa:%s" % h for h in hit[:3]], False)

    # 3. modification of an existing plan — requires an ACTION VERB;
    #    target nouns (保额/方案/...) only enrich reason codes
    if result is None:
        mcfg = intents.get("modify_existing_plan", {})
        mhits = _hits(text, mcfg.get("signals") or [])
        if mhits:
            has_case = bool(active_case_id)
            result = build(
                "modify_existing_plan", 1.0, "rule",
                ["rule:modify:%s" % h for h in mhits[:3]]
                + ["rule:modify_target:%s" % t for t in
                   _hits(text, mcfg.get("support_signals") or [])[:2]]
                + ([] if has_case else ["context:active_case_missing"]),
                clarify=not has_case)   # ADR-019 M1 (schema-enforced too)

    # 4. planning request — requires an ACTION signal; familial/financial
    #    context words alone NEVER fire plan (guidance stays guidance)
    #    28.K.28-I-FIX Fix A: a question form (什么/哪个/X不X/需要…吗…,
    #    externalized in markers.question_protection) suppresses the
    #    plan rule UNLESS an exemption applies — adjacency (怎么+配置/
    #    规划/买/投保/安排 = planning REQUEST phrased as a question),
    #    imperative (帮我/请+做/看/评估…), or advice-ask (建议/思路).
    #    Suppressed messages fall through to 4.5/5/7 unchanged.
    qprot = markers.get("question_protection") or {}

    def _qform(t):
        if not qprot or not qprot.get("enabled", True):
            return False
        if _hits(t, qprot.get("markers") or []):
            return True
        return any(re.search(p, t) for p in qprot.get("patterns") or [])

    def _qexempt(t):
        if re.search(qprot.get("adjacency_exempt_pattern") or r"(?!x)x",
                     t):
            return True
        if re.search(qprot.get("imperative_exempt_pattern") or r"(?!x)x",
                     t):
            return True
        return bool(_hits(t, qprot.get("advice_exempt_markers") or []))

    if result is None:
        pcfg = intents.get("insurance_plan", {})
        phits = _hits(text, pcfg.get("signals") or [])
        qf = _qform(text)
        if phits and not (qf and not _qexempt(text)):
            result = build("insurance_plan", 1.0, "rule",
                           ["rule:plan:%s" % h for h in phits[:3]]
                           + ["rule:plan_ctx:%s" % c for c in
                              _hits(text, pcfg.get("support_signals") or [])[:2]],
                           False)

    # 4.5 planning CONTINUATION (28.K.27-RV4-C1, ADR-019 continuation
    #     addendum): the previous turn in this conversation ended
    #     WAITING_USER from the planning agent (the server derived
    #     pending_clarification from existing run state — no new case
    #     lifecycle). A message with NO new-intent signal is an ANSWER
    #     to those clarification questions and continues the planning
    #     task. Topic switch ALWAYS wins: explicit question/definition/
    #     evaluative/plan-action/modify phrasing falls through to the
    #     normal chain. Bare product nouns (重疾险/医疗险…) are NOT a
    #     switch signal — they are exactly what answers contain
    #     (RV4-A real case). Ack-only replies (好的/是的/极短) are
    #     ambiguous: fail-closed via the existing clarification flag
    #     instead of guessing.
    if result is None and pending_clarification:
        ccfg = (r.get("context") or {}).get("plan_continuation") or {}
        if ccfg.get("enabled", True):
            plan_sig = _hits(text, (intents.get("insurance_plan") or {})
                             .get("signals") or [])
            mod_sig = _hits(text, (intents.get("modify_existing_plan") or {})
                            .get("signals") or [])
            qmark = any(m in text for m in ("？", "?", "吗", "呢", "么"))
            # 28.K.28-I-FIX Fix C: negative service/re-explain/recommend
            # imperatives are switch signals (externalized list) — a
            # pending plan must never "continue" over them.
            neg = _hits(text, ccfg.get("negative_signals") or [])
            switch = bool(definition or product_evaluative or product_specific
                          or plan_sig or mod_sig or qmark or neg)
            if not switch:
                ack_max = int(ccfg.get("ack_max_len", 6))
                reason = ccfg.get("reason_code", "plan:continuation")
                ack_reason = ccfg.get("ack_reason_code",
                                      "plan:continuation:ambiguous_ack")
                ack_only = len(text) <= ack_max
                result = build("insurance_plan", 1.0, "rule",
                               [(ack_reason if ack_only else reason)]
                               + ["context:pending_clarification"],
                               ack_only)   # ambiguous ack -> fail-closed

    # 5. knowledge/concept question
    #    28.K.28-I-FIX Fix A (b): a question form ALSO classifies qa when
    #    the message carries a PLAN signal (the stolen-question scenario
    #    the guard opened) AND its own insurance anchor. Narrow by
    #    construction: vague anchored questions WITHOUT plan nouns keep
    #    the governed-unknown path (K.5/RV2 real behavior preserved);
    #    out-of-domain questions never auto-route (no anchor).
    if result is None:
        dhits = _hits(text, markers.get("definition_markers") or [])
        qhits = _hits(text, intents.get("insurance_qa", {}).get("signals") or [])
        qf_rescue = (qf and phits and has_anchor and not (dhits or qhits))
        if dhits or qhits or qf_rescue:
            reasons = ["rule:qa:%s" % h for h in (dhits + qhits)[:3]]
            if qf_rescue:
                reasons = ["rule:qa:question_form"]
            result = build("insurance_qa", 1.0, "rule", reasons, False)

    # 6. optional LLM candidate — advisory only (rules found nothing).
    #    Candidate contract (28.A-2 adapter): returns (intent, confidence)
    #    on a valid proposal, None when the OUTPUT was rejected (shape /
    #    forbidden keys / out-of-range), or RAISES when the provider is
    #    unavailable (timeout / transport) — both degrade fail-closed.
    if result is None and callable(llm_candidate):
        try:
            proposal = llm_candidate(text, ctx)
            if proposal is None:
                result = _fallback_unknown(["llm:invalid_proposal"],
                                           conversation_id, message_id,
                                           active_case_id)
            else:
                intent, confidence = proposal[0], float(proposal[1])
                if intent in r["vocabulary"] and intent != UNKNOWN:
                    reasons = ["llm:proposal"]
                    clarify = False
                    if intent in high_risk and confidence < floor:
                        # HD-1 floor: no auto-route for low-confidence high-risk
                        clarify = True
                        reasons.append("threshold:high_risk_llm_floor")
                    result = build(intent, confidence, "llm", reasons, clarify)
                else:
                    result = _fallback_unknown(["llm:invalid_proposal"],
                                               conversation_id, message_id,
                                               active_case_id)
        except Exception:  # noqa: BLE001 — candidate failure degrades closed
            result = _fallback_unknown(["llm:candidate_error"],
                                       conversation_id, message_id,
                                       active_case_id)

    # 7. fail-closed unknown
    if result is None:
        # 28.K.7 (S-1): tag insurance-domain unknowns. `has_anchor` (the
        # SAME anchor markers the product/QA rules use, current message
        # only — context inheritance deliberately excluded so a
        # mid-conversation "今天天气怎么样" stays ungoverned) lets the
        # router seam route insurance-domain unknowns into the evidence-
        # governed QA pipeline instead of the ungoverned generic loop.
        # Non-insurance unknowns carry no marker and keep prior behavior.
        reasons = ["fallback:no_signal_match"]
        if has_anchor:
            reasons.append("domain:insurance_anchor")
        result = _fallback_unknown(reasons,
                                   conversation_id, message_id, active_case_id)

    # final gate: output must validate — otherwise degrade to unknown
    errors = [e.message for e in _validator().iter_errors(result)]
    if errors:
        return _fallback_unknown(["schema_validation_failed"] +
                                 [hashlib.sha1(e.encode("utf-8")).hexdigest()[:8]
                                  for e in errors[:2]],
                                 conversation_id, message_id, active_case_id)
    return result
