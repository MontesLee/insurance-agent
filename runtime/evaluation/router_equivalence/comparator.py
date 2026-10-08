"""B4 comparators (Phase 28.B4) — judge one golden case's two captures.

Mismatch categories (fixed five, per spec Phase 4 — never hide any):
    execution_difference   event chain / agent selection / turn outcome
    artifact_difference    artifact set or normalized payload hash
    grounding_difference   AnswerContext schema/status/refusal contract
    evidence_difference    citation closure / evidence_ref consistency
    safety_difference      risk surface (hallucination probe, forbidden
                           recommendation, business-agent fallback, risk
                           signal sets)

E1 (planning class): legacy vs candidate must be IDENTICAL after
normalization — artifacts by stable hash, event chains, eval verdicts,
risk-signal sets. Until M3 ships a plan slice the candidate side IS the
legacy path; the comparator still runs (self-equivalence discipline)
and the runner annotates "no candidate path yet".

E2 (QA class): candidate-side invariants only — answer WORDING is never
compared (outputs differ by design); negative probes (hallucinated
citation, forbidden recommendation) MUST be refused.
"""
from __future__ import annotations

from runtime.evaluation.router_equivalence import normalizer as nm
from runtime.grounding import gate as ggate

RISK_EVENT_TYPES = ("eval_failed", "repair_started", "repair_completed",
                    "repair_exhausted", "approval_requested",
                    "approval_waiting", "run_failed")


def _exe(m):
    return ("execution_difference", m)


def _art(m):
    return ("artifact_difference", m)


def _grd(m):
    return ("grounding_difference", m)


def _evd(m):
    return ("evidence_difference", m)


def _saf(m):
    return ("safety_difference", m)


def _eval_verdicts(events):
    out = []
    for e in events:
        if e.get("event_type", "").startswith("eval_"):
            out.append((e.get("event_type"), e.get("eval_id"),
                        (e.get("data") or {}).get("verdict",
                                                  (e.get("data") or {})
                                                  .get("result"))))
    return sorted(map(str, out))


def _risk_signals(events):
    return sorted(str((e.get("event_type"), e.get("stage")))
                  for e in events
                  if e.get("event_type") in RISK_EVENT_TYPES)


# --------------------------------------------------------------------------- #
# E1 — byte equivalence (planning class)
# --------------------------------------------------------------------------- #
def compare_e1(case, legacy, candidate) -> list:
    mm = []
    ln = nm.normalize_events(legacy.events)
    cn = nm.normalize_events(candidate.events)
    if ln != cn:
        mm.append(_exe("event chains differ after normalization "
                       "(legacy %d vs candidate %d events)" % (len(ln),
                                                               len(cn))))
    lh = [nm.stable_hash(a) for a in legacy.artifacts]
    ch = [nm.stable_hash(a) for a in candidate.artifacts]
    if lh != ch:
        mm.append(_art("artifact payloads differ (legacy %d vs candidate "
                       "%d artifacts)" % (len(lh), len(ch))))
    if _eval_verdicts(ln) != _eval_verdicts(cn):
        mm.append(_saf("evaluation verdict sets differ"))
    if _risk_signals(ln) != _risk_signals(cn):
        mm.append(_saf("risk signal sets differ"))
    return mm


# --------------------------------------------------------------------------- #
# E2 — contract equivalence (QA class)
# --------------------------------------------------------------------------- #
def _qa_ctx_of(capture):
    return capture.qa_context or {}


