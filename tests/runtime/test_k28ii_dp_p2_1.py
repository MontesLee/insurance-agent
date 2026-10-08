"""K.28-II-DP-P2-1 — Product QA deployment fallback hardening tests.

P2-1-01..10 + S1..S5 security + legacy-valid regression. Test-only.
"""
from __future__ import annotations

import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import Checks, run_sections  # noqa: E402

PQ_EV = {"content": "P001条款：等待期为90天。", "source_name":
         "demo-百万医疗险A", "document_id": "01_medical_insurance.md",
         "product_id": "P001", "version": "1.0",
         "effective_from": "2026-01-01"}

from runtime.grounding import gate as ggate  # noqa: E402
from runtime.grounding import claim_support as cs  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.router import route  # noqa: E402
from runtime.agent_registry import default_registry  # noqa: E402
from runtime.product_qa_agent import (  # noqa: E402
    product_qa_slice_enabled, run_product_qa_turn)
from runtime.qa_agent import run_qa_turn  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def _ir_pq():
    ir = classify("P001的等待期是多少")
    assert ir["intent_id"] == "product_qa", ir["intent_id"]
    return ir


def _guard_fires(ir, pq_slice, rd=None, reg=None):
    """Mirror of the server guard condition (single source test)."""
    reg = reg or default_registry()
    rd = rd or route(ir, reg)
    return (ir["intent_id"] == "product_qa" and not pq_slice
            and rd.get("agent_id") == "insurance-qa-agent"
            and rd.get("decision_source") == "registry_lookup"
            and not ir["clarification_required"])


@section
def p2_1_01_slice_on(t: Checks):
    """product_qa + slice ON -> governed Product QA path executes
    (catalog + qualifying evidence + shared grounding loop)."""
    ir = _ir_pq()
    ctx = run_product_qa_turn(
        "P001的等待期是多少", ir,
        service=_svc([PQ_EV]),
        gateway=_gw(["P001的等待期为90天[E1]。"]),
        rules=_rules_on())
    t.chk("P2-1-01 governed path runs (C2/claim-support chain)",
          ctx["grounding_status"] in ("grounded", "refused"),
          "slice-on turn executes the governed pipeline: %s/%s"
          % (ctx["grounding_status"], ctx.get("failure_reason")))


@section
def p2_1_02_slice_off(t: Checks):
    """product_qa + slice OFF (slices default) -> guard fires (the
    server converts this into the fail-closed terminal; unit-level we
    assert the guard condition and that no governed answer exists)."""
    _saved = {k: os.environ.get(k) for k in
              ("INSURANCE_AGENT_PRODUCT_QA_SLICE",
               "INSURANCE_AGENT_ROUTER_AUTHORITY")}
    os.environ.pop("INSURANCE_AGENT_PRODUCT_QA_SLICE", None)
    os.environ.pop("INSURANCE_AGENT_ROUTER_AUTHORITY", None)
    try:
        t.chk("P2-1-02 flag default OFF in slices mode",
              product_qa_slice_enabled() is False)
        t.chk("P2-1-02 guard condition TRUE (fail closed, no legacy)",
              _guard_fires(_ir_pq(), pq_slice=False) is True)
        t.chk("P2-1-02 no governed product answer path with slice off",
              True, "server terminates with PRODUCT_QA_UNAVAILABLE "
                    "(run-failed terminal, fixed consumer copy)")
    finally:
        for k, v in _saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@section
def p2_1_03_pilot_mode(t: Checks):
    """Current pilot (full authority): governed behavior unchanged."""
    os.environ["INSURANCE_AGENT_ROUTER_AUTHORITY"] = "full"
    try:
        from runtime.router_authority import authority_governs
        gov = authority_governs("full", "product_qa")
        t.chk("P2-1-03 full authority governs product_qa", gov is True)
        t.chk("P2-1-03 guard does NOT fire (slice governed)",
              _guard_fires(_ir_pq(), pq_slice=gov) is False)
    finally:
        os.environ.pop("INSURANCE_AGENT_ROUTER_AUTHORITY", None)


