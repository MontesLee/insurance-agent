# Design Decisions — why the runtime is shaped this way

> Interview-ready trade-off records. Format per decision:
> Problem · Decision · Reason · Trade-off · Current limitation.
> Full ADRs (7) live in [../adr/](../adr/).

### Why not one big agent?

**Problem:** a monolithic agent has no enforceable boundaries.
**Decision:** 4 specialists + 9 skills, each with its own contract and eval.
**Reason:** tool scope can be physically limited per agent; failures
localize; eval is per-artifact; work parallelizes.
**Trade-off:** more moving parts; needs orchestration (which became the
harness).
**Limitation:** assignment is a fixed registry mapping — dynamic team
composition is future work.

### Why a Planner (and not the agents deciding what to do next)?

**Problem:** agents choosing tasks = agents controlling the runtime.
**Decision:** a Planner emits a task graph; agents only execute nodes.
**Reason:** planning is reviewable/validatable as data; execution becomes
deterministic scheduling.
**Trade-off:** plans can be wrong — handled by validation + replanning,
not by trusting the model.
**Limitation:** replanning is bounded (budget 2) and trigger-deterministic.

### Why separate Planner and Harness?

**Problem:** whoever plans should not also grade execution.
**Decision:** Planner = WHAT (untrusted → validated), Harness = WHEN/
control (the only state authority).
**Reason:** single writer discipline; deterministic commits; testable
scheduling invariants.
**Trade-off:** replanning needs a controlled Harness→Planner round-trip
(implemented as a validated, revisioned operation).
**Limitation:** none material for a single-process runtime.

### Why can't agents modify runtime state?

**Problem:** concurrent agent writes corrupt CaseState/graph.
**Decision:** workers execute on deep-copied state; only the scheduler
thread commits (merge + eval + checkpoint, in graph order).
**Reason:** eliminates lost updates and id-collisions by construction;
artifact/eval ids become deterministic.
**Trade-off:** copy-merge cost per round; sequential commits.
**Limitation:** single-writer scales to one process — acceptable and
stated for this prototype.

### Why is Eval NOT inside the agent's tools?

**Problem:** self-grading invites false passes.
**Decision:** tools store artifacts (skip_eval); the harness is the only
eval owner; workers returning OK cannot produce PASS (tested).
**Reason:** quality authority must be independent of the producer — the
same reason code authors don't merge their own PRs.
**Trade-off:** an extra lifecycle step; repair re-runs the producer.
**Limitation:** eval rules are declarative files — good determinism,
limited expressiveness (no LLM-judge by design).

### Why an Artifact Registry?

**Problem:** "the model said so" is not an auditable result.
**Decision:** every result is a registered artifact (producer, inputs,
fingerprint, evidence refs); content lives once, metadata+lineage in the
registry.
**Reason:** answers "where did this recommendation come from?" without
re-running anything; fingerprint mismatches fail loudly.
**Trade-off:** write discipline (append/replace rules, freeze guards).
**Limitation:** per-type single artifact (repair replaces) — sufficient
for this pipeline shape.

### Why provenance?

**Problem:** recommendations must trace to evidence and catalog entries.
**Decision:** evidence artifacts keep document/chunk ids; eval checks
provenance resolvability; human input arrives as a `human-input` artifact
with source_type=human and append-only conflict records (FACT_CONFLICT),
never a direct CaseState overwrite.
**Reason:** trust in a regulated domain = traceability.
**Trade-off:** agents must carry references (ids only, no payload copies).
**Limitation:** demo knowledge base is local/fictional.

### Why replanning (and why bounded)?

**Problem:** a frozen plan can't survive a real run (blocked tasks,
unrecoverable failures).
**Decision:** deterministic triggers → planner → same validator →
immutable graph revisions with diffs; budget ≤ 2; identical-graph guard.
**Reason:** recovery without unbounded loops or graph anarchy; completed
work is never re-executed (idempotency).
**Trade-off:** no mid-round replanning (safe barriers only).
**Limitation:** reject stops replanning for the project (V0.1 semantics).

### Why are HITL and HOTL two different things?

**Problem:** "human in the loop" conflates gate-waiting with supervision.
**Decision:** HITL = approval gates at high-impact decisions
(WAITING_HUMAN); HOTL = supervision above the DAG (monitor → policy →
pause/notify/resume).
**Reason:** different UX, different state machines, different failure
modes; all-HITL makes humans bottlenecks, all-HOTL loses sign-off.
**Trade-off:** two control systems to keep consistent (approval keeps
priority over supervisor actions).
**Limitation:** approval UI is API-only; notifications are persisted
records (Feishu adapter is future work).

### Why is the scheduler local, not distributed?

**Problem:** distributed scheduling adds failure modes without proving
more agent competence.
**Decision:** single-process BSP scheduler, ThreadPoolExecutor, durable
JSON state.
**Reason:** for a portfolio prototype the value is the *semantics*
(barriers, isolation, determinism), which are easiest to verify — and
tamper-test — locally.
**Trade-off:** no horizontal scale.
**Limitation:** stated openly; state/event stores are the seam for a
future distributed version.

### Why no Redis/PostgreSQL/Kafka?

Same reasoning as above, plus reproducibility: JSONL + JSON files make
every run diffable, auditable and replayable in an interview — an
infra-backed version would hide exactly what this project demonstrates.

### Why is the product catalog a separate module?

**Problem:** product facts change independently of logic and are a
compliance surface.
**Decision:** versioned, effective-dated, explicitly `is_demo` catalog;
eval invariants reject any product not in it.
**Reason:** data lifecycle ≠ code lifecycle; makes "demo data" honest and
swap-to-real-catalog a config change.
**Trade-off:** catalog freshness is manual in this prototype.

### Why is insurance a Domain Adapter?

**Problem:** proving the runtime isn't insurance-flavored.
**Decision:** generic modules (scheduler/approval/control/state/eval
mechanics) are code-level domain-free; insurance lives in registries,
workflow, skills, contracts, catalog, knowledge — and a second
(software-engineering) adapter runs on the unchanged runtime.
**Reason:** generalization demonstrated, not claimed.
**Trade-off:** three friction points remain (CaseState schema executor
vocabulary, legacy TASK_DEFS fallback, reference-mode orchestrator path) —
recorded, deliberately not fixed.
