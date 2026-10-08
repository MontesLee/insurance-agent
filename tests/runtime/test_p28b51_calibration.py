"""Phase 28.B5.1 — model-fit calibration regression + safety tests.

Citation set (spec §4): compliance must improve WITHOUT relaxing the
gate — every malformed/missing/unsupported shape still rejected, valid
single- and multi-evidence answers still accepted.

Timeout set (spec §4): bounded per-attempt watchdog + bounded retry +
fail-closed refusal; no hallucinated AnswerContext, no artifacts.
"""
from __future__ import annotations

import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from runtime.grounding import gate as ggate  # noqa: E402
from runtime.grounding import loop as gloop  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.types import LLMRequest, TimeoutError as LLMTimeout  # noqa: E402
from runtime.qa_agent import run_qa_turn, system_prompt  # noqa: E402
from runtime.product_qa_agent import system_prompt as pq_prompt  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from knowledge.service import reset_default_service  # noqa: E402

EMAP = {"E1": {}, "E2": {}}


# ==========================================================================
# CITATION — the gate itself is UNCHANGED; these pin both directions.
# ==========================================================================

def test_citation_valid_single_evidence_accepted():
    v = ggate.check("重大疾病保险常见等待期为90天[E1]。", EMAP)
    assert v["ok"] and v["cited"] == ["E1"], v


def test_citation_valid_multi_evidence_accepted():
    v = ggate.check(
        "目录未列出该产品专项等待期[E1]。关联资料显示百万医疗险常见等待期"
        "为30天[E2]。等待期内出险一般不予赔付[E2]。", EMAP)
    assert v["ok"] and v["cited"] == ["E1", "E2"], v


def test_citation_fullwidth_parens_rejected():
    # the traced F failure mode: （E1） instead of [E1] — still rejected
    v = ggate.check("等待期一般为90天（E1）。", EMAP)
    assert not v["ok"], v


def test_citation_missing_evidence_ref_rejected():
    v = ggate.check("等待期一般为90天[E9]。", EMAP)
    assert not v["ok"] and "citation:not_in_evidence:E9" in v["violations"]


def test_citation_unsupported_fact_claim_rejected():
    v = ggate.check("等待期一般为90天。", EMAP)
    assert not v["ok"], v


def test_citation_prompt_contract_present_and_externalized():
    # the calibrated prompt lives in the RULES files and names the exact
    # contract (format + the traced failure modes); version bumped
    rules = ggate.load_rules()
    p = system_prompt(rules)
    assert rules["generation"]["prompt_version"] == "qa-answer-v3"
    for marker in ("[E1]", "（E1）", "VALID:", "INVALID:", "推测"):
        assert marker in p, marker
    assert os.path.exists(os.path.join(REPO, "config",
                                       "qa-grounding-rules.yaml"))
    from runtime.product_qa_agent import resolution as pr
    pq_rules = pr.load_rules()
    q = pq_prompt(None, pq_rules)
    assert pq_rules["generation"]["prompt_version"] == \
        "product-qa-answer-v3"
    for marker in ("CATALOG RECORD", "（E1）", "推测", "值得买"):
        assert marker in q, marker


def test_gate_rules_unchanged_core():
    # safety pins: the closure rules and thresholds were NOT weakened
    rules = ggate.load_rules()
    assert rules["gate"]["max_regenerations"] == 1
    assert rules["citation"]["pattern"] == r"\[E([0-9]+)\]"
    assert len(rules["gate"]["fact_markers"]) >= 38
    assert rules["templates"]["citation_gate_rejected"].startswith(
        "本次生成的回答未能通过引用校验")


# ==========================================================================
# TIMEOUT — bounded watchdog + bounded retry + fail-closed
# ==========================================================================

class _Provider:
    """Adapts to the gateway via _GatewayProviderAdapter (the chat-model
    protocol the QA slice wraps): scripted latency / failures."""

    def __init__(self, latency=0.0, fail_first=0, content="等待期为90天[E1]。"):
        self.name = "fake"
        self.model = "fake-model"
        self.latency = latency
        self.fail_first = fail_first
        self.content = content
        self.calls = 0

    def generate(self, messages, tools):
        from runtime.agent.model import LLMResponse
        self.calls += 1
        if self.latency:
            time.sleep(self.latency)
        if self.calls <= self.fail_first:
            raise RuntimeError("transient provider failure")
        return LLMResponse(text=self.content, tool_calls=[],
                           usage={"input_tokens": 5, "output_tokens": 5})


def _gw(provider, timeout=0.5, retries=1):
    return LLMGateway(gloop._GatewayProviderAdapter(provider),
                      timeout_s=timeout, max_retries=retries)