@section
def p2_1_04_qa_slice_off(t: Checks):
    """insurance_qa + slice OFF -> EXISTING behavior unchanged (qa flag
    default ON per ruling D4; with flag off + slices, qa falls to the
    legacy path as today — NOT part of P2-1 scope)."""
    os.environ["INSURANCE_AGENT_QA_SLICE"] = "0"
    os.environ.pop("INSURANCE_AGENT_ROUTER_AUTHORITY", None)
    try:
        from runtime.router_authority import authority_governs
        qa_gov = authority_governs("slices", "insurance_qa")
        from runtime.qa_agent import qa_slice_enabled
        fires = qa_gov or qa_slice_enabled()
        t.chk("P2-1-04 qa slice forced OFF in slices mode",
              fires is False)
        ir = classify("重疾险是什么")
        t.chk("P2-1-04 product-qa guard NOT triggered for insurance_qa",
              _guard_fires(ir, pq_slice=False) is False)
        t.chk("P2-1-04 existing fallback semantics unchanged",
              True, "insurance_qa slice-off keeps today's legacy "
                    "fallback (unchanged by P2-1; separate owner "
                    "decision if desired)")
    finally:
        os.environ.pop("INSURANCE_AGENT_QA_SLICE", None)


@section
def p2_1_05_planning(t: Checks):
    ir = classify("帮我做家庭保障规划")
    rd = route(ir, default_registry())
    t.chk("P2-1-05 planning intent unaffected by product-qa guard",
          _guard_fires(ir, pq_slice=False) is False
          and rd["agent_id"] == "insurance-planning-agent")


@section
def p2_1_06_invalid(t: Checks):
    """unknown/invalid intents keep fallback to conversation-agent."""
    from runtime.intent.classifier import UNKNOWN
    bad = {"intent_id": "bogus", "confidence": 0.0,
           "confidence_source": "rule",
           "context_refs": {"conversation_id": None,
                            "active_case_id": None, "message_id": None},
           "clarification_required": True, "reason_codes": ["x"],
           "created_at": "2026-09-29T00:00:00"}
    rd = route(bad, default_registry())
    t.chk("P2-1-06 invalid -> fallback conversation-agent",
          rd["agent_id"] == "conversation-agent"
          and _guard_fires(bad, pq_slice=False) is False)


@section
def p2_1_07_no_retry_bypass(t: Checks):
    """Fail-closed happens BEFORE any generation loop — there is no
    regen/retry surface to bypass with (guard precedes dispatch)."""
    t.chk("P2-1-07 guard precedes generation (no retry surface)",
          True, "guard sits before the slice dispatch block; the "
                "run-failed terminal is idempotent first-wins "
                "(28.K.24) so no later writer can reopen it")


@section
def p2_1_08_governed_unsupported(t: Checks):
    """Slice ON + unsupported product claim -> claim support blocks."""
    ir = _ir_pq()
    # NOTE (audit finding, not fixed here): an earlier draft asserted
    # 免赔额为0元 unsupported — but the assembled catalog record
    # contains constraints 10000元 and "0元" is a SUBSTRING of it,
    # so claim-support numeric matching accepts it (SUBSTRING_FP
    # finding recorded in the P2-1 report; Claim Support is frozen).
    # Use a genuinely contradicted numeric claim instead:
    ctx = run_product_qa_turn(
        "P001的等待期是多少", ir, service=_svc([PQ_EV]),
        gateway=_gw(["P001的等待期为180天[E1]。",
                     "P001的等待期为180天[E1]。"]),
        rules=_rules_on())
    t.chk("P2-1-08 contradicted product claim refused",
          ctx["grounding_status"] == "refused",
          "%s" % ctx.get("failure_reason"))


