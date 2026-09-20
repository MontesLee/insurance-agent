#!/usr/bin/env python3
"""One-time, OFFLINE pilot ingestion (Phase 14.7 §17).

Real documents (already retrieved and saved under documents/, with
their provenance headers) + the metadata table → the EXISTING
chunker → chunk-level sha256 anchors → a SourceRegistry-compatible
registry file + a manifest (document-level hashes + stats).

NOT a production ingestion service: no network, no scheduler, no
crawler. Re-running is idempotent (same inputs → same hashes).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from knowledge.governance import SourceRegistry  # noqa: E402

DOCS = os.path.join(HERE, "documents")
TABLE = os.path.join(HERE, "registry", "pilot_sources.json")
OUT_REGISTRY = os.path.join(HERE, "registry", "pilot_registry.json")
OUT_MANIFEST = os.path.join(HERE, "manifests", "pilot_manifest.json")

REQUIRED_META = ("source_id", "source_type", "authority_level",
                 "jurisdiction", "license", "publication_date",
                 "effective_from", "effective_to", "version",
                 "canonical_reference", "retrieved_at", "content_hash")


def main() -> int:
    reg = SourceRegistry.from_kb(DOCS, TABLE)
    # document-level hashes + per-entry stats (chunk hashes live inside
    # each registry entry — same anchor rule as every other registry)
    manifest = {"generated_at": "2026-09-20T00:00:00Z", "documents": []}
    for e in reg.entries:
        path = os.path.join(DOCS, e["document_id"] + ".md")
        raw = open(path, "rb").read()
        manifest["documents"].append({
            "document_id": e["document_id"],
            "source_id": e["source_id"],
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "file_bytes": len(raw),
            "chunks": len(e["content_hashes"]),
            "authority_level": e["authority_level"],
            "jurisdiction": e["jurisdiction"],
            "effective_from": e["effective_from"],
            "effective_to": e["effective_to"],
            "license_status": e["license_status"],
            "version": e["version"],
            "canonical_uri": e["canonical_uri"],
            "retrieved_at": e.get("retrieved_at"),
            "copy_status": e.get("copy_status"),
        })
    with open(OUT_REGISTRY, "w", encoding="utf-8") as f:
        json.dump(reg.entries, f, ensure_ascii=False, indent=1)
    with open(OUT_MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    print("pilot registry: %d documents, %d chunks anchored"
          % (len(reg.entries),
             sum(len(e["content_hashes"]) for e in reg.entries)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
