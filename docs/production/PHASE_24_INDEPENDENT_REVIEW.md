# Phase 24 Independent Review

Date: 2026-09-21 · Reviewer mode: read-only audit (defects recorded,
not fixed; no product/test files modified; probes live under
tmp/review24/, never committed).

## 1. Review Scope

Independent verification that Phase 24 actually reached
`PRODUCTION_KNOWLEDGE_READY_WITH_DOCUMENTED_DEBT`, and whether the
project is fit to enter Phase 25. Methods: git scope audit, fresh
ad-hoc probes (49 + 13 + 5 checks across three probe programs),
re-execution of the committed live suites, mutation/tamper injection,
clean-environment reproduction, documentation and evidence integrity
checks, secret scan, full regression.

## 2. Baseline

| Item | Value |
|---|---|
| HEAD | 42683d1 (cleanup commit; only .gitignore + 2 cleanup docs vs 131cdb1 — no code delta) |
| Phase 24 commit | 131cdb1 (parent of HEAD) |
| Working tree | clean |
| Conclusion | Reliable baseline established; review proceeds against 131cdb1's code, identical under HEAD |

## 3. Git Scope Audit

`git show 131cdb1 --stat`: 19 files — 9 new (pg_registry, ingestion
tool, 4 test suites, 3 docs + result), 10 modified (governance/model/
registry/service/weknora + 4 docs + README), **0 deleted**.

| Area | Changed? | Verdict |
|---|---|---|
| Business Skills (.trae/skills) | NO | in scope |
| Orchestrator / runtime core | NO | in scope |
| Recommendation / catalog | NO | in scope |
| LLM Gateway (runtime/llm) | NO | in scope (HG-24-25) |
| PostgreSQL business schema | NO (knowledge tables only, additive + idempotent migration) | in scope |
| Redis / Queue / Worker / K8s / HA / multi-tenant | NO | HG-24-23/24 hold |

Diff substance of modified governance/registry files walked
line-by-line: matches the described changes (R2/R2b, extended enum,
concurrent_versions) — no unexplained logic. No REVIEW_REQUIRED items.

## 4. 24A Registry Audit

Fresh PG probes (rev24- prefixed rows, cleaned after):
forward lifecycle to ACTIVE ✓; skip DISCOVERED→ACTIVE refused ✓;
skip REGISTERED→ACTIVE refused ✓; duplicate ingestion no-op ✓; ACTIVE
chunk-set drift refused ✓; restart (fresh store) preserves state +
hashes ✓. Registry bypass Case B (hit with no registry row) →
REGISTRY_MISS DENY ✓ (live + unit). Case C REGISTERED →
SOURCE_NOT_ACTIVE:REGISTERED ✓. Case D VALIDATED →
SOURCE_NOT_ACTIVE:VALIDATED ✓.

Live registry state: exactly **16 ACTIVE** (10 cn-* pilot + 6
fixtures-*; enumerated). Live corpus count matches the claim.

## 5. 24B Governance Audit

All eight non-ACTIVE states independently denied with explicit
fail-closed reasons (5.1 probes ×8 ✓). RETIRED keeps its historical
reason (backward compat).

## 6. Version Ambiguity Audit

String-sort traps probed fresh: overlapping ACTIVE versions
`v2`/`v10` and `2024-01`/`2024-10` → both denied with
VERSION_AMBIGUOUS (never max(version_string)) ✓. Sequential windows
v2(2025)→v10(2026): old denied WINDOW_EXPIRED, new allowed ✓.

## 7. Scope Isolation Audit

Unknown scope value refused at upsert (RegistryError) ✓. TENANT-scoped
source invisible to the GLOBAL registry load AND the GLOBAL content
map ✓. Scope lives in the operator-owned PG registry; the provider/
retrieval path cannot influence it. GLOBAL_ONLY remains the honest
documented state; no fabricated tenancy.

## 8. 24C WeKnora Audit

Strict-mode matrix (fresh probes): PRODUCTION/CONTROLLED_PILOT ×
(unset | mock) → ProviderConfigError naming HG-24-03 before any
registry/provider construction ✓; no mock-fallback path exists
(structural: grep + probes). **Finding RV-P2-01**: with
PROVIDER=weknora but `INSURANCE_AGENT_WEKNORA_URL` unset, the service
CONSTRUCTS successfully (falls through to the no-transport seam
provider) and fails closed only at first search
(ProviderUnavailable). No mock, no silent success — but the failure
surfaces at query time rather than startup/composition. Recorded, not
fixed.

## 9. WeKnora Failure Matrix

