# Phase 13 P1 Stage 1 / Item 1b — Restore Report

Date: 2026-09-19 · Scope: Item 1b ONLY (restore + verification). Item 2
retention/erasure, R-05 provider verification, Stage 2: DEFERRED.

## 1. Scope

Restore of a VERIFIED Item-1a backup into the harness root, as a
consistent project state, under the existing R-01 lock / R-04 encryption /
checkpoint+registry validators — with no approval creation, no runtime
semantic change, all-or-nothing failure semantics.

## 2. Actual Implementation

```text
NEW  runtime/state/restore.py   (restore_project + _staging_sanity + CLI)
NEW  tests/runtime/test_p1_restore.py  (9 sections, 57 checks)
FIX  runtime/state/durable.py    FileLock re-entrancy (see §5 — a genuine
                               R-01 defect found BY restore, fixed within
                               the R-01 contract, all R-01 tests re-verified)
No other runtime file touched.
```

## 3. Restore Flow (as implemented)

```text
bk.verify_backup()          invalid → RESTORE_REJECTED (never staged)
  ↓
R-01 FileLock(projects.json) — held for the ENTIRE restore
  ↓
identity: manifest.project_id == target (no restore-as-new in 1b)
  ↓
encryption invariant: strict mode refuses plaintext-source backups
  ↓
STAGING (<root>/.restore_staging_<id>/) — files copied bytes-as-is
  ↓ (manifest travels with the tree for post-commit re-verification)
staging validation:
  project.json parses + ids match;
  EVERY case dir loads through the EXISTING store/cp.validate
  (schema + registry fingerprints + task→stage);
  undecryptable state (no key) → fail closed;
  approvals.jsonl shape-sanity (known statuses only)
  ↓
ATOMIC COMMIT: live dir renamed aside → staging renamed in → index
updated via locked_update_json (same lock) → on ANY failure the old
tree is renamed back
  ↓
POST-COMMIT VERIFY: verify_backup on the committed tree + index readable
failure → rollback (old tree restored) → RESTORE_FAILED
  ↓
RESTORE_SUCCESS (+ restore.log audit entry)
```

## 4. Staging Strategy

Restore never writes the live project first. Any staging/validation
failure removes the staging dir and returns RESTORE_FAILED with the live
project untouched (R33/R11 verified). No plaintext is ever materialized:
files are copied bytes-as-is; ciphertext stays ciphertext.

## 5. Locking Strategy — and an R-01 defect found & fixed

Restore holds `FileLock(projects.json)` for its whole duration and then
updates the index through `locked_update_json` — the SAME lock path.
This exposed a genuine R-01 defect: the per-path thread lock was a
non-reentrant `Lock`, so same-thread re-acquisition DEADLOCKED (observed
as a hung restore during testing). Fix (within the existing contract, in
`durable.py`): the thread lock is an `RLock`, and the OS-level byte
lock is taken only on the OUTERMOST acquisition (msvcrt/fcntl range
locks are not re-entrant across handles). All 7 R-01 sections + 11
backup sections re-verified green after the fix.

## 6. Atomic Commit Strategy

Directory-swap commit: existing live dir → renamed aside; staging →
renamed into place; index updated under the same lock; post-commit
verification; on failure the aside tree is renamed back. No window with
`case_state restored + projects.json old` (single lock covers both).

## 7. Encryption Strategy

Copies are bytes-as-is; no key is read, written, logged or echoed. The
key is consulted only indirectly (existence) to decide decryptability
during staging validation. Strict-mode roots REFUSE plaintext-source backups
(RESTORE_REJECTED) — no plaintext permanent restore (§13 of the brief);
restored encrypted case files stay `IA1:` ciphertext at rest (R44).

## 8. Approval Boundary

