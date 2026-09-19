"""LLM provider data-policy gate (Phase 13 R-05).

Round-1 finding: the provider's data-retention / training-usage / region
policy was UNKNOWN — no evidence in-repo. The audit rule is strict:
UNKNOWN must BLOCK real client payloads, never silently allow.

Evidence status (2026-09-19, see
docs/production/provider-policy-verification.md for the full record):

  * The official privacy policy lives behind a JS-rendered SPA
    (docs.bigmodel.cn / open.bigmodel.cn) — verbatim primary text could
    NOT be independently retrieved by automated fetch during remediation.
  * A third-party investigation (zhihu column comparing DeepSeek / Zhipu /
    Ali Bailian) reports the Zhipu general API terms retain an
    "anonymized data may be used for training" clause, with the Coding
    Plan explicitly promising no training — but third-party summaries are
    NOT acceptable as a final production judgment per the evidence rules.

Therefore the gate defaults to BLOCKED for real client data. It opens ONLY
when the operator, after personally reading the current official terms,
sets INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1 (and acknowledges the
record). This is an explicit human-verified opt-in, fail-closed by
default, with no silent fallback.
"""
from __future__ import annotations

import os

# the three client-data modes
SYNTHETIC = "synthetic"   # benchmark / demo / test data (default)
REAL = "real"              # real client PII — requires verified policy


def client_data_mode() -> str:
    mode = os.environ.get("INSURANCE_AGENT_CLIENT_DATA", SYNTHETIC).lower()
    return REAL if mode == REAL else SYNTHETIC


def provider_policy_verified() -> bool:
    """True only on the operator's explicit post-verification opt-in."""
    return os.environ.get("INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED") == "1"


def client_data_allowed() -> tuple:
    """Gate decision for sending payloads to the configured LLM provider.

    Returns (allowed: bool, reason: str). Fail-closed: REAL data without
    a verified provider policy is BLOCKED — never a silent fallback."""
    mode = client_data_mode()
    if mode == SYNTHETIC:
        return True, "synthetic/demo data — provider policy gate not required"
    if provider_policy_verified():
        return True, ("provider policy operator-verified "
                      "(INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1)")
    return False, ("PROVIDER_POLICY_UNVERIFIED: real client data is BLOCKED "
                   "until the operator verifies the provider's data "
                   "retention/training/region terms and sets "
                   "INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1 "
                   "(see docs/production/provider-policy-verification.md)")


class ClientDataBlocked(RuntimeError):
    """Raised by the runtime when real client data would reach an
    unverified provider — fail-closed, never a silent fallback."""
