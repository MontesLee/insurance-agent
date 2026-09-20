"""Governance data model — Phase 14.3.

The governance layer sits BETWEEN the provider boundary and evidence:

    KnowledgeProvider → KnowledgeHit → GOVERNANCE (here) → Evidence

It is provider-independent BY CONSTRUCTION: it consumes only hits
(attribute-compatible with knowledge.provider.base.KnowledgeHit),
registry metadata, and a QueryContext. It never imports a concrete
provider and never branches on provider identity (Phase 14.3 §19).

Decision vocabulary (§7): CURRENT may enter candidate evidence;
EXPIRED / FUTURE may not ground current decisions (history/audit
only); UNKNOWN is the fail-closed default — a missing effective_from
is NEVER treated as currently-valid.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Deterministic enums — mirror the project's existing ladder
AUTHORITY_LEVELS = ("S", "A", "B", "C", "D")
LICENSE_STATUSES = ("ALLOWED", "RESTRICTED", "UNKNOWN")
JURISDICTION_NATIONAL = "CN"

STATUS_CURRENT = "CURRENT"
STATUS_EXPIRED = "EXPIRED"
STATUS_FUTURE = "FUTURE"
STATUS_UNKNOWN = "UNKNOWN"


class RegistryError(Exception):
    """Malformed registry — fail-closed at LOAD time, never at query
    time (a broken registry must refuse to govern, not guess)."""


@dataclass
class QueryContext:
    """What the decision is being made FOR. as_of is REQUIRED (no
    hidden 'today' default that could mask a missing business date);
    jurisdiction defaults to the national scope CN."""
    as_of: str                                # ISO date "YYYY-MM-DD"
    jurisdiction: str = JURISDICTION_NATIONAL

    def __post_init__(self):
        if not isinstance(self.as_of, str) or len(self.as_of) != 10 \
                or self.as_of[4] != "-" or self.as_of[7] != "-":
            raise RegistryError(
                "QueryContext.as_of must be an ISO date (YYYY-MM-DD), "
                "got %r" % (self.as_of,))


@dataclass
class GovernanceDecision:
    """Deterministic verdict for one hit. reasons are machine-readable
    rule ids + facts, never free prose that could smuggle judgment."""
    allowed: bool
    status: str                               # CURRENT/EXPIRED/FUTURE/UNKNOWN
    reasons: list = field(default_factory=list)
    entry: Optional[dict] = None              # the governing registry entry
