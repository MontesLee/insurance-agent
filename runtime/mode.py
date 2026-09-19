"""Runtime execution mode (Phase 13 P0.1).

One explicit environment selector instead of inferring intent from
scattered booleans:

    INSURANCE_AGENT_MODE = DEMO | EVALUATION | CONTROLLED_PILOT | PRODUCTION
    (default: DEMO)

Mode semantics (the production-safety hardening contract):

  DEMO / EVALUATION
      The Phase 7–12 validation posture: final review OFF, encryption
      optional, authentication optional (local loopback), demo catalog.
      Every existing benchmark/portfolio suite runs in these modes.

  CONTROLLED_PILOT / PRODUCTION
      Fail-closed production safety defaults — the operator cannot weaken
      them by forgetting a flag:
        * FINAL REVIEW MANDATORY  (cannot be disabled)
        * ENCRYPTION MANDATORY    (missing key → BLOCK, no plaintext)
        * AUTHENTICATION MANDATORY (missing key config → BLOCK)
      Combined with R-05's provider gate, these are the three defaults
      this hardening round enforces.

This module is pure policy: it only ANSWERS questions (mode(), is_*()
predicates, required_*() checks). Enforcement stays at the existing
boundaries (harness constructor, store, server startup).
"""
from __future__ import annotations

import os

DEMO = "demo"
EVALUATION = "evaluation"
CONTROLLED_PILOT = "controlled_pilot"
PRODUCTION = "production"

VALID_MODES = (DEMO, EVALUATION, CONTROLLED_PILOT, PRODUCTION)
# the fail-closed modes — identical hardening contract
STRICT_MODES = (CONTROLLED_PILOT, PRODUCTION)

_UNKNOWN_MSG = ("INSURANCE_AGENT_MODE must be one of %s (got %%r); "
                "refusing to guess — an unknown mode must never fall back "
                "to permissive defaults" % "/".join(VALID_MODES))


def mode() -> str:
    raw = os.environ.get("INSURANCE_AGENT_MODE", DEMO).strip().lower()
    if raw == "local":          # legacy alias from the auth module
        raw = DEMO
    if raw not in VALID_MODES:
        raise RuntimeError(_UNKNOWN_MSG % raw)
    return raw


def is_strict() -> bool:
    """True for CONTROLLED_PILOT / PRODUCTION — the hardened modes."""
    return mode() in STRICT_MODES


def validate_mode(raw: str) -> None:
    """Fail-closed validation of an explicit mode string (used at startup
    so a typo BLOCKS instead of defaulting)."""
    r = (raw or "").strip().lower()
    if r == "local":
        r = DEMO
    if r not in VALID_MODES:
        raise RuntimeError(_UNKNOWN_MSG % raw)


def final_review_required(explicit_flag: bool = False) -> bool:
    """R-02 hardening: in strict modes the final-review gate is MANDATORY
    — an explicit require_final_review=False cannot disable it."""
    return True if is_strict() else bool(explicit_flag)


def encryption_required() -> bool:
    """R-04 hardening: strict modes REQUIRE an at-rest encryption key."""
    return is_strict()


def authentication_required() -> bool:
    """R-06 hardening: strict modes REQUIRE configured API keys — the
    absence of keys may never be interpreted as 'development'."""
    return is_strict()
