"""Phase 28.K.11-F2 — gateway call-log observability tests.

T1 success record · T2 timeout classification · T3 retryable with
attempt numbers · T4 persistent exhaustion trail · T5 non-retryable
no-retry · T6 no secret/PII leakage · T7 existing behavior unchanged
(covered by the battery; here: business outcomes identical shapes).
"""
from __future__ import annotations

import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
sys.path.insert(0, HERE)

import runtime.obs as obs  # noqa: E402
from runtime.llm import gateway as gw_mod  # noqa: E402
from runtime.llm.gateway import LLMGateway  # noqa: E402
from runtime.llm.types import (LLMError, LLMRequest,  # noqa: E402
                               RateLimitError, TimeoutError)

SECRET = "sk-SECRETKEY123456"


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
def cap(monkeypatch):
    # runtime.obs re-exports the log() FUNCTION, shadowing the submodule
    # attribute — fetch the real module object from sys.modules.
    import importlib
    obs_log_mod = importlib.import_module("runtime.obs.log")

    class _Sink(obs_log_mod.JsonlLogger):
        """Real pipeline (classification + redaction), zero output:
        path=None writes nothing; we only keep the returned records."""
        def __init__(self):
            super().__init__(path=None, mirror_stderr=False)
            self.records = []

        def emit(self, event, **kw):
            rec = super().emit(event, **kw)
            self.records.append(rec)
            return rec
    sink = _Sink()
    monkeypatch.setattr(obs_log_mod, "default_logger", lambda: sink)
    return sink


def _llm_calls(sink):
    return [r for r in sink.records if r.get("event") == "llm.call"]


def _req(**kw):
    return LLMRequest(messages=[], metadata={"purpose": "qa-answer"}, **kw)


def test_t1_success_record(cap):
    p = _Scripted(["ok"])
    resp = LLMGateway(p, max_retries=1).generate(_req())
    assert resp.content == "ok"
    recs = _llm_calls(cap)
    assert len(recs) == 1
    r = recs[0]
    assert r["status"] == "OK" and r["attempt"] == 0  # 0-based
    assert r["request_id"] and r["purpose"] == "qa-answer"
    assert r["duration_ms"] is not None


def test_t2_timeout_classified(cap):
    p = _Scripted([TimeoutError("LLM timeout after 90s: x")])
    with pytest.raises(LLMError):
        LLMGateway(p, max_retries=0).generate(_req())
    r = _llm_calls(cap)[0]
    assert r["timeout"] is True
    assert r["error"]["error_class"]  # classified, not opaque
    assert r["error"]["retryable"] is True
    assert r["duration_ms"] is not None  # failed attempt duration kept


def test_t3_retryable_attempts_visible(cap, monkeypatch):
    monkeypatch.setattr(gw_mod, "_sleep", lambda s: None)
    p = _Scripted([RateLimitError("LLM 429 rate limited"),
                   "recovered"])
    resp = LLMGateway(p, max_retries=2).generate(_req())
    assert resp.content == "recovered"
    recs = _llm_calls(cap)
    assert [r["attempt"] for r in recs] == [0, 1]  # 0-based
    assert recs[0]["status"] == "RETRY"
    assert recs[0]["error"]["retryable"] is True
    assert recs[0]["error"]["error_class"]


def test_t4_persistent_failure_full_trail(cap, monkeypatch):
    monkeypatch.setattr(gw_mod, "_sleep", lambda s: None)
    p = _Scripted([RateLimitError("429"), RateLimitError("429"),
                   RateLimitError("429")])
    with pytest.raises(RateLimitError):
        LLMGateway(p, max_retries=2).generate(_req())
    recs = _llm_calls(cap)
    assert [r["status"] for r in recs] == ["RETRY", "RETRY", "RETRY",
                                           "EXHAUSTED"]
    assert [r["attempt"] for r in recs] == [0, 1, 2, 2]  # 0-based
    assert all(r["error"]["error_class"] for r in recs)


def test_t5_non_retryable_no_fake_retry(cap):
    p = _Scripted([LLMError("auth", retryable=False),
                   "never"])
    with pytest.raises(LLMError):
        LLMGateway(p, max_retries=2).generate(_req())
    recs = _llm_calls(cap)
    assert [r["status"] for r in recs] == ["FAIL"]
    assert p.calls == 1  # exactly one provider call — no fake retry
    # the RETRY DECISION is the status (FAIL = not retried); the error
    # block's `retryable` is the taxonomy's CLASS-level view (LLM-GENERIC
    # is classed retryable), not the instance flag — both are recorded.
    assert recs[0]["error"]["error_class"]


def test_t6_no_secret_or_payload_leakage(cap, monkeypatch):
    monkeypatch.setattr(gw_mod, "_sleep", lambda s: None)

    class _Leaky(_Scripted):
        def generate(self, request):
            self.calls += 1
            raise RuntimeError(
                "LLM provider error 429: key=%s prompt=买重疾险给白血病 "
                "response=fake" % SECRET)

    p = _Leaky([])
    with pytest.raises(LLMError):
        LLMGateway(p, max_retries=1).generate(_req())
    blob = json.dumps(cap.records, ensure_ascii=False, default=str)
    for bad in (SECRET, "买重疾险", "response=fake", "Authorization",
                "api_key", '"messages"', '"prompt"'):
        assert bad not in blob, bad
    for r in _llm_calls(cap):
        assert r.get("error", {}).get("error_class")


def test_t7_business_outcomes_unchanged(cap, monkeypatch):
    """The observation additions cannot alter results: same scripted
    inputs produce identical responses/raises with the sink active."""
    monkeypatch.setattr(gw_mod, "_sleep", lambda s: None)
    p = _Scripted([RateLimitError("429"), "fine"])
    resp = LLMGateway(p, max_retries=2).generate(_req())
    assert resp.content == "fine" and p.calls == 2
    p2 = _Scripted([LLMError("fatal", retryable=False)])
    with pytest.raises(LLMError):
        LLMGateway(p2, max_retries=2).generate(_req())
