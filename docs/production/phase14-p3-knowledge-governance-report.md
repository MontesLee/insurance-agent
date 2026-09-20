# Phase 14.3 — Real Insurance Knowledge Governance Report

Date: 2026-09-20 · Scope: agent-side governance ONLY — no external
infrastructure, no WeKnora, no databases, no runtime/orchestrator
changes.

## 1. Executive Summary

```text
Phase 14.3 = PASS (all 12 acceptance gates green)
```

The governance layer is implemented and deterministically tested: a
fail-closed Source Registry, provider-independent hit validation
(authority · effective window · jurisdiction · version · license ·
hash), the §15 version-replacement rule, an additive evidence builder
carrying the full citation tuple, and a 16-row evaluation matrix. Zero
external software; zero runtime semantic changes; the 14.1 provider
boundary and 14.2 BLOCKED verdict are untouched.

## 2. Before / After Architecture

```text
BEFORE (14.1/14.2):                          AFTER (14.3):
Provider → KnowledgeHit → (agent trusts)     Provider → KnowledgeHit
                                                    ↓
                                              SourceRegistry lookup
                                                    ↓
                                              validate_hit (9 rules)
                                                    ↓
                                              allowed hits ──► Evidence
                                              (citation tuple +
                                               governance block)
                                              rejected hits ──► reasons
                                              (audit; never silently
                                               dropped, never trusted)
```

Runtime wiring is deliberately NOT changed this phase (the tool /
orchestrator paths adopt governance at the already-planned 14.5
integration / F-01 closure) — governance ships as a library layer with
pipeline tests proving the full chain on mock-provider output.

## 3. Source Registry (`knowledge/governance/registry.py`)

Entry = one (document, version) record — exactly what any backend
uploads as one document: document_id (unique, == hit.document_id),
source_id (groups versions: the 2024/2026 editions share it),
source_name/type, authority_level (S/A/B/C/D), jurisdiction
(CN / CN-XX), version, effective_from / effective_to (ISO; null=open),
status (ACTIVE/RETIRED), license_status (ALLOWED/RESTRICTED/UNKNOWN),
canonical_uri, content_hashes {chunk_id: sha256}.

- **Load is fail-closed**: duplicates, bad enums, malformed/backwards
  dates, missing hashes → RegistryError for the WHOLE registry (a
  broken registry refuses to govern, never guesses).
- **`from_kb`** builds a registry from a metadata table + KB directory,
  computing chunk hashes with the EXISTING heading-aware chunker —
  hashes can never drift from what retrieval returns. This is the
  anchor rule future ingestion reuses.
- **`provider_stamps()`** is the metadata PROJECTION (the WeKnora
  upload model): {document_id → version_id/jurisdiction/authority}.
  Stamping hits is data projection, never a decision.

## 4. Governance Rules (`knowledge/governance/governance.py`)

`validate_hit(hit, QueryContext, registry) → GovernanceDecision` —
deterministic, all failed rules collected, machine-readable reason ids:

| Rule | Fail-closed behavior |
|---|---|
| R1 registry | unregistered document → REJECT (REGISTRY_MISS) |
| R2 lifecycle | RETIRED source → REJECT |
| R3 version | missing / conflicting version_id → REJECT |
| R4 authority | provider claim missing → REJECT; ≠ registry → REJECT (agent-side registry is authoritative) |
| R5 window | as_of < from → FUTURE; as_of > to → EXPIRED; unresolvable → UNKNOWN — all REJECT for current decisions |
| R6 jurisdiction | re-verified (provider filters are hints); national CN governs CN-*, local never governs national |
| R7 license | UNKNOWN / RESTRICTED → REJECT (UNKNOWN never becomes ALLOWED) |
| R8 hash | missing / unregistered chunk / mismatch → REJECT |
| R9 content | empty → REJECT |

`govern_search_result()` filters a whole canonical result; all-rejected
degrades to `insufficient_evidence` with the rule ids as reason —
**never an empty success**; a governance summary lands in
retrieval_metadata for audit.

## 5. Effective Date

QueryContext.as_of is REQUIRED (no hidden "today" that could mask a
missing business date). ISO date comparison is lexicographic and
deterministic. CURRENT/EXPIRED/FUTURE/UNKNOWN statuses per §7; UNKNOWN
fail-closed.

## 6. Jurisdiction

Entry/ctx match iff equal, or entry == "CN" and ctx startswith "CN"
(national rules apply in every CN-* region; a CN-BJ rule never
governs a CN-SH or national query). Mismatch → REJECT with
JURISDICTION_MISMATCH.

## 7. Authority