def _req(timeout=0.5):
    return LLMRequest(messages=[{"role": "user", "content": "q"}],
                      system_prompt="s", timeout_s=timeout)


def test_timeout_provider_succeeds_first_attempt():
    p = _Provider()
    resp = _gw(p).generate(_req())
    assert resp.content == "等待期为90天[E1]。" and p.calls == 1


def test_timeout_watchdog_kills_slow_provider():
    p = _Provider(latency=2.0)
    t0 = time.time()
    try:
        _gw(p, timeout=0.3, retries=0).generate(_req(timeout=0.3))
        raise AssertionError("watchdog must fire")
    except LLMTimeout:
        pass
    assert time.time() - t0 < 1.5, "watchdog must bound the wall clock"


def test_timeout_retry_succeeds():
    # a TRANSIENT (retryable) failure — the gateway by design only
    # retries retryable errors (TimeoutError family), never content
    # errors; a raw RuntimeError is intentionally NOT retried
    from runtime.llm.types import TimeoutError as LLMTimeout

    class _Flaky(_Provider):
        def generate(self, messages, tools):
            from runtime.agent.model import LLMResponse
            if _Provider.generate(self, messages, tools) is None:
                pass  # parent returns a response; only its counting runs
            if self.calls == 1:
                raise LLMTimeout("transient timeout", provider=self.name)
            return LLMResponse(text=self.content, tool_calls=[],
                               usage={"input_tokens": 5,
                                      "output_tokens": 5})

    p = _Flaky()
    resp = _gw(p, retries=1).generate(_req())
    assert p.calls == 2 and resp.content


def test_timeout_retry_also_times_out_fails_closed():
    p = _Provider(latency=2.0)
    t0 = time.time()
    from runtime.llm.types import LLMError
    try:
        _gw(p, timeout=0.3, retries=1).generate(_req(timeout=0.3))
        raise AssertionError("must raise")
    except LLMError:
        pass
    assert time.time() - t0 < 2.5, "total budget must stay bounded"


def test_timeout_total_budget_bounded():
    # worst case wall = timeout * (1 + retries) + slack — never the
    # unbounded 174.6s behavior traced in B5
    p = _Provider(latency=5.0)
    t0 = time.time()
    from runtime.llm.types import LLMError
    try:
        _gw(p, timeout=0.4, retries=1).generate(_req(timeout=0.4))
    except LLMError:
        pass
    wall = time.time() - t0
    assert wall < 0.4 * 2 + 1.0, wall


def test_timeout_refuses_fail_closed_no_hallucination():
    # a slow live provider end-to-end: AnswerContext = refusal, valid,
    # zero evidence_refs, template answer (never a fabricated grounded
    # answer and never an artifact)
    reset_default_service()
    ir = classify("重疾险的等待期是什么")
    ctx = run_qa_turn("重疾险的等待期是什么", ir,
                      gateway=_gw(_Provider(latency=5.0), timeout=0.3,
                                  retries=0))
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "llm_unavailable"
    assert ctx["evidence_refs"] == []          # no fabricated citations
    assert ctx["evidence_map"] == {}
    assert "不可用" in ctx["answer"]            # honest template, not fake
    from runtime.grounding import context as gctx
    assert not gctx.validate(ctx)


def test_timeout_no_artifact_side_effect():
    # QA refusals never register artifacts (D1) — enforced again here:
    # the grounding loop has no artifact path at all (structural check)
    import inspect
    src = inspect.getsource(gloop)
    for banned in ("artifact_registry", "reg.register", "artifacts["):
        assert banned not in src, banned


def test_timeout_budget_externalized():
    rules = ggate.load_rules()
    g = rules["generation"]
    # 28.K.10-F1 (owner-authorized): 60 -> 90 per the re-measured
    # provider latency distribution (23-56s, K.9.1 window max 56.2s =
    # 94% of the old budget). Retry budgets unchanged; the fixture pins
    # the CURRENT calibrated values and their bounded worst case.
    assert g["timeout_s"] == 90.0 and g["gateway_max_retries"] == 1
    # observed legitimate slow success (B5 D ~50s; K.9.1 C-window
    # 56.2s) — budget must accommodate it while bounding the worst case
    assert 56.2 < g["timeout_s"]
    assert g["timeout_s"] * (1 + g["gateway_max_retries"]) <= 190.0


if __name__ == "__main__":
    failures = 0
    fns = [v for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    for fn in fns:
        try:
            fn()
            print("PASS %s" % fn.__name__)
        except AssertionError as exc:
            failures += 1
            print("FAIL %s :: %s" % (fn.__name__, exc))
    print("\n%d test(s), %d failure(s)" % (len(fns), failures))
    sys.exit(1 if failures else 0)