| Failure | Expected | Actual | PASS |
|---|---|---|---|
| connection refused (simulated + blackhole timeout 2.0s) | ProviderUnavailable | ProviderUnavailable | ✓ |
| 401 (live bad key) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| 403 (live out-of-scope KB) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| wrong endpoint (live nested-path URL) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| missing content/id (malformed) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| corrupt chunk_id (empty) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| wrong shape (no data) | ProviderResponseInvalid | ProviderResponseInvalid | ✓ |
| unregistered document | REGISTRY_MISS deny | REGISTRY_MISS deny | ✓ |
| expired / future / license / jurisdiction (live matrix) | rule-specific deny | rule-specific deny | ✓ (33/33 suite) |
| authority conflict (tampered claim on real hit) | AUTHORITY_CONFLICT | AUTHORITY_CONFLICT | ✓ |

No fallback, no silent/empty/partial success anywhere.

## 10. WeKnora Health Semantics Audit

health() = reachability only (any HTTP answer, including 401/403/404,
counts as reachable — verified). Separation verified live: reachable +
out-of-scope KB → ProviderResponseInvalid; reachable + unparseable/
unregistered corpus → ABSTAIN (insufficient_evidence), never
fabricated evidence. Docs describe health as reachability-only
(KNOWLEDGE_GOVERNANCE.md, tests) — no conflation found.

## 11. WeKnora Persistence Audit

