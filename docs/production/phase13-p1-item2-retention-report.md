# Phase 13 P1 Stage 1 / Item 2 — Retention / Sweep / Erasure-Audit Report

Date: 2026-09-19 · Scope: Item 2 ONLY (retention policy + automated
sweep + erasure audit). Stage 2, R-05 provider verification: DEFERRED /
BLOCKED as before.

## 1. Scope

Projects past a retention window are provably purged; every erasure
leaves an audit record; nothing is deleted that has no verified backup
when the policy requires one first — with zero runtime-semantic change
(deletion is the EXISTING R-04 `delete_project`; locking is the EXISTING
re-entrant R-01 index lock).

## 2. Actual Implementation

```text
NEW  runtime/state/retention.py  (load_policy + sweep_expired +
                                  _terminal_reason + _find_verified_backup +
                                  erasure-log audit + CLI)
NEW  tests/runtime/test_p1_retention.py  (7 sections, 93 checks)
No other runtime file touched (zero wiring — verified structurally
by a test: no runtime module imports the sweep).
```

## 3. Retention Policy (per-root `retention_policy.json`)

```json
{"schema_version": "1.0",
 "max_age_days": 90,
 "require_verified_backup": true,
 "backup_root": "backups"}
```

- **Absent file → INERT**: the sweep is a no-op with ZERO side effects —
  not even an `erasure.log` is created. Existing suites are unaffected
  by construction (they configure no policy).
- **Malformed → fail-closed**: unreadable JSON, wrong schema_version,
  missing/negative/non-numeric `max_age_days`, non-boolean
  `require_verified_backup`, or `backup_root` missing when backups are
  required → the ENTIRE sweep is refused (`POLICY_INVALID`, audited);
  the tool never guesses a window.
- `require_verified_backup` defaults to TRUE (the safe side);
  `backup_root` resolves relative to the harness root.

## 4. Sweep Decision Flow (as implemented)

```text
mode check            unknown INSURANCE_AGENT_MODE → SWEEP_REFUSED
                        (mode.py: never fall back on a typo)
  ↓
load_policy           absent → NO_POLICY (inert) / malformed → refuse
  ↓
for each project in the index (snapshot):
  R-01 FileLock(projects.json) held for decision AND deletion
  (re-entrant since Item 1b → delete_project's inner lock is safe)
    ↓
  loadable?            index entry w/o dir → KEEP "not loadable"
  terminal?            protected project status (pending / running /
                        paused / waiting_review / waiting_approval)
                        → KEEP; any task status outside
                        {PASSED, PASS, COMPLETED, NEEDS_REVIEW,
                        BLOCKED, SKIPPED} → KEEP (RUNNING/PENDING/
                        REPAIRING = in-flight; FAILED/FAIL = repair or
                        replan may revive it; unknown = never guess)
  aged?                updated_at (UTC) within window → KEEP;
                        unparsable timestamp → KEEP (fail-closed)
  backup-first?        policy requires → newest VALID verify_backup
                        for THIS project_id under backup_root, else
                        → REFUSED (audited; project survives)
  execute?             dry-run → SWEEP_PLANNED (nothing deleted);
                        execute → the EXISTING R-04 delete_project
                        (files + index entry) → SWEEP (file count +
                        backup reference recorded)
```

Terminality mapping note: the plan's task vocabulary
(PASSED/COMPLETED/NEEDS_REVIEW/BLOCKED) is enforced together with the
runtime's two actual vocabularies (harness `PASSED`/`BLOCKED`/… and
Step-3 `PASS`/`SKIPPED`); everything else — including FAILED and
unknown statuses — keeps the project.

## 5. Erasure Audit Log (`<root>/erasure.log`, append-only JSONL)

Every decision is recorded — including dry-run ones:

```json
{"sweep_id": "swp_…", "project_id": "proj_…", "decision": "SWEEP",
 "reason": "aged terminal project (40.2d), verified backup bkp_…",
 "files_deleted": 7, "backup_id": "bkp_…", "mode": "demo",
 "dry_run": false, "timestamp": "2026-09-19T…Z"}
```

