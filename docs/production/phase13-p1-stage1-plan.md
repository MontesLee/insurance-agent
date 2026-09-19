# Phase 13 P1 — Stage 1 Implementation Plan (Planning only — no code)

Date: 2026-09-19 · Baseline: P0 + P0.1 complete (370 runtime / 12
portfolio / 51-0-1 regression / 11-11 benchmark / all demos green).
Inputs: the full `docs/production/` audit trail + live code probes run
during this planning round (findings cited per item).

## 0. Stage 1 goal

> Give the single-node controlled pilot a reliable **real-client-data
> lifecycle foundation**: the data can be backed up, restored
> (verified), retained, and provably deleted — without touching any
> frozen runtime semantics.

---

## 1. Stage 1 Scope

### Included (2 items, evidence-selected)

| Item | P1 ref | Round-1 evidence |
| --- | --- | --- |
| **Item 1 — Backup / Restore tooling** | R-08 ("no backup tooling; real client data single-copy") | git grep found docs mentions only; live probe today confirms a project's durable surface = `project.json`, `case_state.json` (soon + `events.jsonl`/`checkpoints.jsonl` after activity) + the `projects.json` index entry, with **no copy/restore path anywhere** |
| **Item 2 — Retention policy + automated sweep + erasure audit** | Round-1 data audit ("no retention/erasure story") + final-gate P1 #3 | `delete_project` exists and is tested (probe today: 3 files + index entry removed under the R-01 lock), but nothing records a retention policy, nothing sweeps, and erasure leaves **no audit evidence** |

### Excluded (with reasons, from the audit backlog)

