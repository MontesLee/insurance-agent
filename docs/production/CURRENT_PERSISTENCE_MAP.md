# Current Persistence Map — Phase 22A-01

Measured from code, not documentation. Every write/read entry point
mapped to its storage surface.

## Write Paths

| Surface | Write Entry | Atomicity | Lock | Data |
|---|---|---|---|---|
| `projects.json` | `harness._save()` → `_index_upsert()` | atomic_write_json | FileLock(projects.json) | project index (id, name, status, timestamps) |
| `case_state.json` | `state/store.py:save()` | write_protected (Fernet) | none (per-project dir) | full CaseState (tasks, stages, artifacts, events) |
| `artifacts/*.json` | `case_state.py:put_artifact()` → within store.save() | within case_state save | none | artifact content |
| `events.jsonl` | `case_state.py` → `_append_jsonl()` | append-only | none (single writer) | event records |
| `checkpoints.jsonl` | `case_state.py` → append | append-only | none | checkpoint snapshots |
| `approvals.jsonl` | `approval/store.py:append()` → atomic rewrite | atomic rewrite | none | approval records |
| `messages.jsonl` | `case_state.py` → append | append-only | none | inter-agent messages |

## Read Paths

| Surface | Read Entry | Used By |
|---|---|---|
| `projects.json` | `_index_read()` → `read_json_retry` | harness, backup, restore, retention |
| `case_state.json` | `state/store.py:load()` | orchestrator, harness, evidence loop |
| `artifacts/*.json` | `state/store.py:load_artifact()` | eval engine, recommendation |
| `events.jsonl` | `_read_jsonl()` | observability, trace |
| `checkpoints.jsonl` | checkpoint.py validate/resume | harness recovery |
| `approvals.jsonl` | `approval/store.py:get()/all()` | approval manager, orchestrator |

## Atomicity Requirements

| Operation | Must be atomic | Current mechanism |
|---|---|---|
| projects.json update | YES | FileLock + atomic_write_json |
| case_state.json save | YES (all artifacts + state together) | write_protected (temp+rename) |
| approvals.jsonl update | YES (whole-file rewrite) | atomic rewrite in store.py |
| event append | NO (append-only, single writer) | _append_jsonl |
| checkpoint append | NO (append-only) | append |

## What Goes Where (target)

| Data | PostgreSQL | Local File / Object Store | Why |
|---|---|---|---|
| Project metadata | ✅ | — | Needs indexing, transactions |
| CaseState (structured) | ✅ | — | Needs transactions, concurrent access |
| CaseState (artifacts) | ✅ metadata / file content | Needs transactions for metadata; content stays local for now |
| Events | ✅ | — | Needs indexing, querying, retention |
| Checkpoints | ✅ metadata / blob in DB | Needs atomic task+checkpoint update |
| Approvals | ✅ | — | Needs transactional state transitions |
| Knowledge registry | ✅ | — | Needs versioned history, querying |
| LLM logs | — | ✅ Object Storage (future) | Size + PII |
| Report content | — | ✅ Object Storage (future) | Size, read-heavy |

## Deletion Requirements

| Data | Must support deletion | Mechanism |
|---|---|---|
| Projects | YES | delete_project (existing) |
| CaseState | YES | via delete_project |
| Events | NO (append-only) | retention sweep |

## Audit Requirements

| Data | Must be auditable | Mechanism |
|---|---|---|
| All state changes | YES | events.jsonl (existing) |
| Approval decisions | YES | approval_decisions (new table) |
| Erasure operations | YES | erasure.log (existing) |
| Governance decisions | YES | in evidence metadata (existing) |
