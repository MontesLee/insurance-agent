"""Provenance closure — Phase 14.5.

Deterministic validators for the complete, auditable lineage:

    Decision → Evidence → KnowledgeHit → Document → Version → Source

Rules P001–P010 (fail-closed, all violations collected as
machine-readable rule ids — never prose, never guessed defaults):

    P001 evidence identity exists (evidence_id)
    P002 the Evidence locates its KnowledgeHit (chunk identity, and the
         chunk is registered under the document's hashes)
    P003 the hit locates its Document (registry entry exists)
    P004 the Document locates its Version (version_id == source@version)
    P005 the Evidence locates its Source (source_id matches the registry)
    P006 provenance does not CONFLICT with governance metadata
         (version / authority / window status re-derived from the
          registry + the recorded as-of)
    P007 content_hash matches the registry-anchored chunk hash
    P008 jurisdiction matches the registry
    P009 license UNKNOWN never becomes ALLOWED (and must be ALLOWED)
    P010 broken lineage fails closed — no partial "complete provenance"

Design rules (Phase 14.5 §3/§4): the hit identity IS the deterministic
chunk_id (no random UUIDs; identical inputs → identical lineage); the
explicit `knowledge_hit_id` field is that identity, surfaced. NOTHING
here stores chain-of-thought — only structured, machine-parsable
provenance.
"""
from __future__ import annotations

from typing import Any, Optional

from .model import QueryContext
from .registry import SourceRegistry
from .governance import expected_version_id, validate_hit

_BANNED_COT_KEYS = ("chain_of_thought", "reasoning_trace",
                    "hidden_reasoning", "internal_deliberation",
                    "thought_process")

_NO_EVIDENCE_MARKERS = ("NO_EVIDENCE_REQUIRED",)


def _get(item: Any, key: str, default=None):
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def validate_provenance(evidence_item: Any, registry: SourceRegistry,
                        as_of: Optional[str] = None) -> tuple:
    """Cross-lineage consistency check — NOT a field-presence-only
    check: every hop is resolved against the registry and every value
    is re-derived. Returns (ok, reasons[list of P-rule ids])."""
    reasons: list = []

    # P001 — identity
    evidence_id = _get(evidence_item, "evidence_id")
    if not evidence_id:
        reasons.append("P001:evidence_id_missing")

    # P002 — hit locatable (explicit field preferred; chunk_id is the
    # deterministic hit identity)
    hit_id = _get(evidence_item, "knowledge_hit_id") \
        or _get(evidence_item, "chunk_id")
    if not hit_id:
        reasons.append("P002:knowledge_hit_id_missing")
        return (not reasons), reasons          # nothing else resolvable

    # P003 — document
    document_id = _get(evidence_item, "document_id")
    entry = registry.get_entry(document_id) if document_id else None
    if entry is None:
        reasons.append("P003:document_unresolvable:%s"
                       % (document_id or "<missing>"))
        return (not reasons), reasons

    hashes = entry.get("content_hashes") or {}
    if hit_id not in hashes:
        reasons.append("P002:chunk_unregistered:%s" % hit_id)

    # P004 — version
    version_id = _get(evidence_item, "version_id") or ""
    want_vid = expected_version_id(entry)
    if not version_id:
        reasons.append("P004:version_missing")
    elif version_id != want_vid:
        reasons.append("P004:version_conflict:%s!=%s"
                       % (version_id, want_vid))
    elif str(_get(evidence_item, "version") or "") != str(
            entry.get("version")):
        reasons.append("P006:version_disagrees_with_version_id")

    # P005 — source
    source_id = _get(evidence_item, "source_id") or ""
    if source_id != entry.get("source_id"):
        reasons.append("P005:source_conflict:%s!=%s"
                       % (source_id, entry.get("source_id")))

    # P006 — governance-consistency (window status re-derivation)
    gov = _get(evidence_item, "governance") or {}
    eff_from, eff_to = entry.get("effective_from"), entry.get("effective_to")
    as_of = as_of or gov.get("as_of")
    if as_of:
        if as_of < eff_from:
            want_status = "FUTURE"
        elif eff_to is not None and as_of > eff_to:
            want_status = "EXPIRED"
        else:
            want_status = "CURRENT"
        if gov.get("window_status") not in (None, want_status):
            reasons.append("P006:window_status_conflict:%s!=%s"
                           % (gov.get("window_status"), want_status))
        if gov.get("as_of") and as_of != gov.get("as_of"):
            reasons.append("P006:as_of_conflict")
    auth = _get(evidence_item, "authority_level") \
        or _get(evidence_item, "source_level") or ""
    if auth and auth != entry.get("authority_level"):
        reasons.append("P006:authority_conflict:%s!=%s"
                       % (auth, entry.get("authority_level")))

    # P007 — hash
    content_hash = _get(evidence_item, "content_hash") or ""
    if not content_hash:
        reasons.append("P007:hash_missing")
    elif hit_id in hashes and content_hash != hashes[hit_id]:
        reasons.append("P007:hash_mismatch:%s" % hit_id)

    # P008 — jurisdiction
    jurisdiction = _get(evidence_item, "jurisdiction")
    if jurisdiction is None or jurisdiction != entry.get("jurisdiction"):
        reasons.append("P008:jurisdiction_conflict:%r!=%s"
                       % (jurisdiction, entry.get("jurisdiction")))

    # P009 — license (UNKNOWN can never pass as ALLOWED)
    license_status = _get(evidence_item, "license_status")
    entry_license = entry.get("license_status")
    if license_status != "ALLOWED" or entry_license != "ALLOWED":
        reasons.append("P009:license_not_allowed:%r/%s"
                       % (license_status, entry_license))

    # P010 — retrieval timestamp (lineage completeness includes WHEN)
    if not _get(evidence_item, "retrieved_at"):
        reasons.append("P010:retrieved_at_missing")

    return (not reasons), reasons


