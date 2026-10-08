# -*- coding: utf-8 -*-
"""§11: register the 29 KB-V1 documents (post bge-m3 migration chunks)
into the runtime PostgreSQL knowledge registry, through the Phase-24A
guarded lifecycle (DISCOVERED->INGESTED->REGISTERED->VALIDATED->ACTIVE).

Documents already exist in WeKnora kb insurance-kb-v1 (upload skipped);
chunks are fetched LIVE from WeKnora so registry hashes anchor the
post-migration chunk set. Metadata = knowledge/pilot/registry/
kb1_sources.json (built from source-manifest.yaml).

Env: INSURANCE_AGENT_WEKNORA_URL, INSURANCE_AGENT_WEKNORA_JWT,
AGENT_PG_PASSWORD. Usage: python ingest_kb1_registry.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "knowledge" / "pilot"))

from knowledge.pilot.sync_weknora_registry import (  # noqa: E402
    URL, JWT, _req, fetch_chunks)
from knowledge.pilot.ingest_registry_pg import (  # noqa: E402
    _pg_store, _krs, _audit)

KBID = os.environ.get("INSURANCE_AGENT_WEKNORA_PILOT_KB",
                      "44af9ff2-ecef-445e-87c6-cb1458cd4d44")
META = REPO / "knowledge/pilot/registry/kb1_sources.json"
OUT = HERE.parents[1] / "evidence" / "eval" / "registry_ingest_kb1.json"


def list_kb_docs() -> dict:
    """file_name -> knowledge id (paged)."""
    docs = {}
    page = 1
    while True:
        batch = (_req("GET", "/api/v1/knowledge-bases/%s/knowledge"
                      "?limit=20&page=%d" % (KBID, page), auth=JWT)
                 .get("data") or [])
        if not batch:
            break
        for d in batch:
            docs[d["file_name"]] = d
        if len(batch) < 20:
            break
        page += 1
    return docs


def register_document(krs, kid: str, fname: str, meta: dict,
                      document_hash) -> dict:
    version_id = "%s@%s" % (meta["source_id"], meta["version"])
    krs.upsert_source({**meta, "document_hash": document_hash})
    krs.upsert_version({**meta, "content_hashes": {}}, "DISCOVERED")
    raw = fetch_chunks(kid)
    if not raw_chunks_ok(raw):
        return {"document_id": meta["document_id"], "state": "REJECTED",
                "detail": "no chunks"}
    ordered = sorted(raw, key=lambda c: (c.get("chunk_index") or 0,
                                         c.get("seq") or 0))
    chunks = [{"chunk_id": c["id"], "chunk_index": i,
               "content": c.get("content") or ""}
              for i, c in enumerate(ordered) if c.get("id")]
    cur = krs.get_version(version_id)
    if cur and cur["status"] == "ACTIVE":
        krs.upsert_chunks(version_id, chunks)
        check = krs.selfcheck(version_id)
        if not check["ok"]:
            return {"document_id": meta["document_id"], "state": "INVALID",
                    "detail": ";".join(check["problems"])}
        return {"document_id": meta["document_id"], "state": "ACTIVE",
                "chunks": len(chunks), "detail": "(re-verified)"}
    krs.transition(version_id, "INGESTED")
    krs.upsert_chunks(version_id, chunks)
    krs.transition(version_id, "REGISTERED")
    check = krs.selfcheck(version_id)
    if not check["ok"]:
        return {"document_id": meta["document_id"], "state": "INVALID",
                "detail": ";".join(check["problems"])}
    krs.transition(version_id, "VALIDATED")
    krs.transition(version_id, "ACTIVE")
    _audit(krs, "knowledge.active",
           {"version_id": version_id, "chunks": len(chunks),
            "note": "kb-v1 bge-m3 migration registration"}, version_id)
    return {"document_id": meta["document_id"], "state": "ACTIVE",
            "chunks": len(chunks), "detail": ""}


def raw_chunks_ok(raw) -> bool:
    return bool(raw)


def main() -> int:
    import hashlib
    metas = {m["document_id"]: m
             for m in json.loads(META.read_text(encoding="utf-8"))}
    docs = list_kb_docs()
    print("KB docs listed:", len(docs))
    assert len(docs) == 29, len(docs)
    store = _pg_store()
    krs = _krs(store)
    results = []
    for stem, meta in sorted(metas.items()):
        fname = next((f for f in docs if f.rsplit(".", 1)[0] == stem), None)
        if fname is None:
            results.append({"document_id": stem, "state": "MISSING_IN_KB"})
            continue
        kid = docs[fname]["id"]
        if docs[fname].get("parse_status") != "completed":
            results.append({"document_id": stem, "state": "NOT_PARSED",
                            "detail": docs[fname].get("parse_status")})
            continue
        # document_hash: official-source checksum from the manifest
        document_hash = meta.get("checksum") or ""
        if document_hash and len(document_hash) != 64:
            document_hash = ""
        try:
            r = register_document(krs, kid, fname, meta, document_hash
                                  or None)
        except Exception as e:  # noqa: BLE001 — record, stay pre-ACTIVE
            r = {"document_id": stem, "state": "FAILED",
                 "detail": "%s: %s" % (type(e).__name__, str(e)[:140])}
        print("  %-8s -> %s %s (%s chunks)"
              % (stem, r["state"], r.get("detail", ""),
                 r.get("chunks", "-")), flush=True)
        results.append(r)
    active = sum(1 for r in results if r["state"] == "ACTIVE")
    total_chunks = sum(r.get("chunks", 0) for r in results
                       if r["state"] == "ACTIVE")
    print("== %d/%d ACTIVE, %d chunks" % (active, len(results),
                                          total_chunks))
    OUT.write_text(json.dumps(
        {"ran_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%S"),
         "kb": KBID, "active": active, "total": len(results),
         "chunks": total_chunks, "results": results},
        ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if active == 29 and total_chunks == 791 else 1


if __name__ == "__main__":
    raise SystemExit(main())
