"""Knowledge Source Registry — Phase 14.3 (G1/G5/G6).

A registry ENTRY is one (document, version) record — the unit WeKnora
or any backend will project as one uploaded document:

    document_id       unique KB document id == hit.document_id
    source_id         canonical source identity (groups versions:
                      the 2024 and 2026 editions of one regulation
                      share source_id, differ in version/window)
    source_name / source_type / canonical_uri
    authority_level   S/A/B/C/D  — AUTHORITATIVE on the agent side
    jurisdiction      CN | CN-<REGION>
    version           the source's own dating (e.g. "2024")
    effective_from / effective_to   ISO dates; effective_to null = open
    status            ACTIVE | RETIRED (tiny lifecycle, nothing more)
    license_status    ALLOWED | RESTRICTED | UNKNOWN
    content_hashes    {chunk_id: sha256} — provenance anchors (§12)

Load-time validation is fail-closed (RegistryError): duplicates, bad
enums, malformed dates, or backwards windows refuse the WHOLE registry
rather than governing with partial trust.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Optional

from .model import (AUTHORITY_LEVELS, LICENSE_STATUSES, RegistryError)


def _valid_date(s) -> bool:
    if not isinstance(s, str) or len(s) != 10:
        return False
    if s[4] != "-" or s[7] != "-":
        return False
    try:
        int(s[:4]); int(s[5:7]); int(s[8:10])
    except ValueError:
        return False
    return 1 <= int(s[5:7]) <= 12 and 1 <= int(s[8:10]) <= 31


class SourceRegistry:
    """Read-only, deterministic registry over validated entries."""

    def __init__(self, entries: list):
        self._by_document: dict = {}
        for e in entries:
            self._validate(e)
            doc = e["document_id"]
            if doc in self._by_document:
                raise RegistryError("duplicate document_id: %s" % doc)
            self._by_document[doc] = e
        self.entries = list(entries)

    # ---- load / build ------------------------------------------------ #
    @staticmethod
    def _validate(e: dict) -> None:
        for f in ("document_id", "source_id", "source_name", "version"):
            if not isinstance(e.get(f), str) or not e[f]:
                raise RegistryError("entry missing %s" % f)
        if e.get("authority_level") not in AUTHORITY_LEVELS:
            raise RegistryError(
                "entry %s: bad authority_level %r"
                % (e["document_id"], e.get("authority_level")))
        if e.get("license_status") not in LICENSE_STATUSES:
            raise RegistryError(
                "entry %s: bad license_status %r"
                % (e["document_id"], e.get("license_status")))
        if not _valid_date(e.get("effective_from")):
            raise RegistryError(
                "entry %s: effective_from must be an ISO date"
                % e["document_id"])
        eto = e.get("effective_to")
        if eto is not None and not _valid_date(eto):
            raise RegistryError(
                "entry %s: effective_to must be ISO or null"
                % e["document_id"])
        if eto is not None and eto < e["effective_from"]:
            raise RegistryError(
                "entry %s: effective_to before effective_from"
                % e["document_id"])
        if e.get("status", "ACTIVE") not in ("ACTIVE", "RETIRED"):
            raise RegistryError("entry %s: bad status" % e["document_id"])
        hashes = e.get("content_hashes")
        if not isinstance(hashes, dict) or not hashes:
            raise RegistryError(
                "entry %s: content_hashes {chunk_id: sha256} required"
                % e["document_id"])

    @classmethod
    def from_json(cls, path: str) -> "SourceRegistry":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    @classmethod
    def from_kb(cls, kb_dir: str, table_path: str) -> "SourceRegistry":
        """Build a registry from a metadata table + the KB the mock
        engine ingests: chunk hashes are COMPUTED with the EXISTING
        heading-aware chunker, so they can never drift from what
        retrieval actually returns. (Future ingestion pipelines use
        the same anchor rule.)"""
        from knowledge.rag.store import chunk_markdown
        with open(table_path, encoding="utf-8") as f:
            table = json.load(f)
        entries = []
        for row in table:
            path = os.path.join(kb_dir, row["document_id"] + ".md")
            if not os.path.isfile(path):
                raise RegistryError(
                    "table row %s: no KB document at %s"
                    % (row["document_id"], path))
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
            chunks = chunk_markdown(text, row["document_id"],
                                    row["document_id"])
            e = dict(row)
            e["content_hashes"] = {
                ch.chunk_id: hashlib.sha256(
                    ch.content.encode("utf-8")).hexdigest()
                for ch in chunks}
            entries.append(e)
        return cls(entries)

    # ---- lookups ------------------------------------------------------ #
    def get_entry(self, document_id: str) -> Optional[dict]:
        return self._by_document.get(document_id)

    def versions_of(self, source_id: str) -> list:
        """All registered versions of one canonical source, newest
        effective_from first — the §11 'same source, distinguishable
        versions' primitive."""
        vs = [e for e in self.entries if e["source_id"] == source_id]
        return sorted(vs, key=lambda e: e["effective_from"], reverse=True)

    def current_entry(self, source_id: str, as_of: str) -> Optional[dict]:
        """The version in force at as_of, or None (gap / not yet)."""
        for e in self.versions_of(source_id):
            if e["effective_from"] <= as_of and (
                    e.get("effective_to") is None
                    or as_of <= e["effective_to"]):
                return e
        return None

    def provider_stamps(self) -> dict:
        """Metadata PROJECTION for providers (the WeKnora upload model):
        {document_id: {version_id, jurisdiction, authority_level}}.
        Stamping hits with this is data projection, NOT governance —
        governance re-verifies against the registry afterwards."""
        return {e["document_id"]:
                {"version_id": "%s@%s" % (e["source_id"], e["version"]),
                 "jurisdiction": e["jurisdiction"],
                 "authority_level": e["authority_level"]}
                for e in self.entries}
