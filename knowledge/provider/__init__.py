"""KnowledgeProvider package — Stage 14.1 composition boundary.

Provider SELECTION lives HERE (configuration), never inside the
knowledge tool or any agent logic (plan §12: no
`if production: WeKnora() else: Mock()` in tools). Selection order:

    1. an explicitly injected default (set_default_provider) — tests
       and future composition roots;
    2. INSURANCE_AGENT_KNOWLEDGE_PROVIDER (default "mock").

Fail-closed selection: an unknown provider name raises
ProviderConfigError — it NEVER falls back to mock (a typo must not
silently change the production knowledge source).
"""
from __future__ import annotations

import os
from typing import Optional

from .base import (KnowledgeFilters, KnowledgeHit, KnowledgeProvider,
                   KnowledgeSearchResult, ProviderConfigError,
                   ProviderError, ProviderResponseInvalid,
                   ProviderUnavailable)
from .mock import MockKnowledgeProvider
from .weknora import WeKnoraKnowledgeProvider, map_weknora_response

PROVIDER_ENV = "INSURANCE_AGENT_KNOWLEDGE_PROVIDER"
DEFAULT_PROVIDER_NAME = "mock"
# Phase 18 (HG15, closes F-02): in STRICT runtime modes the provider
# must be EXPLICIT — an unset configuration never silently selects the
# offline mock. The strict-mode set mirrors runtime/mode.py WITHOUT
# importing it (this package must stay free of runtime imports —
# enforced by the Phase-14.1 boundary tests).
_STRICT_MODES = ("controlled_pilot", "production")

_default_provider: Optional[object] = None


def _strict_mode_requires_explicit_provider() -> bool:
    return os.environ.get("INSURANCE_AGENT_MODE", "demo").strip().lower() \
        in _STRICT_MODES


def build_named_provider(name: str):
    """Named construction — the ONLY place provider names are resolved."""
    n = (name or "").strip().lower()
    if n == "mock":
        return MockKnowledgeProvider()
    if n == "weknora":
        # No transport in 14.1: the real client is wired in the 14.2
        # POC. A selected-but-unconfigured WeKnora FAILS CLOSED at
        # search time (ProviderUnavailable), it never degrades to mock.
        return WeKnoraKnowledgeProvider()
    raise ProviderConfigError(
        "unknown knowledge provider %r (supported: mock, weknora) — "
        "refusing to guess" % name)


def default_provider():
    """The provider the knowledge tool uses. Explicit injection wins
    over the environment; unknown env values fail closed. In STRICT
    modes an UNSET provider env fails closed too (HG15): mock is a
    deliberate choice, never a silent default."""
    global _default_provider
    if _default_provider is not None:
        return _default_provider
    name = os.environ.get(PROVIDER_ENV)
    if name is None and _strict_mode_requires_explicit_provider():
        raise ProviderConfigError(
            "strict runtime mode requires an explicit "
            "INSURANCE_AGENT_KNOWLEDGE_PROVIDER (mock|weknora) — "
            "refusing to silently default to the offline mock")
    return build_named_provider(name or DEFAULT_PROVIDER_NAME)


def set_default_provider(provider) -> None:
    """Composition root / test injection point."""
    global _default_provider
    _default_provider = provider


def injected_provider():
    """The explicitly-injected provider (set_default_provider), or
    None. The KnowledgeService composition consults this FIRST so an
    injection always wins over env/default selection."""
    return _default_provider


def reset_default_provider() -> None:
    """Drop an explicit injection; selection falls back to the env."""
    global _default_provider
    _default_provider = None


__all__ = [
    "KnowledgeProvider", "KnowledgeFilters", "KnowledgeHit",
    "KnowledgeSearchResult",
    "ProviderError", "ProviderConfigError", "ProviderUnavailable",
    "ProviderResponseInvalid",
    "MockKnowledgeProvider", "WeKnoraKnowledgeProvider",
    "map_weknora_response",
    "default_provider", "set_default_provider", "reset_default_provider",
    "build_named_provider", "PROVIDER_ENV", "DEFAULT_PROVIDER_NAME",
]
