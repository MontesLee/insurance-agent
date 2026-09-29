"""Shared grounded-generation loop (Phase 28.C-1 built / 28.C-2 extracted).

Everything BOTH grounded agents (knowledge QA, product QA) share, and
NOTHING they don't:

    _GatewayProviderAdapter / build_gateway   LLM Gateway wiring (D2)
    kb_header / evidence_block                 evidence prompt assembly
    conflict_answer                            deterministic both-sides
    generate_grounded                          attempts loop: gateway
                                              generation -> citation
                                              closure gate -> ONE bounded
                                              regeneration -> refuse

Per-agent responsibilities stay per-agent (input validation, evidence
RETRIEVAL and scoping, system prompt, slice policy). This module never
routes, never retrieves, never registers artifacts, and never sees an
intent other than as opaque echo fields.
"""
from __future__ import annotations

from typing import Optional

from runtime.llm.types import LLMError, LLMRequest
from runtime.grounding import context as gctx
from runtime.grounding import gate as ggate

_gateway_cache = {"provider": None, "gateway": None}


class _GatewayProviderAdapter:
    """Adapt a runtime.agent.model-style provider (.generate(messages,
    tools) -> model.LLMResponse) to the gateway LLMProvider protocol
    (.generate(LLMRequest) -> types.LLMResponse). Same pattern as
    runtime/llm/glm.py::GLMProvider — a thin translation, no new client."""

    def __init__(self, inner):
        self._inner = inner
        self.name = getattr(inner, "name", "") or "adapted"

    def generate(self, request: LLMRequest):
        # 28.B5.1: enforce request.timeout_s with a wall-clock watchdog —
        # the adapter previously ignored the gateway budget (the wrapped
        # provider's 60s httpx timeout is per-READ, so slow-dripping
        # responses ran far past it: traced 2 x ~87s = 174.6s). Raises
        # llm TimeoutError (retryable) so the gateway's EXISTING retry
        # policy handles it; total budget bounded at
        # timeout_s * (1 + max_retries). Same watchdog pattern as
        # runtime/intent/llm_candidate.py.
        import threading
        from runtime.llm.types import (LLMResponse, LLMUsage,
                                       TimeoutError as LLMTimeout)
        msgs = [{"role": m.get("role", "user"),
                 "content": m.get("content", "")}
                for m in (request.messages or [])]
        box: dict = {}

        def _call():
            try:
                box["resp"] = self._inner.generate(
                    msgs, list(request.tools or []))
            except Exception as exc:  # noqa: BLE001 — surfaced below
                box["err"] = exc

        budget = float(request.timeout_s or 60.0)
        _t = threading.Thread(target=_call, daemon=True,
                              name="qa-gateway-adapter")
        _t.start()
        _t.join(budget)
        if "resp" not in box:
            if _t.is_alive():
                raise LLMTimeout(
                    "adapter watchdog: provider exceeded %.0fs wall "
                    "budget" % budget, provider=self.name)
            raise box.get("err", RuntimeError("no provider response"))
        if "err" in box:
            raise box["err"]
        inner = box["resp"]
        usage = inner.usage or {}
        pt, ct = usage.get("input_tokens"), usage.get("output_tokens")
        return LLMResponse(
            request_id=request.request_id,
            provider=self.name,
            model=getattr(self._inner, "model", "") or request.model or "",
            content=inner.text,
            finish_reason="stop",
            usage=LLMUsage(
                prompt_tokens=pt if isinstance(pt, int) else "UNKNOWN",
                completion_tokens=ct if isinstance(ct, int) else "UNKNOWN",
                total_tokens=(pt + ct if isinstance(pt, int)
                             and isinstance(ct, int) else "UNKNOWN")),
            latency_ms=int(inner.latency_ms or 0))



    def generate_stream(self, request: LLMRequest, on_text):
        """28.K.26: STREAMING variant of generate() — same wall-clock
        watchdog, same error semantics. Forwards ONLY content-kind text
        via on_text (reasoning deltas are consumed and discarded — the
        consumer boundary never sees them); returns the assembled
        response so the existing final gates run unchanged."""
        import threading
        import time as _time
        from runtime.llm.types import (LLMResponse, LLMUsage,
                                       TimeoutError as LLMTimeout)
        msgs = [{"role": m.get("role", "user"),
                 "content": m.get("content", "")}
                for m in (request.messages or [])]
        box: dict = {}

        def _call():
            try:
                stream = getattr(self._inner, "stream_generate", None)
                if stream is None:
                    # no streaming at the provider: fall back to a single
                    # call delivered as one on_text (still under watchdog)
                    resp = self._inner.generate(msgs,
                                                list(request.tools or []))
                    if resp is not None and resp.text:
                        on_text(resp.text)
                    box["resp"] = resp
                    return
                gen = stream(msgs, list(request.tools or []))
                try:
                    while True:
                        delta = next(gen)
                        if delta.get("kind") == "reasoning":
                            continue  # never forwarded — E-2 boundary
                        text = delta.get("text") or ""
                        if text:
                            on_text(text)
                except StopIteration as stop:
                    box["resp"] = stop.value
            except Exception as exc:  # noqa: BLE001 — surfaced below
                box["err"] = exc

        budget = float(request.timeout_s or 60.0)
        _t = threading.Thread(target=_call, daemon=True,
                              name="qa-gateway-adapter-stream")
        _t.start()
        _t.join(budget)
        if "resp" not in box:
            if _t.is_alive():
                raise LLMTimeout(
                    "adapter stream watchdog: provider exceeded %.0fs "
                    "wall budget" % budget, provider=self.name)
            raise box.get("err", RuntimeError("no provider response"))
        if "err" in box:
            raise box["err"]
        inner = box["resp"]
        usage = inner.usage or {}
        pt, ct = usage.get("input_tokens"), usage.get("output_tokens")
        return LLMResponse(
            request_id=request.request_id,
            provider=self.name,
            model=getattr(self._inner, "model", "") or request.model or "",
            content=inner.text,
            finish_reason="stop",
            usage=LLMUsage(
                prompt_tokens=pt if isinstance(pt, int) else "UNKNOWN",
                completion_tokens=ct if isinstance(ct, int) else "UNKNOWN",
                total_tokens=(pt + ct if isinstance(pt, int)
                             and isinstance(ct, int) else "UNKNOWN")),
            latency_ms=int(inner.latency_ms or 0))

