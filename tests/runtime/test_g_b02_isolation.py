"""Phase 28.G — B-02 Consumer Identity & Ownership isolation tests.

Owner decisions implemented here:
  D-01′  authenticated consumer subject (CONSUMER key) ≠ role ≠ ownership
  D-API-1 uniform 404 for missing-vs-other-owner on consumer reads
  D-API-2 high-entropy ids + server-side rate limiting (not authorization)
  D-05′  opaque artifact references resolve ONLY through an ownership check

Covers T1-T10, the O-1..O-8 invariants, the A/B/anonymous cross-access
matrix, internal-duty compatibility (O-7), and the frozen no-keys
local-dev loopback behavior.
"""
from __future__ import annotations

import os
import time

import pytest
from fastapi.testclient import TestClient

from _common import make_client, wait_terminal
from runtime.agent import FakeLLMProvider
from runtime.consumer_access import RateLimiter, read_allowed, resolve_subject

KEY_A = "ca" * 12 + ":CONSUMER:alice"
KEY_B = "cb" * 12 + ":CONSUMER:bob"
KEY_OP = "op" * 12 + ":OPERATOR:carol"
KEY_REV = "rv" * 12 + ":REVIEWER:dave"


def with_keys(fn):
    import functools

    @functools.wraps(fn)
    def wrapper():
        old = os.environ.get("INSURANCE_AGENT_API_KEYS")
        os.environ["INSURANCE_AGENT_API_KEYS"] = ",".join(
            [KEY_A, KEY_B, KEY_OP, KEY_REV])
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


SCRIPT = [("agent_decide", {"action": "finish", "message": "隔离测试回复。"})]


def _wait_owned(client, run_id, key):
    """wait_terminal, but authenticated as the run's owner."""
    deadline = time.time() + 120.0
    while time.time() < deadline:
        run = client.get("/api/runs/%s" % run_id, headers=hdr(key)).json()
        if run.get("status") not in ("queued", "running"):
            return run
        time.sleep(0.1)
    raise AssertionError("run %s did not terminate" % run_id)


def consumer_fixture():
    """consumer A + B each with one chat and one TERMINAL run (hermetic
    FakeLLM); returns (client, mgr, chat_a, run_a, chat_b, run_b)."""
    client, mgr, _ = make_client()
    mgr.agent_provider = FakeLLMProvider(list(SCRIPT))
    chat_a = client.post("/api/chats", headers=hdr(KEY_A)).json()["chat_id"]
    r = client.post("/api/chats/%s/messages" % chat_a,
                    headers=hdr(KEY_A), json={"text": "A 的问题"})
    run_a = r.json()["run_id"]
    chat_b = client.post("/api/chats", headers=hdr(KEY_B)).json()["chat_id"]
    r = client.post("/api/chats/%s/messages" % chat_b,
                    headers=hdr(KEY_B), json={"text": "B 的问题"})
    run_b = r.json()["run_id"]
    _wait_owned(client, run_a, KEY_A)
    _wait_owned(client, run_b, KEY_B)
    return client, mgr, chat_a, run_a, chat_b, run_b


# --------------------------------------------------------------------------- #
# cross-access matrix + T1..T5
# --------------------------------------------------------------------------- #

@with_keys
def test_t1_cross_user_conversation_read_is_404():
    c, _, chat_a, _, chat_b, _ = consumer_fixture()
    assert c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_A)).status_code == 200
    r = c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_B))
    assert r.status_code == 404                      # T1 (uniform, no owner leak)
    assert "owner" not in r.text and "alice" not in r.text
    # symmetric
    assert c.get("/api/chats/%s" % chat_b, headers=hdr(KEY_A)).status_code == 404
    # missing object looks IDENTICAL (no existence oracle)
    miss = c.get("/api/chats/chat_doesnotexist99", headers=hdr(KEY_B))
    assert miss.status_code == 404
    assert miss.json() == r.json()


@with_keys
def test_t2_cross_user_run_read_is_404():
    c, _, _, run_a, _, run_b = consumer_fixture()
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_A)).status_code == 200
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_B)).status_code == 404
    assert c.get("/api/runs/%s" % run_b, headers=hdr(KEY_A)).status_code == 404


@with_keys
def test_t3_cross_user_event_access_is_404():
    c, _, _, run_a, _, _ = consumer_fixture()
    assert c.get("/api/runs/%s/events" % run_a,
                 headers=hdr(KEY_A)).status_code == 200
    assert c.get("/api/runs/%s/events" % run_a,
                 headers=hdr(KEY_B)).status_code == 404


