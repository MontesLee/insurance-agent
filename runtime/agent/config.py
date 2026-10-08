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

# 28.K.27 — reasoning budget for ALWAYS-THINKING models (GLM's
# `reasoning_effort`; glm-5.3 rejects disabling thinking outright with
# code 1210 "该模型始终思考…请使用 low、high 或 max").
#
# Why a bound is mandatory (evidence, 2026-09-28, glm-5.3 on this repo's real
# agent prompt): with an unbounded/provider-default budget an agent-loop step-1
# call streamed 4418 `reasoning` deltas in 90s and would not reach
# content/tool_calls before the generation watchdog killed it at exactly
# GENERATION_WALL_S (240s). 3 attempts (LLM_RETRY=2) = 720s, burning the 900s run
# budget, so the turn UNCONDITIONALLY ended needs_review ("没能生成有效的分析
# 步骤"). "max" reproduces this: measured 2456 deltas / 10241 chars and STILL
# streaming after 90s, never reaching its tool call — do not select it.
#
# NOTE (28.K.28 SUPERSEDES 28.K.20/E-2): reasoning IS user-visible now — the
# step-output box renders it in a de-emphasized "思考" segment. So this budget is
# no longer a free safety valve: it decides how much text the user sees, and
# "low" was measured to sometimes stream NOTHING AT ALL. Repeated samples
# (2026-09-28, real prompt + all 11 tool specs):
#     low  → 16–56 deltas, 72–265 chars, 6.1–16.3s; a CONTINUATION step (after a
#            tool result) yielded 0 deltas and still completed in 5.7s → the
#            step box stays empty for the whole step.
#     high → 107–242 deltas, 499–1146 chars (4–8x), 11.8–30.4s (~+5s per
#            continuation step); step-1 was FASTER on high in 2 of 3 samples.
# The default stays "low" (cost/latency first) — pilots that care about the
# visible stream set LLM_REASONING_EFFORT=high (28.K.30 did exactly that in the
# gitignored .env). Re-measure before changing the default: single samples on
# this provider swing by 3-4x.
#
# Override via LLM_REASONING_EFFORT (env or .env):
#   low | high | max      → sent as `reasoning_effort`
#   default | none | off  → omit the parameter (pre-28.K.27 behaviour)
REASONING_EFFORT_ENV = "LLM_REASONING_EFFORT"
_DEFAULT_REASONING_EFFORT = "low"
_OMIT_REASONING_EFFORT = frozenset(("default", "none", "off"))

__all__ = ["LLMConfig", "ProviderNotConfigured", "load_llm_config",
           "redact_secrets", "REPO_ROOT", "DEFAULT_ENV_PATH",
           "REASONING_EFFORT_ENV"]


@dataclass
class LLMConfig:
    provider: str = ""
    model: str = ""
    api_key: str = ""
    base_url: str = ""          # explicit override; "" → provider default
    fast_model: str = ""        # cheap tier for routine steps; "" → same as model
    # 28.K.32-C: independent QA-slice tier (K.32-B isolation seam);
    # "" → follows the fast tier, so default behavior is unchanged
    qa_model: str = ""
    reasoning_effort: str = _DEFAULT_REASONING_EFFORT

    @property
    def resolved_base_url(self) -> str:
        return (self.base_url or _DEFAULT_BASE_URLS.get(self.provider, "")
                or "https://api.openai.com/v1")

    @property
    def resolved_fast_model(self) -> str:
        """The fast tier, falling back to the main model (single-tier setups)."""
        return self.fast_model or self.model

    @property
    def resolved_qa_model(self) -> str:
        """The QA-slice tier (28.K.32-C): qa → fast → main fallback chain.
        Unset qa_model keeps the pre-K.32-C shared-slot behavior exactly."""
        return self.qa_model or self.resolved_fast_model

    @property
    def resolved_reasoning_effort(self) -> str:
        """`reasoning_effort` to send, or "" to omit the parameter entirely."""
        value = (self.reasoning_effort or _DEFAULT_REASONING_EFFORT).strip().lower()
        return "" if value in _OMIT_REASONING_EFFORT else value

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
            "qa_model": (self.resolved_qa_model or None) if self.provider else None,
            # only meaningful once a provider is chosen (avoids a misleading
            # OpenAI default when nothing is configured)
            "base_url": (self.resolved_base_url or None) if self.provider else None,
            # effective reasoning budget ("" = parameter omitted); not a secret
            "reasoning_effort": self.resolved_reasoning_effort or None,
        }

    def to_provider(self, fast: bool = False,
                    qa: bool = False) -> OpenAICompatProvider:
        """Build the provider; fast=True selects the cost tier for routine steps
        (same endpoint/key — only the model differs; falls back to the main
        model when LLM_FAST_MODEL is unset, so single-tier setups are unchanged)."""
        missing = self.missing()
        if missing:
            raise ProviderNotConfigured(
                "LLM provider is not configured — missing: %s. Set them in the "
                "process environment or in %s (see .env.example), or switch the "
                "UI to Demo Mode." % (", ".join(missing), DEFAULT_ENV_PATH))
        if qa:
            model = self.resolved_qa_model
        elif fast:
            model = self.resolved_fast_model
        else:
            model = self.model
        return OpenAICompatProvider(
            name=self.provider,
            model=model,
            api_key=self.api_key,
            base_url=self.resolved_base_url,
            reasoning_effort=self.resolved_reasoning_effort)


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
        qa_model=pick("LLM_QA_MODEL"),
        # "" → the documented default applies (see _DEFAULT_REASONING_EFFORT)
        reasoning_effort=pick(REASONING_EFFORT_ENV),
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
