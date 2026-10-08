# CLAUDE.md — Claude Code Session Protocol

This file binds every Claude Code session in this repository.

**Project conventions live in [`AGENTS.md`](AGENTS.md)** (naming,
skill boundaries, canonical client state, determinism-first, eval
discipline, no-fabrication). Read it before creating or modifying any
Skill; do not duplicate its rules here.

**Phase evidence lives in `docs/production/`** (phase reports,
ADR-008..018, `DEFERRED_WORK.md`). Phase docs are the authoritative
record of what was done and verified.

## Project Identity & Architecture Guardrails

**This project is** a **Chat-first Insurance Agent Platform** for
ordinary insurance consumers (NOT a back-office system, dashboard
product, manual-review tool, or general chatbot). The binding product
contract is
[`docs/production/architecture/PRODUCT_VISION.md`](
docs/production/architecture/PRODUCT_VISION.md) (identity + User/
Operator/Developer space boundaries, FROZEN baseline v1.0); the
binding architecture rules are
[`docs/production/architecture/ARCHITECTURE_PRINCIPLES.md`](
docs/production/architecture/ARCHITECTURE_PRINCIPLES.md) (six frozen
principles: Chat is the Product Surface · Intent ≠ Prompt · Router
is Deterministic · Insurance Fact Requires Evidence · One Runtime ·
Human Review is Escalation). Legacy stubs at `docs/PROJECT_VISION.md`
/ `docs/ARCHITECTURE_PRINCIPLES.md` only redirect there.

### Product Alignment Check (before ANY task)

Answer before starting any non-trivial task:

1. **Does this feature ultimately serve the Chat UI?** If not, it
   must belong to Operator or Developer Space — say which.
2. **Which Space**: User / Operator / Developer?
3. **Does it add a new Agent / Router / Workflow / Artifact?** If
   yes: check the relevant ADR (docs/adr/ 001-007, docs/production/
   ADR-008..018 in force; ADR-019..024 PROPOSED — until approved
   their subject matter is design, not license) and the feature
   proposal template (`docs/templates/feature-proposal-template.md`).
4. **Drift** — does this reduce architecture drift or add to it?
   (Baseline: `docs/production/governance/product-direction-audit.md`
   — P0/P1/P2 list must converge, never grow.)

**If uncertain: STOP and request clarification** — do not guess the
product intent.

### Architecture Drift Detection (before code changes)

Before executing any code modification, inspect `git diff`. If the
touched files change **Runtime** — `orchestrator`, **agent
execution** (runtime/agent/, runtime/agents/, registry, router),
or **artifact lifecycle** (artifact registry, storage layout,
contracts) — you MUST flag: **"Architecture Impact Detected"**,
re-check the governing ADRs and principles, and either cite the
authorizing ADR/phase or pause for human decision before proceeding.

### Forbidden Actions (absolute, no silent exceptions)

Claude Code must never:

1. Create a new Agent Runtime (parallel execution model).
2. Create a new Workflow Engine (parallel orchestration).
3. Invoke an Agent bypassing the Router (once the Router is
   authoritative; during migration, follow the phase's shadow-mode
   rules).
4. Make a Prompt the source of business rules (intent truth lives
   in schema + rules + runtime events).
5. Create insurance facts without evidence (Catalog / WeKnora
   governed evidence only — no param-memory facts).
6. Expose Developer UI (dashboard, dev mode, raw ids/events) to
   the User Space.

### Before Large Features

Must inspect first:

- `docs/production/architecture/PRODUCT_VISION.md`
- `docs/production/architecture/ARCHITECTURE_PRINCIPLES.md`
- Existing ADRs (see Product Alignment Check #3)

Also honor `docs/DEVELOPMENT_CHECKLIST.md` (Step 0 product alignment
→ Step 1 architecture check → Step 2 implementation → Step 3
validation) for every phase, and fill
`docs/templates/feature-proposal-template.md` for any new feature.
Periodic drift re-check: `/product-audit`.

## Session & Context Management

Conversation is short-term memory. Project files are long-term
memory. Anything a future session needs MUST be persisted to project
files — never rely on conversation history.

### Session Boundary

One closed-loop feature task per Claude Code session. A closed-loop
task has: a clear objective, explicit scope, acceptance criteria, and
independent verifiability. Do not batch unrelated features into one
session.

### Session Start

At the start of a new session, read in this order — and nothing more
until the task requires it:

1. `CLAUDE.md` (this file)
2. `.agent/current-task.md`
3. `.agent/checkpoint.md`
4. The current phase document (pointer in checkpoint)
5. Only the ADRs directly relevant to the task

Do not scan the whole repository without purpose.

### Checkpoint Trigger

Update `.agent/checkpoint.md` when any of these happens:

- an important milestone completes
- an architecture decision is made
- the implementation strategy changes mid-debug
- a blocker is discovered
- the conversation context grows noticeably
- `/compact` is about to be executed
- the session is about to end

Keep the checkpoint concise: only what a future session truly needs.
No stale info, no debug logs, no conversation dumps. Important
decisions also go to `.agent/decisions.md`; decision records that
change architecture go further into an ADR.

### Context Pressure

When the conversation context grows large:

1. Stop accumulating unrelated conversation
2. Update `.agent/checkpoint.md`
3. Update `.agent/decisions.md` if a significant decision was made
4. Drop stale temporary context
5. Suggest `/compact`
6. Continue the current task after compaction

Never change the task goal because of context pressure. Do not run
`/compact` or `/clear` mechanically on a timer or token counter —
`/clear` is never executed automatically by project tooling.

### Task Completion

When the task is done:

1. Run the relevant tests / evals
2. Verify acceptance criteria
3. Update `.agent/checkpoint.md`
4. Update the relevant phase document
5. Update an ADR when warranted
6. Review `git diff`
7. Output a concise Session Handoff (template below)
8. Do not start the next unrelated task

Then recommend the user start a fresh Claude Code session.

### Session Handoff template

```
SESSION HANDOFF

Task:            ...
Status:          COMPLETE / BLOCKED / IN_PROGRESS
Completed:       - ...
Validation:      - ...
Important Decisions: - ...
Known Issues:    - ...
Remaining:       - ...
Next Recommended Action: ...
```

No large code dumps, no full debug logs.
