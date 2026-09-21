"""Insurance knowledge governance — Phase 14.3 core.

Deterministic, provider-independent validation of KnowledgeHits
against the agent-side SourceRegistry, plus the evidence builder that
carries the full citation tuple downstream.

Layer contract (§3/§19/§24):

    KnowledgeHit ──► validate_hit(hit, ctx, registry)
                        │  authority · window · jurisdiction ·
                        │  version · license · hash
                        ▼
                  GovernanceDecision ──► build_evidence_item()
                        │                       │
                   allowed hits            Evidence with
                   (candidate)         source/version/window/hash

Every rule FAILS CLOSED: missing metadata is never guessed into
validity ("unknown" ≠ "currently valid"). Reasons are machine-readable
rule ids — no LLM, no scores, no provider identity anywhere.
"""
from __future__ import annotations

import time
from typing import Any, Optional

from .model import (GovernanceDecision, QueryContext, STATUS_CURRENT,
                    STATUS_EXPIRED, STATUS_FUTURE, STATUS_UNKNOWN,
                    JURISDICTION_NATIONAL)
from .registry import SourceRegistry

_VERSION_SEP = "@"


def expected_version_id(entry: dict) -> str:
    return "%s%s%s" % (entry["source_id"], _VERSION_SEP, entry["version"])


def _jurisdiction_ok(entry_j: str, query_j: str) -> bool:
    if entry_j == query_j:
        return True
    # national rules govern every CN-* sub-jurisdiction; a local rule
    # never governs a national-scope query
    return entry_j == JURISDICTION_NATIONAL and query_j.startswith("CN")


def validate_hit(hit: Any, ctx: QueryContext,
                 registry: SourceRegistry) -> GovernanceDecision:
    """Validate ONE hit. Duck-typed on the hit (any object with the
    KnowledgeHit attribute surface) — no provider import, no provider
    branching. All failed rules are collected (audit completeness)."""
    reasons: list = []
    status = STATUS_UNKNOWN
    entry = registry.get_entry(getattr(hit, "document_id", ""))

    # R1 registry resolution — an unregistered document can never
    # ground an insurance decision (Case A/F family)
    if entry is None:
        reasons.append("REGISTRY_MISS:%s" % getattr(hit, "document_id", ""))
        return GovernanceDecision(False, STATUS_UNKNOWN, reasons, None)

    # R2 lifecycle — only an ACTIVE registration may ground evidence;
    # pre-activation states (DISCOVERED/INGESTED/REGISTERED/VALIDATED)
    # and anomaly states (REJECTED/EXPIRED/SUPERSEDED/INVALID) fail
    # closed with the state visible in the reason (Phase 24 §14/§20)
    reg_state = entry.get("status", "ACTIVE")
    if reg_state == "RETIRED":
        reasons.append("SOURCE_RETIRED")
    elif reg_state != "ACTIVE":
        reasons.append("SOURCE_NOT_ACTIVE:%s" % reg_state)

    # R2b version currency — if the registry holds MORE THAN ONE active
    # version of this source covering as_of, the current version is
    # ambiguous and must not ground a decision (never resolved by
    # version-string ordering — Phase 24 §21)
    if reg_state == "ACTIVE" and len(
            registry.concurrent_versions(entry["source_id"],
                                         ctx.as_of)) > 1:
        reasons.append("VERSION_AMBIGUOUS")

    # R3 version identity — which version of the source is this hit?
    hit_version = getattr(hit, "version_id", "") or ""
    want_version = expected_version_id(entry)
    if not hit_version:
        reasons.append("VERSION_MISSING")
    elif hit_version != want_version:
        reasons.append("VERSION_CONFLICT:%s!=%s"
                       % (hit_version, want_version))

    # R4 authority — provider CLAIM must match the agent-side registry
    hit_level = getattr(hit, "source_level", "") or ""
    if not hit_level:
        reasons.append("AUTHORITY_MISSING")            # Case B
    elif hit_level != entry["authority_level"]:
        reasons.append("AUTHORITY_CONFLICT:%s!=%s"     # Case C
                       % (hit_level, entry["authority_level"]))

    # R5 effective window (as-of) — the §6/§7/§15 rule
    as_of = ctx.as_of
    efrom = entry.get("effective_from")
    eto = entry.get("effective_to")
    if efrom is None:
        reasons.append("WINDOW_UNRESOLVED")            # fail closed
        status = STATUS_UNKNOWN
    elif as_of < efrom:
        reasons.append("WINDOW_FUTURE:%s>%s" % (efrom, as_of))
        status = STATUS_FUTURE
    elif eto is not None and as_of > eto:
        reasons.append("WINDOW_EXPIRED:%s<%s" % (eto, as_of))
        status = STATUS_EXPIRED
    else:
        status = STATUS_CURRENT

    # R6 jurisdiction — provider filters are hints; we re-verify
    entry_j = entry.get("jurisdiction", "")
    if not entry_j or not _jurisdiction_ok(entry_j, ctx.jurisdiction):
        reasons.append("JURISDICTION_MISMATCH:%s!~%s"   # Case E
                       % (entry_j, ctx.jurisdiction))

    # R7 license — UNKNOWN/RESTRICTED never enter the production path
    lic = entry.get("license_status")
    if lic == "UNKNOWN":
        reasons.append("LICENSE_UNKNOWN")              # Case D
    elif lic != "ALLOWED":
        reasons.append("LICENSE_RESTRICTED")

    # R8 provenance hash — the anchor that makes tampering detectable
    hit_hash = getattr(hit, "content_hash", "") or ""
    chunk_id = getattr(hit, "chunk_id", "") or ""
    hashes = entry.get("content_hashes") or {}
    if not hit_hash:
        reasons.append("HASH_MISSING")
    elif chunk_id not in hashes:
        reasons.append("CHUNK_UNREGISTERED:%s" % chunk_id)
    elif hit_hash != hashes[chunk_id]:
        reasons.append("HASH_MISMATCH:%s" % chunk_id)  # Case G

    # R9 content presence
    if not (getattr(hit, "content", "") or "").strip():
        reasons.append("CONTENT_EMPTY")

    return GovernanceDecision(not reasons, status, reasons, entry)


