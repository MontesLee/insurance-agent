# Phase 26A + 26B — Independent Principal Engineer Gate Review

Date: 2026-09-21 · Read-only adversarial review. Probes:
tmp/rev26/adversarial_probes.py (10/10, never committed). No tracked
file modified; nothing committed.

```
==================================================
PHASE 26A + 26B
INDEPENDENT PRINCIPAL ENGINEER GATE REVIEW
==================================================

Baseline:      59bb76f (25.1) → 8eb3007 (26A) → 7ac15aa (26B)
Reviewed:      7ac15aa (HEAD)
Working Tree:  CLEAN (this report + tmp/rev26/ are the only additions)
```

## ACTUAL_RUNTIME_ARCHITECTURE (from code, not docs)

1. Task creation — ANY process with DB access via
   `TaskQueueStore.enqueue` (26B agent path: the test/composition
   layer enqueues one `agent-run` task; no server wiring yet — the
   queue is not behind the HTTP API in this phase).
2. Claim — `TaskQueueStore.claim`: ONE SQL statement
   (UPDATE...WHERE task_id=(SELECT...FOR UPDATE SKIP LOCKED)) on a
   psycopg2 default-transaction connection (commit at with-block
   exit). No SELECT→Python→UPDATE window exists.
3. Lease — generated INSIDE that statement (`lease_id` param bound
   before execution; unguessable 20-hex). 4. Attempt — incremented in
   the same statement (`attempt = attempt + 1`). 5. Agent execution —
   `AgentTaskWorker._execute` → `make_agent_executor`'s closure →
   `orchestrator.seed_case/run/resume` (business core unchanged).
   6. Checkpoints — the orchestrator (existing machinery) into
   `run_root/attempt-N/`; attempt dirs chosen from the CLAIMED row's
   attempt (a stale worker structurally cannot write a newer dir).
   7. Artifacts — existing case-state persistence (per-attempt dir +
   PG artifacts table on the cutover path). 8. Terminal state —
   `store.succeed/fail` CAS (status+lease+expiry). 9. Retry —
   `fail(retry=True)` requeues while attempt<max_attempts (bounded).
   10. "Completed" — only the SUCCEEDED row (idempotency key
   task#attempt; duplicates are no-ops). 11. Cancel —
   `QueueOps.cancel` (OWNER/OPERATOR, audited). 12. Approve —
   `QueueOps.approve_and_resume` (OWNER/REVIEWER/OPERATOR; marker
   bound to project/run/task/stage). 13. Recovery —
   `recover_expired()` requeues expired LEASED/RUNNING (claims also
   pick up expired leases directly).

PostgreSQL Authority: **PASS** — task state, lease, attempt,
terminal, ops audit all live in PG; the filesystem holds only
checkpoint/artifact payloads, markers and logs (never task state).

## Core audit results

Transaction Boundary: **PASS** — claim is a single
statement-in-transaction; all other mutations are single CAS
statements; psycopg2 default isolation (read committed) suffices
because every correctness argument rests on row locks + CAS, not on
read staleness. Two processes cannot both lease one task: the SKIP
LOCKED subquery takes the row lock inside the UPDATE's own
transaction; the second process skips the locked row (probed: 4-way
race one winner; locked-row skip fast).

Concurrent Claim: PASS · Stale Worker: **PASS** (ADV-1: ALL four
write kinds rejected post-expiry; current owner settles after the
attack). Checkpoint: **PASS** (ADV-4: a deliberately late attempt-1
write cannot poison the newest-first lineage; attempt dir = claimed
row's attempt → stale workers write only their superseded dir).
Artifact Idempotency: **PASS** (single terminal result per task,
DUPLICATE_SUCCESS no-op; per-attempt artifact files are lineage, not
competing results — the queue row is the one business result).
Duplicate Execution: PASS (bounded re-execution, deterministic
skills). Crash Recovery: PASS (C1–C7 matrix; durable/lost/retried
per point: PG row durable at each CAS; only in-flight compute is
lost; re-execution is checkpoint-truncated). Retry: **PASS with
finding** — bounded product, see F-26R-P3-02: worst case per
provider-timeout = TaskAttempts(≤3) × SkillExecutions(1+2 repairs)
× LLMCalls(1+2 retries) = 27; provider layer has no retry (×1).

HITL: **PASS with finding** — defer→marker→requeue→resume verified
incl. REAL races (200-round cancel/succeed: one winner, never both;
approval binding matrix: cross-task/stage/run/decision all rejected).
Race answers: A two-worker resume — impossible before approval (not
claimable while FAILED); after requeue exactly one claim wins (CAS).
B duplicate approval — approve on non-waiting task refused (status
check hardened); idempotent requeue refused for non-FAILED. C old
approval/new attempt — marker is stage+task+run bound; consumed by
the lineage that paused at that stage; a consumed-then-crashed
lineage may re-consume the same stage approval after checkpoint
rollback → bounded re-execution of subsequent stages (at-least-once;
same deterministic outputs) — INFO-02. D approval after CANCEL —
refused (status≠FAILED). E attempt change — markers are not
attempt-bound; binding is (task, run, stage): safe for the same
logical gate, cannot cross tasks.

Cancel: PASS (RBAC before mutation; CAS makes cancel-vs-complete
exactly-one-winner; cancelled tasks can never settle — probed 200
rounds + suite). Multi-process: **PASS** — ADV-5: two REAL OS
processes ran the REAL agent pipeline (each COMPLETED once, distinct
process-lifecycle worker ids); 26A suite separately proved 3×12 and
5×50 real-process queue contention.

Business Invariance: **PASS_WITH_CONCERNS** — the oracle shares the
business core with the implementation (direct path and worker path
both call orch.seed/run): it proves EXECUTION EQUIVALENCE (worker
wrapper changes nothing), NOT distributed correctness — which rests
on the separate lease/crash/race suites and this review's probes.
The result doc's claim (artifact deep-equality) is accurate for
equivalence; the concern is scope-of-proof, not a defect.

Knowledge/Evidence/Provenance/LLM Gateway: **PASS** — agent_runtime
imports orchestrator only; empty-KB case stays fail-closed through
the queue; zero gateway/governance diffs (git diff 8eb3007..7ac15aa
confined to runtime/queue + tests + docs).

Security: PASS — lease is the sole write credential (possession =
authority; unguessable by construction — worker identity fields are
informational, F-26R-INFO-01); permission checks precede mutations
(ops layer); cancelled/stale/foreign writes rejected (probed).

## Test independence

Critical Test Circularity: **CONCERNS** (not MATERIAL) — (a) the
invariance oracle shares the business core (inherent to the claim it
makes); (b) E26-01 asserts literal transition pairs against
model.TRANSITIONS (a real table-vs-literal oracle: editing the table
to legalize an illegal pair fails the test) — acceptable; (c) the
mutation checks are partly structural (SQL text) + partly behavioral
(forged-lease, auth-bypass, terminal-reclaim races) — the behavioral
ones are the load-bearing ones and are independent.
Mutation Quality: PASS (behavioral mutations attack real guards).
Oracle Quality: PASS with the invariance caveat above.
Multi-process Test Authenticity: PASS (subprocess.Popen + fresh
connections per process; agent-path real-process case now ALSO
covered by this review's ADV-5 — the committed suite uses threads
there, noted as INFO-04).
Failure Injection Quality: PASS (dead-DB, mid-statement loss —
no fabricated outcomes; OutcomeUnknown surfaces RECOVERY_REQUIRED;
claim-side commit-unknown is safe-direction: a phantom lease simply
expires).

## Observability

Trace / Worker / Attempt / Lease identity: PASS (context adoption to
knowledge/LLM records; task.* records carry the full set; join on
task_id). Crash Localizability: **PASS with gap** —
F-26R-P3-01: `recover_expired()` emits NO structured log (recovery
visible only in the DB); checkpoint saves likewise log only into the
case trace, not the worker log. Neither breaks correctness; both
weaken "which worker recovered what" answers.

## Findings

F-26R-P2-01 | HITL approval markers are filesystem-scoped →
multi-HOST workers would see divergent approval state. The runtime is
de-facto a SINGLE-HOST distributed-process model (shared run_root),
not a multi-host production model. Location: ops._write_marker /
agent_runtime._read_approval. Exploit: two hosts → approval on host A
never resumes on host B (stuck WAITING) or diverges. Mitigation
today: single-host scope is the stated deployment boundary.
Recommendation: move markers to PG in 26C. Blocking: NO (26C is
single-host by design until then).

F-26R-P2-02 | Business-invariance oracle shares the business core
with the SUT → proves execution equivalence only (see G9/G10).
Recommendation: keep crash/lease suites as the distributed oracle;
state the equivalence-scope in the result doc. Blocking: NO.

F-26R-P3-01 | recover_expired / checkpoint-save emit no structured
observability events. Recommendation: obs emission at recovery +
checkpoint in 26C. Blocking: NO.

F-26R-P3-02 | AGENT_WORKER_RUNTIME.md says "no multiplication" for
retry layering; the true statement is a BOUNDED PRODUCT (≤27 calls
worst case). Documentation fix. Blocking: NO.

F-26R-P3-03 | store.cancel remains DB-access-open beneath the ops
RBAC layer (any process with DB credentials can cancel); acceptable
at the current trust boundary, must be revisited for multi-party
operation. Blocking: NO.

V-26V-P3-01 | (found by the completion verification 2026-09-22 —
NOT by this original review; provenance: verification) Worker
concurrency backpressure: Phase 26A implements max_concurrent_tasks
/ at_capacity (worker.py), but this gate review did not audit the
capability and tests/ contains no dedicated backpressure coverage.
Impact: low blast radius (worker-local reliability control); no
evidence it compromises queue atomicity, lease correctness,
stale-worker protection, checkpoint safety, artifact idempotency,
HITL security, or PG task authority. Disposition: non-blocking
documented debt → Phase 26C (audit semantics + add deterministic
backpressure coverage). Status: CLOSED 2026-09-22 by Phase 26C-1
(audited semantics, real check-then-act bug fixed F-26C1-P2-01,
deterministic suite 12/12 + 80/80 checks incl. real-process crash
and mutation kills — see PHASE_26C1_RESULT.md).

F-26R-INFO-01 | lease_id is the sole write credential; worker
identity columns are informational (by design).
F-26R-INFO-02 | a consumed approval can be re-consumed after
checkpoint rollback (bounded, deterministic re-execution).
F-26R-INFO-03 | commit-unknown on claim is safe-direction; on settle
it surfaces RECOVERY_REQUIRED with no auto-reconciler (lease expiry
eventually resolves; operator runbook step).
F-26R-INFO-04 | committed agent-path concurrency tests use threads;
real-process agent execution is proven by THIS review's ADV-5 (not
yet in the suite).

P0: 0 · P1: 0 · P2: 2 · P3: 4 · INFO: 4
(P3 = 3 original review findings + V-26V-P3-01 from the completion
verification)

## Regression

Review battery: first pass 537 passed + 3 FAILED — the 3 failures
were CAUSED BY THIS REVIEW (adversarial probes ran concurrently
against the same PostgreSQL; probe residue was claimed by unfiltered
test claims). Residue purged → the 3 tests pass in isolation
(3/3, 4.5s). A clean uncontaminated full battery was re-run for the
final numbers:

```
Runtime:     540 passed / 0 failed (5:56)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
```

Final numbers independently re-confirmed by the completion
verification (2026-09-22): full battery re-run 540 passed / 0
failed — interpreter PATH python 3.11.8 (psycopg2 2.9.11);
PostgreSQL agent-postgres 127.0.0.1:5433; WeKnora available.

Historical regression (git diff 8eb3007..7ac15aa): only
additions to runtime/queue (task_types ctor param + requeue method —
no semantic change to 26A paths) + new tests + docs. No removed or
weakened assertions anywhere. Scope integrity: zero
skills/knowledge/governance/evidence/provenance/gateway/catalog
changes — CLEAN.

## KEY QUESTIONS

1. 26A genuinely proves distributed queue correctness? YES —
single-statement SKIP LOCKED claim proven at SQL level + real-process
contention (3×12, 5×50) + this review's races.
2. 26B genuinely proves agent worker integration? YES — real
pipeline through the queue incl. real multi-process (ADV-5), HITL
hand-back, checkpoint resume; with the equivalence-vs-distributed
scope separation respected.
3. Checkpoint recovery actually safe? YES — attempt-dir isolation is
structural (dir = claimed attempt); late-write poisoning probed and
rejected; no rollback path exists (loads only go to older-or-equal
lineage).
4. Can stale workers mutate? NO — all four write kinds rejected
post-expiry (probed); lease columns on FAILED rows are inert.
5. Duplicate execution → duplicate business artifacts? NO — one
terminal result per task (CAS + duplicate no-op); artifact files per
attempt are lineage history; the task row is the business result.
6. HITL safe under races? YES (single-host) — approval binding
matrix + status machine refuse every cross-application; multi-host
divergence documented as P2.
7. Cancel safe under races? YES — 200-round interleavings: exactly
one winner, never both effects; cancelled tasks never complete.
8. Business invariance independently meaningful? AS EQUIVALENCE,
yes; as distributed correctness, no — that load is carried by the
lease/crash/race suites (PASS_WITH_CONCERNS).
9. Tests circular anywhere materially? NO — CONCERNS only
(invariance oracle shares the business core; state-machine test uses
literal-pair oracle).
10. PostgreSQL the sole task authority? YES — every task-state
transition is a PG CAS; files never gate correctness.

## EXECUTION SEMANTICS

At-least-once: PASS · Idempotent completion: PASS · Stale-lease
rejection: PASS · Checkpoint recovery: PASS ·
Exactly-once: NOT CLAIMED (and none of the components secretly
depend on it — searched).

## FINAL GATE

G1 PASS · G2 PASS · G3 PASS · G4 PASS · G5 PASS · G6 PASS · G7 PASS
· G8 PASS · G9 PASS_WITH_CONCERNS · G10 CONCERNS · G11 PASS ·
G12 PASS · G13 PASS · G14 **YES_WITH_CONCERNS** (single-host
deployment boundary + equivalence-scope caveat — both documented and
non-blocking for a single-host 26C).

## FINAL STATUS

```
READY_FOR_PHASE_26C_WITH_DOCUMENTED_DEBT
```

STOP: YES — no fixes applied, no Phase 26C started, repository
untouched (this report is the only addition).

## Review Closure

Following the independent completion verification on 2026-09-22
(verdict: REVIEW_COMPLETION_CONFIRMED_WITH_GAPS), this report was
closed out with documentation-only fixes:

1. Retry finding citation corrected from F-26R-P3-03 to
   F-26R-P3-02 (F-26R-P3-02 = retry multiplication documentation;
   F-26R-P3-03 = store.cancel DB-access trust boundary — contents,
   severities and numbering of all original findings unchanged).
2. Final independent regression result recorded as 540 passed /
   0 failed (replacing the unfilled clean-battery placeholder;
   verification date 2026-09-22, PATH python 3.11.8,
   agent-postgres :5433, WeKnora available).
3. V-26V-P3-01 registered as a non-blocking P3 documented debt
   for Phase 26C (provenance: completion verification, not this
   review). [Update 2026-09-22: CLOSED by Phase 26C-1 — audit,
   atomic-reservation fix, deterministic coverage; see
   PHASE_26C1_RESULT.md.]

No runtime, business logic, queue semantics, or production
capability was changed as part of this closure.

Phase 26A and Phase 26B remain frozen.

Final Findings: P0 = 0 · P1 = 0 · P2 = 2 · P3 = 4 · INFO = 4

Final Gate Review Status:
READY_FOR_PHASE_26C_WITH_DOCUMENTED_DEBT
