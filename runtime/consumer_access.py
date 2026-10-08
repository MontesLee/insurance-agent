"""Consumer access control (Phase 28.G — B-02 remediation).

Three deliberately SEPARATE concepts (Owner decision D-01′):

    Consumer Identity  ≠  RBAC Role  ≠  Object Ownership

* Identity — the authenticated subject resolved SERVER-SIDE from the
  request credentials (runtime/auth.py bearer identity). Frontend- or
  client-supplied owner fields are never trusted.
* Role — the internal RBAC class (OWNER/REVIEWER/OPERATOR/CONSUMER).
  A role never implies ownership; `CONSUMER` grants nothing here — it
  only classifies the subject so internal gates can EXCLUDE it.
* Ownership — a server-recorded owner string on Conversations and Runs
  (Artifacts inherit their Run's owner). The deterministic check is
  `subject == object.owner`.

Cross-user semantics (Owner decision D-API-1): an authenticated subject
asking for a missing object or ANOTHER subject's object gets the same
404 — no existence oracle, no owner disclosure. Unauthenticated access
while keys are configured fails closed with 401 (T10). The documented
no-keys local-dev loopback mode (auth.py, Phase 13) keeps its existing
all-allow behavior — that is a frozen deployment mode, not a bypass.

Opaque references (Owner decision D-API-2 / D-05′): consumer-facing
artifact references are high-entropy opaque tokens resolved server-side
to (run_id, artifact_type) — a reference is NEVER authorization; the
ownership check still runs after resolution.
"""
from __future__ import annotations

import threading
import time
import uuid
from typing import Optional

from runtime import auth as runtime_auth


# --------------------------------------------------------------------------- #
# subject resolution
# --------------------------------------------------------------------------- #

def keys_configured() -> bool:
    return bool(runtime_auth.load_identities())


def resolve_subject(ident: Optional[runtime_auth.Identity]) -> Optional[str]:
    """The trusted subject string for an authenticated identity, or None.

    `consumer:<user>` for CONSUMER keys, `rbac:<user>` for internal roles.
    The subject is what ownership compares against — never the raw key.
    """
    if ident is None:
        return None
    prefix = "consumer" if ident.role == "CONSUMER" else "rbac"
    return "%s:%s" % (prefix, ident.user)


def is_internal(ident: Optional[runtime_auth.Identity]) -> bool:
    """Internal (Operator/Developer) duty identity — may read any object
    (existing behavior; NOT a consumer grant). Dev mode (None) is not
    'internal': it follows the dev-allow rule below."""
    return ident is not None and ident.has_role("OPERATOR")


def read_allowed(ident: Optional[runtime_auth.Identity],
                 owner: Optional[str]) -> bool:
    """Deterministic object-read decision at the endpoint boundary (O-8).

    401 / 404 are raised by the caller (server) so response shaping stays
    uniform; this function only answers may-read.
    """
    if ident is None:
        # documented no-keys local-dev loopback: objects have no owners
        # and no subject exists — existing all-allow behavior (auth.py)
        return not keys_configured() and owner is None
    if is_internal(ident):
        return True  # operator/developer duty (O-7 — unchanged)
    return resolve_subject(ident) == owner


# --------------------------------------------------------------------------- #
# opaque artifact references (D-05′) — in-memory V0.1 (matches the
# ChatManager/RunManager persistence tier; survives with the process)
# --------------------------------------------------------------------------- #

class ArtifactRefRegistry:
    """ref -> (run_id, artifact_type). Issued per (owner-visible) request;
    resolution ALWAYS re-checks run ownership — a ref alone grants nothing."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._refs: dict = {}

    def issue(self, run_id: str, artifact_type: str) -> str:
        ref = "ar_%s" % uuid.uuid4().hex[:24]
        with self._lock:
            self._refs[ref] = (run_id, artifact_type)
        return ref

    def resolve(self, ref: str) -> Optional[tuple]:
        with self._lock:
            return self._refs.get(ref)

    def revoke_for_run(self, run_id: str) -> int:
        """28.I (D-GOV-4): artifact refs follow the PARENT run lifecycle —
        deleting a run's business data invalidates every ref into it, so
        no deep link outlives its object. Returns revoked count."""
        with self._lock:
            dead = [r for r, (rid, _) in self._refs.items() if rid == run_id]
            for r in dead:
                del self._refs[r]
            return len(dead)


# --------------------------------------------------------------------------- #
# enumeration protection (D-API-2) — minimal in-memory sliding window
# --------------------------------------------------------------------------- #

class RateLimiter:
    """Per-key sliding window. Server-side only; never a substitute for
    authorization — it throttles probing on top of uniform 404s."""

    def __init__(self, limit: int = 240, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._lock = threading.Lock()
        self._hits: dict = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # occasional sweep so idle keys don't accumulate
            if len(self._hits) > 4096:
                self._hits = {k: [t for t in v if now - t < self.window_s]
                              for k, v in self._hits.items()}
            hits = [t for t in self._hits.get(key, []) if now - t < self.window_s]
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


artifact_refs = ArtifactRefRegistry()
consumer_limiter = RateLimiter(limit=240, window_s=60.0)
