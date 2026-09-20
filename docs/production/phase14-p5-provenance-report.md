# Phase 14.5 — Evidence & Provenance Closure Report

Date: 2026-09-20 · Scope: lineage closure only — no retrieval changes,
no runtime semantics changes, no new governance rules, no CoT logging.

## 1. Objective

The system can now answer, for any knowledge-backed agent conclusion:
which Evidence, which KnowledgeHit, which Document, which Version,
which Source, in force WHEN, verified by WHAT hash, retrieved WHEN —
machine-parsably, fail-closed.

## 2. Architecture Before

14.4 already produced evidence items with the full citation tuple,
but nothing VALIDATED the chain end-to-end: no cross-lineage
consistency check, no decision→evidence validator, no explicit hit
identity field, no deterministic-clock injection, and the decision
side relied solely on the eval-time `provenance_recommendation_evidence`
invariant (existence of refs, not lineage validity).

## 3. Architecture After

```text
Decision (evidence_refs | NO_EVIDENCE_REQUIRED)
   ↓ validate_decision_provenance()            [D001–D003]
Evidence (evidence_id + knowledge_hit_id + citation tuple + governance)
   ↓ validate_provenance()                     [P001–P010]
KnowledgeHit (chunk_id — the deterministic hit identity)
   ↓ registry lookup
Document → Version → Source                    [registry-anchored]
```

Both real paths (tool artifact and orchestrator provide_evidence)
feed the SAME validator — there is no path-specific provenance logic.

## 4. Evidence Lineage

Every governance-built evidence item now carries the explicit
`knowledge_hit_id` (= chunk_id — deterministic, no UUIDs; identical
inputs → identical lineage) in addition to the 14.4 tuple:
source_id/source_name, document_id/document_name, version_id/version,
effective_from/effective_to, authority_level, jurisdiction,
license_status, canonical_uri, content_hash, retrieved_at, governance
{as_of, jurisdiction, window_status, checked_rules}.

## 5. Provenance Model (knowledge/governance/provenance.py)

`validate_provenance(item, registry, as_of=None)` — P001 identity ·
P002 hit registered under the document's chunk hashes · P003 document
resolvable · P004 version_id == source@version (and version agrees) ·
P005 source matches · P006 governance-consistency (window status
RE-DERIVED from the registry + recorded as-of; authority re-checked) ·
P007 hash equality with the registry anchor · P008 jurisdiction ·
P009 license must be ALLOWED on BOTH item and registry (UNKNOWN can
never pass, forged ALLOWED against an UNKNOWN registry fails) ·
P010 retrieved_at present. All violations collected as machine-readable
rule ids; the validator resolves every hop — never field-presence-only.

`validate_decision_provenance(decision, evidence_index, registry)` —
D001 evidence-required-but-missing · D002 unresolvable ref ·
D003 ref resolves to lineage-invalid evidence (full P-chain re-run).
`NO_EVIDENCE_REQUIRED` (explicit policy flag) passes — nothing is
forced to be evidence-backed.

`scan_chain_of_thought()` — defensive scan for banned reasoning-leak
keys (chain_of_thought / reasoning_trace / hidden_reasoning /
internal_deliberation / thought_process); nothing produces them and
the tests assert it stays that way.

## 6. Decision Binding

Recommendation already binds via `payload.evidence_refs` (existing
eval invariant checks existence/resolution); the new validator adds
LINEAGE validity on top (a ref pointing at tampered evidence fails
D003). The validator accepts both `evidence_refs` and structured
`decision_basis[].evidence_id`. Reports remain RENDERERS (§7 of the
brief): the report engine consumes the stored knowledge-evidence
artifact (evidence appendix) and performs no retrieval — asserted by
the static scan.

## 7. Fail-Closed Rules

Missing identity/hit/document/version/source/hash/retrieved_at,
governance conflict, jurisdiction mismatch, license UNKNOWN, forged
ALLOWED, broken lineage → collected rule ids, verdict FAIL. No
auto-fill of unknowns, no confidence fabrication, no fallback paths.
Deterministic clock: `KnowledgeService(now_fn=...)` — tests inject a
fixed stamp; the default is the runtime's UTC ISO convention (one
format everywhere).

## 8. Tests (tests/runtime/test_p14_provenance.py — 44/44, dual-mode)

