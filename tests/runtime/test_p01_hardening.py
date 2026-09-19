"""Phase 13 P0.1 — production safety defaults hardening tests.

Proves the three strict-mode (CONTROLLED_PILOT/PRODUCTION) defaults are
MANDATORY and fail-closed, while DEMO/EVALUATION preserve every Phase
7–12 behavior:

  R-02  final review cannot be disabled in strict modes
  R-04  encryption key mandatory; no plaintext fallback
  R-06  authentication mandatory; no keys → startup BLOCK; wildcard CORS
        blocked outside dev
Plus mode validation (typo → BLOCK, never permissive fallback).
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import REPO, Checks, run_sections  # noqa: E402

import runtime.mode as M  # noqa: E402
from runtime.harness import LongRunningHarness  # noqa: E402
from runtime.state import store as ss  # noqa: E402


def fernet_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()

SECTIONS = []


def section(fn):
    SECTIONS.append(fn)
    return fn


def fresh_dir():
    return tempfile.mkdtemp(prefix="p01_", dir=os.path.join(REPO, "tmp"))


def with_env(**env):
    import functools
    keys = ("INSURANCE_AGENT_MODE", "INSURANCE_AGENT_DATA_KEY",
            "INSURANCE_AGENT_KEYFILE", "INSURANCE_AGENT_API_KEYS",
            "INSURANCE_AGENT_API_KEYS_FILE", "INSURANCE_AGENT_DEV",
            "INSURANCE_AGENT_CORS_ORIGINS", "INSURANCE_AGENT_NO_DOTENV")

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(c):
            old = {k: os.environ.get(k) for k in keys}
            os.environ.setdefault("INSURANCE_AGENT_NO_DOTENV", "1")
            for k, v in env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            try:
                return fn(c)
            finally:
                for k, v in old.items():
                    if v is None:
                        os.environ.pop(k, None)
                    else:
                        os.environ[k] = v
        return wrapper
    return deco


# ------------------------------------------------------------------ #
# Mode selection & validation
# ------------------------------------------------------------------ #
@section
@with_env(INSURANCE_AGENT_MODE=None)
def test_m01_mode_selection(c: Checks):
    c.chk("M-01: default mode is DEMO", M.mode() == M.DEMO)
    for m in M.VALID_MODES:
        os.environ["INSURANCE_AGENT_MODE"] = m
        c.chk("M-01: mode %s selectable" % m, M.mode() == m)
    os.environ["INSURANCE_AGENT_MODE"] = "pr0duction"   # typo
    try:
        M.mode()
        c.chk("M-01: typo mode BLOCKS (never permissive fallback)", False)
    except RuntimeError:
        c.chk("M-01: typo mode BLOCKS (never permissive fallback)", True)
    os.environ["INSURANCE_AGENT_MODE"] = "local"        # legacy alias
    c.chk("M-01: legacy 'local' alias maps to DEMO", M.mode() == M.DEMO)


# ------------------------------------------------------------------ #
# R-02 hardening: final review mandatory in strict modes
# ------------------------------------------------------------------ #
@section
@with_env(INSURANCE_AGENT_MODE="production")
def test_h02_final_review_mandatory(c: Checks):
    c.chk("H-02: production mode is strict", M.is_strict())
    c.chk("H-02: final review required by default",
          M.final_review_required(False) is True)
    c.chk("H-02: explicit require_final_review=False CANNOT disable it",
          M.final_review_required(False) is True)
    c.chk("H-02: explicit True still True",
          M.final_review_required(True) is True)
    # the harness constructor honours the mode (flag cannot disable)
    d = fresh_dir()
    try:
        h = LongRunningHarness(d, require_final_review=False)
        c.chk("H-02: harness forces the gate ON in production",
              h.require_final_review is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
@with_env(INSURANCE_AGENT_MODE="controlled_pilot")
def test_h02_pilot_same_contract(c: Checks):
    c.chk("H-02: controlled_pilot is strict too", M.is_strict())
    d = fresh_dir()
    try:
        h = LongRunningHarness(d, require_final_review=False)
        c.chk("H-02: pilot harness forces the gate ON",
              h.require_final_review is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
@with_env(INSURANCE_AGENT_MODE=None)
def test_h02_demo_compat(c: Checks):
    c.chk("H-02: DEMO is not strict", not M.is_strict())
    d = fresh_dir()
    try:
        h_off = LongRunningHarness(d, require_final_review=False)
        c.chk("H-02: DEMO honors flag=False (benchmark semantics)",
              h_off.require_final_review is False)
        h_on = LongRunningHarness(d, require_final_review=True)
        c.chk("H-02: DEMO honors flag=True", h_on.require_final_review is True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# R-04 hardening: encryption mandatory in strict modes
# ------------------------------------------------------------------ #
@section
@with_env(INSURANCE_AGENT_MODE="production",
          INSURANCE_AGENT_DATA_KEY=None, INSURANCE_AGENT_KEYFILE=None)
def test_h04_encryption_mandatory(c: Checks):
    d = fresh_dir()
    try:
        c.chk("H-04: encryption required in production",
              M.encryption_required() is True)
        try:
            ss.save({"case_id": "c1", "artifacts": {}}, d)
            c.chk("H-04: production save without a key BLOCKS", False)
        except RuntimeError as e:
            c.chk("H-04: production save without a key BLOCKS",
                  "ENCRYPTION_REQUIRED" in str(e))
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
@with_env(INSURANCE_AGENT_MODE="production")
def test_h04_invalid_key_blocks(c: Checks):
    d = fresh_dir()
    os.environ["INSURANCE_AGENT_DATA_KEY"] = "not-a-valid-key"
    try:
        try:
            ss.save({"case_id": "c1", "artifacts": {}}, d)
            c.chk("H-04: invalid key BLOCKS (no silent plaintext)", False)
        except Exception:
            c.chk("H-04: invalid key BLOCKS (no silent plaintext)", True)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
@with_env(INSURANCE_AGENT_MODE="production")
def test_h04_valid_key_passes(c: Checks):
    d = fresh_dir()
    os.environ["INSURANCE_AGENT_DATA_KEY"] = fernet_key()
    try:
        ss.save({"case_id": "c1", "artifacts": {}, "x": 1}, d)
        loaded = ss.load(d, "c1")
        c.chk("H-04: valid key → encrypted save + clean round-trip",
              loaded is not None and loaded["x"] == 1)
        raw = open(os.path.join(d, "c1", "case_state.json"), "rb").read()
        c.chk("H-04: ciphertext on disk (no plaintext)", b"case_id" not in raw)
    finally:
        shutil.rmtree(d, ignore_errors=True)


@section
@with_env(INSURANCE_AGENT_MODE=None,
          INSURANCE_AGENT_DATA_KEY=None, INSURANCE_AGENT_KEYFILE=None)
def test_h04_demo_compat(c: Checks):
    d = fresh_dir()
    try:
        c.chk("H-04: DEMO does not require encryption",
              M.encryption_required() is False)
        ss.save({"case_id": "c1", "artifacts": {}, "x": 1}, d)
        c.chk("H-04: DEMO plaintext save still works (portfolio compat)",
              ss.load(d, "c1")["x"] == 1)
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ------------------------------------------------------------------ #
# R-06 hardening: authentication mandatory in strict modes
# ------------------------------------------------------------------ #
@section
@with_env(INSURANCE_AGENT_MODE="production",
          INSURANCE_AGENT_API_KEYS=None, INSURANCE_AGENT_API_KEYS_FILE=None,
          INSURANCE_AGENT_DATA_KEY=None)
def test_h06_startup_blocks_without_auth(c: Checks):
    from runtime.server import _validate_production_defaults
    try:
        _validate_production_defaults()
        c.chk("H-06: production startup without auth keys BLOCKS", False)
    except RuntimeError as e:
        c.chk("H-06: production startup without auth keys BLOCKS",
              "AUTHENTICATION_REQUIRED" in str(e), str(e)[:80])


@section
@with_env(INSURANCE_AGENT_MODE="production",
          INSURANCE_AGENT_DATA_KEY=None,
          INSURANCE_AGENT_API_KEYS="k" * 24 + ":OWNER:alice")
def test_h06_startup_blocks_without_encryption(c: Checks):
    from runtime.server import _validate_production_defaults
    try:
        _validate_production_defaults()
        c.chk("H-06: production startup without a data key BLOCKS", False)
    except RuntimeError as e:
        c.chk("H-06: production startup without a data key BLOCKS",
              "ENCRYPTION_REQUIRED" in str(e), str(e)[:80])


@section
@with_env(INSURANCE_AGENT_MODE="production",
          INSURANCE_AGENT_API_KEYS="k" * 24 + ":OWNER:alice,"
          + "o" * 24 + ":OPERATOR:carol",
          INSURANCE_AGENT_DATA_KEY=None)
def test_h06_authenticated_requests(c: Checks):
    os.environ["INSURANCE_AGENT_DATA_KEY"] = fernet_key()
    from _common import make_client
    client = make_client()[0]
    # no credentials → 401 (fail closed, NOT implicit dev mode)
    r = client.post("/api/approvals/appr_x/approve", json={})
    c.chk("H-06: production request without bearer → 401 (no implicit "
          "dev fallback)", r.status_code == 401, r.status_code)
    # invalid key → 401
    r2 = client.post("/api/approvals/appr_x/approve",
                     headers={"Authorization": "Bearer wrong"}, json={})
    c.chk("H-06: invalid key → 401", r2.status_code == 401)
    # valid key, insufficient role → 403
    r3 = client.post("/api/approvals/appr_x/approve",
                      headers={"Authorization": "Bearer " + "o" * 24},
                      json={})
    c.chk("H-06: OPERATOR on approve → 403", r3.status_code == 403)
    # valid key + role → passes authz (404 unknown approval)
    r4 = client.post("/api/approvals/appr_x/approve",
                      headers={"Authorization": "Bearer " + "k" * 24},
                      json={"actor": "agent:forge"})
    c.chk("H-06: OWNER passes authz (404 = unknown approval, not 401/403)",
          r4.status_code == 404, r4.status_code)


@section
@with_env(INSURANCE_AGENT_MODE="production")
def test_h06_wildcard_cors_blocked(c: Checks):
    import runtime.auth as A
    os.environ["INSURANCE_AGENT_CORS_ORIGINS"] = "*"
    os.environ.pop("INSURANCE_AGENT_DEV", None)
    origins = A.cors_origins()
    c.chk("H-06: wildcard CORS BLOCKED in production (allowlist only)",
          "*" not in origins, origins)


@section
@with_env(INSURANCE_AGENT_MODE=None,
          INSURANCE_AGENT_API_KEYS=None, INSURANCE_AGENT_API_KEYS_FILE=None)
def test_h06_demo_compat(c: Checks):
    from _common import make_client
    client = make_client()[0]
    r = client.get("/api/health")
    c.chk("H-06: DEMO startup without keys works (local dev preserved)",
          r.status_code == 200)
    c.chk("H-06: DEMO does not require auth",
          M.authentication_required() is False)


def main():
    return run_sections(SECTIONS, "webui_test_p01_log.txt",
                        "P0.1 SAFETY DEFAULTS")


if __name__ == "__main__":
    sys.exit(main())
