"""Phase 28.K.7 — P1 remediation regressions (S-1 / S-2 / G-2).

S-1 (D-K6-1 = B): insurance-DOMAIN unknowns take the evidence-governed
knowledge-QA pipeline; non-insurance unknowns keep the generic path.
S-2 (D-K6-2 = ②): SOLUTION_VALIDATION query template calibrated (suffix
cleared) — deterministic, template-only, no free text.
G-2 (D-K6-3): provider 429 normalized into the gateway's bounded retry
with exponential backoff; persistent 429 = honest failure.
"""
from __future__ import annotations

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

from _common import make_client  # noqa: E402

from runtime.agent import FakeLLMProvider  # noqa: E402
from runtime.grounding import gate as ggate  # noqa: E402
from runtime.intent.classifier import classify  # noqa: E402
from runtime.llm import gateway as gw_mod  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.mock import MockLLMProvider  # noqa: E402
from runtime.llm.types import LLMError, LLMRequest, RateLimitError  # noqa: E402
from runtime.qa_agent import run_qa_turn  # noqa: E402
from knowledge.service import reset_default_service  # noqa: E402

GOOD_ANSWER = ("重大疾病保险常见等待期为90天[E1]。"
               "等待期内确诊重疾一般仅退还保费[E1]。")
UNCITED_ADVICE = "建议你直接买XX重疾险，再配一份YY医疗险，越早买越好。"

# --------------------------------------------------------------------------- #
# S-1 — classifier domain marker
# --------------------------------------------------------------------------- #

def test_s1_insurance_unknown_carries_domain_marker():
    r = classify("保险这东西水太深了，我都看不明白")
    assert r["intent_id"] == "unknown_insurance_intent"
    assert "domain:insurance_anchor" in r["reason_codes"]


@pytest.mark.parametrize("text", [
    "今天天气怎么样，适合出去玩吗",
    "帮我写一首诗",
])
def test_s1_non_insurance_unknown_has_no_marker(text):
    r = classify(text)
    assert r["intent_id"] == "unknown_insurance_intent"
    assert "domain:insurance_anchor" not in r["reason_codes"]


# --------------------------------------------------------------------------- #
# S-1 — run_qa_turn input contract (A1/A2/A3)
# --------------------------------------------------------------------------- #

def _unknown_ir():
    reset_default_service()
    return classify("保险这东西水太深了，我都看不明白")


def _gw(content=GOOD_ANSWER):
    return LLMGateway(MockLLMProvider(content=content), max_retries=0)


def test_s1_a2_governed_unknown_with_evidence_answers_grounded():
    ctx = run_qa_turn("重疾险的等待期是什么", _unknown_ir(), gateway=_gw())
    assert ctx["grounding_status"] == "grounded"
    assert ctx["evidence_refs"], "governed answer must cite evidence"
    assert not any(x in ctx["answer"] for x in ("建议你直接买",))
    g = ctx["generation_provenance"]
    assert g["gateway"] is True  # through the governed gateway path


def test_s1_a1_governed_unknown_without_evidence_fails_closed():
    ctx = run_qa_turn("量子保险精算的布里渊区是什么", _unknown_ir(),
                      gateway=_gw())
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "insufficient_evidence"
    assert ctx["answer"], "refusal must still be a consumer-safe message"


def test_s1_a3_induced_recommendation_never_ungoverned():
    """Push for a direct recommendation: with evidence the gate enforces
    citations; uncited advice is rejected (bounded regen) -> refusal."""
    ctx = run_qa_turn("别啰嗦直接说，重疾险的等待期是什么",
                      _unknown_ir(), gateway=_gw(UNCITED_ADVICE))
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "citation_gate_rejected"
    assert "建议你直接买" not in ctx["answer"]  # advice never delivered


def test_s1_contract_rejects_non_governed_unknown_and_clarified_qa():
    weather = classify("今天天气怎么样，适合出去玩吗")
    ctx = run_qa_turn("天气", weather, gateway=_gw())
    assert ctx["grounding_status"] == "refused"
    assert ctx["failure_reason"] == "invalid_input"
    # insurance_qa WITH pending clarification stays invalid (unchanged)
    ir = classify("重疾险的等待期是什么")
    ir["clarification_required"] = True
    ctx2 = run_qa_turn("重疾险的等待期是什么", ir, gateway=_gw())
    assert ctx2["failure_reason"] == "invalid_input"


# --------------------------------------------------------------------------- #
# S-1 — slice wiring e2e (hermetic TestClient)
# --------------------------------------------------------------------------- #

def test_s1_slice_takes_insurance_unknown_governed():
    reset_default_service()
    c, mgr, _ = make_client()
    mgr.agent_provider = FakeLLMProvider([GOOD_ANSWER])
    chat = c.post("/api/chats").json()["chat_id"]
    r = c.post("/api/chats/%s/messages" % chat,
               json={"text": "保险这东西水太深了，我都看不明白"})
    run_id = r.json()["run_id"]
    import time as _t
    for _ in range(120):
        st = c.get("/api/runs/%s" % run_id).json().get("status")
        if st not in ("queued", "running"):
            break
        _t.sleep(0.2)
    evs = c.get("/api/runs/%s/events" % run_id).json()
    evs = evs.get("events", evs) if isinstance(evs, dict) else evs
    types = [e["event_type"] for e in evs]
    qa = [e for e in evs if e["event_type"] == "qa_answered"]
    assert qa, "governed unknown must go through the knowledge-qa slice"
    assert qa[0]["data"]["slice"] == "knowledge-qa"
    assert st == "completed"