Restore ≠ Approve (R36–R39, all negative-tested):
- the restored approval state is byte-for-byte what the backup held;
- restore creates NO new approval and NO new actor;
- no READY_FOR_MANUAL_DELIVERY is manufactured (project status comes
  from the backup's project.json, unchanged by restore);
- a forged approval status in the backup fails staging sanity closed;
- `restore.py` never imports ApprovalManager / approval APIs (structural);
- R-02 enforcement is runtime-time (mode-derived at the next run()),
  so a restored unapproved deliverable is still gated.

## 9. Provenance / Catalog Boundary

Fingerprints and lineage travel byte-for-byte; staging validation runs the
EXISTING `cp.validate` + registry fingerprints (tampered artifacts cannot
restore). Catalog governance is a run-time property of the next `run()`
(the R-03 eval checks); restore invents no governance fields and cannot
whitelist a historical product.

## 10. Failure Safety (R01–R10 all verified)

Invalid manifest / checksum / missing file / extra file / plaintext
substitution / decrypt failure / schema failure / identity mismatch /
commit failure / post-commit failure → in every case the live project
is unchanged and no partial directory survives (staging removed; old tree
renamed back on commit-path failures).

## 11. Concurrency Tests (R14–R17)

restore vs concurrent saves (different project) → serialized, index has
both projects; restore vs backup concurrently → both lock-safe;
restore-after-delete → clean; two simultaneous restores of the same
backup → lock serializes, final state consistent; projects.json always
valid JSON.

## 12. Security Tests (R40–R44)

No key/token in logs or the audit log; no plaintext PII in logs; no
staging residue; failed restores leave no plaintext permanent files;
encrypted sources restore to ciphertext at rest.

## 13. Regression Results

```text
pytest tests/runtime -q   → 390 passed (381 baseline + 9 restore tests)
pytest tests/portfolio -q → 12 passed
full regression           → 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR
benchmark B001–B011       → 11/11 ALL GREEN
compileall                → OK
demos basic/insurance/generalization/portfolio → all exit 0
temp-dir leaks           → 0 (fixture dirs cleaned; stale lock holders
                           were stopped and their dirs removed)
P0 suites re-run         → R-01..R-06 + P0.1 + Item 1a: 67 passed
```

## 14. Known Limitations

- Same-node restore only; restore-as-new-project deliberately NOT built.
- Overwrite restores replace the live project atomically (old tree aside
  then delete after verification); the pre-overwrite tree is not itself
  backed up first — the operator should take a backup before
  overwriting (Item 1a exists for exactly this).
- Staging validation loads case state through the existing validators;
  cases whose workflow schema evolved since the backup would fail closed
  (RESTORE_FAILED) rather than migrate — correct, but noted.
- Crash AFTER the index update but before cleanup leaves the restored
  tree + updated index (a CONSISTENT state, verified consistent on
  restart via the existing load/validate path); crash-specific
  recovery hooks were out of scope (not added, per §16).

### F-02 addendum (final human review, 2026-09-19) — full crash-window
### map and recovery principle

Three crash windows exist on the commit path (all inside the single
R-01 index-lock hold, so CONCURRENT mutation can never interleave —
these are crash-only windows, not silent-corruption windows):

1. **Between the two directory renames** (live tree already moved to
   `<pid>.restore_old_<restore_id>`, staging not yet committed): the
   canonical `<pid>/` directory is absent while the index still lists
   the project; the live tree sits intact at the `.restore_old_*` path
   and the `.restore_staging_*` directory still holds the candidate.
2. **After the staging→committed rename, before the index update**: the
   restored tree is in place but the index does not list it (the
   project is invisible to `list_projects` until the index lands);
   the old tree (if any) still sits at the `.restore_old_*` path.
3. **After the index update, before cleanup** — the case already
   documented above (consistent; nothing to do).

Recovery principle for windows 1–2 (operator intervention; no recovery
code shipped in Stage 1, per the final-review rules): re-running
`restore_project` with `--allow-overwrite` deterministically re-stages
and re-commits from the VERIFIED backup, atomically replacing whatever
partial artifact state exists; alternately the operator may manually
rename the `.restore_old_*` tree back to `<pid>/`. Leftover
`.restore_staging_*` / `.restore_old_*` directories from an interrupted
run are inert and can be inspected/removed by hand. In every window the
on-disk state is either the pre-restore tree, the fully restored tree,
or an obviously-named intermediate — never a mix of two time points.

## 15. Deferred Items

```text
Item 2 — retention policy / sweep / erasure audit
R-05   — provider-policy operator verification (gate still BLOCKED)
R-07 / R-10 / R-11 / case ownership — later stages
Stage 2 — not planned
```

## 16. Acceptance Decision

```text
ITEM_1B = PASS
```

All functional, security, integrity, human-control, runtime-neutrality
and regression criteria met (§30 checklist fully checked, 57/57
machine-verified). One additive fix inside the R-01 module (lock
re-entrancy) was required and is itself acceptance-covered by the
existing R-01 suite. Rollback of Item 1b = delete `restore.py` + test;
Item 1a and everything earlier remain usable unchanged.
