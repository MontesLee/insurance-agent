> 🌐 **Language:** 🇨🇳 [中文版](ADR-007-checkpoint-resume.zh-CN.md) · 🇺🇸 English

# ADR-007 · Checkpoint / Resume

## Context
An agent running a long chain (9 steps + possibly multiple repairs) gets interrupted: waiting for
the client to supply data, waiting for human review, the process being killed. Rerunning from
scratch on every interruption wastes work and repeats side effects (e.g. repeated retrieval).

## Decision
- **Checkpoint**: after each stage ends in OK/GATE/NEEDS_REVIEW, `run()` persists
  (`case_state.json` + a `checkpoints[]` entry).
- **Trust after validate**: `load()` runs 5 checks (file exists/parses, `case_id` matches, schema
  valid, registry fingerprints consistent, task→stage references complete);
  **any failure is `CHECKPOINT_INVALID` + a reason list — never silently resume from a corrupted
  state**.
- **Resume** reruns only tasks that are not PASS and **reports** any PASSed task that was rerun
  (normally empty).
- **Gates are real stopping points**: gate `stop` → `PAUSED_NEEDS_REVIEW`; `next_runnable` still
  points at the gated stage, **retries cannot bypass it** — an explicit `approve()` is required.

## Alternatives
- No persistence, memory only: everything is lost when the process dies.
- Persist but don't validate: silently resuming from a corrupted state produces wrong conclusions
  that are hard to spot.
- Make the gate a "suggestion": human review becomes meaningless.

## Why
Recoverability requires both "can resume" and "resume correctly". Validation is the precondition
of the latter; preconditions require the **producer stage to be `COMPLETED`** (not merely the
artifact to exist) — otherwise a stage parked at `NEEDS_REVIEW` cannot hold back downstream.

## Trade-offs
- Every checkpoint persists the full state; IO-heavy for large cases (acceptable at current
  scale).
- Strict validation will false-positive `CHECKPOINT_INVALID` on environment migration (e.g.
  absolute path changes); requires human intervention.
- Freezing + validation means "hand-edit the state and rerun" is not allowed; debugging must go
  through the proper repair path.