| Candidate | Why excluded from Stage 1 |
| --- | --- |
| Provider Policy Verification (R-05) | **Operation, not code** — see §2. The gate ships BLOCKED and stays BLOCKED; Stage 1 must not "solve" it by inventing evidence |
| Durable token/cost records (R-07) | Cost observability, not data lifecycle; independent of backup/retention |
| Insurance-report eval depth (R-10) | Quality, not data lifecycle |
| Deployment definition (R-11) | Operational hosting, orthogonal; sequenced after the data lifecycle exists |
| Case ownership granularity (final-gate #6) | Auth-model extension; roles already suffice for 1–3 trusted users |
| R-09 non-atomic writes | **Already fixed in the P0 round** (R-01 `atomic_write_json`); the register row predates it |

---

## 2. Special handling: R-05 Provider Policy is NOT a Stage 1 code item

Re-verified during this planning round (live probes): the official
policy/agreement URLs return 404 or a JS-rendered SPA shell — primary
text remains machine-unreachable. Per the brief (§6) and the audit
evidence rules:

- **Code**: done — the fail-closed gate (`runtime/agent/data_policy.py`)
  blocks real client data and opens only on the operator's explicit
  post-verification opt-in. No Stage 1 change.
- **Operation**: outstanding — the operator procedure is already
  documented in `provider-policy-verification.md` (read the policy in a
  browser, record quoted clauses + version + date, then set
  `INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1` for an acceptable
  provider only).
- Stage 1 does **not** mark R-05 resolved and does not gate its own
  acceptance on it: backup/retention are required for real data **when**
  the operator verification happens, with or before it.

---

## 3. Dependency graph (from actual code, not assumption)

```text
Encryption at rest (DONE — P0.1, mandatory in strict modes)
        │   backups copy ciphertext only BECAUSE data is encrypted;
        │   a pre-encryption backup tool would have copied plaintext
        ▼
Item 1a: backup   (locked snapshot copy of one project / whole root)
        │
        ▼
Item 1b: restore  (writes back under the R-01 locked index update;
        │           re-validates via the EXISTING checkpoint validation:
        │           schema + fingerprint + task→stage integrity)
        ▼
Item 2:  retention + sweep + erasure audit
        │   automated deletion is only safe AFTER a verified restore
        │   exists (delete-without-recoverable-backup is a data-loss
        │   hazard, not a lifecycle feature)
        ▼
(erasure audit log closes the loop: proof that deletion happened)
```

External to the graph: **R-05 operator verification** — parallel track,
no code dependency on either item.

### Ordering constraints (what cannot be done together)

- **Retention sweep must NOT ship in the same change as backup.** Why
  separate: a sweep that deletes on a schedule and a brand-new backup
  tool have opposite failure modes (one loses data, one must preserve
  it); shipping them together means a sweep bug could destroy the only
  copy before restore was ever exercised. Sequence: 1a → 1b → 2.
- **Restore must not bypass the final-review gate.** A restored project
  carries its `approvals.jsonl`; a restored-but-unapproved deliverable
  must land in `waiting_review`, not `completed`. Restore is a copy
  operation — it must not re-evaluate or re-approve anything.
- **Backup must not bypass encryption.** In strict modes the source is
  ciphertext; the tool copies bytes opaquely and never needs the key.
  (Restoring INTO a strict-mode root requires a key configured — same
  rule as any save.)

---

## 4. Item structures

### Item 1 — Backup / Restore (P1 R-08)

**Goal** — an operator can create a verifiable backup of a project (or
the whole harness root) and restore it — on the same single node — with
integrity checks and zero runtime-semantic change.

**Round 1 Evidence** — risk register R-08 (P1): "Real client data
single-copy"; git grep found backup mentions in docs only. Today's probe:
`delete_project` removes 3 files + index entry; nothing ever copies them
anywhere.

**Current State** — no backup/restore code. Persistence is per-project
JSON/JSONL + the shared `projects.json` index, written atomically under
`runtime/state/durable.py` locks (R-01). Case store may be
Fernet-encrypted (P0.1; ciphertext carries the `IA1:` magic).

**Why It Matters** — with real client data, a disk error or accidental
`delete_project` is unrecoverable. The pilot's data lifecycle starts at
"there is a second, verified copy".

**Scope**
- `backup_project(harness_root, project_id, dest)` — coherent snapshot
  of one project dir (including `.lock` exclusion) + its index entry,
  written under the R-01 `FileLock` so a concurrent save cannot tear the
  snapshot; manifest (file list + sizes + sha256 of each file + mode +
  timestamp); single archive file per backup.
- `backup_root(harness_root, dest)` — whole-root variant (index + every
  project).
- `restore_project(backup_file, harness_root)` — restores into the root:
  re-adds the index entry via `locked_update_json`; refuses to overwrite
  an existing live project unless the operator passes an explicit
  allow-overwrite flag; after copy, runs the EXISTING
  `checkpoint.validate` + `reg.verify` on the restored state and deletes
  the restore if validation fails (fail-closed restore).
- CLI entry (`python -m runtime.backup …`) for the operator; also usable
  programmatically.

**Non-Goals** — no remote/cloud targets; no scheduling/automation
(that's retention's sweep, and even that only sweeps deletion); no
cross-node consistency; no encryption-key management (key stays wherever
the operator keeps it; backups remain ciphertext blobs when the source
was encrypted); no dedup/incrementals.

**Dependencies** — R-01 locks (done), encryption-at-rest (done, P0.1 —
makes backups plaintext-safe by construction), `delete_project` (done,
used for fail-closed restore cleanup).

**Affected Components** — new module (e.g. `runtime/state/backup.py`) +
thin CLI; **no changes** to harness/scheduler/eval/approval/control
code. Uses existing `durable.FileLock`, `atomic_write_json`,
`locked_update_json`, `dataprotection` magic handling.

**Data Model Impact** — none (backup manifest is a new sidecar artifact,
not CaseState).

**API Impact** — none in Stage 1 (CLI only; an authenticated server
endpoint is a later, separate decision — deliberately excluded to keep
the attack surface unchanged this round).

**Runtime Semantic Impact** — **NONE**. Scheduler/Harness/Eval/Repair/
Replan/HITL/HOTL/MessageBus/A2A/Provenance untouched; restore only
writes files + one index row through the existing lock.

**Migration Impact** — none (reads current formats; plaintext legacy and
`IA1:` ciphertext both copied byte-for-byte).

**Security Impact** — backups inherit at-rest protection (ciphertext
copies; no key involvement). Restore into strict modes requires a
configured key (same as any save). Manifest hashes make tampering
detectable.

**Testing Strategy**
- *Positive*: backup of an active project → manifest lists every durable
  file with matching sha256; restore into a fresh root → project loads
  (`load_project`), state validates (`cp.validate`), index entry present
  under the lock; encrypted-root backup → backup file contains no
  plaintext PII (scan for synthetic markers).
- *Negative*: restore onto an existing live project without the overwrite
  flag → refused; tampered backup (flip one byte in one archived file /
  manifest hash mismatch) → restore refuses; restoring a truncated
  archive → refuses.
- *Failure/Recovery*: kill mid-backup → no partial backup accepted
  (manifest written last, atomically — a backup without a valid manifest
  is not a backup); restore whose post-copy validation fails → restored
  copy deleted, original (if any) untouched; concurrent save during
  backup → snapshot still coherent (R-01 lock).
- *Gate-specific*: a restored project that was `waiting_review`/unapproved
  is still `waiting_review` after restore (final review not bypassed).

**Regression Gates** — full battery (§6); specifically R-01 concurrency
suites, harness suites (index behavior), data-protection suites
(ciphertext handling), approval suites (restored gate state).

**Acceptance Criteria**
```text
PASS = backup+restore round-trips a project (plain + encrypted roots);
       manifests verify; tampered/truncated backups refused;
       restore refuses overwrite without flag; failed restore cleans up;
       restored unapproved deliverable still waits for review;
       370 runtime + 12 portfolio + 51-0-1 + 11/11 benchmark unchanged.
```

**Rollback Strategy** — delete the new module + CLI; nothing else
referenced them (no runtime wiring), so removal is a pure revert with
zero data-format impact.

**Risk** — low: pure additive tooling; worst case a refused restore
(fail-closed everywhere). Watch: Windows file-locked reads during
snapshot (mitigated by the R-01 lock discipline already in place).

**Estimated Complexity** — S/M (one module + CLI + 1 test suite; the
hard parts — locking, atomicity, validation — already exist and are
reused).

---

### Item 2 — Retention policy + automated sweep + erasure audit (data-audit P1)

**Goal** — projects past a retention window are provably purged; every
erasure leaves an audit record; nothing is deleted that has no verified
backup when the policy requires one first.

**Round 1 Evidence** — data audit: "no retention or deletion policy";
final-gate P1 #3 ("erasure primitive exists, tested" — i.e. exactly the
sweep + policy + audit layers are missing).