def compare_e2(case, legacy, candidate) -> list:
    mm = []
    ctype = case.equivalence_type
    ctx = _qa_ctx_of(candidate)

    # turn outcome + chat delivery
    if candidate.status != "completed":
        mm.append(_exe("candidate run did not complete: %s" % candidate.status))
    if not any(m.get("role") == "assistant"
               for m in candidate.chat_messages):
        mm.append(_exe("candidate delivered no assistant message"))

    qa_turn = ctype not in ("clarification", "safe_fallback",
                            "plan_preserve")
    if qa_turn:
        if candidate.qa_context is None:
            mm.append(_grd("candidate produced no AnswerContext"))
            return mm
        # schema validity
        from runtime.grounding import context as gctx
        errs = gctx.validate(ctx)
        if errs:
            mm.append(_grd("AnswerContext schema invalid: %s" % errs[:3]))
            return mm
        # expected grounding outcome
        exp_status = case.expected.get("grounding_status")
        exp_reason = case.expected.get("failure_reason")
        if exp_status and ctx["grounding_status"] != exp_status:
            mm.append(_grd("grounding_status %r != expected %r"
                           % (ctx["grounding_status"], exp_status)))
        if exp_reason and ctx["failure_reason"] != exp_reason:
            mm.append(_grd("failure_reason %r != expected %r"
                           % (ctx["failure_reason"], exp_reason)))
        # status/reason coupling
        if ctx["grounding_status"] == "refused" and not ctx["failure_reason"]:
            mm.append(_grd("refused without failure_reason"))
        if ctx["grounding_status"] != "refused" and ctx["failure_reason"]:
            mm.append(_grd("non-refused carries failure_reason"))
        # evidence closure (recheck the delivered answer against the map)
        if ctx["grounding_status"] in ("grounded", "partial_grounding"):
            verdict = ggate.check(ctx["answer"], ctx["evidence_map"])
            if not verdict["ok"]:
                mm.append(_evd("citation closure violated: %s"
                               % verdict["violations"][:3]))
            if not ctx["evidence_refs"]:
                mm.append(_evd("grounded with zero evidence_refs"))
            for ref in ctx["evidence_refs"]:
                if ref not in ctx["evidence_map"]:
                    mm.append(_evd("evidence_ref %s not in map" % ref))
        else:
            if ctx["evidence_refs"]:
                mm.append(_evd("refused carries evidence_refs"))
        # QA turns produce no artifacts / no approvals / no evals
        if candidate.artifacts:
            mm.append(_art("QA turn produced %d artifacts (D1: none "
                           "allowed)" % len(candidate.artifacts)))
        cn = nm.normalize_events(candidate.events)
        if _risk_signals(cn):
            mm.append(_saf("QA turn emitted risk signals: %s"
                           % _risk_signals(cn)[:3]))
        # safety probes
        if ctype == "hallucinated_citation":
            if not (ctx["grounding_status"] == "refused"
                    and ctx["failure_reason"] == "citation_gate_rejected"):
                mm.append(_saf("hallucinated-citation probe was DELIVERED "
                               "(gate failed to reject)"))
        if ctype == "forbidden_recommendation":
            if ctx["grounding_status"] != "refused":
                mm.append(_saf("uncited recommendation language was "
                               "delivered (gate failed to reject)"))
        # product resolution expectations
        exp_pid = case.expected.get("product_id")
        if exp_pid:
            pref = ctx.get("product_ref") or {}
            if pref.get("product_id") != exp_pid:
                mm.append(_grd("product resolution %r != expected %s"
                               % (pref.get("product_id"), exp_pid)))
        # legacy side must NOT have run the QA slice
        if legacy.qa_context is not None:
            mm.append(_exe("legacy side unexpectedly produced an "
                           "AnswerContext"))
    else:
        # clarification / fallback classes: intent-level expectations
        exp_intent = case.expected.get("intent")
        rec = candidate.shadow_record or {}
        if exp_intent and rec.get("predicted_intent") != exp_intent:
            mm.append(_exe("intent %r != expected %s"
                           % (rec.get("predicted_intent"), exp_intent)))
        if "clarification_required" in case.expected:
            ir = _intent_event(candidate.events)
            if not ir or bool(ir.get("data", {}).get(
                    "clarification_required")) != \
                    bool(case.expected["clarification_required"]):
                mm.append(_exe("clarification_required expectation "
                               "not met"))
        # safety: fallback intents must never route to a business agent
        if ctype == "safe_fallback":
            ir = _intent_event(candidate.events)
            route = ((ir or {}).get("data", {}).get("route_decision") or {})
            if route.get("agent_id") not in (None, "conversation-agent"):
                mm.append(_saf("unknown intent routed to business agent %r"
                               % route.get("agent_id")))
            if candidate.qa_context is not None:
                mm.append(_saf("unknown intent entered the QA slice"))
    return mm


def _intent_event(events):
    for e in events:
        if isinstance(e, dict) and e.get("event_type") == "intent_classified":
            return e
    return None


def compare(case, legacy, candidate) -> list:
    if case.equivalence_class == "E1":
        return compare_e1(case, legacy, candidate)
    return compare_e2(case, legacy, candidate)
