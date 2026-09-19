# Phase 13 P1 Stage 1 / Item 1a — Backup Report

Date: 2026-09-19 · Scope: Item 1a ONLY (backup + verify). Restore,
retention, erasure audit, provider verification: DEFERRED (Items 1b/2).

## 1. Implementation Scope

Project-level and root-level backup with a checksum manifest, atomic
manifest placement, fail-closed verification, and an operator CLI —
layered over the existing R-01/R-04/P0.1 infrastructure. Zero runtime
semantic change.

## 2. Actual Components Changed

```text
NEW  runtime/state/backup.py     (the whole feature; ~260 lines incl. CLI)
NEW  tests/runtime/test_p1_backup.py  (11 sections, 50 checks)
MODIFIED: none in runtime/  — no frozen file touched
```

## 3. Backup Format

```text
<dest_dir>/<backup_id>/
    <project files copied byte-for-byte at their relative paths>
    manifest.json          (written LAST, atomically)
manifest = {
  schema_version: "1.0", backup_id, project_id, case_id, created_at,
  project_status_at_backup, index_entry (for Item 1b restore),
  files: [{relative_path, size, sha256, encrypted}, ...]
}
```
No plaintext content, no keys, no tokens — paths/hashes/sizes only.

## 4. Locking Strategy (plan questions Q1–Q3)

- Q1: ONE lock — the EXISTING R-01 `FileLock(projects.json)` — held for
  the entire snapshot. It serializes against every `Project._save` (index
  upsert), `delete_project`, and any concurrent backup. No new lock.
- Q2: manifest collection happens inside the critical section; after the
  copy, the volatile sources (`project.json`) are re-hashed and compared
  — the manifest can only exist for a copy whose sources did not move.
- Q3: a concurrent mutation that beats the re-check → `BACKUP_FAILED`,
  partial directory deleted (fail-closed). Additionally, backups are
  only taken for QUIESCENT projects: any task RUNNING or project
  mid-run → `BACKUP_REJECTED`.

## 5. Encryption Strategy

Reuses P0.1 unchanged; the tool never calls the key. Encryption state
is RE-DERIVED per file from the `IA1:` ciphertext magic and recorded in
the manifest; `verify_backup` re-checks magic-vs-flag (a plaintext swap
of an encrypted-flagged file → INVALID). Encrypted sources back up as
opaque ciphertext (B06: no plaintext PII bytes in the backup); demo-mode
plaintext sources copy as plaintext, flagged as such. Documented
boundary (verified in tests): the case store is the encrypted surface;
`project.json` is task metadata and stays plaintext in both modes.

## 6. Manifest Atomicity

`atomic_write_json` (temp + fsync + os.replace) — the existing R-01
primitive — writes the manifest LAST. Any failure before that point
deletes the backup directory: a directory without a complete manifest is
by definition not a backup (B13: no partial dir survives a crash before
manifest; B14: temp-manifest-only → INVALID; B15: no `.tmp` residue).

## 7. Verification Strategy

`verify_backup(dir)`: manifest exists/parses/has schema fields → every
listed file exists with matching size + sha256 + magic-vs-flag → no
unlisted stray files → VALID. Anything else → INVALID with a reason.
Fail-closed; a corrupt manifest raises loudly (B10).

## 8. Test Matrix

| Group | Tests | Result |
| --- | --- | --- |
| Happy path | B01–B06 (+ encrypted-source B06 variant) | PASS |
| Negative | B07 (manifest deleted), B08 (file modified), B09 (missing file), B10 (truncated manifest, loud), B11 (checksum flipped), B12 (plaintext swap detected) | PASS |
| Atomicity/crash | B13 (crash before manifest → FAILED, no dir), B14 (temp-only → INVALID), B15 (atomic final, no .tmp), B16 (immediate verify VALID) | PASS |
| Concurrency | B17 (8 concurrent backups: all valid, index intact), B18 (backup vs concurrent `Project._save`: consistent-or-failed-closed), B19 (delete after backup keeps it VALID; backup of deleted project → REJECTED) | PASS |
| Security | B20 (no encryption key), B21 (no API key), B22 (no secret-shaped strings in manifest), B23 (no secrets in logs), B24 (errors carry no PII) | PASS |
| Modes + neutrality | all four modes selectable; CaseState/project.json/index byte-identical before/after backup; no side-effect files | PASS |