**Current State** — `delete_project` (R-04) performs complete erasure
(files + index under the R-01 lock) and is tested; projects carry
`created_at`/`updated_at`; nothing reads them for lifecycle decisions.

**Why It Matters** — real client data with no retention bound is a
standing privacy exposure (Round-1 R-04 finding); uncontrolled
auto-deletion without a backup-first rule is a data-loss hazard. Both
halves are needed for a defensible lifecycle.

**Scope**
- Retention policy declaration: per-root config (e.g. a small JSON in
  the harness root: max age in days for terminal projects; whether a
  verified backup is required before sweep; dry-run default ON).
- `sweep_expired(harness_root, now=None)` — enumerates projects, keeps
  non-terminal (any task not PASSED/COMPLETED/NEEDS_REVIEW/BLOCKED —
  never sweep an in-flight or review-gated project), applies the age
  window to terminal ones, and — per the policy — requires a successful
  `verify_backup` (Item 1's manifest check) before calling the existing
  `delete_project`.
- Erasure audit log: append-only `erasure.log` in the harness root
  (project_id, decision, reason, deleted file count, backup reference,
  actor/mode, timestamp) — written even for dry-run decisions; the log
  itself is never swept.
- CLI (`python -m runtime.retention sweep|--dry-run`), dry-run by
  default; actual deletion requires an explicit flag.

**Non-Goals** — no legal-hold machinery; no per-project custom policies;
no scheduled daemon (the operator runs the sweep; automation scheduling
belongs to the deployment item, R-11); no cross-root retention; no
deletion of the provider-side data (that is R-05's operator procedure).

**Dependencies** — Item 1 (backup + manifest verification MUST exist and
be acceptance-passed first); `delete_project` (done); R-01 index locking
(done).

**Affected Components** — new module (e.g. `runtime/state/retention.py`)
+ CLI; reuses `delete_project`, Item 1's `verify_backup`,
`load_project`/`list_projects`.

**Data Model Impact** — none to existing structures; adds the root-level
policy file + `erasure.log` (sidecars, not CaseState).

**API Impact** — none (CLI only; server endpoint deliberately out).

**Runtime Semantic Impact** — **NONE**. The sweep only ever acts on
terminal projects between runs; it never runs inside `run()`, never
touches the scheduler, and never deletes anything the harness would still
execute.

**Migration Impact** — none; absent policy file = no sweep (inert by
default, including in existing suites).

**Security Impact** — erasure audit strengthens the privacy story;
dry-run-by-default and the backup-first rule prevent the new tool from
becoming a data-loss vector; the audit log is append-only and records
the acting mode.

**Testing Strategy**
- *Positive*: policy + terminal project older than the window + verified
  backup → swept (files gone, index entry gone, `erasure.log` entry
  with reason + counts + backup ref); younger project → kept; dry-run →
  logged decision, nothing deleted.
- *Negative*: no policy file → sweep is a no-op (inert default);
  in-flight/review-gated project past the window → never swept; policy
  requires backup and none verified → deletion refused with an audit
  "refused" entry.
- *Failure/Recovery*: sweep interrupted mid-delete → index remains
  consistent (delete_project already locks); re-run completes; audit log
  survives (root sidecar, not project dir).
- *Gate interaction*: `waiting_review` projects never swept (protects the
  final-review gate from timing-out into deletion).

**Regression Gates** — full battery (§6); specifically harness/idempotency
suites (nothing swept under them — no policy configured), R-04
data-protection suites, R-01 suites.

**Acceptance Criteria**
```text
PASS = aged terminal project with verified backup swept + audited;
       aged project without required backup refused + audited;
       in-flight/review-gated never swept; dry-run deletes nothing;
       no-policy = inert; all regression baselines unchanged.
```

**Rollback Strategy** — remove the module/CLI/policy file; `delete_project`
and all data remain; `erasure.log` is inert history.

**Risk** — the inherent risk is "automation that deletes data":
mitigated by dry-run default, explicit-flag deletion, backup-first,
terminal-only, and the audit trail. Residual: operator misreads the
policy file — keep the schema tiny and fail-closed on malformed policy
(refuse to sweep on parse errors, log it).

**Estimated Complexity** — S (one module + CLI + 1 test suite; deletion
and locking are existing, tested primitives).

---

## 5. Runtime semantic impact summary (§15 of the brief)

```text
Scheduler · Harness · Persistence · Eval · Repair · Replan · HITL ·
HOTL · MessageBus · A2A · Provenance : NONE for both items.
Both items are operator tooling layered over the frozen persistence:
they read/write the same files through the existing R-01 locks and the
existing delete primitive. No core module is modified.
```

## 6. Regression baseline & expected blast radius

Baseline to hold: **370 runtime · 12 portfolio · 51/0/1 full regression
· 11/11 benchmark · compileall · demos green.**

Most-affected existing suites if Stage 1 is implemented (none should
fail — they are the watch list):
- `test_p0_r01_*` (index locking — restore writes index rows)
- `test_harness`, `test_cross_process_recovery` (project lifecycle)
- `test_p0_r04_*` (ciphertext handling in copies)
- `test_p0_r02` / approval suites (restored-state gate preservation)

Required regression suites (run per item, and full battery at the exit
gate): the four above + `pytest tests/runtime -q`, `tests/portfolio`,
`tmp/run_regression.py`, benchmark runner, compileall, all four demos.

## 7. STAGE 1 EXIT GATE

```text
All Stage 1 items implemented          (Items 1 and 2, in order 1a→1b→2)
All positive tests pass
All negative tests pass
All recovery tests pass
Phase 11 regression preserved          (benchmark 11/11, runtime suites)
Phase 12 regression preserved          (portfolio 12, demos exit 0)
No P0 introduced
No existing P0 reopened               (R-01..R-06 all still PASS)
No security bypass                     (backups ciphertext; restore validates)
No provenance regression              (fingerprints verified on restore)
No approval bypass                    (restored unapproved deliverables wait)
No data-policy bypass                 (R-05 gate untouched, still BLOCKED)
```

## 8. NEXT STAGE — NOT PLANNED YET

Stage 2 must be re-evaluated only after Stage 1 is implemented and has
passed this exit gate. Candidate backlog exists (R-07 cost records,
R-10 report eval depth, R-11 deployment, case ownership, R-05 operator
outcome) but **no Stage 2 planning is in this document**.

## 9. Stage 1 Recommendation

```text
READY TO IMPLEMENT
```

for Items 1 and 2 exactly as scoped (backup/restore, then
retention/sweep/audit — sequenced, not merged). This recommendation
covers Stage 1 only; it is NOT a production-ready verdict for Phase 13,
and R-05 remains BLOCKED on operator verification regardless of Stage 1.


---

## Item 1a implementation outcome (2026-09-19 — plan text above preserved)

Item 1a is implemented and acceptance-passed; see
`phase13-p1-item1a-backup-report.md`. Outcome summary: new
`runtime/state/backup.py` (+ CLI, no runtime wiring changes) with the
R-01-index-lock whole-snapshot strategy, quiescent-only backups
(RUNNING/mid-run → REJECTED), post-copy source re-hash consistency check
(fail-closed), per-file sha256 + ciphertext-magic manifest written last
via the existing atomic write, and a fail-closed `verify_backup`.
11 test sections / 50 checks green; regression 381 runtime / 12
portfolio / 51-0-1 / 11-11 benchmark / compileall / demos all green.
Item 1b (Restore) and Item 2 remain unplanned-for-implementation until
this outcome is human-reviewed.


---

## Item 1b implementation outcome (2026-09-19 — earlier text preserved)

Item 1b is implemented and acceptance-passed; see
`phase13-p1-item1b-restore-report.md`. Outcome summary: new
`runtime/state/restore.py` (+ CLI) — verify-first, whole-restore under
the R-01 index lock, staging directory with existing-validator
sanity (cp.validate per case dir, approvals shape), directory-swap atomic
commit with rollback, post-commit re-verification, and a minimal
restore.log audit (ids/reasons only). Restore ≠ Approve verified by four
dedicated negative tests. One additive R-01 fix shipped with 1b:
`durable.FileLock` re-entrancy (same-thread re-acquisition of the
index lock deadlocked; RLock + outermost-only OS lock, R-01 suites
re-verified). 9 test sections / 57 checks green; regression 390
runtime / 12 portfolio / 51-0-1 / 11-11 benchmark / compileall /
demos green. Item 2 and Stage 2 remain pending human review.


---

## Item 2 implementation outcome (2026-09-19 — earlier text preserved)

Item 2 is implemented and acceptance-passed; see
`phase13-p1-item2-retention-report.md`. Outcome summary: new
`runtime/state/retention.py` (+ CLI, `python -m runtime.state.retention`,
dry-run by default, `--execute` to delete) — per-root
`retention_policy.json` (absent = inert zero-side-effect no-op;
malformed = POLICY_INVALID fail-closed refusal, audited), terminal-only
sweep (task statuses {PASSED, PASS, COMPLETED, NEEDS_REVIEW, BLOCKED,
SKIPPED} + protected project statuses pending/running/paused/
waiting_review/waiting_approval never swept — the final-review gate
cannot time out into deletion), backup-first rule via Item 1a's
`verify_backup` (no/tampered/wrong-project backup → REFUSED + audited;
explicit policy opt-out), per-project decision + deletion under one hold
of the re-entrant R-01 index lock, and the append-only `erasure.log`
(ids/counts/reasons/mode only; logs dry-run decisions too; never swept).
Unknown `INSURANCE_AGENT_MODE` blocks the whole sweep (mode.py
fail-closed philosophy). 7 test sections / 93 checks green; regression
397 runtime (PATH python; workbuddy python lacks `cryptography` for the
eager-import P0/P1 suites) / 12 portfolio / 51-0-1 full regression /
42-42 benchmark / compileall / 4 demos green. Stage 1 exit gate: met
(see report §15). Stage 2 remains NOT planned.


---

## Final human review outcome (2026-09-19 — documentation-only closeout)

Read-only architecture/code review of the full Stage 1 (Items 1a / 1b /
2) re-verified every baseline independently (397 runtime / 12 portfolio /
51-0-1 regression / 42-42 benchmark / compileall / 4 demos exit 0) and
found zero BLOCKERs and zero runtime-boundary or security/governance
violations. Verdict:

```text
READY TO FREEZE WITH DOCUMENTED CONCERNS
```

Five findings (3 CONCERN/LOW + 2 INFO) were recorded verbatim as dated
addenda in the item reports' Known Limitations — F-01 (backup
approvals.jsonl consistency window; pre-existing ApprovalStore write
semantics) in the 1a report §11; F-02 (restore crash windows + operator
recovery principle; no silent corruption) in the 1b report §14; F-03
(sweep vs runner startup window; pre-existing delete_project semantics,
mitigation = no runs during sweep), F-04 (project-level `needs_review`
is sweepable by design) and F-05 (`max_age_days: 0` is a valid
aggressive policy) in the Item 2 report §13. No code, test or
configuration was changed for any finding — Stage 1 scope was not
expanded.
