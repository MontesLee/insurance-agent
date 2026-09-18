# Agent Developer / Agent Engineer — what I actually built

> For technical interviewers. Everything below maps to code in this repo and
> to tests that prove it. Claims → evidence table at the bottom.

Not "an AI insurance chatbot" — **a state-driven, long-running multi-agent
runtime**, with insurance as the first domain adapter.

## 1. Planner — WHAT should happen

- LLM plans are **untrusted**: strict JSON task-graph schema + a 10-check
  validator (unique ids, registry-only task types, dependency existence,
  Kahn cycle detection, entry/terminal tasks, reachability, transitive
  artifact contract, eval contract, field whitelisting). Invalid → bounded
  retry ≤ 2 → fail closed. (`runtime/planner/`)
- **Dynamic replanning (Phase 8)**: deterministic triggers (blocked
  dead-ends; repair-exhausted failures with dependents), ReplanContext
  construction, immutable graph revisions with parent lineage,
  machine-computed diff (added/removed/preserved/rerun/dep-changes),
  fingerprint-based no-change loop guard, bounded budget.
- Agents can never invoke the planner; humans can trigger replans only
  through the existing path.

## 2. Harness — WHEN / reliability (the runtime authority)

- Task lifecycle (PENDING→RUNNING→PASSED/NEEDS_REVIEW/BLOCKED/COMPLETED)
  with harness-only transitions; dependency barriers.
- **Bounded parallel DAG scheduler (Phase 7)**: BSP rounds, up to
  `max_concurrency` isolated workers on deep-copied CaseState, **the
  scheduler thread is the only state mutator** (graph-order commits →
  deterministic artifact/eval ids regardless of thread timing).
- Checkpoint per terminal task; cross-process resume; RUNNING→PENDING
  crash recovery; idempotent, audited control commands recovered after
  crashes. Safe barriers everywhere: no pause/replan mid-round, no worker
  killed mid-commit.

## 3. Multi-Agent

- Hand-curated Agent Registry (4 specialists) with deterministic
  task→agent mapping; per-agent tool scopes validated before execution.
- Specialist executor: bounded LLM loop (8 steps), schema-validated tool
  calls, artifact-contract output check, returns ARTIFACT_READY — never
  PASS.
- **A2A MessageBus (Phase 6)**: persistent, idempotent, fail-closed
  message validation (sender/target/type/artifact refs), communication
  policy (who may talk to whom), ACK-only-after-PASS handoff lifecycle.
  The bus never schedules anything.

## 4. Reliability

- **Eval is harness-owned** (`runtime/eval_engine.py`): 7 deterministic
  check families (schema, required fields, non-empty, contamination,
  provenance, cross-artifact, catalog invariants) driven entirely by rule
  files. Bounded repair ≤ 2 (3 executions), then NEEDS_REVIEW.
- **Fail-closed everywhere**: empty knowledge → no fabricated evidence;
  agent outage → needs_review, no silent fallback; worker exceptions fail
  one task, never the run.
- Artifact registry: sequential deterministic ids, sha256 fingerprints
  (mutation → loud CHECKPOINT_INVALID), lineage back to client facts.

## 5. Runtime control

- **HITL (Phase 9)**: approval gateway — PENDING→WAITING_HUMAN→
  APPROVED→RESUMED / REJECTED / EXPIRED, actor allowlist (human only),
  unapproved graphs can never activate.
- **HOTL (Phase 10)**: deterministic RuntimeMonitor (9 signal types,
  fingerprint dedup, alert lifecycle) → deterministic InterventionPolicy
  (LOW→NONE … CRITICAL→PAUSE) → audited idempotent commands (pause at safe
  barriers, resume with alert acknowledgment, validated retry, fail-closed
  cancel, replan through Phase 8).

## 6. Evaluation of the runtime itself

Deterministic benchmark (11 cases: happy path, missing info, knowledge/
product failures, repair exhaustion, replanning, parallel equivalence,
HITL, HOTL notify/pause, 4-agent golden), 18-row fault-injection matrix,
adversarial false-pass suite (count 0), tamper testing (breaking the
runtime breaks the benchmark), parallel consistency (concurrency 1 vs 2
semantically identical incl. artifact ids), 3× determinism.

## 7. Generalization

Same runtime, second domain: a software-engineering workflow (requirement
→ risk → solution → implementation plan → test plan) completes with 5/5
tasks, 5/5 evals, verified lineage — via a ~40-line declarative domain
adapter. Zero runtime fork. `demos/demo_generalization.py`.

## Claims → evidence

| Claim | Evidence |
| --- | --- |
| Agents never self-PASS | `tests/runtime/test_eval_boundary.py`, `test_parallel_scheduler.py::test_t9b`, failure-injection F18 |
| Scheduler is sole writer; deterministic commits | Phase-7 suite T13/T20 (identical artifact ids across runs) |
| Replanning preserves completed work | `tests/runtime/test_dynamic_replanning.py` T9 |
| Approval gateway fail-closed | `tests/runtime/test_approval.py` (T5–T12) |
| Pause only at safe barriers | `tests/runtime/test_human_on_loop.py` T17/T18 (in-flight parallel pause) |
| Benchmark exercises the real runtime | Phase-11 audit: instrumented real-runtime calls + 6 tamper probes each flip the benchmark to FAIL |
| Generalization demonstrated | `demos/demo_generalization.py` + `tests/portfolio/test_demo_generalization.py` (no-fork + real-scheduler probe) |