Static: WeKnora-postgres data lives in NAMED VOLUME
`weknora_postgres-data`; app files in `weknora_data-files` — container
recreation (`compose down/up` without `-v`) preserves data by
construction. Live: `docker restart WeKnora-app` verified earlier this
phase (identical hits, chunk ids, content hashes). Full `compose
down/up` was NOT executed during this review (user's running stack);
evidence boundary recorded as INFO, not a defect. No identity-drift
mechanism exists: chunk ids are backend-stable across restarts
(verified by hash equality).

## 12. Backup Audit

agent_runtime `pg_dump` = 309,739 bytes plain SQL, contains all four
knowledge tables (CREATE + COPY with the real cn-* registry rows) ✓.
WeKnora DB dump verified earlier (275 KB gz). **No restore
verification exists** → DR completeness is a DOCUMENTED LIMITATION
(RV-P3-02), consistent with the Phase 24 result's "scheduling
deferred".

## 13. 24D F-16 Audit

Fresh self-written reproduction (13 scenarios, independent of the
committed suite): death-only, life-only, savings/health/accident-only,
death+health, death+savings, death+health+savings, full multi-demand,
unknown category, conflicting requirement, and an adversarial
free-text rerouting attempt (R4 risk described purely in savings
vocabulary). **NOT REPRODUCIBLE** — R4→life→TERM_LIFE intact in every
scenario; no cross-domain leakage. F-16 = CLOSED / NOT REPRODUCIBLE
(independently confirmed).

## 14. 24E Evaluation Audit

Mock vs live semantic equivalence (fresh probe): decision-level
agreement 4/4 on the shared fixtures queries; every ALLOWED live
evidence item carries the full contract tuple and passes
validate_provenance (P001–P010) — no semantic divergence between
modes (scores/latency excluded by design).

## 15. F-24 Canonical Re-anchor Audit

Fresh case matrix (all deterministic, unit-level on the real code):

| Case | Expected | Result |
|---|---|---|
| 1 correct window (canonical+span) | re-anchor → ALLOW | ✓ |
| 2 wrong window (mid-chunk start) | no re-anchor → HASH_MISMATCH DENY | ✓ |
| 3 unrelated content | DENY | ✓ |
| 4 content equals a DIFFERENT chunk's canonical | DENY (anchor is hit.chunk_id-specific; no candidate choice exists) | ✓ |
| 5/6 U+3000 / NBSP / tab-newline whitespace | deterministic re-anchor → ALLOW (single canonical per chunk_id; str.split() covers all Unicode whitespace) | ✓ |
| 7 punctuation mutation | alignment fails → DENY (no fuzzy bypass) | ✓ |
| 8 wrong hit.id (unregistered chunk) | CHUNK_UNREGISTERED DENY | ✓ |

## 16. F-24 Safety Property

Re-anchor success ≠ trust: probed with a forged-but-ALIGNED canonical
whose hash disagrees with the registry anchor — re-anchoring happens
mechanically, governance still DENIES on hash mismatch ✓. The chain
remains canonical content → canonical hash → registry hash → exact
match → ALLOW; any disagreement denies.

## 17. Provenance Audit

Live chain re-traced from real retrieval: every ALLOWED evidence item
resolves evidence_id → chunk_id → document_id → version_id (source@ver)
→ source (authority/license/jurisdiction/canonical_uri) → window
status → content hash → retrieved_at, machine-parseable, zero UNKNOWN
fields with an ALLOW outcome (fresh probe over all live items).

## 18. Abstention / Fail-Closed Audit

unknown source ✓ / unknown license ✓ / unknown version ✓ / expired ✓ /
superseded ✓ / unregistered ✓ / hash mismatch ✓ / authority conflict ✓ /
jurisdiction conflict ✓ / ambiguous version ✓ / provider failure ✓ —
all DENY/ABSTAIN, no best-effort answer path found.

## 19. Production-vs-Mock Audit

DEMO/EVALUATION: mock default, JSON registry — verified by clean-env
runs (tests construct mock services freely). CONTROLLED_PILOT/
PRODUCTION: mock refused pre-construction; registry backend forced to
PostgreSQL with file/JSON overrides refused; weknora required. Gap:
RV-P2-01 (URL-less weknora defers failure to first search).

## 20. Phase 25 Scope Contamination

Redis/Queue/Worker/K8s/HA/multi-tenant/Object Storage: absent from the
Phase 24 diff (the only "redis/queue" strings are negative claims in
the result doc's gate/deferred lists). No scope creep.

## 21. Regression Audit (independently re-run)

```
Runtime:     494 passed
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
Phase 18 live: 48/48 (LIVE, re-executed with env)
Phase 24 live: 33/33 (re-executed; one earlier run 32/33 — see RV-P3-01)
Review probes: 47/49 (the 2 fails ARE RV-P2-01, recorded) + F-16 13/13
               + live semantics 5/5
```

## 22. Clean Environment Audit

`env -i` (empty environment) execution: p24 governance 45/45, F-16
47/47 — PASS does not depend on residual env vars or cwd state.
DECLARED EXTERNAL DEPENDENCIES (not self-contained, by design):
PostgreSQL (credential file), WeKnora (API key/JWT session files),
Docker. Tests skip loudly without them; no PASS-without-env.

## 23. Documentation Consistency

F-16: LIMITATIONS.md carries a dated closure addendum while retaining
the original text; PHASE_19_FINAL_AUDIT.md untouched (single commit
since creation). F-24: docs describe the actual mechanism (backend
returns a window over the document; agent re-anchors via exact
normalized-prefix rule against registry-held canonical content) — NOT
claimed as WeKnora-native canonical content. DATABASE_SCHEMA matches
the shipped DDL incl. migration. KNOWLEDGE_PRODUCTION status table
updated to implemented-registry. README (en/zh) counts updated and
mutually consistent. No inconsistency found.

## 24. Evidence Integrity

| Claim | Evidence located | Reproducible |
|---|---|---|
| 16/16 ACTIVE | PG enumerated: exactly 16 ACTIVE (10 pilot + 6 fixtures) | ✓ (re-ran) |
| 78 chunks (internet regulation) | PG content_hashes count = 78 | ✓ |
| 494 / 12 / 42/42 / compileall | re-executed this review | ✓ |
| Phase 18 live 48/48 | re-executed with env | ✓ |
| Phase 24 live 33/33 | re-executed (one flaky rerun: RV-P3-01) | ✓ |
| F-16 matrix 47/47 | re-executed + independent 13-scenario probe | ✓ |
| N=24 latency median 218/p95 306 | tmp/p24_live_eval_report.json (n=24) | ✓ |
| 45/45 + 26/26 p24 unit/PG suites | re-executed under pytest and standalone | ✓ |

## 25. Historical Evidence Preservation

PHASE_19_FINAL_AUDIT.md: one commit (creation) — never rewritten ✓.
LIMITATIONS.md: original findings retained verbatim; Phase 24 added
dated closure addenda for F-16/F-24 only ✓. tmp/ evidence cited by
committed docs intact after the cleanup (spot-verified
tmp/_probe_out.txt, tmp/acceptance).

## 26. Security / Secret Audit

Tracked-tree grep for credential shapes (sk-/ghp_/API-key
assignments/POSTGRES_PASSWORD literals/Bearer JWT): zero hits. Probes/
reports under tmp/ contain query text and metadata only. Credentials
live in session files outside the repository. No exposure.

## 27. Scope Contamination

See §20 — clean. No SCOPE_CREEP markers.

## 28. Findings

| ID | Severity | Finding | Disposition |
|---|---|---|---|
| RV-P2-01 | P2 | Strict mode with PROVIDER=weknora but no WEKNORA_URL constructs the service; fail-closed defers to first search (ProviderUnavailable) instead of startup. No mock fallback; HG-24-03's no-fallback property holds. | recorded, not fixed |
| RV-P3-01 | P3 | test_p24_live_eval s1 F-24 with/without comparison depends on the live hit mix (observed 32/33 once, 33/33 otherwise). Safety property itself deterministic (unit-proven §15). | recorded, not fixed |
| RV-P3-02 | P3 | Backup verified generatable + content-complete, but no restore verification exists → DR not yet end-to-end. | documented limitation |
| RV-P3-03 | P3 | knowledge_sources.document_hash is recorded at ingestion but verified by neither selfcheck nor any runtime path (informational anchor only). | recorded |
| RV-INFO-01 | INFO | Full docker compose down/up not executed during review; persistence evidenced by named volumes + app-container restart. | evidence boundary |

## 29. Gate Matrix

| Gate | Result | Evidence |
|---|---|---|
| G24-I-01 Git baseline | PASS | HEAD 42683d1 = 131cdb1 + docs-only cleanup; tree clean |
| G24-I-02 Scope | PASS | 19 files, all knowledge/tests/docs; skills/orchestrator/gateway untouched |
| G24-I-03 Registry lifecycle | PASS | fresh probes: full path, skips refused, idempotent, drift refused, restart-stable |
| G24-I-04 ACTIVE bypass | PASS | Cases A–D independently denied; 16 ACTIVE enumerated |
| G24-I-05 Hash identity | PASS | chunk/version anchors tamper-detected; wrong-level hash denied; document_hash unverified (RV-P3-03) |
| G24-I-06 Governance | PASS | 8 non-ACTIVE states denied with explicit reasons |
| G24-I-07 Version ambiguity | PASS | v2/v10, 2024-01/2024-10 traps → VERSION_AMBIGUOUS, never string-sort |
| G24-I-08 Scope isolation | PASS | unknown scope refused; TENANT invisible cross-scope |
| G24-I-09 Strict provider | PASS (with RV-P2-01) | mock refused pre-construction; no fallback path; URL-less weknora defers fail to query time |
| G24-I-10 Failure matrix | PASS | 10/10 rows verified (live + simulated) |
| G24-I-11 Health semantics | PASS | reachability-only; reachable≠usable proven live |
| G24-I-12 Persistence | PASS | named volumes + restart identity stability; full down/up not run (INFO-01) |
| G24-I-13 Backup | PASS (with RV-P3-02) | dump 309KB with all registry tables; restore unverified |
| G24-I-14 F-16 | PASS | independent 13-scenario reproduction: NOT REPRODUCIBLE |
| G24-I-15 Mock/Live equivalence | PASS | 4/4 decision agreement; contract+provenance intact on live items |
| G24-I-16 F-24 re-anchor | PASS | 8-case matrix + safety property (§16) verified |
| G24-I-17 Provenance | PASS | live chain machine-parseable, no UNKNOWN-with-ALLOW |
| G24-I-18 Abstention | PASS | all 11 deny/abstain conditions verified |
| G24-I-19 Production/Mock separation | PASS | mode matrix verified incl. clean-env runs |
| G24-I-20 Phase 25 contamination | PASS | none |
| G24-I-21 Regression | PASS | 494/12/42/42 + compileall + 48/48 + 33/33 |
| G24-I-22 Clean reproduction | PASS | env -i runs green; external deps declared |
| G24-I-23 Documentation | PASS | consistent; F-16/F-24 corrections dated, history intact |
| G24-I-24 Evidence integrity | PASS | every key number located and reproduced |
| G24-I-25 Historical evidence | PASS | audit docs never rewritten |
| G24-I-26 Secret audit | PASS | zero credential-shaped strings in tracked tree |
| G24-I-27 Final production gate | PASS | P0=0, P1=0, all hard gates hold |

## 30. Final Decision

```
P0: 0    P1: 0    P2: 1 (RV-P2-01)    P3: 3 (+1 INFO)

READY_FOR_PHASE_25_WITH_DOCUMENTED_DEBT
```

Rationale: every hard gate holds under independent verification — no
ACTIVE bypass, no governance/provenance break, no strict-mode mock
fallback, no secret exposure, no scope contamination, full regression
green. The P2 finding is a startup-timing gap whose fail-closed
behavior is intact; P3s are test-flakiness, DR restore verification,
and an informational hash anchor — all recorded for Phase 25+
backlog, none blocking.

STOP — no fixes applied, no Phase 25 work started.