Decisions: `SWEEP` / `SWEEP_PLANNED` / `REFUSED` (backup-first rule) /
`KEEP` (terminality / age / loadability) — plus run-level
`POLICY_INVALID` and `SWEEP_REFUSED`. Ids, counts, reasons and the
acting mode only: no case content, no case_id, no key material
(negative-tested by scanning the raw log). The log, the policy file and
the backups directory are root sidecars — the sweep never sweeps them,
and prior entries survive every later run (append-only, verified).

## 6. Backup-First Rule (Item 1 dependency)

A deletion is authorized only by a backup that passes Item 1a's
`verify_backup` RIGHT NOW, for THIS project_id (manifest + size +
sha256 + ciphertext-magic; no key involvement — hash-only checks). When
several valid backups exist, the newest (`created_at`) is recorded in
the audit entry. Tampered (byte-flipped), incomplete, or
other-project backups do NOT authorize deletion → `REFUSED` + audited.
`require_verified_backup: false` is the explicit policy opt-out
(positive-tested: sweeps without any backup — an operator decision,
recorded as such).

## 7. Gate Interaction (final-review protection)

`waiting_review` and `waiting_approval` project statuses are protected
 — the final-review gate cannot time out into deletion. NEEDS_REVIEW
tasks are terminal at task level by design (review-completed records),
while the project-level review/approval-waiting states stay
unsweepable. Negative-tested with a valid backup present.

## 8. Concurrency & Failure Safety

- Per-project decision + deletion happen under ONE hold of the R-01
  index lock (re-entrant since Item 1b). A concurrent save on another
  project serializes against the lock (positive-tested with a saver
  thread: aged project swept, concurrently-saved young project
  survives, index stays valid JSON).
- `delete_project` interruption semantics are the existing, tested R-04
  ones (rmtree + locked index removal); a re-run completes the sweep
  (verified: re-run on a swept root is a clean no-op, log intact).
- Unknown `INSURANCE_AGENT_MODE` BLOCKS the sweep before any decision
  (`SWEEP_REFUSED`, audited) — consistent with mode.py's
  never-fall-back-on-permissive-defaults rule.

## 9. Runtime Neutrality

