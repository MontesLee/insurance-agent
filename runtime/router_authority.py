"""Router Authority staging (Phase 28.M4 / ADR-025 §5, APPROVED).

The staged authority value — a SINGLE knob with three levels:

    slices   (default / unset)  per-slice feature flags govern; the
                                Router dispatches nothing by itself
    no-plan                      insurance_qa + product_qa are
                                Router-AUTHORITATIVE (their slice
                                flags are bypassed); planning and the
                                rest stay flag-governed
    full                        all three verified paths (QA, Product
                                QA, Planning) are Router-authoritative

FAIL-CLOSED: an invalid value RAISES AuthorityConfigError — the server's
fail-quiet shadow block then leaves every slice un-fired (an authority
grant can never happen through a typo). Setting `full` in PRODUCTION is
a separate owner decision (the production authorization gate); this
module only RESOLVES the mode, it never promotes itself.

Unknown intents are NOT staged: the Router table's conversation-agent
fallback already serves them and no conversation behavior unit exists
(scope: the three verified paths only).
"""
from __future__ import annotations

import os
from typing import Optional

AUTHORITY_ENV = "INSURANCE_AGENT_ROUTER_AUTHORITY"

MODE_SLICES = "slices"
MODE_NO_PLAN = "no-plan"
MODE_FULL = "full"

_MODES = (MODE_SLICES, MODE_NO_PLAN, MODE_FULL)

# intents the Router is authoritative for, per mode (ADR-025 §5)
_AUTHORITATIVE = {
    MODE_SLICES: frozenset(),
    MODE_NO_PLAN: frozenset({"insurance_qa", "product_qa"}),
    MODE_FULL: frozenset({"insurance_qa", "product_qa", "insurance_plan",
                          "modify_existing_plan"}),
}


class AuthorityConfigError(ValueError):
    """Invalid authority value — refuse to grant anything (fail-closed)."""


def authority_mode(env: Optional[dict] = None) -> str:
    e = os.environ if env is None else env
    raw = str(e.get(AUTHORITY_ENV, "")).strip().lower()
    if raw == "":
        return MODE_SLICES
    if raw not in _MODES:
        raise AuthorityConfigError(
            "%s=%r unsupported (slices|no-plan|full) — refusing to "
            "grant authority (fail closed)" % (AUTHORITY_ENV, raw[:40]))
    return raw


def authority_governs(mode: str, intent_id: str) -> bool:
    """Does the Router (not a slice flag) govern this intent under
    `mode`? Pure set lookup — no env, no side effects."""
    return intent_id in _AUTHORITATIVE.get(mode, frozenset())


def authoritative_intents(mode: str) -> frozenset:
    return _AUTHORITATIVE.get(mode, frozenset())
