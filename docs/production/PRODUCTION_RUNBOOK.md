# Production Runbook — Single-Node Controlled Pilot (Phase 26C-5)

Every procedure below has been PERFORMED during Phases 26A–26C-5
(not aspirational). Windows dev box + Docker Desktop.

## Startup

1. Start Docker Desktop
   (`C:\Users\aubor\AppData\Local\Programs\DockerDesktop\Docker
   Desktop.exe`); wait for `docker info` to succeed (~20–60s).
2. Verify the stack: `docker ps` — expect `agent-postgres`
   (127.0.0.1:5433→5432, postgres:16.4-alpine) and the WeKnora
   containers. If WeKnora-app shows Exited(127): `docker start
   WeKnora-app` (known post-reboot behavior), wait for healthy.
3. PG credential file `%TEMP%\pg_cred.txt`
   (`AGENT_PG_PASSWORD=...`) — if missing (Temp cleanup), recover
   read-only: `docker exec agent-postgres env` → POSTGRES_PASSWORD.
4. Runtime interpreter: PATH python 3.11.8 (D:/Programs/Python/
   Python311-64 — has psycopg2 2.9.11). The workbuddy python does
   NOT (it is only for the standalone-script runner
   tmp/run_regression.py).
5. Health: `python -c "...PostgresStore().connect..."` SELECT 1;
   observability health endpoints (Phase 25) for llm_gateway/
   knowledge dependencies.

## Readiness (before admitting any case)

`python -m pytest tests/runtime -q` → 0 failed (expect 596+).
Portfolio 12/12 · benchmark 42/42 · targeted compileall (runtime,
tests, evals/agent-benchmark, demos, demo, .trae/skills).

## Backup (daily; PA-26C5-P1-01 procedure)

    docker exec agent-postgres pg_dump -U agent -d agent_runtime -Fc \
        > backups/agent_runtime_$(date +%Y%m%d).dump

(filestate side: runtime/state/backup.py project snapshots, Phase
13 P1 tooling.) Retention per Phase 13 P1 item 2 policy.

## Restore drill (verified 2026-09-23; rerun after every tag)

    docker exec agent-postgres psql -U agent -d postgres \
        -c "CREATE DATABASE agent_restore_drill OWNER agent;"
    docker exec -i agent-postgres pg_restore -U agent \
        -d agent_restore_drill --no-owner < backups/<dump>
    # verify table/row parity, then:
    docker exec agent-postgres psql -U agent -d postgres \
        -c "DROP DATABASE agent_restore_drill;"

Real-restore (incident): same flow into a fresh `agent_runtime`
after stopping workers. Restore is byte-faithful — all CAS/
terminal/approval/budget invariants carry over; run
`reconcile_once()` afterwards to settle any external drift.

## Shutdown

Stop workers (SIGTERM → graceful release, 26A-20) → stop intake →
daily pg_dump → optional `docker stop` of the stack.

## Recovery procedures (all state repairs via sanctioned entries)

* Dead worker / stuck RUNNING: wait for lease expiry →
  `RecoveryController.reconcile_once()` (requeues via 26A
  recover_expired; terminalises overdue runs via 26C-2) → workers
  resume claims. NEVER hand-UPDATE queue_tasks/agent_runs.
* Run/task drift (bypass/corruption class): reconcile_once
  classifies HEALTHY/RECOVERABLE/STALE/INCONSISTENT — INCONSISTENT
  rows are flagged, not auto-repaired: operator review required
  (read recovery_events; decide; the fix is a NEW run, not a
  mutated terminal).
* Overdue waiting runs: reconcile_once (expire step) → approval
  then correctly refused.
* DB loss mid-write: worker surfaces RECOVERY_REQUIRED (never
  guessed); lease-expiry path converges; rerun reconcile_once.

## Rollback

* Code: `git revert` to the pilot tag (worktree is committed
  before Stage 1 — PA-26C5-P2-02).
* Database: restore last pg_dump (procedure above). No in-place
  schema-migration tooling exists — schema changes ship as NEW
  DDL (CREATE IF NOT EXISTS) and old dumps restore into their own
  schema version; cross-version restore = NOT APPLICABLE today.
* Knowledge: PG registry rows versioned (Phase 24); product
  catalog versioned (Phase 12/13) — rollback = re-point to prior
  version, never delete.

## Environment gotchas (all hit and solved in this project)

MSYS path conversion mangles docker-exec `/tmp` args (use
`//tmp` or stdin/stdout pipes) · psycopg2 NUMERIC → Decimal ·
`%` in LIKE with params needs parameterization · a failed
`docker cp` can leave a same-named DIRECTORY behind ·
worker-instance concurrency needs N caller threads · first
battery of the day can crawl (rerun before diagnosing).