def build_gateway(provider, rules: Optional[dict] = None, refresh=False):
    """Process-level gateway (circuit-breaker/rate-limit state survives
    across turns); rebuilt only when the wrapped provider identity
    changes. The gateway itself (runtime/llm/gateway.py) is untouched."""
    from runtime.llm.gateway import LLMGateway
    r = rules or ggate.load_rules()
    gen = r.get("generation") or {}
    if (not refresh and _gateway_cache["gateway"] is not None
            and _gateway_cache["provider"] is provider):
        return _gateway_cache["gateway"]
    strict = False
    try:
        from runtime import mode as rt_mode
        strict = rt_mode.is_strict()
    except Exception:  # noqa: BLE001 — mode probe must never block wiring
        strict = False
    gw = LLMGateway(
        _GatewayProviderAdapter(provider),
        timeout_s=float(gen.get("timeout_s", 30.0)),
        max_retries=int(gen.get("gateway_max_retries", 1)),
        strict_mode=strict)
    _gateway_cache["provider"] = provider
    _gateway_cache["gateway"] = gw
    return gw


def kb_header(item: dict) -> str:
    """Display header for ONE governed WeKnora evidence item (the format
    the 28.C-1 prompt established — unchanged)."""
    return ("source: %s | version: %s | effective: %s ~ %s | authority: %s"
            % (item.get("source_name") or item.get("document_name", ""),
               item.get("version", ""),
               item.get("effective_from") or "?",
               item.get("effective_to") or "open",
               item.get("authority_level", "")))


def evidence_block(evidence: list) -> str:
    """evidence: [(label, {"content": str, "header": str}), ...]"""
    lines = ["Evidence (governed, ACTIVE only):"]
    for label, e in evidence:
        lines.append("[%s] %s" % (label, e["header"]))
        lines.append(e.get("content", ""))
        lines.append("")
    return "\n".join(lines).strip()


def conflict_answer(evidence: list, rules: dict) -> str:
    """Deterministic both-sides presentation (ADR-022: 双方并陈, never
    average, never pick). Each evidence sentence carries its own label so
    the record passes the same closure gate as any grounded answer."""
    templates = rules.get("templates") or {}
    parts = [templates.get("conflicting_evidence",
                           "检索到相互冲突的依据：")]
    for label, e in evidence:
        for seg in ggate.split_sentences(e.get("content", ""), rules)[:6]:
            if seg:
                parts.append("[%s] %s。" % (label, seg.rstrip("。；；;")))
    return "\n".join(parts)