Structural test: the retention module references no scheduler/eval/
approval internals, and NO runtime module imports it (walked every
runtime/*.py). Scheduler · Harness · Persistence · Eval · Repair ·
Replan · HITL · HOTL · MessageBus · A2A · Provenance: untouched. The
sweep never runs inside a run(); it acts only between runs.

## 10. CLI

`python -m runtime.state.retention <root> [--execute]` — dry-run by
default (prints SWEEP_PLANNED lines + summary); `--execute` is required
for actual deletion; exit 0 on SWEEP_RUN / NO_POLICY, 1 on
POLICY_INVALID / SWEEP_REFUSED. Subprocess-tested both ways, including
the inert policy-less root.

## 11. Test Sections (7 sections / 93 checks, all green)

```text
S1  policy loading      inert default · 8 malformed variants →
                        POLICY_INVALID + audited · valid minimal parse
S2  positive sweep      dry-run plans & deletes nothing · execute sweeps
                        exactly the aged one · young kept · audit fields
S3  terminality gates   5 task statuses + 5 project statuses never
                        swept · backed-up-but-RUNNING kept · genuinely
                        terminal variants swept · un-loadable kept
S4  backup-first        empty root / tampered / wrong-project → REFUSED
                        · newest valid backup recorded · opt-out sweeps
S5  audit discipline    JSONL shape · dry-run decisions logged ·
                        append-only · no content/key material · sidecars
                        survive · clean re-run
S6  recovery/conc/CLI   unknown mode blocks · concurrent saves ·
                        CLI dry-run/--execute/inert (subprocess)
S7  runtime neutrality  no banned references · no runtime imports
```

## 12. Regression Results

```text
pytest tests/runtime -q (PATH python 3.11) → 397 passed
                         (390 baseline + 7 retention tests)
pytest tests/portfolio -q                  → 12 passed
full regression (workbuddy python)         → 51 PASS / 0 FAIL /
                                             1 pre-existing INFRA_ERROR
                                             (step3-mutation GBK — known)
benchmark standalone                       → 42/42 ALL GREEN (11 cases)
compileall                                 → OK
demos basic(-m)/insurance/generalization/portfolio → all exit 0
```

(Interpreter note, recorded for the next round: the workbuddy python
lacks `cryptography`, so the eager-import P0/P1 pytest suites must run
under the PATH python; the workbuddy python remains the full-regression
runner, as before.)

## 13. Known Limitations

- Single node, operator-run; no scheduling daemon (R-11 deployment
  item), no legal-hold machinery, no per-project policy overrides —
  all deliberate non-goals from the plan.
- Backup freshness is not enforced: a verified backup older than the
  project's last update still authorizes deletion (the audit entry
  records the backup id, and the manifest's created_at is inspectable;
  tightening to backup-created_at ≥ project-updated_at is a Stage-2
  candidate if wanted).
- The erasure.log is append-only and unbounded (an operator hygiene
  concern, not a correctness one; it is never swept by design).
- Provider-side data deletion remains R-05's operator procedure — this
  tool only governs the local harness root.

### F-03 addendum (final human review, 2026-09-19) — sweep vs runner
### startup window

The per-project decision AND the deletion share one R-01 index-lock
hold (§8), so no *decide → release lock → mutate → delete* interleaving
exists. The residual window is runner STARTUP: a run() that has already
picked the project up in memory but has not yet performed its first
index-locked `_save()` — the sweep's locked re-load then still sees the
old terminal state, deletes the project, and the runner's subsequent
`_save()` partially re-creates the directory.

- This is the PRE-EXISTING `delete_project` / runner-startup semantics
  (a manual `delete_project` during run start has the same exposure) —
  NOT something Stage 1 / Item 2 introduced.
- Operational mitigation (required operator discipline): **do not start
  runs while a sweep is executing.** The age window also limits the
  blast radius (only long-idle terminal projects are ever targets).
- A real fix would need a dedicated runtime lifecycle design (runner
  startup persisting an in-flight marker before the sweep can see the
  project) — explicitly OUT of Stage 1 scope.

### F-04 addendum (final human review, 2026-09-19) — project-level
### `needs_review` IS sweepable (intentional)

Project status `needs_review` (set when a human REJECTS the final
review — harness.py `reject_final_review`) is NOT in the protected set.
It is a CONCLUDED, fail-closed outcome, not an in-flight approval
state; the protected open-flow states are `waiting_review` /
`waiting_approval`. Therefore a rejected-review project CAN be swept
once (terminal tasks + retention age + verified backup) are all
satisfied — with the usual REFUSED/KEEP/SWEEP audit trail. This is
intentional lifecycle semantics (the privacy retention bound applies to
dead-ended projects too), not a bug.

### F-05 addendum (final human review, 2026-09-19) — `max_age_days: 0`
### is a valid aggressive policy

`max_age_days = 0` passes validation and means: eligible terminal
projects enter the sweep decision IMMEDIATELY (no age grace). This is
an operator-chosen aggressive retention policy, not a misconfiguration
to reject — and even under it the other safeguards are unchanged:
dry-run remains the default, `--execute` is still required, and the
backup-first rule still applies.

## 14. Deferred Items

```text
Stage 2 — NOT planned (per plan §8; re-evaluate against the exit gate)
R-05   — provider-policy operator verification (gate still BLOCKED)
R-07 / R-10 / R-11 / case ownership — later stages
```

## 15. Stage 1 Exit Gate Assessment

```text
All Stage 1 items implemented (1a → 1b → 2, sequenced)   ✓
All positive / negative / recovery tests pass            ✓ (93/93)
Phase 11 regression preserved (benchmark, runtime)       ✓ (42/42, 397)
Phase 12 regression preserved (portfolio, demos)         ✓ (12, exit 0)
No P0 introduced                                         ✓ (zero wiring)
No existing P0 reopened (R-01..R-06 suites green)        ✓
No security bypass (backup-first, ciphertext untouched)  ✓
No provenance regression (no restore path involved)      ✓
No approval bypass (review-gated projects never swept)   ✓
No data-policy bypass (R-05 gate untouched, BLOCKED)     ✓
```

## 16. Acceptance Decision

```text
ITEM_2 = PASS
STAGE_1_EXIT_GATE = MET (pending human review of this report)
```

Rollback of Item 2 = delete `retention.py` + test (+ optionally the
policy file); Item 1a/1b and everything earlier remain usable
unchanged — the sweep is the top of the Stage-1 dependency chain and
nothing depends on it.