A complete lineage on the REAL tool artifact (+ walk + window/time) ·
B/C/D/E missing hit/document/version + hash mismatch · P001/P010 ·
F governance conflicts (version disagreement + forged window_status) ·
G jurisdiction · H license (UNKNOWN + forged-ALLOWED-vs-UNKNOWN
registry) · I decision with missing/tampered refs (D001/D002/D003) ·
J explicit NO_EVIDENCE_REQUIRED PASS · K tool/orchestrator parity
(both paths lineage-valid; identical values on 11 citation fields per
shared chunk) · L no CoT leakage · §16 static scan (report = renderer;
recommendation consumes stored evidence only; orchestrator builds no
engine; ONE validator; identity produced only by governance/adapter;
no WeKnora client/Docker/DB on runtime paths).

## 9. Regression (Before → After → Delta)

```text
pytest tests/runtime -q       421 → 427  (+6 provenance)        PASS
pytest tests/portfolio -q     12  → 12   (=)                   PASS
14.1 provider suite           52/52 (unchanged)
14.2 POC suite                33/33 (unchanged)
14.3 governance suite         74/74 (unchanged — semantics intact)
14.4 runtime suite            52/52 (unchanged)
14.5 provenance suite         44/44 (new)
full regression (workbuddy)   51 PASS / 0 FAIL / 1 pre-existing GBK
                              INFRA_ERROR (= baseline)
benchmark                     42/42 (=)
compileall                    PASS
```

## 10. Static Architecture Scan

All seven §16 assertions green (see §8): report-generation performs no
retrieval; recommendation has no service/provider calls; orchestrator
constructs no engine; single validate_provenance/decision validator;
evidence identity assigned only in governance.py + the canonical
adapter; no HTTP/docker/DB tokens on runtime knowledge paths; WeKnora
adapter remains transport-injected only.

## 11. Files Changed

```text
NEW  knowledge/governance/provenance.py   (P001–P010 + D001–D003 +
     scan_chain_of_thought)
NEW  tests/runtime/test_p14_provenance.py (44 checks)
NEW  docs/production/phase14-p5-provenance-report.md
MOD  knowledge/governance/governance.py   (+1 field: knowledge_hit_id)
MOD  knowledge/governance/__init__.py     (exports)
MOD  knowledge/service.py                 (now_fn deterministic clock)
MOD  adapters/knowledge_search_adapter.py (+1 passthrough field)
(14.4 uncommitted work unchanged; results.json benchmark timestamp)
UNCHANGED: Scheduler · Planner · HITL · HOTL · Approval · Runtime Mode
· R-05 · Product Catalog · Recommendation logic · Persistence ·
schemas/ contract files
```

## 12. Findings

- **F-09 (P2, informational)**: decision→evidence binding is enforced
  today by (a) the existing eval invariant for recommendations and (b)
  the new validator at library level; other decision types (risk/gap/
  solution) have no evidence_refs convention yet — extending the
  CONVENTION (not the validator) to those artifacts is future work
  when their skills gain knowledge dependence.
- F-02/F-04/F-05/F-06/F-08 unchanged (production-cutover gates /
  environment / deferred perf).
- No P0/P1 found. No scope expansion performed.

## 13. Deferred Items

WeKnora live POC (F-06); strict-mode provider startup enforcement
(F-02); engine-cache optimization (F-08); risk/gap/solution evidence
conventions (F-09); knowledge eval dimensions (Phase 14.6 scope);
real-source pilot (Phase 14.7 scope).

## 14. Acceptance Gates

G1 lineage ✓ · G2 decision→evidence ✓ · G3 recommendation provenance ✓
· G4 report renders only ✓ · G5 governance/provenance consistency ✓ ·
G6 hash fail-closed ✓ · G7 jurisdiction fail-closed ✓ · G8 license
fail-closed ✓ · G9 missing lineage fail-closed ✓ · G10 path parity ✓ ·
G11 no CoT ✓ · G12 no WeKnora/Docker/DB/API ✓ · G13 regression green ✓

## 15. Final Recommendation

```text
Phase 14.5 = PASS
```

Proceed (on human approval) to Phase 14.6 — Knowledge Evaluation —
with the provenance validator as one of its evaluation primitives.
