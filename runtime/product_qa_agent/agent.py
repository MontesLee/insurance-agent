"""Insurance Product QA Agent — minimal production loop (Phase 28.C-2).

The product-facts behavior unit of registry agent insurance-qa-agent
(the Router maps product_qa -> insurance-qa-agent; which behavior module
runs is below the routing layer). One turn =

    validated IntentResult (product_qa)
      -> product resolution (catalog: message -> context; deterministic)
      -> KnowledgeService.build_evidence        (governed retrieval; the
         KB is ALWAYS queried — its unavailability fails the turn closed
         even when a catalog anchor exists, K003 no-fallback)
      -> evidence assembly:
           resolved   E1 = deterministic catalog record (version-pinned)
                      E2.. = governed evidence QUALIFYING for the product
                      (evidence_refs-linked doc or content naming it)
           unresolved ordinary knowledge path (no catalog anchor)
      -> parameter guard: an asked parameter absent from BOTH the
         catalog record and the qualifying evidence => refused
         catalog_missing_fact (ruling D6 — honest absence, no generic
         substitution)
      -> shared grounding loop (LLM Gateway -> citation closure gate ->
         one regeneration) -> AnswerContext

Forbidden by design (spec boundary): purchase recommendations, plan
design, coverage calculation, sales advice — the system prompt forbids
them and the module contains no tool or path that could produce them.
Fail-closed everywhere; never raises to the caller.
"""
from __future__ import annotations

import os
from typing import Optional

from runtime.grounding import context as gctx
from runtime.grounding import gate as ggate
from runtime.grounding.loop import (build_gateway, conflict_answer,
                                    generate_grounded, kb_header)
from runtime.product_qa_agent import resolution as pr

SLICE_ENV = "INSURANCE_AGENT_PRODUCT_QA_SLICE"

# System prompt externalized since 28.B5.1: canonical text in
# config/product-qa-rules.yaml generation.system_prompt (calibrated
# against traced live failure modes; gate unchanged).
_FALLBACK_PROMPT = (
    "You are the Insurance Product QA Agent. Answer using ONLY the "
    "numbered evidence; cite [E1]-style after every fact sentence; "
    "relay catalog values exactly; no recommendations.")


def system_prompt(rules=None, product_rules=None) -> str:
    pq = product_rules or pr.load_rules()
    return ((pq.get("generation") or {}).get("system_prompt")
            or _FALLBACK_PROMPT)


def product_qa_slice_enabled(env: Optional[dict] = None) -> bool:
    """Feature flag for the product-QA production slice — DEFAULT OFF
    (28.C-2 spec Step 3; unlike the knowledge-QA slice which is D4
    default-ON)."""
    e = os.environ if env is None else env
    return str(e.get(SLICE_ENV, "0")).strip().lower() in ("1", "true",
                                                          "yes", "on")


