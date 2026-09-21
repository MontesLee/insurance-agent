#!/usr/bin/env python3
"""Knowledge ingestion pipeline → PostgreSQL registry — Phase 24A.

OPERATOR tool (never called by the Agent runtime — Phase 24 §15: the
runtime uploads nothing). Env-gated, fail-closed, idempotent:

    prepare (ensure corpus in WeKnora, parse-verified)
      → INGESTED   (WeKnora side verified: chunks exist)
      → REGISTERED (canonical chunks + hashes + version anchor in PG)
      → VALIDATED  (selfcheck: at-rest integrity reproduced)
      → ACTIVE     (guarded: chunks anchored, no ambiguous overlap)

WeKnora and PostgreSQL are NOT one distributed transaction: every
intermediate state is non-ACTIVE and therefore ineligible to ground
evidence (governance R2 fails closed). A crash at ANY step leaves the
version in a safe pre-activation state; re-running advances it again
(transitions are idempotent no-ops when already in the target state).

Usage (env): INSURANCE_AGENT_WEKNORA_URL / _JWT (admin session),
AGENT_PG_DSN or AGENT_PG_PASSWORD (PostgreSQL registry), optional
INSURANCE_AGENT_WEKNORA_PILOT_KB (existing pilot KB id).
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

from knowledge.pilot.sync_weknora_registry import (  # noqa: E402
    FIXTURES_KB, fetch_chunks, get_or_create_kb, upload_if_absent,
    wait_parsed)


def _pg_store():
    from runtime.state.pg import PostgresStore
    return PostgresStore()


def _krs(store):
    from knowledge.governance.pg_registry import KnowledgeRegistryStore
    krs = KnowledgeRegistryStore(store.connect)
    krs.init_schema()
    return krs


def _audit(krs, event_type: str, payload: dict,
           version_id: str = "") -> None:
    """Registration lifecycle event — the registry's OWN append-only
    audit table (operator domain, separate from runtime case events)."""
    try:
        krs.audit(event_type, payload, version_id=version_id)
    except Exception as e:  # noqa: BLE001 — audit must not break ingest
        print("  ! audit write failed (non-fatal): %s" % str(e)[:80])


def ingest_document(store, krs, kbid, doc_md_path, meta: dict) -> dict:
    """One (document, version) through the full guarded lifecycle."""
    from knowledge.governance.model import RegistryError

    stem = os.path.splitext(os.path.basename(doc_md_path))[0]
    if stem != meta["document_id"]:
        raise RegistryError("table row %s does not match KB file %s"
                            % (meta["document_id"], stem))
    version_id = "%s@%s" % (meta["source_id"], meta["version"])

    # 1) ensure uploaded to WeKnora + parse-verified (idempotent)
    kid, created = upload_if_absent(kbid, doc_md_path)
    if created and wait_parsed(kbid, kid) != "completed":
        krs.upsert_source({**meta, "document_hash": None})
        krs.upsert_version({**meta, "content_hashes": {}}, "DISCOVERED")
        _audit(krs, "knowledge.rejected", {
            "version_id": version_id,
            "reason": "weknora parse not completed"})
        return {"document_id": stem, "state": "REJECTED",
                "detail": "weknora parse failed"}

    with open(doc_md_path, "rb") as f:
        document_hash = hashlib.sha256(f.read()).hexdigest()

    # 2) source + version rows (DISCOVERED → INGESTED after the
    #    retrieval side is verified to hold canonical chunks)
    krs.upsert_source({**meta, "document_hash": document_hash})
    krs.upsert_version({**meta, "content_hashes": {}}, "DISCOVERED")
    raw_chunks = fetch_chunks(kid)
    if not raw_chunks:
        _audit(krs, "knowledge.rejected", {
            "version_id": version_id, "reason": "no chunks in weknora"})
        return {"document_id": stem, "state": "REJECTED",
                "detail": "weknora returned no chunks"}

    # canonical chunks (ORDERED; hashes computed by the store —
    # caller-provided hashes are never trusted)
    ordered = sorted(raw_chunks, key=lambda c: (c.get("chunk_index") or 0,
                                                c.get("seq") or 0))
    chunks = [{"chunk_id": c["id"], "chunk_index": i,
               "content": c.get("content") or ""}
              for i, c in enumerate(ordered) if c.get("id")]

    # idempotent re-run: the version is already ACTIVE — verify the
    # chunk set still matches (upsert_chunks refuses drift) and the
    # at-rest integrity still holds, then stop (no transitions).
    cur = krs.get_version(version_id)
    if cur and cur["status"] == "ACTIVE":
        krs.upsert_chunks(version_id, chunks)     # refuses on drift
        check = krs.selfcheck(version_id)
        if not check["ok"]:
            _audit(krs, "knowledge.invalid", {
                "version_id": version_id,
                "problems": check["problems"]})
            return {"document_id": stem, "state": "INVALID",
                    "detail": ";".join(check["problems"])}
        return {"document_id": stem, "state": "ACTIVE",
                "chunks": len(chunks), "detail": "(re-verified)"}

    krs.transition(version_id, "INGESTED")
    integ = krs.upsert_chunks(version_id, chunks)
    krs.transition(version_id, "REGISTERED")

    # 4) at-rest integrity selfcheck → VALIDATED
    check = krs.selfcheck(version_id)
    if not check["ok"]:
        _audit(krs, "knowledge.invalid", {
            "version_id": version_id, "problems": check["problems"]})
        return {"document_id": stem, "state": "INVALID",
                "detail": ";".join(check["problems"])}
    krs.transition(version_id, "VALIDATED")

    # 5) guarded activation (refuses ambiguous window overlap)
    try:
        krs.transition(version_id, "ACTIVE")
    except RegistryError as e:
        return {"document_id": stem, "state": "VALIDATED",
                "detail": "activation refused: %s" % str(e)[:120]}
    _audit(krs, "knowledge.active", {
        "version_id": version_id, "chunks": len(chunks),
        "version_hash": integ[:16]})
    return {"document_id": stem, "state": "ACTIVE",
            "chunks": len(chunks), "detail": ""}


def ingest_corpus(store, krs, corpus: str) -> list:
    """corpus: 'fixtures' (synthetic contract tests) or 'pilot' (the
    real-document pilot). Each pairs a KB with its agent metadata."""
    if corpus == "fixtures":
        kbid, _ = get_or_create_kb("agent-fixtures",
                                   "deterministic fixtures corpus (synced)")
        kb_dir = FIXTURES_KB
        table = os.path.join(REPO, "knowledge", "governance", "fixtures",
                             "fixtures_sources.json")
    elif corpus == "pilot":
        kbid = os.environ.get("INSURANCE_AGENT_WEKNORA_PILOT_KB", "")
        assert kbid, "pilot corpus requires INSURANCE_AGENT_WEKNORA_PILOT_KB"
        kb_dir = os.path.join(HERE, "documents")
        table = os.path.join(HERE, "registry", "pilot_sources.json")
    else:
        raise SystemExit("unknown corpus %r (fixtures|pilot)" % corpus)

    with open(table, encoding="utf-8") as f:
        metas = {m["document_id"]: m for m in json.load(f)}
    results = []
    for fname in sorted(os.listdir(kb_dir)):
        if not fname.endswith(".md"):
            continue
        stem = os.path.splitext(fname)[0]
        meta = metas.get(stem)
        if meta is None:
            results.append({"document_id": stem, "state": "SKIPPED",
                            "detail": "no agent metadata (unregistered)"})
            continue
        try:
            r = ingest_document(store, krs, kbid,
                                os.path.join(kb_dir, fname), meta)
        except Exception as e:  # noqa: BLE001 — record, stay pre-ACTIVE
            r = {"document_id": stem, "state": "FAILED",
                 "detail": "%s: %s" % (type(e).__name__, str(e)[:120])}
        print("  %-42s -> %s %s" % (stem, r["state"], r.get("detail", "")))
        results.append(r)
    return results


def main() -> int:
    url = os.environ.get("INSURANCE_AGENT_WEKNORA_URL", "").strip()
    jwt = os.environ.get("INSURANCE_AGENT_WEKNORA_JWT", "").strip()
    assert url and jwt, ("set INSURANCE_AGENT_WEKNORA_URL and _JWT "
                         "(admin session)")
    store = _pg_store()
    krs = _krs(store)
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    corpora = ["fixtures", "pilot"] if which == "all" else [which]
    all_results = {}
    for corpus in corpora:
        print("== corpus: %s" % corpus)
        all_results[corpus] = ingest_corpus(store, krs, corpus)
    active = sum(1 for rs in all_results.values() for r in rs
                 if r["state"] == "ACTIVE")
    total = sum(len(rs) for rs in all_results.values())
    print("== %d/%d ACTIVE" % (active, total))
    return 0 if active == total else 1


if __name__ == "__main__":
    sys.exit(main())
