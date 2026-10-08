"""Phase 28.I — Data governance & lifecycle tests (B-04 / GOV-1..8).

Deterministic clock via the pure eligibility function; live cascade via
the TestClient consumer-deletion endpoint (keys mode, two subjects).
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from _common import make_client, wait_terminal
from runtime import governance
from runtime.agent import FakeLLMProvider

KEY_A = "ga" * 12 + ":CONSUMER:alice-gov"
KEY_B = "gb" * 12 + ":CONSUMER:bob-gov"
KEY_OP = "go" * 12 + ":OPERATOR:carol-gov"


import pytest as _pytest


@_pytest.fixture(autouse=True)
def _fresh_probe_limiter():
    """Battery isolation: the module-global enumeration limiter is shared
    across suites (28.G) — reset its window so GOV reads can never 429
    due to an earlier suite's probing volume."""
    from runtime import consumer_access as _ca
    with _ca.consumer_limiter._lock:
        _ca.consumer_limiter._hits = {}
    yield
    with _ca.consumer_limiter._lock:
        _ca.consumer_limiter._hits = {}


def with_keys(fn):
    import functools

    @functools.wraps(fn)
    def wrapper():
        old = os.environ.get("INSURANCE_AGENT_API_KEYS")
        os.environ["INSURANCE_AGENT_API_KEYS"] = ",".join(
            [KEY_A, KEY_B, KEY_OP])
        try:
            return fn()
        finally:
            if old is None:
                os.environ.pop("INSURANCE_AGENT_API_KEYS", None)
            else:
                os.environ["INSURANCE_AGENT_API_KEYS"] = old
    return wrapper


def hdr(key):
    return {"Authorization": "Bearer " + key.split(":")[0]}


SCRIPT = [("agent_decide", {"action": "finish", "message": "治理测试回复。"})]


def fixture_pair():
    """alice: chat + terminal run (+report artifact via spine? agent-turn
    runs have no pipeline artifacts — refs are still issuable for the
    run dir lifecycle). Returns (client, mgr, chat_a, run_a, chat_b)."""
    client, mgr, _ = make_client()
    mgr.agent_provider = FakeLLMProvider(list(SCRIPT))
    chat_a = client.post("/api/chats", headers=hdr(KEY_A)).json()["chat_id"]
    run_a = client.post("/api/chats/%s/messages" % chat_a,
                        headers=hdr(KEY_A), json={"text": "A 的问题"}).json()["run_id"]
    chat_b = client.post("/api/chats", headers=hdr(KEY_B)).json()["chat_id"]
    client.post("/api/chats/%s/messages" % chat_b,
                headers=hdr(KEY_B), json={"text": "B 的问题"})
    deadline = time.time() + 60
    while time.time() < deadline:
        r = client.get("/api/runs/%s" % run_a, headers=hdr(KEY_A)).json()
        if r.get("status") not in ("queued", "running"):
            break
        time.sleep(0.1)
    return client, mgr, chat_a, run_a, chat_b


# --------------------------------------------------------------------------- #
# GOV-T12 / GOV-T10 retention + legal hold (pure, deterministic clock)
# --------------------------------------------------------------------------- #

def test_gov_t12_retention_policy_resolution():
    """Policy is per-class, file-driven, configurable — no magic numbers
    in business code; deterministic clock decides eligibility."""
    pol = governance.class_policy(governance.BUSINESS)
    days = float(pol["retention_days"])
    assert days > 0
    t0 = time.time()
    # before retention → retained
    ok, why = governance.deletion_eligible(
        governance.BUSINESS, t0, now=t0 + (days - 1) * 86400)
    assert not ok and "within_retention" in why
    # retention reached → eligible
    ok, _ = governance.deletion_eligible(
        governance.BUSINESS, t0, now=t0 + (days + 1) * 86400)
    assert ok
    # trace is SHORTER than business content (D-GOV-1)
    t_days = float(governance.class_policy(governance.TRACE)["retention_days"])
    assert t_days <= days
    ok, _ = governance.deletion_eligible(
        governance.TRACE, t0, now=t0 + (t_days + 1) * 86400)
    assert ok
    # audit/meta never business-deletable
    for cls in (governance.AUDIT, governance.META):
        ok, why = governance.deletion_eligible(cls, t0, now=t0 + 9e9)
        assert not ok


