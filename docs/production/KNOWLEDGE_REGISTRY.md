# Knowledge Registry — Phase 24A (as implemented)

The knowledge governance registry is the AGENT-side authority over what
retrieved knowledge may ground a decision. WeKnora (or any retrieval
backend) is NEVER the authority — it only finds documents.

## Data model (PostgreSQL authoritative)

| Table | Role | Key fields |
|---|---|---|
| `knowledge_sources` | canonical source identity | source_id, authority_level, jurisdiction, license_status, canonical_uri, scope, document_hash |
| `knowledge_versions` | one (document, version) registration | version_id (`source@version`), document_id, effective_from/to, status (lifecycle), superseded_by, version_hash, content_hashes |
| `knowledge_chunks` | canonical chunk contents | chunk_id, version_id, chunk_index, content, content_hash |
| `knowledge_registry_events` | append-only lifecycle audit (operator domain, separate from runtime case events) | event_type, payload |

Code: `knowledge/governance/pg_registry.py` (`KnowledgeRegistryStore`).
The in-process read model remains `SourceRegistry`
(`knowledge/governance/registry.py`); JSON registry files are the
non-strict (DEMO/EVALUATION) default, unchanged since Phase 14.3/18.

## Hash discipline (three anchors, never mixed)

| Anchor | Definition | Purpose |
|---|---|---|
| chunk hash | sha256(chunk content) | evidence-unit integrity (governance R8, provenance P007) |
| version hash | sha256 over ordered chunk hashes | registration integrity (at-rest tamper detection) |
| document hash | sha256(source document bytes) | ingestion anchor (recorded at upload) |

Hashes are always COMPUTED by the store from content — caller-provided
hashes are never trusted.

## Registration lifecycle

```
DISCOVERED → INGESTED → REGISTERED → VALIDATED → ACTIVE
                 (any pre-ACTIVE step may → REJECTED)
ACTIVE → RETIRED | EXPIRED | SUPERSEDED
terminal: REJECTED / EXPIRED / SUPERSEDED / INVALID / RETIRED
```

Rules (all fail-closed, `knowledge/governance/pg_registry.py`):

- Only `ACTIVE` may ground evidence. Governance R2 denies everything
  else with `SOURCE_NOT_ACTIVE:<state>` (pre-chunking states surface as
  `REGISTRY_MISS` — no registered chunk identity exists yet).
- Illegal transitions are refused (no skip-to-ACTIVE, no terminal exits).
- Activation requires: registered chunks + version_hash (anchors exist)
  AND no other ACTIVE version of the same source with an overlapping
  effective window (ambiguity refuses activation — see below).
- An ACTIVE version re-registered with a different chunk set is
  REFUSED (registration drift); identical sets are idempotent no-ops.
- `supersede(old, new)` is the explicit operator action that lets a
  successor version activate over an overlapping window.

## Version currency (no string ordering)

The current version of a source at time T is determined ONLY by
registry metadata (effective windows + lifecycle state). If MORE THAN
ONE ACTIVE version of a source covers T, currency is AMBIGUOUS:
activation is refused at ingestion time, and governance denies hits
with `VERSION_AMBIGUOUS` at query time (defense in depth).

## Ingestion pipeline (operator tool, not runtime)

`knowledge/pilot/ingest_registry_pg.py` — env-gated, idempotent,
fail-closed:

```
ensure corpus in WeKnora (parse-verified, idempotent uploads)
  → INGESTED   (retrieval side verified: chunks exist)
  → REGISTERED (canonical chunks + computed hashes + version anchor)
  → VALIDATED  (selfcheck: at-rest integrity reproduced)
  → ACTIVE     (guarded activation)
```

WeKnora and PostgreSQL are NOT one distributed transaction. Every
intermediate state is non-ACTIVE, therefore ineligible to ground
evidence — a crash at ANY step fails closed, and re-running the
pipeline advances from wherever the state machine sits (transitions
are idempotent no-ops in the target state).

## Backend selection

`knowledge/service.py: resolve_registry_backend()`

| Mode | Registry of record |
|---|---|
| CONTROLLED_PILOT / PRODUCTION | PostgreSQL (REQUIRED; JSON or file overrides FORBIDDEN — HG-24-02) |
| DEMO / EVALUATION | JSON default; `INSURANCE_AGENT_KNOWLEDGE_REGISTRY_BACKEND=postgres` opts in |

## Scope / tenancy

`knowledge_sources.scope ∈ {GLOBAL, TENANT, PRIVATE}` (default
GLOBAL). The registry load and the re-anchoring content map are
scope-filtered. Current state: **GLOBAL_ONLY** — no tenant knowledge
exists; the isolation is enforced and tested, not claimed.

## F-24 canonical re-anchoring

WeKnora search returns a WINDOW over the original document starting at
the hit's anchor chunk (chunks have overlapping boundaries, so raw
window text cannot hash to the registered chunk hash). Identity is the
backend-asserted `hit.id` = registered canonical chunk_id. When the
window provably starts at that chunk's boundary (whitespace-normalized
prefix rule — exact, documented, not fuzzy), the provider replaces the
hit content with the CANONICAL REGISTERED CHUNK and preserves the raw
window in `metadata.search_window`. Windows that cannot be aligned are
left untouched — governance then denies them on `HASH_MISMATCH`
(fail-closed; never guessed). Code: `knowledge/provider/weknora.py:
reanchor_hit`. Only available with the PostgreSQL registry backend
(canonical contents); the JSON projection registry keeps the documented
Phase-18 behavior.

## At-rest integrity selfcheck

`KnowledgeRegistryStore.selfcheck(version_id)` recomputes chunk hashes
from stored contents, re-derives the version hash, and cross-checks
the projection — detects CHUNK_TAMPERED / VERSION_HASH_MISMATCH /
PROJECTION_DRIFT. Run by the ingestion pipeline before VALIDATED and by
the registry tests after deliberate tampering.
