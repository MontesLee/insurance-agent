#!/usr/bin/env python3
"""Canonical KnowledgeEvidence traceability (Step 2, spec section 6 / 22).

The chain that must resolve:

    Recommendation -> Evidence -> Document -> Chunk

Before Step 2 `adapters.knowledge_search_adapter.to_canonical` dropped `document_id` and
`chunk_id` and emitted `provenance: []`, so a consumer could only point at an opaque
`evidence_id`. This test makes that regression impossible to reintroduce: it runs a REAL
retrieval over the domain corpus and asserts every hop is independently resolvable.
"""
from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (REPO, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

KB_DIR = os.path.join(REPO, "domain", "insurance", "references")
EVIDENCE_SCHEMA = os.path.join(REPO, "contracts", "knowledge-evidence.schema.json")

NAME = "test_knowledge_evidence_traceability"


def run():
    if not os.path.isdir(KB_DIR):
        return (NAME, False, "domain corpus missing: %s" % KB_DIR)

    from knowledge.rag.store import KnowledgeStore
    from knowledge.rag.engine import KnowledgeSearchEngine
    from adapters.knowledge_search_adapter import to_canonical

    ks_rules = os.path.join(REPO, ".trae", "skills", "knowledge-search",
                            "resources", "config", "retrieval.rules.json")
    rk_rules = os.path.join(REPO, ".trae", "skills", "knowledge-search",
                            "resources", "config", "ranking.rules.json")
    rules = {}
    for p in (ks_rules, rk_rules):
        if os.path.exists(p):
            import json
            with open(p, encoding="utf-8") as f:
                rules.update(json.load(f))

    store = KnowledgeStore()
    store.ingest_dir(KB_DIR)
    engine = KnowledgeSearchEngine(store, rules)
    result = engine.search("百万医疗险 保障范围 免赔额")
    raw = result.to_dict() if hasattr(result, "to_dict") else result

    artifact = to_canonical(raw)
    errors = []

    # 1. contract-valid
    try:
        import json
        from jsonschema import Draft7Validator
        with open(EVIDENCE_SCHEMA, encoding="utf-8") as f:
            schema = json.load(f)
        for e in sorted(Draft7Validator(schema).iter_errors(artifact), key=str):
            errors.append("contract: %s" % e.message)
    except ImportError:
        errors.append("jsonschema missing")

    items = artifact.get("payload", {}).get("evidence", []) or []
    if not items:
        errors.append("no evidence returned for a known-good query")

    known_chunks = {c.chunk_id for c in store.all_chunks()}

    for i, it in enumerate(items):
        if not it.get("evidence_id"):
            errors.append("evidence[%d]: missing evidence_id" % i)
        if not it.get("document_id"):
            errors.append("evidence[%d]: missing document_id (Document hop unresolvable)" % i)
        if not it.get("chunk_id"):
            errors.append("evidence[%d]: missing chunk_id (Chunk hop unresolvable)" % i)
        prov = it.get("provenance") or []
        types = {p.get("source_type") for p in prov}
        if "DOCUMENT" not in types or "CHUNK" not in types:
            errors.append("evidence[%d]: provenance lacks DOCUMENT+CHUNK (got %s)" % (i, sorted(types)))
        if it.get("chunk_id") and it["chunk_id"] not in known_chunks:
            errors.append("evidence[%d]: chunk_id %s not present in the corpus"
                          % (i, it["chunk_id"]))
        if not it.get("retrieval_method"):
            errors.append("evidence[%d]: missing retrieval_method" % i)

    if errors:
        return (NAME, False, "; ".join(errors))
    return (NAME, True, "%d evidence items fully traceable to Document+Chunk" % len(items))


if __name__ == "__main__":
    name, ok, detail = run()
    print("[%s] %s" % ("PASS" if ok else "FAIL", name))
    if not ok:
        print("       " + detail)
    sys.exit(0 if ok else 1)