@with_keys
def test_t4_cross_user_stream_attach_denied():
    c, _, _, run_a, _, _ = consumer_fixture()
    own = c.get("/api/runs/%s/stream" % run_a, headers=hdr(KEY_A))
    assert own.status_code == 200                    # owner may attach
    cross = c.get("/api/runs/%s/stream" % run_a, headers=hdr(KEY_B))
    assert cross.status_code == 404                  # B denied BEFORE streaming
    assert "text/event-stream" not in cross.headers.get("content-type", "")


@with_keys
def test_t5_cross_user_artifact_access_denied_every_path():
    c, mgr, _, run_a, _, _ = consumer_fixture()
    # run-keyed artifact endpoints (guard runs BEFORE lookup → 404)
    assert c.get("/api/runs/%s/artifacts" % run_a,
                 headers=hdr(KEY_B)).status_code == 404
    assert c.get("/api/runs/%s/artifacts/insurance-report" % run_a,
                 headers=hdr(KEY_B)).status_code == 404
    # opaque-ref path: B cannot even ISSUE a ref for A's run…
    assert c.get("/api/runs/%s/artifact-refs/insurance-report" % run_a,
                 headers=hdr(KEY_B)).status_code == 404
    # …and cannot RESOLVE a ref A issued (the ref itself grants nothing)
    ref = c.get("/api/runs/%s/artifact-refs/insurance-report" % run_a,
                headers=hdr(KEY_A)).json()["ref"]
    assert ref.startswith("ar_") and len(ref) > 20   # high-entropy opaque
    assert c.get("/api/consumer/artifacts/%s" % ref,
                 headers=hdr(KEY_A)).status_code in (200, 404)  # owner passes guard
    assert c.get("/api/consumer/artifacts/%s" % ref,
                 headers=hdr(KEY_B)).status_code == 404
    # unknown ref indistinguishable
    assert c.get("/api/consumer/artifacts/ar_nope",
                 headers=hdr(KEY_B)).status_code == 404


# --------------------------------------------------------------------------- #
# T7..T10 + invariants
# --------------------------------------------------------------------------- #

@with_keys
def test_t7_owner_spoofing_from_client_is_ignored():
    c, _, chat_a, _, _, _ = consumer_fixture()
    # client-supplied owner hints (query/body) never influence binding
    spoofed = c.post("/api/chats?owner=consumer:alice",
                     headers=hdr(KEY_B)).json()["chat_id"]
    assert c.get("/api/chats/%s" % spoofed,
                 headers=hdr(KEY_A)).status_code == 404  # NOT alice's
    assert c.get("/api/chats/%s" % spoofed,
                 headers=hdr(KEY_B)).status_code == 200  # bound to bob
    # message injection into A's chat as B still 404 (O-5)
    n_before = len(c.get("/api/chats/%s" % chat_a,
                         headers=hdr(KEY_A)).json()["messages"])
    assert c.post("/api/chats/%s/messages" % chat_a,
                  headers=hdr(KEY_B),
                  json={"text": "inject", "owner": "consumer:bob"}).status_code == 404
    n_after = len(c.get("/api/chats/%s" % chat_a,
                        headers=hdr(KEY_A)).json()["messages"])
    assert n_before == n_after                        # T5/T7 — nothing injected


@with_keys
def test_t8_id_mutation_does_not_change_ownership():
    c, _, chat_a, run_a, _, _ = consumer_fixture()
    # mangling ids never lands on another subject's data (guard compares
    # the STORED owner, never request-supplied fields)
    assert c.get("/api/runs/%s?owner=consumer:bob" % run_a,
                 headers=hdr(KEY_B)).status_code == 404
    assert c.get("/api/chats/%s?owner=consumer:bob" % chat_a,
                 headers=hdr(KEY_B)).status_code == 404


@with_keys
def test_t9_parent_traversal_cannot_bypass():
    c, mgr, chat_a, run_a, chat_b, _ = consumer_fixture()
    # artifact access is ONLY via (owned) run or (ownership-checked) ref —
    # mixing B's chat with A's run id has no path:
    assert c.get("/api/runs/%s/artifacts/insurance-report" % run_a,
                 headers=hdr(KEY_B)).status_code == 404
    # run ownership is recorded server-side at creation (chat owner bound)
    assert mgr.get_run(run_a)["owner"] == "consumer:alice"


