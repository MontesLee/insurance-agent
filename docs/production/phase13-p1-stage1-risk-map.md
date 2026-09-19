# Stage 1 Risk Map (auxiliary to phase13-p1-stage1-plan.md)

Dependency-and-coupling analysis backing the plan's sequencing decisions.
Evidence sources: live probes run this round + the P0/P0.1 code.

## Dependency chains (verified against code)

```text
Encryption at rest (P0.1, done)
    └── makes backups plaintext-safe by construction
        └── Item 1a: backup (manifest + locked snapshot)
            └── Item 1b: restore (validation + locked index write)
                └── verify_backup (manifest + hash check)
                    └── Item 2: retention sweep (backup-first rule)
                        └── erasure audit log
```

External/parallel (no code dependency):
```text
R-05 provider-policy verification — operator action only;
gate stays BLOCKED; Stage 1 neither blocks on it nor resolves it
```

## Explicit "cannot do together" decisions

| Pair | Decision | Why |
| --- | --- | --- |
| Backup + retention sweep in one change | **Sequenced (1 → 2), never one change** | A sweep deletes on a policy; a fresh backup tool must preserve. Shipping together means a sweep bug can destroy the only copy before restore was ever exercised. Separate acceptance per item. |
| Restore + re-evaluation of approvals | **Never coupled** | Restore is a copy. Re-evaluating or auto-approving on restore would create an approval bypass (restored deliverable must land in `waiting_review`). |
| Backup + key handling | **Never coupled** | The tool must not know the key: strict-mode sources are ciphertext (`IA1:` magic); copying is opaque. Key involvement would widen the secret's exposure to a new code path. |
| Retention + in-flight projects | **Never** | Sweep acts on terminal projects only; deleting a RUNNING or `waiting_review` project would break scheduler/final-review invariants. Enforced by status filter + tests. |
| Provider verification + Stage 1 code | **Never** | Official policy is machine-unreachable (re-probed this round: 404/SPA); the audit rules forbid third-party evidence as the judgment. Any "automated verification" would be invented evidence. |

## Blast-radius watch list (if Stage 1 is implemented)

| Existing suite | Why it could feel this | Expected outcome |
| --- | --- | --- |
| `test_p0_r01_*` | restore writes index rows | pass (same `locked_update_json` path) |
| `test_harness`, `test_cross_process_recovery` | project lifecycle neighbors | pass (no lifecycle change) |
| `test_p0_r04_*` | ciphertext copy handling | pass (opaque byte copy) |
| `test_p0_r02` / approval suites | restored gate state | pass (copy-only restore) |
| Everything else | no shared code path | pass |

## New-risk register entries introduced by Stage 1 (to be added at implementation time)

| Risk | Severity | Mitigation (built into the plan) |
| --- | --- | --- |
| Backup contains ciphertext but operator loses the key | P2 (operator) | documented in backup output: "encrypted source; restore requires the same key" |
| Sweep runs with a malformed policy file | P2 | fail-closed: refuse to sweep, audit-log the parse error |
| Restore used to resurrect deleted-for-cause data | P2 | audit log records restore events too (add at implementation) |
| erasure.log grows unbounded | P3 | out of Stage 1 scope; noted for the deployment item |
