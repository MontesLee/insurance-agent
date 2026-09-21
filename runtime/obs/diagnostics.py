"""Runtime diagnostics — Phase 25G (read-only, secret-free).

Answers: who am I (version/commit/mode), what am I running on
(backends/providers), since when (startup/uptime), and how are my
dependencies. HARD denylist: no environment dump, no credentials, no
tokens, no DSNs — only per-item configured/not-configured booleans and
non-secret identifiers.
"""
from __future__ import annotations

import os
import time
from typing import Optional

_STARTUP = time.time()
_DENY_KEYS = ("KEY", "PASSWORD", "SECRET", "TOKEN", "DSN", "AUTH",
              "CREDENTIAL")

try:
    _VERSION = "0.2.0"
except Exception:  # noqa: BLE001
    _VERSION = "UNKNOWN"


def _git_commit() -> str:
    """Short commit hash via DIRECT .git file reads — no subprocess in
    the request path (a `git` subprocess deadlocked under the ASGI
    test portal; file reads cannot). Handles normal repos and
    worktrees; UNKNOWN on anything unexpected."""
    try:
        repo = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        git = os.path.join(repo, ".git")
        if os.path.isfile(git):                    # worktree pointer
            line = open(git, encoding="utf-8").read().strip()
            if line.startswith("gitdir:"):
                git = line.split(":", 1)[1].strip()
        head = open(os.path.join(git, "HEAD"),
                    encoding="utf-8").read().strip()
        if head.startswith("ref: "):
            ref = head[5:].strip()
            ref_file = os.path.join(git, *ref.split("/"))
            sha = open(ref_file, encoding="utf-8").read().strip()
        else:                                       # detached HEAD
            sha = head
        return sha[:7] if len(sha) >= 7 else "UNKNOWN"
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _config_status() -> dict:
    """Configured / not-configured per integration. VALUES NEVER
    INCLUDED — only booleans and non-secret identifiers."""
    from runtime import mode as rt_mode
    prov_env = "INSURANCE_AGENT_KNOWLEDGE_PROVIDER"
    return {
        "runtime_mode": rt_mode.mode(),
        "state_backend": _state_backend(),
        "knowledge_provider": os.environ.get(prov_env, "mock"),
        "weknora_url_configured": bool(os.environ.get(
            "INSURANCE_AGENT_WEKNORA_URL", "").strip()),
        "weknora_kb_configured": bool(os.environ.get(
            "INSURANCE_AGENT_WEKNORA_KNOWLEDGE_BASE_ID", "").strip()),
        "llm_provider": os.environ.get("LLM_PROVIDER", "") or None,
        "llm_key_configured": bool(os.environ.get(
            "LLM_API_KEY", "").strip()),
        "knowledge_registry_backend": _registry_backend(),
    }


def _state_backend() -> str:
    try:
        from runtime.state.persistence import resolve_backend
        return resolve_backend()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def _registry_backend() -> str:
    try:
        from knowledge.service import resolve_registry_backend
        return resolve_registry_backend()
    except Exception:  # noqa: BLE001
        return "UNKNOWN"


def snapshot(include_readiness: bool = True) -> dict:
    from runtime.obs.health import readiness
    out = {
        "version": _VERSION,
        "git_commit": _git_commit(),
        "startup_time": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ", time.gmtime(_STARTUP)),
        "uptime_s": round(time.time() - _STARTUP, 1),
        "configuration_status": _config_status(),
    }
    if include_readiness:
        out["dependency_status"] = readiness()
    # final defense-in-depth: strip any key whose name smells like a
    # secret from every nested dict we produced
    return _scrub(out)


def _scrub(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            looks_secret = any(d in k.upper() for d in _DENY_KEYS)
            if looks_secret and isinstance(v, str):
                out[k] = "<redacted>"      # secret-shaped NAME+STRING
            elif looks_secret and isinstance(v, bool):
                out[k] = v                 # a boolean FACT (configured
                                           # or not) carries no secret
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(obj, list):
        return [_scrub(x) for x in obj]
    if isinstance(obj, str):
        # value-shape defense: a credential that snuck into a value
        from runtime.state.dataprotection import \
            redact_credential_values
        return redact_credential_values(obj)
    return obj
