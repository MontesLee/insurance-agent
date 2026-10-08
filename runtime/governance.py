"""Data governance & lifecycle (Phase 28.I — B-04 / D-GOV-1..6).

Implements the OWNER-DECIDED governance principles as a small, testable
core — deliberately NO scheduler (eligibility is a pure function; a
scheduled executor can be attached later as an adapter):

  * Data classification      D1..D5 (see config/data-governance-policy.json)
  * Retention policy         configurable per class (file + env override);
                             business code NEVER reads magic day numbers
  * Deletion eligibility     pure: f(created_at, now, policy, legal_hold)
  * Legal hold               runtime registry; blocks business deletion
                             (minimal generic mechanism — no legal rulings)
  * Consumer deletion        authenticated subject + ownership + policy →
                             auditable cascade (wired in server.py)
  * Tombstones               identity/timestamp/reason only — no content
  * Access audit             actor/object/action metadata only (GOV-7)

SECURITY/AUDIT records are independent: business deletion NEVER cascades
into them (D-GOV-1); trace/eval carry user content and therefore cascade
WITH their parent object (D-GOV-5).
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Optional

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_POLICY_PATH = os.path.join(REPO, "config",
                                   "data-governance-policy.json")
POLICY_ENV = "INSURANCE_AGENT_RETENTION_POLICY"

BUSINESS = "business_content"
TRACE = "operational_trace"
EVAL = "evaluation_data"
AUDIT = "security_audit"
META = "system_metadata"
DATA_CLASSES = (BUSINESS, TRACE, EVAL, AUDIT, META)

STATUS_ACTIVE = "ACTIVE"
STATUS_DELETED = "DELETED"


class GovernanceError(RuntimeError):
    """Refused lifecycle operation (fail closed)."""


# --------------------------------------------------------------------------- #
# policy
# --------------------------------------------------------------------------- #
_POLICY_LOCK = threading.Lock()
_POLICY_CACHE: dict = {}


def load_policy(path: Optional[str] = None) -> dict:
    """The retention/deletion policy. Source: explicit path arg (tests),
    then INSURANCE_AGENT_RETENTION_POLICY, then the repo default file.
    Values are DEPLOYMENT CONFIG (owner decision D-GOV-1) — never law."""
    p = path or os.environ.get(POLICY_ENV, "") or DEFAULT_POLICY_PATH
    key = os.path.abspath(p)
    mtime = os.path.getmtime(key) if os.path.isfile(key) else -1
    with _POLICY_LOCK:
        hit = _POLICY_CACHE.get(key)
        if hit and hit[0] == mtime:
            return hit[1]
        with open(key, encoding="utf-8") as f:
            policy = json.load(f)
        for cls in DATA_CLASSES:
            if cls not in policy.get("classes", {}):
                raise GovernanceError(
                    "retention policy missing class %r (%s)" % (cls, key))
        _POLICY_CACHE[key] = (mtime, policy)
        return policy


def class_policy(data_class: str, path: Optional[str] = None) -> dict:
    pol = load_policy(path).get("classes", {}).get(data_class)
    if pol is None:
        raise GovernanceError("unknown data class %r" % data_class)
    return pol


def deletion_eligible(data_class: str, created_at: float, *,
                      now: Optional[float] = None,
                      legal_hold: bool = False,
                      consumer_requested: bool = False,
                      path: Optional[str] = None) -> tuple:
    """Pure eligibility: (eligible, reason). Deterministic clock injectable.

    Rules (D-GOV-1/3): legal hold blocks business deletion; a CONSUMER
    request may delete business content at ANY time (its own lifecycle);
    otherwise eligibility arrives after the class retention window.
    security_audit / system_metadata are never business-deletable.
    """
    if data_class not in (BUSINESS, TRACE, EVAL):
        return False, "class_not_business_deletable"
    if legal_hold:
        return False, "legal_hold"
    days = float(class_policy(data_class, path).get("retention_days", 0))
    age_days = ((now if now is not None else time.time()) - created_at) / 86400.0
    if consumer_requested and data_class == BUSINESS:
        return True, "consumer_requested"
    if age_days >= days:
        return True, "retention_reached"
    return False, "within_retention (%.1f/%.0f days)" % (age_days, days)


# --------------------------------------------------------------------------- #
# legal holds (minimal generic mechanism; no legal scenario definitions)
# --------------------------------------------------------------------------- #
_HOLDS_LOCK = threading.Lock()
_HOLDS: set = set()


def set_legal_hold(object_key: str, held: bool = True) -> None:
    with _HOLDS_LOCK:
        if held:
            _HOLDS.add(object_key)
        else:
            _HOLDS.discard(object_key)


def has_legal_hold(object_key: str) -> bool:
    with _HOLDS_LOCK:
        return object_key in _HOLDS


# --------------------------------------------------------------------------- #
# tombstones (identity only — no user content, not restorable)
# --------------------------------------------------------------------------- #
_TOMB_LOCK = threading.Lock()
_TOMBSTONES: dict = {}


def write_tombstone(object_class: str, object_id: str, *,
                    reason: str, actor: str) -> dict:
    ts = {
        "object_class": object_class,
        "object_id": object_id,
        "deleted_at": _now_iso(),
        "reason": reason,
        "actor": actor,
    }
    with _TOMB_LOCK:
        _TOMBSTONES["%s:%s" % (object_class, object_id)] = ts
    return ts


def tombstone(object_class: str, object_id: str) -> Optional[dict]:
    with _TOMB_LOCK:
        return _TOMBSTONES.get("%s:%s" % (object_class, object_id))


# --------------------------------------------------------------------------- #
# access audit (D-GOV-6 / GOV-7): metadata only — NEVER content/secrets
# --------------------------------------------------------------------------- #
_AUDIT_LOCK = threading.Lock()
_AUDIT: list = []


def audit(actor: str, action: str, object_class: str, object_id: str, *,
          subject: str = "", purpose: str = "",
          outcome: str = "ok") -> dict:
    """Append an access/lifecycle audit record. Fields are bounded to
    identifiers and enums by construction — callers cannot smuggle
    message/artifact bodies in (strings are truncated defensively)."""
    rec = {
        "ts": _now_iso(),
        "actor": _clip(actor),
        "action": _clip(action, 32),
        "object_class": _clip(object_class, 32),
        "object_id": _clip(object_id, 64),
        "subject": _clip(subject, 64),
        "purpose": _clip(purpose, 64),
        "outcome": _clip(outcome, 16),
    }
    with _AUDIT_LOCK:
        _AUDIT.append(rec)
    return rec


def audit_records(limit: int = 200) -> list:
    with _AUDIT_LOCK:
        return list(_AUDIT[-limit:])


def _clip(value: str, n: int = 128) -> str:
    return (str(value or ""))[:n]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
