"""Phase 13 P0 R-05 — provider data-policy gate tests.

Round-1 finding: provider data policy UNKNOWN → must BLOCK real client
data (never silently allow). Proves: synthetic allowed; real+unverified
BLOCKED (fail closed); real+operator-verified allowed; no silent fallback;
the server gate refuses real data at the agent-turn boundary.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

from runtime.agent import data_policy as dp  # noqa: E402

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_env():
    old = {k: os.environ.get(k) for k in
           ("INSURANCE_AGENT_CLIENT_DATA",
            "INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED",
            "INSURANCE_AGENT_NO_DOTENV")}
    os.environ["INSURANCE_AGENT_NO_DOTENV"] = "1"
    return old


def restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@section
def test_t_r05_01_synthetic_allowed(c: Checks):
    old = fresh_env()
    try:
        os.environ.pop("INSURANCE_AGENT_CLIENT_DATA", None)
        os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
        allowed, reason = dp.client_data_allowed()
        c.chk("R-05-01: default mode is synthetic", dp.client_data_mode()
              == "synthetic")
        c.chk("R-05-01: synthetic data allowed",
              allowed and "synthetic" in reason)
    finally:
        restore(old)


@section
def test_t_r05_02_real_unverified_blocked(c: Checks):
    old = fresh_env()
    try:
        os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "real"
        os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
        allowed, reason = dp.client_data_allowed()
        c.chk("R-05-02: real mode active", dp.client_data_mode() == "real")
        c.chk("R-05-02: UNKNOWN → BLOCK (fail closed, never allow)",
              not allowed)
        c.chk("R-05-02: reason names the gate",
              "PROVIDER_POLICY_UNVERIFIED" in reason, reason[:80])
        c.chk("R-05-02: no silent fallback path exists",
              dp.provider_policy_verified() is False)
    finally:
        restore(old)


@section
def test_t_r05_03_real_verified_allowed(c: Checks):
    old = fresh_env()
    try:
        os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "real"
        os.environ["INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED"] = "1"
        allowed, reason = dp.client_data_allowed()
        c.chk("R-05-03: operator-verified real data allowed", allowed)
        c.chk("R-05-03: reason records the verification",
              "operator-verified" in reason)
    finally:
        restore(old)


@section
def test_t_r05_04_server_gate_blocks_real(c: Checks):
    """The server's agent-turn boundary refuses REAL client data with an
    unverified policy — before any text reaches the provider."""
    old = fresh_env()
    try:
        os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "real"
        os.environ.pop("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED", None)
        from _common import make_client
        client = make_client()[0]
        r = client.post("/api/chats", json={})
        chat_id = r.json()["chat_id"]
        r2 = client.post("/api/chats/%s/messages" % chat_id,
                         json={"text": "real client says hello"})
        c.chk("R-05-04: real-data chat turn blocked at the boundary",
              r2.status_code == 451, r2.status_code)
        c.chk("R-05-04: block reason surfaced",
              "PROVIDER_POLICY_UNVERIFIED" in str(r2.json()))
        # synthetic mode on the SAME server works
        os.environ["INSURANCE_AGENT_CLIENT_DATA"] = "synthetic"
        r3 = client.post("/api/chats/%s/messages" % chat_id,
                         json={"text": "synthetic hello"})
        c.chk("R-05-04: synthetic mode unaffected (no provider needed "
              "in this env → structured failure, not a silent pass)",
              r3.status_code in (200, 409, 503), r3.status_code)
    finally:
        restore(old)


@section
def test_t_r05_05_verification_record_exists(c: Checks):
    """The evidence record must exist and state the honest status."""
    path = os.path.join(REPO, "docs", "production",
                        "provider-policy-verification.md")
    c.chk("R-05-05: verification record file exists",
          os.path.exists(path))
    if os.path.exists(path):
        text = open(path, encoding="utf-8").read()
        c.chk("R-05-05: record does NOT claim verified PASS",
              "VERDICT: NOT VERIFIED" in text or
              "PARTIALLY VERIFIED" in text or "UNVERIFIED" in text)
        c.chk("R-05-05: record cites official sources",
              "docs.bigmodel.cn" in text or "bigmodel.cn" in text)
        c.chk("R-05-05: record states third-party evidence limitation",
              "third-party" in text.lower() or "第三方" in text)


def main():
    return run_sections(SECTIONS, "webui_test_r05_log.txt",
                        "P0 R-05 PROVIDER POLICY")


if __name__ == "__main__":
    sys.exit(main())
