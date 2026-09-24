# Pilot Runbook (Phase 27)

Superset of PRODUCTION_RUNBOOK.md (single node). Pilot-specific:

## Start
PRODUCTION_RUNBOOK startup (Docker → agent-postgres :5433 +
WeKnora stack → pg_cred → PATH python). Pilot adds nothing.

## Submit a case
    python docs/production/pilot/tools/run_pilot.py [--case=C01]
Cases C01–C12 defined in the tool. Evidence lands in
docs/production/pilot/data/pilot-machine-results.json; bulky run
roots in tmp/pilot27/<id>/ (gitignored).

## Monitor
queue rows (queue_tasks/agent_runs/agent_run_budgets via SQL),
obs stderr events (run.*/task.*), elapsed per case ≈1.3s.

## Review (human)
Open tmp/pilot27/<id>/attempt-N/<id>/artifacts/*.json and fill
pilot-review-template.md per case; record into pilot-results.md.

## Stop / Recover / Rollback
PRODUCTION_RUNBOOK procedures apply verbatim (graceful SIGTERM,
reconcile_once, restore-from-dump, git revert to the
phase26c-productionization-v1.0 tag). Pilot adds NO runtime hooks.

## Pilot stop conditions
See pilot-protocol.md / PRODUCTION_ACCEPTANCE.md — any P0 event
stops the pilot immediately; record Incident/Evidence/Affected/
Containment/RootCause/NextAction.
