"""Unified LLM configuration (Phase 2.6+).

One config layer for EVERY consumer (web server AND smoke test):

    process env (explicit)  >  <repo root>/.env  >  defaults

GLM is NOT a special agent — it is an OpenAI-compatible backend:

    LLMConfig → OpenAICompatProvider → /chat/completions → GLM

Security rules:
  * the API key is read, used, and never surfaced — not in events, trace,
    artifacts, errors, logs or the frontend;
  * error/validation messages NAME the missing variable, never its value;
  * `describe()` exposes provider/model/base_url only.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional, Union

from runtime.agent.model import (_DEFAULT_BASE_URLS, OpenAICompatProvider,  # noqa: E402
                                 ProviderNotConfigured)

# <repo root> = this file → runtime/agent/ → runtime/ → root (never trust cwd)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_ENV_PATH = os.path.join(REPO_ROOT, ".env")

__all__ = ["LLMConfig", "ProviderNotConfigured", "load_llm_config",
           "redact_secrets", "REPO_ROOT", "DEFAULT_ENV_PATH"]


@dataclass
class LLMConfig:
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""          # explicit override; "" → provider default
    fast_model: str = ""        # cheap tier for routine steps; "" → same as model

    @property
    def resolved_base_url(self) -> str:
        return (self.base_url or _DEFAULT_BASE_URLS.get(self.provider, "")
                or "https://api.openai.com/v1")

    @property
    def resolved_fast_model(self) -> str:
        """The fast tier, falling back to the main model (single-tier setups)."""
        return self.fast_model or self.model

    def missing(self) -> list:
        """Names of the missing required variables (never their values)."""
        out = []
        if not self.provider:
            out.append("LLM_PROVIDER")
        if not self.model:
            out.append("LLM_MODEL")
        if not (self.api_key):
            out.append("LLM_API_KEY (or OPENAI_API_KEY)")
        return out

    def describe(self) -> dict:
        """Public, key-free view (safe for /api/agent/config, logs, smoke output)."""
        return {
            "configured": not self.missing(),
            "provider": self.provider or None,
            "model": self.model or None,
            "fast_model": (self.resolved_fast_model or None) if self.provider else None,
            # only meaningful once a provider is chosen (avoids a misleading
            # OpenAI default when nothing is configured)
            "base_url": (self.resolved_base_url or None) if self.provider else None,
        }

    def to_provider(self, fast: bool = False) -> OpenAICompatProvider:
        """Build the provider; fast=True selects the cost tier for routine steps
        (same endpoint/key — only the model differs; falls back to the main
        model when LLM_FAST_MODEL is unset, so single-tier setups are unchanged)."""
        missing = self.missing()
        if missing:
            raise ProviderNotConfigured(
                "LLM provider is not configured — missing: %s. Set them in the "
                "process environment or in %s (see .env.example), or switch the "
                "UI to Demo Mode." % (", ".join(missing), DEFAULT_ENV_PATH))
        return OpenAICompatProvider(
            name=self.provider,
            model=self.resolved_fast_model if fast else self.model,
            api_key=self.api_key,
            base_url=self.resolved_base_url)


def _read_dotenv(path: Union[str, os.PathLike]) -> dict:
    """Read a .env file into a dict WITHOUT touching os.environ.

    Prefers python-dotenv; if the library is absent (some CI venvs), falls back
    to a minimal built-in parser for the simple KEY=VALUE subset — an unreadable
    or missing file is simply {}, never a crash and never a silent skip of
    values that ARE present."""
    try:
        from dotenv import dotenv_values
        return {k: v for k, v in dotenv_values(path).items() if isinstance(v, str)}
    except ImportError:
        return _parse_dotenv_minimal(path)
    except Exception:  # noqa: BLE001 — unreadable/absent .env is not fatal
        return {}


def _parse_dotenv_minimal(path: Union[str, os.PathLike]) -> dict:
    values: dict = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip().removeprefix("export ").strip()
                val = val.split(" #")[0].strip().strip("'\"")
                if key:
                    values[key] = val
    except OSError:
        return {}
    return values


def load_llm_config(env: Optional[dict] = None,
                    dotenv_path: Union[str, os.PathLike, None, bool] = None) -> LLMConfig:
    """Resolve the LLM config.

    env=None            → real usage: process env merged OVER the repo-root .env
    env={...}           → explicit mapping only (tests; .env is NOT read unless
                          dotenv_path points at one)
    dotenv_path=False   → skip .env entirely
    dotenv_path=<path>  → use that .env (tests)

    Precedence everywhere: explicit env > .env > defaults. Existing process
    environment variables are never overwritten.
    """
    env = os.environ if env is None else env
    file_values: dict = {}
    if dotenv_path is not False:
        if dotenv_path in (None, True):
            # real usage: repo-root .env, unless hermetic/test mode asks to skip
            if not os.environ.get("INSURANCE_AGENT_NO_DOTENV"):
                file_values = _read_dotenv(DEFAULT_ENV_PATH)
        else:
            # explicit path (tests) — always honoured, never blocked
            file_values = _read_dotenv(dotenv_path)

    def pick(name: str, legacy: tuple = ()) -> str:
        v = env.get(name)
        if v:
            return str(v).strip()
        for alt in legacy:
            v = env.get(alt)
            if v:
                return str(v).strip()
        fv = file_values.get(name)
        return str(fv).strip() if fv else ""

    return LLMConfig(
        provider=pick("LLM_PROVIDER").lower(),
        model=pick("LLM_MODEL"),
        api_key=pick("LLM_API_KEY", legacy=("OPENAI_API_KEY",)),
        base_url=pick("LLM_BASE_URL"),
        fast_model=pick("LLM_FAST_MODEL"),
    )


_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{8,}"),
    re.compile(r"(?i)(api[_-]?key|authorization|token)\s*[=:]\s*\S+"),
)


def redact_secrets(text: str, extra_secrets: tuple = ()) -> str:
    """Strip anything key-shaped before it can reach a message/event/log."""
    out = str(text or "")
    for secret in extra_secrets:
        if secret and len(str(secret)) >= 6:
            out = out.replace(str(secret), "***REDACTED***")
    for pat in _SECRET_PATTERNS:
        out = pat.sub("***REDACTED***", out)
    return out
