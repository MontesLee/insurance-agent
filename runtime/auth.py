"""Authentication / authorization for the controlled pilot (Phase 13 R-06).

Round-1 finding: the server had NO authentication, CORS `allow_origins=
["*"]`, and trusted client-supplied `actor` strings on approval/control
endpoints. Scope here is deliberately minimal — single node, owner + 1–3
trusted users — not enterprise IAM.

Design:

* Identity — static API keys provisioned by the owner via
  `INSURANCE_AGENT_API_KEYS` (comma-separated `key:role:user` entries) or
  a keys file `INSURANCE_AGENT_API_KEYS_FILE` (one `key:role:user` per
  line). Roles: `OWNER` (everything), `REVIEWER` (read + approve/reject),
  `OPERATOR` (read + run/control), `CONSUMER` (28.G: an authenticated
  CONSUMER subject — access ONLY to objects it owns; ownership lives on
  the objects, NEVER on this role). Requests authenticate with
  `Authorization: Bearer <key>`.
* Authorization — endpoint classes declare a minimum role; the
  authenticated identity (never the request body) becomes the actor.
* CORS — allowlist from `INSURANCE_AGENT_CORS_ORIGINS` (comma-separated).
  `*` is only honored in explicit development mode
  (`INSURANCE_AGENT_DEV=1`), never by default.
* Fail-closed — when any API keys are configured but the request carries
  no/unknown credentials, protected endpoints return 401. When NO keys
  are configured the server refuses to start in production mode
  (`INSURANCE_AGENT_MODE=production`) and otherwise runs in the
  documented local-development mode (loopback-bound).
"""
from __future__ import annotations

import os
from typing import Optional

ROLES = ("OWNER", "REVIEWER", "OPERATOR", "CONSUMER")
# rank order preserved (REVIEWER ⊇ OPERATOR ⊇ …); CONSUMER sits below
# every internal role — it passes no internal gate (28.G G-B02-10)
_ROLE_RANK = {"CONSUMER": 1, "OPERATOR": 2, "REVIEWER": 3, "OWNER": 4}


class Identity:
    def __init__(self, user: str, role: str, key_id: str):
        self.user = user
        self.role = role
        self.key_id = key_id  # first 8 chars only — never the full key

    @property
    def rank(self) -> int:
        return _ROLE_RANK.get(self.role, 0)

    def has_role(self, minimum: str) -> bool:
        return self.rank >= _ROLE_RANK.get(minimum, 99)


def load_identities() -> dict:
    """key -> Identity. Empty dict = no auth configured (dev mode)."""
    raw = os.environ.get("INSURANCE_AGENT_API_KEYS", "")
    kf = os.environ.get("INSURANCE_AGENT_API_KEYS_FILE")
    if not raw and kf and os.path.isfile(kf):
        with open(kf, encoding="utf-8") as f:
            raw = ",".join(l.strip() for l in f if l.strip()
                           and not l.startswith("#"))
    identities = {}
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) != 3:
            continue
        key, role, user = parts
        role = role.upper()
        if role not in ROLES or len(key) < 16:
            continue  # malformed entry — skipped, never trusted
        identities[key] = Identity(user, role, key[:8])
    return identities


def authenticate(header_value: Optional[str],
                 identities: Optional[dict] = None) -> Optional[Identity]:
    """Resolve the Bearer token to an Identity; None when unauthenticated."""
    identities = load_identities() if identities is None else identities
    if not identities or not header_value:
        return None
    scheme, _, token = header_value.partition(" ")
    if scheme.lower() != "bearer":
        return None
    return identities.get(token.strip())


def cors_origins() -> list:
    """CORS allowlist. `*` only in explicit dev mode; production defaults
    to the UI dev-server origins on loopback."""
    dev = os.environ.get("INSURANCE_AGENT_DEV") == "1"
    raw = os.environ.get(
        "INSURANCE_AGENT_CORS_ORIGINS",
        "*" if dev else "http://localhost:5173,http://127.0.0.1:5173")
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    if "*" in origins and not dev:
        # wildcard is only honored in explicit dev mode; outside it the
        # allowlist silently drops the wildcard (fail-closed to loopback)
        origins = [o for o in origins if o != "*"] or [
            "http://localhost:5173", "http://127.0.0.1:5173"]
    return origins


def production_mode() -> bool:
    return os.environ.get("INSURANCE_AGENT_MODE", "").lower() == "production"
