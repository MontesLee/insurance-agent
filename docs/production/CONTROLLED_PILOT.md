# Controlled Pilot Definition (Phase 26C-5)

Scope: OWNER + 1–3 trusted users, real (small) case volume, real
customer data UNDER the constraints below. Single node, single
authority domain.

## Stage 0 — Production-like local environment

Entry: regression 0 failed; PG + WeKnora healthy; pg_cred present;
PATH python (psycopg2).
Exit: smoke run of one managed case end-to-end (defer → approve →
resume → COMPLETED) through RunControl.
Stop/Rollback: any failed gate → fix or abort; nothing is live yet.

## Stage 1 — Owner only, real data, mandatory human review

Entry criteria:
1. Commit + tag the current tree (PA-26C5-P2-02) — the running
   code MUST be a tagged commit, not a worktree.
2. Daily `pg_dump` scheduled (RUNBOOK) + one more restore drill on
   the tagged environment (PA-26C5-P1-01 acceptance).
3. Real customer data path = deterministic skills ONLY (no LLM
   call on real data) OR provider policy verified + explicit
   opt-in env (PA-26C5-P1-03; the gate enforces this itself).
4. Budget configured per run (26C-3) and deadline set (26C-2).
5. Every recommendation passes the human gate (26B/26C-2 HITL) —
   the Owner is the sole approver.

Exit criteria: ≥10 real cases completed with mandatory review; zero
stop-condition events; one operator recovery drill (kill worker →
reconcile_once → verify) executed on live data.
Stop: any stop condition (see PRODUCTION_ACCEPTANCE.md) or any
UNKNOWN→success attempt observed.
Rollback: stop intake; pg_dump snapshot; git revert to tag if code
is implicated; cases stay in PG (durable) for review.

## Stage 2 — 1–3 trusted users

Entry: Stage 1 exit + PA-26C5-P1-02 risk acceptance SIGNED OFF by
the Owner (all users are trusted operators in one authority
domain; no object-level isolation exists — role gates only).
Additional constraints: one shared REVIEWER identity per person
(auth.py identities file); all approvals audited (queue_ops_events);
weekly pg_dump restore-spot-check; weekly reconcile_once +
expire_overdue pass by the operator.
Exit: ≥20 additional cases; zero cross-user incidents; zero
approval anomalies.
Stop: any stop condition, OR any evidence of a user touching
another user's case flow → immediate stop + audit.

## Stage 3 — 20–50 cases cumulative

Entry: Stage 2 exit + P1-02 remediation decision point (object
isolation design) + provider-policy re-verification attempt.
Exit: pilot report; go/no-go for the external-stage gate list
(object isolation, provider policy, PG backup tooling, measured
RPO/RTO, LLM metering, review MODIFY).

## Hard pilot constraints (all stages)

* Single host (single-host scope is the stated deployment boundary:
  approval markers are files, workers share run_root).
* No auto-budget-increase; no auto-approval; terminal runs never
  resurrect (enforced by 26A/26C-2/26C-3/26C-4 CAS).
* All operator actions through QueueOps (audited) — never raw SQL
  against queue/agent_runs tables on live data (reconcile_once is
  the sanctioned state-repair entry).
