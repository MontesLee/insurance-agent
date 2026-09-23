# Phase 26C-5 Audit — Production Acceptance Evidence

Date: 2026-09-23 · Method: Code > Tests > Runtime Evidence > Config >
Docs > Claims. Every row below cites where its evidence lives. This
audit ADDED no code and changed no tests.

## Hard-gate evidence (live-verified this audit)

1. **PG backup/restore — REAL drill executed** (§18):
   `pg_dump -Fc` (131,238 bytes) → scratch DB `agent_restore_drill`
   → `pg_restore` → verified: 16 tables restored; seeded managed
   run restored FIELD-IDENTICAL (task SUCCEEDED/attempt=1/result
   seed=true; budget max=7/used=2/tokens=100; ledger event
   present). Scratch DB dropped afterwards. Restore is byte-
   faithful → every CAS/terminal/approval/budget invariant carries
   over by construction; the 26C-4 reconciler handles any
   externally-corrupted post-restore drift.
2. **Secrets** (§15): grep over runtime/tests/docs/demos/.trae for
   hardcoded `api_key|password|secret|token` value patterns → ZERO
   hits (only env-var names / redaction code). Real credentials:
   PG password via AGENT_PG_PASSWORD env/session file; GLM key via
   env; both outside the repo.
3. **Provider policy R-05** (§13): provider-policy-verification.md
   verdict = **NOT VERIFIED** → `runtime/agent/data_policy.py`
   BLOCKS real client data at the LLM gate by default; opens only
   on explicit operator opt-in after verification. UNKNOWN → NOT
   APPROVED holds.
4. **AuthN/AuthZ** (§7/§8): runtime/auth.py Identity + API-key
   authenticate; server refuses to START unauthenticated when the
   mode requires auth (Phase 13 hardening, 370-test battery);
   missing/invalid credential → DENY (no anonymous fallback). Role
   checks (`_require_role`) on diagnostics/metrics. Queue ops:
   OWNER/REVIEWER/OPERATOR gates (26B), unauthenticated → OpsDenied.
5. **Human Review** (§9): orchestrator gate_policy=stop →
   PAUSED_NEEDS_REVIEW; the agent CANNOT deliver a final
   recommendation directly (26B defer + 26C-2 WAITING_HUMAN +
   approval binding matrix: wrong task/stage/run/cancelled/expired
   all fail closed — E26B-11/12, E26C2-08). Review actions today:
   APPROVE / REJECT (no MODIFY — P2 debt).
6. **Cross-user isolation** (§6): NOT IMPLEMENTED at object level —
   the system is single-tenant, role-based; some read endpoints
   lack identity deps; queue ops check role, not per-case
   ownership. For a controlled INTERNAL pilot (single authority
   domain, trusted users) → documented risk acceptance (P1-2);
   hard blocker for any external stage.
7. **Cost** (§20): run budget with soft/hard stop proven (26C-3);
   the queue path makes REAL ZERO LLM calls (deterministic skills)
   — 0 means "no calls on this path", NOT "$0 LLM cost". LLM
   metering integration = NOT MEASURED / FUTURE (F-26C3-INFO-01).

## Findings (this audit)

| ID | Sev | Finding | Disposition |
|---|---|---|---|
| PA-26C5-P1-01 | P1 | PostgreSQL has NO code-level backup tooling (runtime/state/backup.py covers filestate only, predating the 22B PG cutover) | Risk-accepted for internal pilot: REAL drill above + RUNBOOK daily-pg_dump procedure; tooling = pilot debt |
| PA-26C5-P1-02 | P1 | No object-level user isolation (role-based only; some server read endpoints without identity deps; queue ops without per-case ownership) | Risk-accepted for CONTROLLED INTERNAL pilot only (single-tenant, trusted users); BLOCKS external |
| PA-26C5-P1-03 | P1 | Provider data policy NOT VERIFIED → real client data must not enter the LLM provider | Protective gate already enforces (default BLOCKED); pilot constraint: real data on the deterministic path only, or verify policy then opt in |
| PA-26C5-P2-01 | P2 | Review MODIFY action absent (APPROVE/REJECT only) | Pilot debt (fail-closed without it: reject forces re-run) |
| PA-26C5-P2-02 | P2 | All 26C-1..4 work UNCOMMITTED on 7ac15aa | Pilot ENTRY criterion: commit + tag before Stage 1 |
| PA-26C5-P2-03 | P2 | RPO/RTO NOT MEASURED (single node; drill RTO ≈ minutes, not a measured SLO) | Honest UNKNOWN in acceptance doc |

Prior-phase debt unchanged (F-26R-P2-01 marker files single-host,
F-26R-P3-01 recovery obs, F26B-P3-02 per-type caps, F-26C1-INFO-01
global capacity, F-26C3-INFO-01..03, F-26C4-INFO-01..03).

P0 = 0 · P1 = 3 (all risk-accepted/procedure-backed/protectively
gated per pilot definition) · P2 = 3 · P3 = 0 · INFO = prior.
