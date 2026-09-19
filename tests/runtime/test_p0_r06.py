"""Phase 13 P0 R-06 — authentication / CORS / authorization tests.

Round-1 finding: no authn, CORS `*`, client-supplied actor trusted on
approval/control endpoints. Proves: bearer-key identity, role enforcement,
fail-closed 401/403, actor derived from identity (never the body), CORS
allowlist with `*` only in explicit dev mode.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

import runtime.auth as A  # noqa: E402

SECTIONS = []
KEY_OWNER = "k" * 24 + ":OWNER:alice"
KEY_REVIEWER = "r" * 24 + ":REVIEWER:bob"
KEY_OPERATOR = "o" * 24 + ":OPERATOR:carol"


def with_keys(fn):
    import functools

    @functools.wraps(fn)
    def wrapper(c):
        old = {k: os.environ.get(k) for k in
               ("INSURANCE_AGENT_API_KEYS", "INSURANCE_AGENT_DEV",
                "INSURANCE_AGENT_CORS_ORIGINS", "INSURANCE_AGENT_MODE")}
        os.environ["INSURANCE_AGENT_API_KEYS"] = ",".join(
            [KEY_OWNER, KEY_REVIEWER, KEY_OPERATOR])
        try:
            return fn(c)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
    return wrapper


def section(fn):
    SECTIONS.append(fn)
    return fn


def client_with_keys():
    from _common import make_client
    return make_client()[0]


def hdr(key):
    return {"Authorization": "Bearer " + key.split(":")[0]}


@section
@with_keys
def test_t_r06_01_identity_and_roles(c: Checks):
    ids = A.load_identities()
    c.chk("R-06: three identities loaded", len(ids) == 3)
    alice = A.authenticate("Bearer " + "k" * 24, ids)
    c.chk("R-06: bearer token resolves to identity",
          alice is not None and alice.user == "alice" and alice.role == "OWNER")
    c.chk("R-06: wrong token rejected", A.authenticate("Bearer nope", ids) is None)
    c.chk("R-06: no header rejected", A.authenticate(None, ids) is None)
    c.chk("R-06: OWNER >= REVIEWER >= OPERATOR ranks",
          alice.has_role("REVIEWER") and alice.has_role("OPERATOR"))
    bob = ids["r" * 24]
    c.chk("R-06: REVIEWER can approve but not admin",
          bob.has_role("REVIEWER") and not bob.has_role("OWNER"))
    carol = ids["o" * 24]
    c.chk("R-06: OPERATOR cannot approve",
          not carol.has_role("REVIEWER") and carol.has_role("OPERATOR"))


@section
@with_keys
def test_t_r06_02_fail_closed_401(c: Checks):
    client = client_with_keys()
    r = client.post("/api/approvals/appr_x/approve", json={"actor": "human"})
    c.chk("R-06: no credentials → 401 (fail closed)", r.status_code == 401,
          r.status_code)
    r = client.post("/api/approvals/appr_x/approve",
                    headers={"Authorization": "Bearer wrong"},
                    json={})
    c.chk("R-06: unknown key → 401", r.status_code == 401)
    r = client.post("/api/projects/proj_x/control/pause", json={})
    c.chk("R-06: control without auth → 401", r.status_code == 401)


@section
@with_keys
def test_t_r06_03_role_enforcement_403(c: Checks):
    client = client_with_keys()
    # OPERATOR may pause (OPERATOR minimum) but not approve (REVIEWER min)
    r = client.post("/api/projects/proj_x/control/pause",
                    headers=hdr(KEY_OPERATOR), json={})
    c.chk("R-06: OPERATOR can issue control commands (404 project, not 403)",
          r.status_code in (404, 409), r.status_code)
    r = client.post("/api/approvals/appr_x/approve",
                    headers=hdr(KEY_OPERATOR), json={})
    c.chk("R-06: OPERATOR cannot approve → 403", r.status_code == 403)
    r = client.post("/api/approvals/appr_x/approve",
                    headers=hdr(KEY_REVIEWER), json={})
    c.chk("R-06: REVIEWER may approve (404 unknown approval, not 403)",
          r.status_code == 404, r.status_code)


@section
@with_keys
def test_t_r06_04_actor_from_identity_not_body(c: Checks):
    """The actor recorded on an approval must be the authenticated user,
    never a client-supplied string — even a forged 'agent:x' body."""
    import json
    from runtime.harness import LongRunningHarness
    from runtime.approval import ApprovalStore, create_request, \
        APPROVAL_REPLAN
    root = tempfile.mkdtemp(prefix="r06_", dir=os.path.join(REPO, "tmp"))
    os.environ["INSURANCE_AGENT_HARNESS_ROOT"] = root
    try:
        h = LongRunningHarness(root)
        p = h.create_project("r06t", task_graph={"tasks": [
            {"task_id": "task_a", "task_type": "client_profile"}]})
        h._approval_manager(p).create_request(create_request(
            project_id=p.project_id, request_type=APPROVAL_REPLAN,
            reason="r06"))
        h._approval_manager(p).wait(
            ApprovalStore(p._dir).all()[0]["approval_id"])
        client = client_with_keys()
        r = client.post("/api/approvals/%s/approve"
                        % ApprovalStore(p._dir).all()[0]["approval_id"],
                        headers=hdr(KEY_REVIEWER),
                        json={"actor": "agent:insurance_analyst"})
        c.chk("R-06: approve with authenticated REVIEWER succeeds",
              r.status_code == 200, r.status_code)
        rec = ApprovalStore(p._dir).all()[0]
        c.chk("R-06: actor = authenticated identity (human:bob), NOT body",
              rec.get("resolved_by") == "human:bob", rec.get("resolved_by"))
        # forged body actor never becomes a non-human authority
        c.chk("R-06: forged body actor ignored",
              "agent" not in str(rec.get("resolved_by")))
    finally:
        shutil.rmtree(root, ignore_errors=True)


@section
def test_t_r06_05_cors_allowlist(c: Checks):
    old = {k: os.environ.get(k) for k in
           ("INSURANCE_AGENT_DEV", "INSURANCE_AGENT_CORS_ORIGINS")}
    try:
        os.environ.pop("INSURANCE_AGENT_DEV", None)
        os.environ.pop("INSURANCE_AGENT_CORS_ORIGINS", None)
        default = A.cors_origins()
        c.chk("R-06: default CORS is a loopback allowlist (no `*`)",
              "*" not in default and "http://localhost:5173" in default, default)
        os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = "https://ui.example.com"
        c.chk("R-06: configured allowlist honored",
              A.cors_origins() == ["https://ui.example.com"])
        os.environ["INSURANCE_AGENT_DEV"] = "1"
        os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = "*"
        c.chk("R-06: `*` ONLY in explicit dev mode",
              A.cors_origins() == ["*"])
        os.environ.pop("INSURANCE_AGENT_DEV", None)
        os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = "*"
        c.chk("R-06: `*` ignored outside dev mode",
              "*" not in A.cors_origins())
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@section
def test_t_r06_06_dev_mode_compat(c: Checks):
    """No keys configured = documented local-dev mode: endpoints stay open
    (loopback-bound server), body actor honored as before."""
    old = os.environ.pop("INSURANCE_AGENT_API_KEYS", None)
    try:
        ids = A.load_identities()
        c.chk("R-06: no keys → dev mode", ids == {})
        c.chk("R-06: dev mode has no identity", A.authenticate("Bearer x") is None)
        from _common import make_client
        client = make_client()[0]
        r = client.get("/api/health")
        c.chk("R-06: dev mode health open", r.status_code == 200)
        r = client.post("/api/approvals/appr_x/approve", json={})
        c.chk("R-06: dev mode approve not 401 (404 unknown approval)",
              r.status_code == 404, r.status_code)
    finally:
        if old is not None:
            os.environ["INSURANCE_AGENT_API_KEYS"] = old


def main():
    return run_sections(SECTIONS, "webui_test_r06_log.txt",
                        "P0 R-06 AUTH")


if __name__ == "__main__":
    sys.exit(main())