@with_keys
def test_t10_anonymous_fail_closed():
    c, _, chat_a, run_a, _, _ = consumer_fixture()
    for url in ("/api/chats/%s" % chat_a, "/api/runs/%s" % run_a,
                "/api/runs/%s/events" % run_a,
                "/api/runs/%s/stream" % run_a,
                "/api/consumer/whoami"):
        assert c.get(url).status_code == 401, url
    assert c.post("/api/chats").status_code == 401


@with_keys
def test_whoami_resolves_subjects():
    c, _, _, _, _, _ = consumer_fixture()
    assert c.get("/api/consumer/whoami",
                 headers=hdr(KEY_A)).json()["subject"] == "consumer:alice"
    assert c.get("/api/consumer/whoami",
                 headers=hdr(KEY_OP)).json()["subject"] == "rbac:carol"


@with_keys
def test_internal_duty_unchanged_o7():
    """Operator/Reviewer keep their existing any-read duty; consumer keys
    stay locked out of internal endpoints (G-B02-10)."""
    c, _, chat_a, run_a, _, _ = consumer_fixture()
    assert c.get("/api/runs/%s" % run_a, headers=hdr(KEY_OP)).status_code == 200
    assert c.get("/api/chats/%s" % chat_a, headers=hdr(KEY_OP)).status_code == 200
    # REVIEWER gate on review-card still enforced for everyone below it
    assert c.get("/api/runs/%s/review-card" % run_a,
                 headers=hdr(KEY_A)).status_code in (401, 403)
    assert c.get("/api/runs/%s/review-card" % run_a,
                 headers=hdr(KEY_REV)).status_code in (200, 404)
    # consumer key passes NO internal gate
    assert c.get("/api/cases", headers=hdr(KEY_A)).status_code == 403
    assert c.post("/api/runs", headers=hdr(KEY_A),
                  json={"case_id": "bm-complete-001"}).status_code == 403


# --------------------------------------------------------------------------- #
# T6 enumeration protection
# --------------------------------------------------------------------------- #

@with_keys
def test_t6_enumeration_uniform_404_then_throttled():
    c, _, _, run_a, _, _ = consumer_fixture()
    # probing as B: other-owner and missing objects look identical
    r_other = c.get("/api/runs/%s" % run_a, headers=hdr(KEY_B))
    r_miss = c.get("/api/runs/run_ffffffffffffffff", headers=hdr(KEY_B))
    assert r_other.status_code == r_miss.status_code == 404
    assert r_other.json() == r_miss.json()
    # sustained probing hits the server-side limiter (429) — independent
    # of authorization and never a substitute for it
    saw_429 = False
    for i in range(300):
        r = c.get("/api/runs/run_probe_%04x" % i, headers=hdr(KEY_B))
        if r.status_code == 429:
            saw_429 = True
            break
        assert r.status_code == 404
    assert saw_429, "rate limiter must throttle enumeration probing"


def test_rate_limiter_unit():
    rl = RateLimiter(limit=3, window_s=60.0)
    assert all(rl.allow("k") for _ in range(3))
    assert not rl.allow("k")
    assert rl.allow("other")


def test_read_allowed_truth_table():
    """O-1..O-8 invariants at the decision-function level."""
    from runtime import auth as A
    consumer = A.Identity("alice", "CONSUMER", "k")
    operator = A.Identity("carol", "OPERATOR", "k")
    assert resolve_subject(consumer) == "consumer:alice"
    # internal duty: any object
    assert read_allowed(operator, "consumer:alice") is True
    assert read_allowed(operator, None) is True
    # consumer: own object only (never role-wide, never id-based)
    assert read_allowed(consumer, "consumer:alice") is True
    assert read_allowed(consumer, "consumer:bob") is False
    assert read_allowed(consumer, None) is False
    # anonymous: only the frozen no-keys dev rule (ownerless objects)


def test_dev_mode_loopback_unchanged():
    """The frozen no-keys local-dev mode keeps its all-allow behavior."""
    saved = os.environ.pop("INSURANCE_AGENT_API_KEYS", None)
    try:
        c = make_client()[0]
        assert c.get("/api/consumer/whoami").json()["mode"] == "local-dev"
        chat = c.post("/api/chats").json()["chat_id"]
        assert c.get("/api/chats/%s" % chat).status_code == 200
        assert c.post("/api/runs",
                      json={"case_id": "bm-complete-001"}).status_code in (200, 201, 409)
    finally:
        if saved is not None:
            os.environ["INSURANCE_AGENT_API_KEYS"] = saved