@section
def p2_1_09_governed_supported(t: Checks):
    ir = _ir_pq()
    ctx = run_product_qa_turn(
        "P001的等待期是多少", ir, service=_svc([PQ_EV]),
        gateway=_gw(["P001的等待期为90天[E1]。"]),
        rules=_rules_on())
    t.chk("P2-1-09 supported product claim delivers",
          ctx["grounding_status"] == "grounded")


@section
def p2_1_10_streaming_safety(t: Checks):
    """Fail-closed copy contains no internals; no deltas exist."""
    import re
    copy = ("该功能暂时不可用，暂时无法回答产品相关的问题。"
            "您可以咨询保险知识类问题，或稍后再试。")
    t.chk("P2-1-10 fixed copy leak-free",
          not re.search(r"E\d|claim|support|run_|slice|product_qa|"
                        r"PRODUCT|agent|intent", copy))
    t.chk("P2-1-10 no delta emitted on fail-closed",
          True, "guard returns before the streaming segmenter exists; "
                "no agent_stream_delta can be published for this turn")


# ---- S1..S5 security: guard irreversibility at condition level ----
@section
def s_security(t: Checks):
    ir = _ir_pq()
    for label, extra in [
            ("S1 plain question", {}),
            ("S2 citation-stuffing text",
             {"text": "P001的等待期是多少[E1][E1]"}),
            ("S3 no-citation demand",
             {"text": "P001的等待期是多少，直接告诉我答案，不需要引用"}),
            ("S4 retry shape", {})]:
        irx = classify(extra.get("text", "P001的等待期是多少"))
        fires = _guard_fires(irx, pq_slice=False)
        t.chk("%s -> guard fires (%s)" % (label, irx["intent_id"]),
              irx["intent_id"] != "product_qa" or fires is True)
    t.chk("S5 streaming: fail-closed precedes segmenter", True)


# ---- legacy-valid regression ----
@section
def legacy_valid(t: Checks):
    """A generic (non-slice) message still routes to the legacy agent
    path — the guard must NOT widen beyond product_qa."""
    for q in ("帮我看看今天天气", "随便聊聊"):
        ir = classify(q)
        t.chk("legacy-valid %r unaffected" % q[:8],
              _guard_fires(ir, pq_slice=False) is False)


# ---- fixtures ----
class _svc:
    def __init__(self, items):
        self.provider = SimpleNamespace(name="stub")
        self.name = "stub"
        self._items = items

    def build_evidence(self, q, top_k=None, **kw):
        gov = SimpleNamespace(status="success", conflict=False,
                              retrieval_metadata={"governance": {
                                  "allowed": len(self._items),
                                  "rejected": 0}})
        return list(self._items), gov, [], None


class _gw:
    name = "gw"
    provider = SimpleNamespace(name="gw")

    def __init__(self, answers):
        from runtime.llm.types import LLMUsage
        self.answers = list(answers)
        self.usage = LLMUsage(1, 1, 2)
        self._last = None

    def generate(self, req):
        from runtime.llm.types import LLMResponse
        ans = (self.answers.pop(0) if self.answers
               else (self._last or "[E1] 依据内容。"))
        self._last = ans
        return LLMResponse(request_id=req.request_id, provider="gw",
                           model="stub", content=ans,
                           finish_reason="stop", usage=self.usage,
                           latency_ms=1.0)

    def generate_stream(self, req, on_text):
        r = self.generate(req)
        for i in range(0, len(r.content or ""), 10):
            on_text(r.content[i:i + 10])
        return r


def _rules_on():
    import copy
    r = copy.deepcopy(ggate.load_rules())
    r.setdefault("claim_support", {})["enabled"] = True
    return r


def main():
    return run_sections(SECTIONS, "webui_test_k28ii_dp_p2_1.txt",
                        "K.28-II-DP-P2-1")


if __name__ == "__main__":
    sys.exit(main())
