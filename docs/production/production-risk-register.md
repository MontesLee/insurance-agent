# Production Risk Register

| ID | Risk | Evidence | Severity | Production impact if unfixed |
| --- | --- | --- | --- | --- |
| R-01 | Project-index lost update AND read-corruption under concurrent access | probe ×2: 8 concurrent `Project._save()` → 3, then 5 entries (silent loss); re-run also caught a reader thread crashing with JSONDecodeError on a partially written projects.json | **P0** | Projects vanish from the listing AND concurrent readers can crash (unhandled JSONDecodeError escapes `_index_read`) — silent data loss + denial of service on the only shared mutable file |
| R-02 | No enforced human-review gate on the final report/recommendation | policy evaluates replans only; B001 completes without any approval event; agent tools auto-approve stage gates | **P0** | Agent output can reach delivery without the required human Approve/Modify/Reject step — violates the stated production flow |
| R-03 | Product catalog not real-recommendation grade (no effective_to; missing waiting period/exclusions/limits/health/occupation fields) | catalog JSON probe | **P0** (for real cases) | Recommendations rest on demo data; product validity/expiry unverifiable |
| R-04 | Real client data at rest: plaintext, unencrypted, unclassified, no retention/erasure | probe: 156/312 sensitive-term hits in events/state | **P0** (for real client data) | Privacy exposure of income/family/health-adjacent data |
| R-05 | LLM provider data policy (retention/training/region) unverified for real client payloads | repo scan: no evidence found | **P0** (for real client data) — UNKNOWN pending verification | Client data leaves the machine under an unverified processing agreement |
| R-06 | No authentication; CORS `allow_origins=["*"]`; actor strings client-supplied | code probe | **P0** if network-exposed / P1 localhost-pilot | Open approve/control endpoints; forged "human" actor |
| R-07 | Token/cost usage not durably recorded | probe: zero usage fields in durable state | P1 | Cannot answer per-case cost; no cost audit trail |
| R-08 | No backup tooling or procedure | git grep: docs only | P1 | Real client data single-copy |
| R-09 | Non-atomic JSON rewrites (no temp+rename); partial-write prevention absent (detection exists) | code reading; checkpoint validation catches at load | P1 | Crash mid-save → CHECKPOINT_INVALID (fail-closed but work-losing) |
| R-10 | Domain eval thin on insurance-report (payload-presence only) | eval.rules probe | P1 | Final deliverable is the least-evaluated artifact |
| R-11 | No deployment definition (no Dockerfile/service/env separation/restart procedure) | repo scan | P1 | Pilot host runs ad hoc; recovery is manual |
| R-12 | Approval TTL manual-only (no auto-expiry) | code probe | P2 | Stale WAITING_HUMAN projects linger unnoticed |
| R-13 | Monitoring: liveness-only health, no metrics/alerting/structured logs | probe | P2 | Issues discovered by users, not by the system |
| R-14 | Rate limiting absent (loop bounds are the only ceiling) | code | P2 | Burst cost/abuse unthrottled |
| R-15 | Rewrite-on-update JSONL stores (approvals/messages) share the cross-instance coordination gap | code reading | P2 (single-process pilot: safe) | Two processes on one project could interleave updates |
| R-16 | No multi-node anything / external queue / distributed scheduler | by design, documented | P3 (future scale) | Out of scope for this round |

## Hard gates (§19) verdicts

| Hard gate | Verdict |
| --- | --- |
| Real client data cross-user leakage | Not applicable yet (single machine, no users) — becomes P0 the moment authn/data-at-rest are unfixed and users are added |
| Agent bypasses human approval | **TRIGGERED** (R-02) |
| Product recommendation without reliable evidence | **TRIGGERED** for real cases (R-03) |
| LLM failure produces fake result | Not triggered (fail-closed, tested) |
| Agent bypasses eval | Not triggered (tested) |
| Provenance forgeable undetected | Not triggered (fingerprint tamper detection) |
| Secrets in logs | Not triggered (probed) |
| Case state concurrently corruptible | **TRIGGERED** (R-01, index) |
| Unrecoverable tasks | Not triggered (crash-recovery suites) |
| Un-auditable results | Not triggered (durable lineage) |
| Product validity period unverifiable | **TRIGGERED** (R-03) |


---

## Remediation status (Phase 13 P0 round, 2026-09-19 — Round-1 rows above preserved as audited)

| ID | Status | Fix summary | Evidence |
| --- | --- | --- | --- |
| R-01 | **FIXED** | atomic+locked persistence (`runtime/state/durable.py`) | `test_p0_r01.py` (7 sections incl. cross-process) |
| R-02 | **FIXED** | `APPROVAL_FINAL_REVIEW` gate, `ready_for_delivery` (manual delivery), 8 bypass paths negative-tested | `test_p0_r02.py` (10 sections) |
| R-03 | **FIXED** | `runtime/catalog_governance.py`, production mode, expiry/evidence/governance fields in eval | `test_p0_r03.py` (9 sections) |
| R-04 | **FIXED** (single-node boundary) | redaction + optional at-rest encryption + erasure | `test_p0_r04.py` (6 sections) |
| R-05 | **GATE SHIPPED BLOCKED** (honest: policy still NOT VERIFIED) | `runtime/agent/data_policy.py` + server boundary + operator procedure | `test_p0_r05.py` (5 sections) + provider-policy-verification.md |
| R-06 | **FIXED** | `runtime/auth.py`, roles, CORS allowlist, identity-derived actors | `test_p0_r06.py` (6 sections) |

P0 count after remediation: **0** (R-05's blocker is now an enforced gate
that BLOCKS by default, which is the required fail-closed behavior for an
unverifiable policy — the underlying verification remains an operator P1).