def test_s1_non_insurance_unknown_stays_off_the_slice():
    reset_default_service()
    c, mgr, _ = make_client()
    mgr.agent_provider = FakeLLMProvider([("agent_decide", {
        "action": "finish", "message": "今天天气不错，适合出门散步。"})])
    chat = c.post("/api/chats").json()["chat_id"]
    r = c.post("/api/chats/%s/messages" % chat,
               json={"text": "今天天气怎么样，适合出去玩吗"})
    run_id = r.json()["run_id"]
    import time as _t
    for _ in range(120):
        st = c.get("/api/runs/%s" % run_id).json().get("status")
        if st not in ("queued", "running"):
            break
        _t.sleep(0.2)
    evs = c.get("/api/runs/%s/events" % run_id).json()
    evs = evs.get("events", evs) if isinstance(evs, dict) else evs
    assert not [e for e in evs if e["event_type"] == "qa_answered"], \
        "non-insurance unknown must NOT enter the insurance QA pipeline"


# --------------------------------------------------------------------------- #
# G-2 — gateway bounded backoff + 429 normalization
# --------------------------------------------------------------------------- #

class _Scripted:
    def __init__(self, script):
        self.name = "scripted"
        self.model = "m"
        self.script = list(script)
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        from runtime.llm.types import LLMResponse
        return LLMResponse(request_id=request.request_id,
                           provider=self.name, model=self.model,
                           content=item, finish_reason="stop")


@pytest.fixture()
def no_sleep(monkeypatch):
    sleeps = []
    monkeypatch.setattr(gw_mod, "_sleep", lambda s: sleeps.append(s))
    return sleeps


ERR_429 = RuntimeError("LLM provider error 429: rate limited")


def test_g2_normal_request(no_sleep):
    p = _Scripted(["ok"])
    resp = LLMGateway(p, max_retries=2).generate(LLMRequest(messages=[]))
    assert resp.content == "ok" and p.calls == 1 and no_sleep == []


def test_g2_transient_429_recovers_with_backoff(no_sleep):
    p = _Scripted([ERR_429, "recovered"])
    resp = LLMGateway(p, max_retries=2).generate(LLMRequest(messages=[]))
    assert resp.content == "recovered"
    assert p.calls == 2
    assert len(no_sleep) == 1 and no_sleep[0] == gw_mod._RETRY_BACKOFF_S[0]


def test_g2_persistent_429_honest_failure_bounded(no_sleep):
    p = _Scripted([ERR_429, ERR_429, ERR_429, "never"])
    with pytest.raises(RateLimitError):
        LLMGateway(p, max_retries=2).generate(LLMRequest(messages=[]))
    assert p.calls == 3, "exactly 1+max_retries attempts — no unbounded retry"
    assert len(no_sleep) == 2  # backoff between attempts only


def test_g2_non_retryable_fails_immediately(no_sleep):
    p = _Scripted([LLMError("auth", retryable=False)])
    with pytest.raises(LLMError):
        LLMGateway(p, max_retries=2).generate(LLMRequest(messages=[]))
    assert p.calls == 1 and no_sleep == []


def test_g2_backoff_is_exponential_and_bounded():
    assert gw_mod._RETRY_BACKOFF_S[0] < gw_mod._RETRY_BACKOFF_S[-1]
    assert all(0 < s <= 10 for s in gw_mod._RETRY_BACKOFF_S)


# --------------------------------------------------------------------------- #
# S-2 — calibrated deterministic query templates (suffix cleared)
# --------------------------------------------------------------------------- #

def test_s2_solution_validation_templates_deterministic():
    from knowledge.evidence.request import build_query_text
    assert build_query_text("general", "SOLUTION_VALIDATION") == "保险 保障 责任"
    assert build_query_text(
        "medical", "SOLUTION_VALIDATION") == "百万医疗险 保障范围 免赔额 社保目录外"
    assert build_query_text(
        "critical_illness", "SOLUTION_VALIDATION") == "重疾险 确诊给付 保额 收入补偿"
    # other purposes unchanged (still purpose-suffixed, still template-only)
    assert build_query_text(
        "general", "POLICY_FACT") == "保险 保障 责任 条款 约定"


def test_s2_rules_templates_static_no_free_text():
    from knowledge.evidence.request import load_rules
    r = load_rules()
    for dom, tpl in r["domain_query_template"].items():
        assert isinstance(tpl, str) and tpl.strip(), dom
    for purpose, suffix in r["purpose_query_suffix"].items():
        assert isinstance(suffix, str), purpose
    # determinism: same input -> same query
    from knowledge.evidence.request import build_query_text
    assert build_query_text("medical", "SOLUTION_VALIDATION") == \
        build_query_text("medical", "SOLUTION_VALIDATION")