def run_product_qa_turn(question: str, intent_result: dict,
                        conversation_context: Optional[list] = None, *,
                        provider=None, gateway=None, service=None,
                        rules: Optional[dict] = None,
                        product_rules: Optional[dict] = None,
                        emit=None) -> dict:
    """Run ONE product_qa turn. Always returns a schema-valid
    AnswerContext (grounded / partial / refused)."""
    r = rules or ggate.load_rules()
    pq = product_rules or pr.load_rules()
    no_att = gctx.not_attempted_retrieval()

    def _refuse(reason, retrieval=None, generation=None, violations=None,
                pref=None):
        return gctx.refused(reason, intent_result, retrieval or no_att,
                            generation=generation, violations=violations,
                            product_ref=pref)

    # ---- 1. input contract: validated intent, product_qa, no pending
    #         clarification
    if (not isinstance(intent_result, dict)
            or gctx.validate_intent(intent_result)
            or intent_result.get("intent_id") != "product_qa"
            or intent_result.get("clarification_required")):
        return _refuse("invalid_input")

    # ---- 2. product resolution (deterministic; message -> context)
    from runtime.catalog_refs import find_product
    match, source = find_product(question or "",
                                 conversation_context or [],
                                 int((pq.get("resolution") or {}).get(
                                     "context_scan_messages", 8)))
    pref = None
    if match is not None:
        pref = {"resolved": True,
                "product_id": match["product_id"],
                "product_name": match["product_name"],
                "matched_by": (source or {}).get(
                    "matched_by", match["matched_by"])}
    else:
        pref = {"resolved": False}

    # ---- 3. governed retrieval — ALWAYS attempted (K003: no path that
    #         skips the knowledge service; its outage fails the turn)
    from knowledge.service import default_service
    svc = service or default_service()
    top_k = int((r.get("retrieval") or {}).get("top_k", 8))
    query = (question or "").strip()
    if match is not None:
        query = "%s %s" % (query, match["product_name"])
    try:
        items, governed, _decisions, _qr = svc.build_evidence(
            query, top_k=top_k)
    except Exception:  # noqa: BLE001 — provider family fails CLOSED
        return _refuse("kb_unavailable", pref=pref)

    gm = (getattr(governed, "retrieval_metadata", None) or {}).get(
        "governance", {})
    retrieval = gctx.retrieval(
        query, top_k, getattr(svc.provider, "name", ""),
        getattr(governed, "status", "success"),
        len(items), gm.get("rejected", 0) or 0,
        bool(getattr(governed, "conflict", False)),
        domain=(r.get("retrieval") or {}).get("domain_default"))

    # ---- 4. evidence assembly
    if match is None:
        # unresolved product reference: ordinary knowledge path
        if (getattr(governed, "status", "") in ("insufficient_evidence",
                                                "retrieval_error")
                or not items):
            return _refuse("insufficient_evidence", retrieval, pref=pref)
        evidence = [("E%d" % (i + 1),
                     {"content": it.get("content", ""),
                      "header": kb_header(it),
                      "anchor": gctx.anchor(it)})
                    for i, it in enumerate(items[:top_k])]
        governed_status = getattr(governed, "status", "success")
    else:
        catalog_ev = pr.catalog_record(match["product"], pq)
        qualifying = [it for it in items[:top_k]
                      if pr.qualifies(it, match["product"])]
        # parameter guard (ruling D6): asked parameter present in NEITHER
        # the catalog record NOR qualifying evidence => fail closed
        param_terms = [t for t in (pq.get("parameters") or [])
                       if t in (question or "")]
        if param_terms:
            hay = catalog_ev["content"] + "\n" + "\n".join(
                str(it.get("content", "")) for it in qualifying)
            if not any(t in hay for t in param_terms):
                return _refuse("catalog_missing_fact", retrieval, pref=pref)
        evidence = ([("E1", catalog_ev)]
                    + [("E%d" % (i + 2),
                        {"content": it.get("content", ""),
                         "header": kb_header(it),
                         "anchor": gctx.anchor(it)})
                       for i, it in enumerate(qualifying)])
        governed_status = ("success" if qualifying
                           else "partial_evidence")   # catalog-only turn

    # ---- 5. conflicting governed sources: deterministic both-sides
    if getattr(governed, "conflict", False) and len(evidence) > 1:
        answer = conflict_answer(evidence, r)
        verdict = ggate.check(answer,
                              {l: e["anchor"] for l, e in evidence}, r)
        cited = verdict["cited"] or [label for label, _ in evidence]
        if verdict["ok"]:
            return gctx.grounded(answer, cited,
                                 {l: e["anchor"] for l, e in evidence},
                                 intent_result, retrieval,
                                 {"provider": "deterministic-template",
                                  "model": "",
                                  "prompt_version": (pq.get("generation")
                                                     or {}).get(
                                      "prompt_version", ""),
                                  "gateway": False, "attempts": 0},
                                 product_ref=pref)
        return _refuse("citation_gate_rejected", retrieval,
                       violations=verdict["violations"], pref=pref)

    # ---- 6. grounded generation via the shared loop (LLM Gateway, D2)
    if gateway is None:
        if provider is None:
            return _refuse("internal_error", retrieval, pref=pref)
        gateway = build_gateway(provider, r)
    return generate_grounded((question or "").strip(), evidence,
                             intent_result, retrieval, gateway, r,
                             system_prompt(None, pq),
                             governed_status=governed_status,
                             product_ref=pref,
                             emit=emit)  # 28.K.22 Policy B streaming
