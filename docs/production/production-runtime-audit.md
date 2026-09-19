# Durable State & Runtime Audit

## 8.1 Where is state saved?

| State | Location | Format |
| --- | --- | --- |
| CaseState (stages/tasks/artifacts/evals/trace) | `<project>/case/<case_id>/case_state.json` + `artifacts/*.json` | JSON, rewritten per checkpoint |
| Task/project state | `<project>/project.json` | JSON, rewritten per mutation |
| Project index | `<harness_root>/projects.json` | JSON, **read-modify-rewrite, unlocked** |
| Events | `events.jsonl` | append-only |
| Checkpoints | `checkpoints.jsonl` + in-state `checkpoints[]` | append + rewrite |
| Approvals | `approvals.jsonl` | append + rewrite-on-update |
| Messages | `messages.jsonl` | append + rewrite-on-update |
| Supervisor/alerts/notifications/commands | `supervisor.json`, `alerts.jsonl`, `notifications.jsonl`, `control_commands.jsonl` | mixed |

## 8.2 Concurrent cases?

Within one harness: safe (scheduler thread is the sole writer; worker
isolation test-proven). Across harness instances/projects: per-project
dirs are disjoint, but **the shared projects.json index is not
coordinated** — measured silent lost-update (8→3 entries). Approval/
message "rewrite-on-update" files carry the same cross-instance risk if
two processes touch one project.

## 8.3 Lost update / partial write / race / corruption

- Lost update: **yes, measured and re-reproduced** on the index (8
  concurrent saves → 3, then 5 entries on re-run). Worse: the re-run also
  caught a thread **crashing with JSONDecodeError while another thread was
  mid-rewrite** of projects.json — concurrent readers hit partially
  written files. So the index is both lossy AND readable-corrupt under
  concurrency (non-atomic write + no lock).
- Partial write: JSON rewrites are not atomic (no temp-file+rename); a
  crash mid-save can leave truncated JSON. Checkpoint *loading* detects
  this (CHECKPOINT_INVALID, schema + fingerprint checks) — detection
  exists, prevention does not.
- Race: index rewrite (measured); per-project scheduler-internal state is
  race-free by construction (single writer).
- Corruption: fingerprint verification makes artifact corruption loud;
  structural JSON corruption is detected at load and fail-closes.

## 8.4 / 8.5 Crash & machine restart recovery

Process crash: recovered (checkpoint validation, RUNNING→PENDING, task
idempotency, idempotent command replay — all test-proven). Machine
restart: same, provided the JSON tree survived; **no machine-loss story
(no backup, no replication)**.

## 8.6 Historical case query

Yes — every project dir persists forever; `list_projects` /
`load_project` read history. No retention/archive policy (a privacy
consideration, see data audit).

## 8.7 Sufficient for 1–3 trusted users?

The per-project durability and recovery semantics are sufficient for a
controlled single-node pilot. Two things are not: (a) the index
lost-update bug (must be fixed — it corrupts the project listing under
any concurrent use), and (b) absent backup for real client data.

## Failure-injection readiness (existing coverage)

| Failure | Current detection/behavior | Gap | Severity |
| --- | --- | --- | --- |
| DB unavailable | N/A (no DB); disk-full behavior untested | untested | P2 |
| LLM timeout | provider timeout 60s → bounded retry → fail-closed | covered | — |
| Malformed output | schema validation + retry ≤2 → fail-closed | covered (F01/F02) | — |
| Worker crash | exception → one task NEEDS_REVIEW; round commits | covered | — |
| Duplicate task | no-duplicate gate (completed work never restarted) | covered | — |
| Approval timeout | EXPIRED transition exists; **no automatic TTL** | manual only | P2 |
| Expired product | `effective_from` present; **`effective_to` absent from catalog**; no expiry eval check | gap | **P0 (with product data)** |
| Knowledge unavailable | fail-closed, no fabricated evidence | covered (F04) | — |
| Unauthorized access | actor allowlists on approval/control; **no human authn on server** | gap | P1/P0 ext |
| Invalid artifact | contract + eval + registry fingerprints | covered | — |
| Corrupted checkpoint | 5-check validation → CHECKPOINT_INVALID, fail-closed | covered | — |

## Hard-gate check (§19 of the brief)

- Case state concurrently corruptible: **YES — index lost-update (P0)**.
- Agent can bypass human approval for the final deliverable: **YES — no
  report/recommendation approval gate; agent-mode gates auto-approve
  (P0)**.
- Product recommendation without reliable evidence: **YES — demo catalog
  lacks effective_to and core underwriting fields (P0 for real cases)**.
- LLM failure producing fake results: no (fail-closed, tested).
- Agent bypassing eval: no (tested).
- Provenance forgeable undetected: no (fingerprint tamper detection).
- Secrets in logs: no (probed).
- Un-auditable results: no (durable event lineage).