def generate_grounded(question: str, evidence: list, intent_result: dict,
                      retrieval: dict, gateway, rules: dict,
                      system_prompt: str,
                      governed_status: str = "success",
                      product_ref: Optional[dict] = None,
                      emit=None) -> dict:
    """The shared attempts loop. evidence = [(label, {content, header,
    anchor}), ...]. Returns a schema-valid AnswerContext: grounded /
    partial_grounding, or the llm_unavailable / citation_gate_rejected
    refusals. Fail-closed everywhere; never raises to the caller.

    28.K.26 (True LLM Streaming): when `emit` is supplied, generation
    runs through the gateway's STREAMING interface — SENTENCE-LEVEL
    VALIDATED content deltas are emitted DURING generation (each
    complete sentence passes the SAME citation gate before crossing the
    consumer boundary; reasoning never enters the stream). A held
    (gate-fail or trailing incomplete) segment is not streamed; the
    FINAL gate on the assembled full answer remains authoritative and
    arbitrates the terminal result — on final-gate PASS the residual is
    flushed so the streamed content converges to the full answer."""
    import re as _re
    from runtime.consumer_hygiene import sanitize_consumer_text
    from runtime.grounding import claim_support as csupp
    _SENTENCE = _re.compile("[^。！？；\n]*[。！？；\n]+")

    def _make_stream_segmenter():
        state = {"buf": "", "pending": ""}

        def _flush():
            rest = state["pending"] + state["buf"]
            state["pending"] = state["buf"] = ""
            if rest.strip() and emit is not None:
                try:
                    emit("agent_stream_delta",
                         {"kind": "content",
                          "text": sanitize_consumer_text(rest)})
                except Exception:  # noqa: BLE001 — presentation only
                    pass

        def on_text(chunk: str) -> None:
            state["buf"] += chunk
            while True:
                m = _SENTENCE.match(state["buf"])
                if not m:
                    break
                seg = m.group(0)
                state["buf"] = state["buf"][len(seg):]
                if _full_gate(seg)["ok"]:
                    try:
                        emit("agent_stream_delta",
                             {"kind": "content",
                              "text": sanitize_consumer_text(seg)})
                    except Exception:  # noqa: BLE001 — presentation only
                        pass
                else:
                    state["pending"] += seg  # held — final gate decides

        return on_text, _flush
    evidence_map = {label: e["anchor"] for label, e in evidence}

    # 28.K.28-II-IMPL: the production gate = citation closure AND claim
    # support (deterministic; disabled -> identical to ggate alone).
    def _full_gate(text):
        v = ggate.check(text, evidence_map, rules)
        if v["ok"]:
            v = csupp.merge_verdict(v, csupp.check(text, evidence, rules))
        return v
    gen_cfg = rules.get("generation") or {}
    prompt_version = gen_cfg.get("prompt_version", "qa-answer-v1")
    max_regen = int((rules.get("gate") or {}).get("max_regenerations", 1))
    query = (question or "").strip()

    attempts = 0
    last_violations: list = []
    request_id = ""
    for attempt in range(1 + max_regen):
        attempts += 1
        user = "User question: %s\n\n%s" % (
            query, evidence_block([(l, e) for l, e in evidence]))
        if attempt > 0 and last_violations:
            user += ("\n\nYour previous attempt failed the citation gate: "
                     "%s. Fix it: cite [E#] immediately after EVERY "
                     "sentence stating an insurance fact, and use only "
                     "the evidence labels listed above."
                     % "; ".join(last_violations))
        req = LLMRequest(
            messages=[{"role": "user", "content": user}],
            system_prompt=system_prompt,
            max_tokens=int(gen_cfg.get("max_tokens", 1024)),
            timeout_s=float(gen_cfg.get("timeout_s", 30.0)),
            metadata={"purpose": "qa-answer",
                      "prompt_version": prompt_version})
        request_id = req.request_id
        try:
            if emit is not None and hasattr(gateway, "generate_stream"):
                # 28.K.26: TRUE streaming — sentence-validated deltas are
                # emitted DURING generation (T_first_delta < T_final);
                # the final gates below still run on the assembled answer.
                on_text, flush_residual = _make_stream_segmenter()
                resp = gateway.generate_stream(req, on_text)
            else:
                flush_residual = None
                resp = gateway.generate(req)
        except LLMError:
            return gctx.refused("llm_unavailable", intent_result, retrieval,
                                generation={
                                    "provider": getattr(
                                        gateway.provider, "name", ""),
                                    "model": "",
                                    "prompt_version": prompt_version,
                                    "gateway": True,
                                    "attempts": attempts,
                                    "request_id": request_id},
                                product_ref=product_ref)
        answer = (resp.content or "").strip()
        verdict = _full_gate(answer)
        if verdict["ok"]:
            # 28.K.26: residual = held segments + trailing incomplete
            # sentence — emitted ONLY now that the FINAL gate passed
            if flush_residual is not None:
                flush_residual()
            usage = getattr(resp, "usage", None)
            return gctx.grounded(
                answer, verdict["cited"], evidence_map, intent_result,
                retrieval,
                {"provider": resp.provider, "model": resp.model,
                 "prompt_version": prompt_version, "gateway": True,
                 "attempts": attempts, "request_id": request_id,
                 "usage": (usage.to_dict() if usage else None)},
                status=("grounded"
                        if governed_status == "success"
                        else "partial_grounding"),
                product_ref=product_ref)
        last_violations = verdict["violations"]

    return gctx.refused("citation_gate_rejected", intent_result, retrieval,
                        generation={
                            "provider": getattr(gateway.provider, "name", ""),
                            "model": "", "prompt_version": prompt_version,
                            "gateway": True, "attempts": attempts,
                            "request_id": request_id,
                            "gate_violations": last_violations},
                        product_ref=product_ref)
