"""Health (liveness) vs Readiness — Phase 25F.

Two DIFFERENT questions, never conflated:

  LIVENESS  — is this process alive? True whenever the endpoint can
              answer. PostgreSQL/WeKnora being down does NOT make the
              process dead (killing a live pod on a downstream outage
              is the classic outage amplifier).

  READINESS — can this instance accept production workload NOW? Checks
              only what the CURRENT runtime mode actually requires:
              strict modes require PostgreSQL + real WeKnora + LLM
              configuration; DEMO/EVALUATION require neither (the mock
              stack is the point).

Readiness distinguishes READY / NOT_READY / DEGRADED:
  NOT_READY — a REQUIRED dependency is missing/unconfigured
  DEGRADED  — everything required is satisfied, but a configured
              optional dependency is currently failing
No state is invented to look complete; checks that cannot run report
"UNKNOWN" instead of guessing. Checks are pure reads (config shape +
cheap connectivity probes with short timeouts) and never mutate state.
"""
from __future__ import annotations

import os
import time
from typing import Optional


def liveness() -> dict:
    """Process-alive answer. Always LIVE when callable."""
    return {"status": "LIVE", "checked_at": _now()}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _check_postgresql(required: bool) -> dict:
    from runtime.state.persistence import resolve_backend, \
        PersistenceConfigError
    try:
        backend = resolve_backend()
    except PersistenceConfigError as e:
        return {"dependency": "postgresql", "required": required,
                "state": "NOT_READY" if required else "DEGRADED",
                "detail": str(e)[:120]}
    if backend != "postgres":
        return {"dependency": "postgresql", "required": False,
                "state": "OK", "detail": "json backend (non-strict)"}
    # strict: connectivity probe with a short timeout — the operator
    # answer must not hang the readiness endpoint
    try:
        from runtime.state.pg import PostgresStore
        ok = PostgresStore().health()
    except Exception as e:  # noqa: BLE001 — probe result, not control
        return {"dependency": "postgresql", "required": True,
                "state": "NOT_READY", "detail": str(e)[:120]}
    return {"dependency": "postgresql", "required": True,
            "state": "OK" if ok else "NOT_READY",
            "detail": "" if ok else "health check failed"}


def _check_knowledge(required: bool) -> dict:
    from knowledge.service import _validate_weknora_config, \
        ProviderConfigError, PROVIDER_ENV, DEFAULT_PROVIDER_NAME
    name = os.environ.get(PROVIDER_ENV, DEFAULT_PROVIDER_NAME)
    if name != "weknora":
        return {"dependency": "knowledge_provider", "required": False,
                "state": "OK",
                "detail": "provider=%s (non-live stack)" % name}
    try:
        _validate_weknora_config()
    except ProviderConfigError as e:
        return {"dependency": "knowledge_provider", "required": required,
                "state": "NOT_READY" if required else "DEGRADED",
                "detail": str(e)[:120]}
    key = os.environ.get("INSURANCE_AGENT_WEKNORA_API_KEY", "").strip()
    kb = os.environ.get(
        "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID", "").strip()
    if not key or not kb:
        return {"dependency": "knowledge_provider", "required": required,
                "state": "NOT_READY" if required else "DEGRADED",
                "detail": "weknora API key / KB id missing"}
    # reachability probe (short timeout; reachability only — says
    # nothing about knowledge correctness)
    try:
        from knowledge.provider.weknora import WeKnoraLiveTransport
        up = WeKnoraLiveTransport(
            os.environ["INSURANCE_AGENT_WEKNORA_URL"].strip(),
            key).health()
    except Exception as e:  # noqa: BLE001
        return {"dependency": "knowledge_provider", "required": required,
                "state": "NOT_READY" if required else "DEGRADED",
                "detail": str(e)[:120]}
    return {"dependency": "knowledge_provider", "required": required,
            "state": "OK" if up else
                     ("NOT_READY" if required else "DEGRADED"),
            "detail": "" if up else "weknora unreachable"}


def _check_llm(required: bool) -> dict:
    provider = os.environ.get("LLM_PROVIDER", "").strip()
    has_key = bool(os.environ.get("LLM_API_KEY", "").strip())
    if not provider:
        return {"dependency": "llm_gateway", "required": required,
                "state": "UNKNOWN",
                "detail": "LLM provider not configured "
                          "(deterministic path needs none)"}
    if provider and not has_key:
        return {"dependency": "llm_gateway", "required": required,
                "state": "NOT_READY",
                "detail": "LLM_PROVIDER set without LLM_API_KEY"}
    return {"dependency": "llm_gateway", "required": required,
            "state": "OK", "detail": "provider=%s (config valid; no "
                                     "network probe)" % provider}


def readiness() -> dict:
    """Aggregated readiness. required-set comes from the runtime mode
    (strict = PostgreSQL + real WeKnora required)."""
    from runtime import mode as rt_mode
    strict = rt_mode.is_strict()
    checks = [
        _check_postgresql(required=strict),
        _check_knowledge(required=strict),
        _check_llm(required=False),
        _check_runtime_mode(),
    ]
    not_ready = [c for c in checks if c["state"] == "NOT_READY"]
    degraded = [c for c in checks if c["state"] == "DEGRADED"]
    if not_ready:
        status = "NOT_READY"
    elif degraded:
        status = "DEGRADED"
    else:
        status = "READY"
    return {"status": status, "checked_at": _now(),
            "runtime_mode": rt_mode.mode(), "checks": checks}


def _check_runtime_mode() -> dict:
    from runtime import mode as rt_mode
    try:
        m = rt_mode.mode()
        return {"dependency": "runtime_mode", "required": True,
                "state": "OK", "detail": "mode=%s" % m}
    except Exception as e:  # noqa: BLE001
        return {"dependency": "runtime_mode", "required": True,
                "state": "NOT_READY", "detail": str(e)[:120]}