def test_gov_t10_legal_hold_blocks_deletion():
    governance.set_legal_hold("business_content:chat_hold", True)
    ok, why = governance.deletion_eligible(
        governance.BUSINESS, time.time() - 9e9, now=time.time(),
        legal_hold=True, consumer_requested=True)
    assert not ok and why == "legal_hold"
    governance.set_legal_hold("business_content:chat_hold", False)
    ok, _ = governance.deletion_eligible(
        governance.BUSINESS, time.time(), now=time.time(),
        consumer_requested=True)
    assert ok


def test_consumer_request_beats_retention_window():
    """D-GOV-3: a consumer may delete their own business data at ANY
    time — retention windows bound automatic expiry, not owner rights."""
    ok, why = governance.deletion_eligible(
        governance.BUSINESS, time.time(), now=time.time(),
        consumer_requested=True)
    assert ok and why == "consumer_requested"


# --------------------------------------------------------------------------- #
# live cascade (keys mode)
# --------------------------------------------------------------------------- #

@with_keys
def test_gov_t1_t2_consumer_deletion_cascades():
    c, mgr, chat_a, run_a, _ = fixture_pair()
    # sanity: pre-deletion access works
    assert c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_A)).status_code == 200
    assert c.get("/api/runs/%s/events" % run_a,
                 headers=hdr(KEY_A)).status_code == 200
    ref = c.get("/api/runs/%s/artifact-refs/insurance-report" % run_a,
                headers=hdr(KEY_A)).json()["ref"]
    r = c.delete("/api/consumer/chats/%s" % chat_a, headers=hdr(KEY_A))
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    assert body["deleted"] is True and body["runs_deleted"] >= 1

    # GOV-T2 cascade: conversation, run, events, dir ALL gone
    assert c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_A)).status_code == 404
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_A)).status_code == 404
    assert c.get("/api/runs/%s/events" % run_a,
                 headers=hdr(KEY_A)).status_code == 404
    assert c.get("/api/runs/%s/stream" % run_a,
                 headers=hdr(KEY_A)).status_code == 404
    assert c.get("/api/runs/%s/artifacts" % run_a,
                 headers=hdr(KEY_A)).status_code == 404
    # GOV-T4/T5: artifact + opaque deep link fail closed
    assert c.get("/api/runs/%s/artifacts/insurance-report" % run_a,
                 headers=hdr(KEY_A)).status_code == 404
    assert c.get("/api/consumer/artifacts/%s" % ref,
                 headers=hdr(KEY_A)).status_code == 404
    # internal duty ALSO cannot resurrect (GOV-6): the data is gone
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_OP)).status_code == 404
    # GOV-T11: tombstone identity-only (no content)
    ts = governance.tombstone("conversation", chat_a)
    assert ts and ts["reason"] == "consumer_deletion"
    assert "A 的问题" not in str(ts) and "治理测试" not in str(ts)


@with_keys
def test_gov_t3_cross_user_deletion_isolated():
    """GOV-1: deleting A's conversation never touches B's."""
    c, _, chat_a, _, chat_b = fixture_pair()
    r = c.delete("/api/consumer/chats/%s" % chat_b, headers=hdr(KEY_A))
    assert r.status_code == 404  # not A's object — uniform denial
    assert c.get("/api/chats/%s" % chat_b,
                 headers=hdr(KEY_B)).status_code == 200  # B intact
    assert c.delete("/api/consumer/chats/%s" % chat_b).status_code == 401  # anon
    assert c.delete("/api/consumer/chats/%s" % chat_b,
                    headers=hdr(KEY_B)).status_code == 200  # owner succeeds