def govern_search_result(result: Any, ctx: QueryContext,
                         registry: SourceRegistry) -> Any:
    """Filter a whole canonical KnowledgeSearchResult through
    governance. Returns a result of the SAME type with only allowed
    hits; when everything is rejected the status degrades to
    insufficient_evidence with the rule ids as the reason (fail-closed,
    never an empty success)."""
    from knowledge.provider.base import KnowledgeSearchResult
    hits = list(getattr(result, "results", []) or [])
    kept, decisions, rejected_reasons = [], [], []
    for h in hits:
        d = validate_hit(h, ctx, registry)
        decisions.append({"document_id": getattr(h, "document_id", ""),
                          "chunk_id": getattr(h, "chunk_id", ""),
                          "allowed": d.allowed, "status": d.status,
                          "reasons": d.reasons})
        if d.allowed:
            kept.append(h)
        else:
            rejected_reasons.extend(d.reasons)
    meta = dict(getattr(result, "retrieval_metadata", {}) or {})
    meta["governance"] = {
        "as_of": ctx.as_of, "jurisdiction": ctx.jurisdiction,
        "checked": len(hits), "allowed": len(kept),
        "rejected": len(hits) - len(kept),
        "decision_reasons": sorted(set(rejected_reasons)),
    }
    status = getattr(result, "status", "")
    if hits and not kept:
        status = "insufficient_evidence"
    elif not hits and status == "success":
        status = "insufficient_evidence"
    return KnowledgeSearchResult(
        status=status, query=getattr(result, "query", ""),
        normalized_query=getattr(result, "normalized_query", ""),
        results=kept, conflict=getattr(result, "conflict", False),
        reason=(getattr(result, "reason", "")
                if kept or not hits else
                "governance rejected all hits: %s"
                % ",".join(sorted(set(rejected_reasons))[:6])),
        retrieval_metadata=meta), decisions


def build_evidence_item(hit: Any, decision: GovernanceDecision,
                        ctx: QueryContext, now: Optional[str] = None
                        ) -> dict:
    """Validated hit → evidence item carrying the FULL citation tuple:
    source/version/window/authority/jurisdiction/license/hash +
    retrieved_at + the governance block (as_of, status, rules). Fields
    are ADDITIVE to the existing knowledge-evidence contract items
    (which permit additional properties); nothing existing changes."""
    entry = decision.entry or {}
    now = now or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        # ---- existing contract surface (unchanged semantics) --------
        "evidence_id": getattr(hit, "chunk_id", "") or "",
        "content": getattr(hit, "content", ""),
        "source": getattr(hit, "document_name", "") or "",
        "source_type": getattr(hit, "source_type", "") or "",
        "relevance": getattr(hit, "score", None),
        "confidence": (min(1.0, getattr(hit, "score", 0))
                       if isinstance(getattr(hit, "score", 0),
                                     (int, float)) else None),
        "document_id": getattr(hit, "document_id", "") or "",
        "document_name": getattr(hit, "document_name", "") or "",
        "chunk_id": getattr(hit, "chunk_id", "") or "",
        # Phase 14.5: the EXPLICIT deterministic hit identity (equals
        # chunk_id — the stable retrieval-unit id; no random UUIDs)
        "knowledge_hit_id": getattr(hit, "chunk_id", "") or "",
        "section": getattr(hit, "section", "") or "",
        "source_level": entry.get("authority_level",
                                  getattr(hit, "source_level", "") or ""),
        # ---- Phase 14.3 citation tuple (additive) --------------------
        "source_id": entry.get("source_id", ""),
        "source_name": entry.get("source_name", ""),
        "version_id": expected_version_id(entry) if entry else "",
        "version": entry.get("version", ""),
        "effective_from": entry.get("effective_from"),
        "effective_to": entry.get("effective_to"),
        "authority_level": entry.get("authority_level", ""),
        "jurisdiction": entry.get("jurisdiction", ""),
        "license_status": entry.get("license_status", ""),
        "canonical_uri": entry.get("canonical_uri", ""),
        "content_hash": getattr(hit, "content_hash", "") or "",
        "retrieved_at": now,
        "governance": {
            "as_of": ctx.as_of,
            "jurisdiction": ctx.jurisdiction,
            "window_status": decision.status,
            "checked_rules": ["REGISTRY", "LIFECYCLE", "VERSION",
                              "AUTHORITY", "WINDOW", "JURISDICTION",
                              "LICENSE", "HASH", "CONTENT"],
        },
    }