Suite: `tests/runtime/test_p1_backup.py` — 11 sections, **50/50 checks
green** in both pytest and script mode; CLI `--help` OK.

## 9. Regression Results

```text
pytest tests/runtime -q   → 381 passed (370 baseline + 11 backup tests)
pytest tests/portfolio -q → 12 passed
full regression           → 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR
benchmark B001–B011       → 11/11 RESULT: ALL GREEN
compileall                → OK
demos basic/insurance/generalization/portfolio → all exit 0
temp-dir leaks            → 0 (three stray fixture dirs cleaned; clean
                            re-runs verified)
```

## 10. Security Results

Backup never loads or stores any key; copied bytes are ciphertext when
the source was; manifest holds only paths/hashes/sizes; logs/errors emit
ids and reasons only (B20–B24). No API surface was added — the CLI is
operator-run, so no R-06 surface changed. R-05 untouched (gate still
BLOCKED for real client data).

## 11. Known Limitations

- Single-node, directory-output backups only (no archive/remote/cloud,
  by scope).
- `backup_root` takes one lock per project (not a root-wide freeze) —
  each project snapshot is internally consistent; cross-project atomicity
  is not claimed.
- Consistency re-check covers the volatile `project.json`; append-only
  logs (events.jsonl) are line-atomic and covered by the same lock
  discipline, but a hot project is rejected outright (RUNNING →
  BACKUP_REJECTED), which is the primary guard.
- No restore in this item — a verified backup is copy + manifest; the
  round-trip home is Item 1b.

### F-01 addendum (final human review, 2026-09-19) — approvals.jsonl
### consistency window

The post-copy volatile re-check covers `project.json` only. The existing
`ApprovalStore` writes `approvals.jsonl` WITHOUT the R-01 lock — `append()`
is a plain append, and `update()` REWRITES the whole file via a non-atomic
`open("w")` (runtime/approval/store.py:36–45; `_append_jsonl` in
harness.py is likewise unlocked). If a human approval lands exactly while
a backup copies a gated-but-quiescent project (e.g. `waiting_approval`),
the backup can capture a truncated/partial `approvals.jsonl` whose
recorded hashes are SELF-CONSISTENT — so `verify_backup` passes while the
content is later unrestorable.

Recorded facts:

- Root cause is the PRE-EXISTING ApprovalStore write semantics — NOT
  something Stage 1 / Item 1a introduced. The quiescent-only rule plus
  the R-01 lock remain the primary coherence guards.
- Failure is fail-closed downstream: Item 1b restore parses
  `approvals.jsonl` line-by-line during staging sanity and returns
  RESTORE_FAILED on any corrupt line — no live state is ever damaged.
- Residual exposure is narrow (sub-second window, requires the approve()
  rewrite to interleave with the copy phase) but real: a "verified"
  backup can be semantically unrestorable, which weakens the backup-first
  deletion guarantee of Item 2 by a small margin.
- Future remediation candidates (deliberately NOT implemented in
  Stage 1): extend the `_VOLATILE` post-copy re-check to
  `approvals.jsonl` (re-hash or re-parse), or bring `ApprovalStore`
  writes under the R-01 lock.

## 12. Deferred Items

```text
Item 1b — Restore (verify + locked index re-add + overwrite refusal)
Item 2   — Retention policy / sweep / erasure audit
R-05     — Provider policy (operator verification; gate stays BLOCKED)
R-07/R-10/R-11, case ownership — later stages
```

## 13. Acceptance Decision

```text
ITEM_1A = PASS
```

All functional, security, concurrency, runtime-neutrality and regression
criteria met (checklist §22 of the item brief: all boxes checked, 50/50
machine-verified). Rollback is a pure file deletion (no runtime wiring
references the module).