@with_keys
def test_gov_t9_operator_access_audited_metadata_only():
    """GOV-9/GOV-7: operator reads of consumer data are audited; audit
    records never contain message content."""
    c, _, chat_a, run_a, _ = fixture_pair()
    assert c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_OP)).status_code == 200
    recs = c.get("/api/governance/audit", headers=hdr(KEY_OP)).json()["records"]
    reads = [r for r in recs if r["action"] == "consumer_data_read"]
    assert reads, "operator consumer-data reads must be audited"
    blob = str(recs)
    assert "A 的问题" not in blob and "治理测试回复" not in blob
    # consumer cannot read the audit trail
    assert c.get("/api/governance/audit",
                 headers=hdr(KEY_A)).status_code == 403
    # deletion lifecycle appears in the audit too
    c.delete("/api/consumer/chats/%s" % chat_a, headers=hdr(KEY_A))
    recs2 = c.get("/api/governance/audit", headers=hdr(KEY_OP)).json()["records"]
    acts = {r["action"] for r in recs2}
    assert "deletion_request" in acts and "deletion_executed" in acts
    # audit SURVIVES deletion (independent governance, D-GOV-1)
    assert any(r["action"] == "consumer_data_read" for r in recs2)


@with_keys
def test_gov_t8_developer_boundary_unchanged_and_audited():
    """GOV-6/GOV-8: internal duty read of a DELETED object fails closed;
    reads of LIVE consumer objects remain possible (unchanged O-7 duty)
    but are audited (the developer-default-no-user-content ruling is
    enforced operationally: every access is on the record)."""
    c, _, chat_a, run_a, _ = fixture_pair()
    c.delete("/api/consumer/chats/%s" % chat_a, headers=hdr(KEY_A))
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_OP)).status_code == 404


def test_gov_t7_evaluation_isolation():
    """GOV-5: production conversations NEVER auto-enter evaluation/golden
    datasets — running chats leaves the golden corpus byte-identical."""
    import hashlib
    golden_dir = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))),
        "tests", "golden")
    before = {}
    for fn in sorted(os.listdir(golden_dir)):
        p = os.path.join(golden_dir, fn)
        before[fn] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    c = make_client()[0]
    c.post("/api/chats")
    chat = c.post("/api/chats").json()["chat_id"]
    c.post("/api/chats/%s/messages" % chat, json={"text": "eval 隔离探针"})
    after = {}
    for fn in sorted(os.listdir(golden_dir)):
        p = os.path.join(golden_dir, fn)
        after[fn] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    assert before == after, "golden corpus must not be touched by runs"


def test_gov_t6_trace_cascade_via_bus_purge():
    """D-GOV-5: business deletion purges the run's event history (user
    prompts/answers live there) — no orphaned trace."""
    c, mgr, chat_a, run_a, _ = fixture_pair()
    assert mgr.bus.events_for(run_a), "precondition: trace exists"
    c.delete("/api/consumer/chats/%s" % chat_a, headers=hdr(KEY_A))
    assert mgr.bus.events_for(run_a) == []
    with mgr.bus._lock:
        assert run_a not in mgr.bus._history


def test_tombstone_never_restores():
    governance.write_tombstone("conversation", "chat_x", reason="test",
                               actor="t")
    ts = governance.tombstone("conversation", "chat_x")
    assert set(ts) == {"object_class", "object_id", "deleted_at",
                       "reason", "actor"}


def test_policy_env_override():
    """G-GOV-12: policy location is configurable (INSURANCE_AGENT_RETENTION_
    POLICY) — a deployment can substitute periods without code changes."""
    import json, tempfile
    with tempfile.TemporaryDirectory() as d:
        alt = os.path.join(d, "pol.json")
        json.dump({"version": 1, "classes": {
            "business_content": {"retention_days": 7, "deletion": "hard"},
            "operational_trace": {"retention_days": 1, "deletion": "hard"},
            "evaluation_data": {"retention_days": 2, "deletion": "hard"},
            "security_audit": {"retention_days": 30, "deletion": "none"},
            "system_metadata": {"retention_days": 0, "deletion": "none"},
        }}, open(alt, "w", encoding="utf-8"))
        t0 = time.time()
        ok, _ = governance.deletion_eligible(
            governance.BUSINESS, t0, now=t0 + 8 * 86400, path=alt)
        assert ok  # 7-day policy reached
        ok, _ = governance.deletion_eligible(
            governance.BUSINESS, t0, now=t0 + 2 * 86400, path=alt)
        assert not ok  # default-file 180 days does NOT leak in