def decision_evidence_refs(decision: Any) -> list:
    """Pull the evidence references a decision declares (contract
    field first, structured basis second)."""
    if not isinstance(decision, dict):
        return []
    payload = decision.get("payload", decision)
    refs = payload.get("evidence_refs") or []
    if not refs:
        basis = payload.get("decision_basis") or payload.get("basis") or []
        refs = [b.get("evidence_id") for b in basis
                if isinstance(b, dict) and b.get("evidence_id")]
    return [r for r in refs if r]


def is_no_evidence_required(decision: Any) -> bool:
    """An explicit, honest opt-out — never a way to dodge a REQUIRED
    binding (callers decide which decisions require evidence)."""
    if not isinstance(decision, dict):
        return False
    payload = decision.get("payload", decision)
    return bool(payload.get("no_evidence_required")) \
        or payload.get("evidence_policy") in _NO_EVIDENCE_MARKERS


def validate_decision_provenance(decision: Any,
                                 evidence_index: Any,
                                 registry: SourceRegistry,
                                 require_evidence: bool = True) -> tuple:
    """Decision → Evidence → full lineage. evidence_index maps
    evidence_id → evidence item (a stored knowledge-evidence artifact
    payload or a dict). A decision that declares evidence must find
    EVERY ref valid; NO_EVIDENCE_REQUIRED passes explicitly. Returns
    (ok, reasons)."""
    reasons: list = []
    if is_no_evidence_required(decision):
        return True, []
    refs = decision_evidence_refs(decision)
    if not refs:
        if require_evidence:
            reasons.append("D001:evidence_required_but_missing")
        return (not reasons), reasons
    index = evidence_index if isinstance(evidence_index, dict) else {}
    for r in refs:
        item = index.get(r)
        if item is None:
            reasons.append("D002:evidence_ref_unresolvable:%s" % r)
            continue
        ok, why = validate_provenance(item, registry)
        if not ok:
            reasons.extend("D003:%s" % w for w in why)
    return (not reasons), reasons


def scan_chain_of_thought(obj: Any, depth: int = 0) -> list:
    """Return any banned reasoning-leak keys found in a provenance
    structure (defensive check; nothing should ever produce them)."""
    found = []
    if depth > 8:
        return found
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _BANNED_COT_KEYS:
                found.append(str(k))
            found.extend(scan_chain_of_thought(v, depth + 1))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            found.extend(scan_chain_of_thought(v, depth + 1))
    return found
