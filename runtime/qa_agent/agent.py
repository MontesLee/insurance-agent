"""Insurance QA Agent (knowledge questions) — minimal production loop.

Phase 28.C-1 built; Phase 28.C-2 refactored onto the shared grounding
loop (runtime/grounding/loop.py) — behavior-equivalent, extraction not
rewrite. One turn =

    validated IntentResult (insurance_qa)
      -> KnowledgeService.build_evidence      (governed retrieval, K001/K002)
      -> conflict? deterministic both-sides   (ADR-022)
      -> shared loop: LLM Gateway (ruling D2) -> citation closure gate
         -> one bounded regeneration -> AnswerContext

Fail-closed everywhere: kb_unavailable / insufficient_evidence /
llm_unavailable / citation_gate_rejected — never a guess, never a
silent fallback provider (K003). This module owns NO routing, NO
workflow knowledge, NO artifact registration, and never touches WeKnora
except through KnowledgeService.
"""
from __future__ import annotations

import os
from typing import Optional

from runtime.grounding import context as gctx
from runtime.grounding import gate as ggate
from runtime.grounding.loop import (build_gateway, conflict_answer,
                                    generate_grounded, kb_header)

SLICE_ENV = "INSURANCE_AGENT_QA_SLICE"

# System prompt externalized since 28.B5.1: the canonical text lives in
# config/qa-grounding-rules.yaml generation.qa_system_prompt (versioned,
# calibrated against traced live failure modes — see
# phase-28b51-pre-audit.md). The gate is unchanged; this only shapes the
# model's OUTPUT toward the existing contract.
_FALLBACK_PROMPT = (
    "You are the Insurance QA Agent. Answer using ONLY the numbered "
    "evidence provided; cite [E1]-style after every fact sentence.")


def system_prompt(rules: Optional[dict] = None) -> str:
    r = rules or ggate.load_rules()
    return ((r.get("generation") or {}).get("qa_system_prompt")
            or _FALLBACK_PROMPT)


def qa_slice_enabled(env: Optional[dict] = None) -> bool:
    """Ops kill-switch for the knowledge-QA production slice (default ON,
    ruling D4)."""
    e = os.environ if env is None else env
    return str(e.get(SLICE_ENV, "1")).strip().lower() not in ("0", "false",
                                                              "no", "off")


def _bigrams(text: str) -> set:
    """Normalized CJK/alnum bigrams (28.K.27-RV4-C2 qualification
    lexicon — zero new dependencies, deterministic)."""
    import re as _re
    # CJK-only bigrams: digits/latin/punctuation excluded (digit bigrams
    # like 00/10 and punctuation pairs are noise that inflates overlap)
    norm = _re.sub(r"[^一-鿿]+", "", str(text or ""))
    return {norm[i:i + 2] for i in range(len(norm) - 1)}


def _qualified_evidence(items: list, query: str,
                        rules: Optional[dict]) -> list:
    """28.K.27-RV4-C2 (P1-B Phase 1): RetrievedEvidence ->
    QualifiedEvidence relevance floor.

    Governance (K001/K002) qualifies a hit's SOURCE (registry/authority/
    window/hash) — NOT its topical relevance to THIS query. This filter
    closes that gap with the RV4-B-approved lexical rule: a hit may
    enter the [E#] evidence set only when its content/source text shares
    >= `retrieval.qualification.min_query_bigram_overlap` DISTINCT
    query bigrams. All-fail -> [] -> the EXISTING insufficient_evidence
    honest-refusal path (never raw-evidence fallback). Threshold 0 or a
    degenerate query disables filtering (rollback knob / no
    over-filtering)."""
    cfg = ((rules or {}).get("retrieval") or {}).get(
        "qualification") or {}
    k = int(cfg.get("min_query_bigram_overlap", 0) or 0)
    if k <= 0 or not items:
        return items
    generic = set(cfg.get("generic_bigrams") or [])
    qb = _bigrams(query) - generic
    if not qb:
        return items          # only generic terms: do not over-filter
    out = []
    for it in items:
        cb = _bigrams("%s %s" % (
            it.get("content", ""),
            it.get("source_name") or it.get("document_name") or ""))
        if len((qb & cb) - generic) >= k:
            out.append(it)
    return out


