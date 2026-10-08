"""Phase 28.E-6 — Consumer / Internal API space boundary.

The E-6 boundary completes the Phase-13 R-06 endpoint-role declarations
for the remaining operator/developer DATA endpoints (approvals list/
detail, review-card, supervisor/alerts/notifications/control-commands,
cases). With API keys configured:

  * missing/unknown credentials -> 401 (fail closed, _identity_dep)
  * authenticated but wrong role -> 403 (_require_role)
  * consumer surface (chats / runs read / SSE) stays open — the
    consumer authentication model is a DEFERRED OWNER DECISION

No-keys local-dev mode allows everything (documented; ident is None).
"""
from __future__ import annotations

import os

from _common import make_client

KEY_OWNER = "k" * 24 + ":OWNER:alice"
KEY_REVIEWER = "r" * 24 + ":REVIEWER:bob"
KEY_OPERATOR = "o" * 24 + ":OPERATOR:carol"
KEY_CONSUMER = "cz" * 12 + ":CONSUMER:erin"

# internal (operator/developer) DATA endpoints — must be role-gated
REVIEWER_GETS = [
    "/api/projects/p-e6/approvals",
    "/api/approvals/appr_e6_missing",
    "/api/runs/run_e6_missing/review-card",
]
OPERATOR_GETS = [
    "/api/projects/p-e6/supervisor",
    "/api/projects/p-e6/alerts",
    "/api/projects/p-e6/notifications",
    "/api/projects/p-e6/control-commands",
    "/api/cases",
]


def with_keys(fn):
    import functools

    @functools.wraps(fn)
    def wrapper():
        old = {k: os.environ.get(k) for k in
               ("INSURANCE_AGENT_API_KEYS", "INSURANCE_AGENT_DEV",
                "INSURANCE_AGENT_CORS_ORIGINS", "INSURANCE_AGENT_MODE")}
        os.environ["INSURANCE_AGENT_API_KEYS"] = ",".join(
            [KEY_OWNER, KEY_REVIEWER, KEY_OPERATOR, KEY_CONSUMER])
        try:
            return fn()
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return wrapper


def hdr(key):
    return {"Authorization": "Bearer " + key.split(":")[0]}


@with_keys
def test_e6t5_internal_reads_require_authentication():
    """E6-T5/T6: a keyless 'consumer' cannot read internal data."""
    c = make_client()[0]
    for url in REVIEWER_GETS + OPERATOR_GETS:
        r = c.get(url)
        assert r.status_code == 401, (url, r.status_code)


@with_keys
def test_e6_internal_reads_role_matrix():
    """R-06 rank semantics: OWNER(3) ⊇ REVIEWER(2) ⊇ OPERATOR(1).
    REVIEWER-gated data: OPERATOR key → 403; OPERATOR-gated data:
    REVIEWER passes (rank superset). Authorized reads land 200/404."""
    c = make_client()[0]
    for url in REVIEWER_GETS:
        assert c.get(url, headers=hdr(KEY_REVIEWER)).status_code in (200, 404), url
        assert c.get(url, headers=hdr(KEY_OPERATOR)).status_code == 403, url
    for url in OPERATOR_GETS:
        assert c.get(url, headers=hdr(KEY_OPERATOR)).status_code in (200, 404), url
        assert c.get(url, headers=hdr(KEY_REVIEWER)).status_code in (200, 404), url
    # OWNER outranks both
    for url in REVIEWER_GETS + OPERATOR_GETS:
        assert c.get(url, headers=hdr(KEY_OWNER)).status_code in (200, 404), url


@with_keys
def test_e6t7_invalid_credentials_fail_closed():
    """E6-T7: unknown/invalid keys are treated as unauthenticated."""
    c = make_client()[0]
    bad = {"Authorization": "Bearer " + "x" * 24}
    for url in REVIEWER_GETS + OPERATOR_GETS:
        assert c.get(url, headers=bad).status_code == 401, url


@with_keys
def test_e6_consumer_surface_stays_open():
    """28.G (supersedes the E-6 keyless premise — Owner decision D-01′):
    with keys configured the consumer surface REQUIRES an authenticated
    subject; a CONSUMER identity creates its own chat normally."""
    c = make_client()[0]
    # unauthenticated -> fail closed
    assert c.post("/api/chats").status_code == 401
    # authenticated CONSUMER subject -> the surface works
    r = c.post("/api/chats", headers={
        "Authorization": "Bearer " + ("cz" * 12)})
    assert r.status_code == 201, r.status_code


def test_e6_dev_mode_allows_internal_reads():
    """No-keys local-dev mode keeps working (documented loopback mode)."""
    saved = os.environ.pop("INSURANCE_AGENT_API_KEYS", None)
    try:
        assert make_client()[0].get("/api/cases").status_code == 200
        assert make_client()[0].get("/api/projects/p-e6/approvals").status_code in (200, 404)
    finally:
        if saved is not None:
            os.environ["INSURANCE_AGENT_API_KEYS"] = saved