The existing S/A/B/C/D ladder is reused unchanged (enums pinned in
model.py; the ranking weights live where they already were). Authority
is REGISTRY-owned: a provider-claimed level that disagrees with the
registry rejects the hit — LLMs and providers never grade sources.

## 8. Version

`source_id@version` identity on every hit; `versions_of` /
`current_entry(source_id, as_of)` resolve the in-force edition; gaps
return None (fail-closed). The 2024/2026 fixture pair shares
source_id `synthetic-medical-regulation`.

## 9. License

ALLOWED passes; RESTRICTED and UNKNOWN both reject. No copyright
system — only the guarantee that UNKNOWN never enters the production
knowledge path.

## 10. Provenance / Hash

content_hashes are computed at registry build from the SAME chunker
the engine uses; hit hash must match the registered chunk hash
(tamper detection across any provider roundtrip). Four-hop chain
demonstrated: evidence_id → chunk_id → document_id → registry entry
(source_id + version + window).

## 11. Evidence Integration

`build_evidence_item()` emits the EXISTING contract surface PLUS the
additive citation tuple (source_id, source_name, version_id, version,
effective_from/to, authority_level, jurisdiction, license_status,
canonical_uri, content_hash, retrieved_at, governance{as_of,
jurisdiction, window_status, checked_rules}). Verified against the
real `knowledge-evidence.schema.json` via the existing validator —
**the contract file itself is untouched** (additive properties ride
the schema's permissive item policy; asserted by test).

## 12. Negative Tests (A–G) — all green

A registry/window missing → load-time RegistryError + UNKNOWN reject ·
B authority missing · C provider≠registry conflict (this rule caught
the fixture's own default-ingest level mid-development — it works) ·
D license UNKNOWN · E jurisdiction mismatch · F version missing/
conflict · G hash missing/mismatch/unregistered-chunk. Plus §15
replacement: as-of 2025 → only V2024; as-of 2026 → V2024 EXPIRED and
V2026 CURRENT — text relevance cannot resurrect an expired edition.

## 13. Evaluation Results

16-row deterministic matrix (authority correct/wrong/missing · window
current/expired/future · jurisdiction match/national-applies/mismatch
· version present/missing/conflict · license allowed/restricted/
unknown · provenance complete · hash match/mismatch): **16/16 PASS**.
Verdict vocabulary is PASS/FAIL only — no MANUAL/SOFT_PASS. Suite:
tests/runtime/test_p14_governance.py — **74/74 checks, 7 pytest
tests**.

## 14. Regression Results

```text
pytest tests/runtime -q      408 → 415  (+7 governance)      PASS
pytest tests/portfolio -q    12  → 12   (=)                  PASS
14.1 provider suite          52/52 (unchanged — mock stamping additive)
14.2 POC suite               33/33 (unchanged)
full regression (workbuddy)  51 PASS / 0 FAIL / 1 pre-existing GBK
                             INFRA_ERROR (=)
benchmark                    42/42 (=)
compileall                   PASS
```

## 15. WeKnora Boundary

```text
WeKnora integration remains pending.
No external knowledge infrastructure was required or used.
```

The 14.2 BLOCKED verdict stands unchanged. Governance consumes only
the canonical KnowledgeHit surface — when WeKnora arrives it replaces
the provider BELOW the same governance, per the Phase-14 architecture.
MockKnowledgeProvider remains the offline test provider (extended only
with optional metadata PROJECTION stamps; default behavior
byte-identical, 52/52 re-verified). No provider renaming, no fake
WeKnora data, no Docker, no databases.

## Files

```text
NEW  knowledge/governance/{__init__,model,registry,governance}.py
NEW  knowledge/governance/fixtures/governed_sources.json (7-entry table)
NEW  knowledge/governance/fixtures/kb/*.md (7 synthetic docs, all
     self-labelled SYNTHETIC TEST DATA; zero real insurance content)
NEW  tests/runtime/test_p14_governance.py (74 checks)
NEW  docs/production/phase14-p3-knowledge-governance-report.md
MOD  knowledge/provider/mock.py (additive optional stamps — projection
     only, never governance)
(uncommitted 14.1/14.2 work unchanged: tools.py, provider package,
 POC/integration tests, phase14 docs; results.json benchmark timestamp)
```

## Known Concerns (recorded, not fixed — out of scope)

- F-01/F-02/F-04/F-05 unchanged (production-cutover gates).
- F-06 unchanged (no container runtime → real POC still blocked).
- NEW F-07 (P2, informational): governance is not yet wired into the
  live tool/orchestrator path (deliberate — 14.5/F-01 territory);
  pipeline correctness is proven at library level over real
  mock-provider output.