def run_qa_turn(question: str, intent_result: dict,
                conversation_context: Optional[list] = None, *,
                provider=None, gateway=None, service=None,
                rules: Optional[dict] = None,
                emit=None) -> dict:
    """Run ONE insurance_qa turn. Always returns a schema-valid
    AnswerContext (grounded / partial / refused) — never raises to the
    caller, never dispatches, never registers artifacts."""
    r = rules or ggate.load_rules()
    no_att = gctx.not_attempted_retrieval()

    def _refuse(reason, retrieval=None, generation=None, violations=None):
        return gctx.refused(reason, intent_result, retrieval or no_att,
                            generation=generation, violations=violations)

    # ---- 1. input contract: validated intent, insurance_qa, no pending
    #         clarification (the Router layer guarantees this; we verify).
    #         28.K.7 (S-1, D-K6-1 = B): an insurance-DOMAIN unknown
    #         (intent unknown_insurance_intent + classifier anchor
    #         marker) is also accepted — its intrinsic
    #         clarification_required=True is the "uncertain" signal
    #         itself, not a pending router clarification. Non-insurance
    #         unknowns never reach here (no marker at the seam).
    _intent = (intent_result or {}).get("intent_id") if isinstance(
        intent_result, dict) else None
    _governed_unknown = (
        _intent == "unknown_insurance_intent"
        and "domain:insurance_anchor" in (
            (intent_result or {}).get("reason_codes") or []))
    if (not isinstance(intent_result, dict)
            or gctx.validate_intent(intent_result)
            or (_intent != "insurance_qa" and not _governed_unknown)
            or (intent_result.get("clarification_required")
                and not _governed_unknown)):
        return _refuse("invalid_input")

    # ---- 2. governed retrieval (the ONLY evidence path — K001/K002)
    from knowledge.service import default_service
    svc = service or default_service()
    top_k = int((r.get("retrieval") or {}).get("top_k", 8))
    query = (question or "").strip()
    # 28.K.25: the retrieval milestone reuses the agent loop's EXISTING
    # tool_* event vocabulary (consumer mapping: 正在核实相关资料) — real
    # progress for the QA path's longest opaque phase; no new event type.
    if emit is not None:
        try:
            emit("tool_started", {"step": 1, "tool": "knowledge_search"})
        except Exception:  # noqa: BLE001 — observability only
            pass
    try:
        items, governed, _decisions, _qr = svc.build_evidence(
            query, top_k=top_k)
    except Exception:  # noqa: BLE101 — provider family fails CLOSED
        if emit is not None:
            try:
                emit("tool_failed", {"step": 1, "tool": "knowledge_search"})
            except Exception:  # noqa: BLE001
                pass
        return _refuse("kb_unavailable")
    if emit is not None:
        try:
            emit("tool_completed", {"step": 1, "tool": "knowledge_search"})
        except Exception:  # noqa: BLE101 — observability only
            pass

    gm = (getattr(governed, "retrieval_metadata", None) or {}).get(
        "governance", {})
    retrieval = gctx.retrieval(
        query, top_k, getattr(svc.provider, "name", ""),
        getattr(governed, "status", "success"),
        len(items), gm.get("rejected", 0) or 0,
        bool(getattr(governed, "conflict", False)),
        domain=(r.get("retrieval") or {}).get("domain_default"))

    # 28.K.27-RV4-C2: relevance qualification AFTER the provenance
    # record (retrieval.allowed_hits keeps its governance meaning) and
    # BEFORE assembly — the empty check below now sees QUALIFIED hits,
    # so an all-irrelevant result flows into the existing honest
    # refusal instead of becoming [E1] citation fodder (RV4-A case).
    items = _qualified_evidence(items, query, r)

    if getattr(governed, "status", "") in ("insufficient_evidence",
                                           "retrieval_error") or not items:
        return _refuse("insufficient_evidence", retrieval)

    evidence = [("E%d" % (i + 1),
                 {"content": it.get("content", ""),
                  "header": kb_header(it),
                  "anchor": gctx.anchor(it)})
                for i, it in enumerate(items[:top_k])]

    # ---- 3. conflicting sources: deterministic both-sides answer
    if getattr(governed, "conflict", False):
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
                                  "prompt_version": (r.get("generation")
                                                     or {}).get(
                                      "prompt_version", ""),
                                  "gateway": False, "attempts": 0})
        return _refuse("citation_gate_rejected", retrieval,
                       violations=verdict["violations"])

    # ---- 4. grounded generation via the shared loop (LLM Gateway, D2)
    if gateway is None:
        if provider is None:
            return _refuse("internal_error", retrieval)
        gateway = build_gateway(provider, r)
    return generate_grounded(query, evidence, intent_result, retrieval,
                             gateway, r, system_prompt(r),
                             governed_status=getattr(governed, "status",
                                                     "success"),
                             emit=emit)  # 28.K.22 Policy B streaming
