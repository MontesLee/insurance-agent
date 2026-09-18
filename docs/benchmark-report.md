# Phase 11 Benchmark Report

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](benchmark-report.zh-CN.md)

Reproduce with: `python -m evals.benchmark.runner` (deterministic; no LLM).

## 1. Test environment

Windows 11 · Python 3.11 · single process, ThreadPoolExecutor bounded
parallelism, JSON-file persistence. No Redis/Postgres/Kafka/K8s anywhere.

## 2. Benchmark cases (evals/benchmark/cases, schema-validated)

| Case | Category | Scenario | Result |
| --- | --- | --- | --- |
| B001 | happy path | full advisory chain, 4 agents, artifacts+lineage+checkpoints | **PASS** (completed) |
| B002 | missing information | intake agent refuses to fabricate a profile | **PASS** (needs_review, no client-profile artifact) |
| B003 | knowledge failure | empty knowledge → no fabricated evidence, downstream blocked | **PASS** (needs_review) |
| B004 | product failure | no candidates → replan drops product, honest degradation | **PASS** (completed, no product-candidates artifact) |
| B005 | repair exhaustion | invalid product_id ×N → exactly 3 evals / 2 repairs → NEEDS_REVIEW | **PASS** |
| B006 | replanning | blocked path → v1→v2, immutable previous revision | **PASS** |
| B007 | parallel | true-parallel DAG, artifacts+ids deterministic, `task_scheduled` observed | **PASS** |
| B008 | HITL | high-impact replan → WAITING_HUMAN → approve → resume → completed | **PASS** |
| B009 | HOTL notify | failure → signals → NOTIFY → run continues autonomously | **PASS** |
| B010 | HOTL pause | budget exhausted → HIGH → PAUSE at barrier → RESUME → terminal | **PASS** |
| B011 | golden | four-agent parallel golden run with full audit trail | **PASS** |

**benchmark_pass_rate = 1.0 (11/11)**

## 3. Failure injection (matrix F01–F18, all PASS)

Planner invalid JSON/graph → bounded retry ≤ 2 (F01/F02) · agent tool
failure → no fabricated artifact (F03) · knowledge empty → fail closed
(F04) · invalid product → catalog invariant FAIL (F05) · repair exhausted
→ exactly 2 repairs (F06) · task blocked → BLOCKED/replan (F07) · replan
no-change → stop (F08) · replan exhausted → NEEDS_REVIEW (F09) · approval
rejected → fail closed, v1 stays active (F10) · HOTL pause at safe
barrier, no mid-commit kill (F11) · crash during PAUSE → idempotent
recovery, applied once (F12) · crash during RESUME → recovered and
completed (F13) · duplicate command → idempotent no-op (F14) ·
unauthorized actor → rejected by allowlist (F15) · invalid A2A target →
AGENT_MISMATCH (F16) · invalid artifact reference → ARTIFACT_NOT_FOUND
(F17) · forged worker OK → no self-PASS (F18).

## 4. False-pass testing — `false_pass_count = 0`

Bad/empty artifacts, product-contaminated analysis, fingerprint-mutated
registry entries, invalid product ids, unknown task types, duplicate
task ids, dependency cycles, removed-dependency references, wrong/unknown
agents, policy-denied A2A targets, unknown message types, unauthorized
commands, retry of unknown/terminal-ok tasks, forged worker OK —
**every one refused** (`tests/runtime/test_false_pass.py`).

## 5. Parallel consistency — rate 1.0

B007 and B011 at `max_concurrency=1` vs `2`: identical task terminal
states, identical artifact types **and sequential artifact ids**,
identical graph revision, identical eval verdicts per artifact type.
(Sequential mode legitimately records extra eval rows for stage-tool
artifacts — the harness eval plus the stage runner's internal one;
parallel workers discard the copy's — verdicts are identical, documented
Phase-7 asymmetry.)

## 6. Replanning

B004/B006: revision 2 accepted with recorded diff; revision 1 snapshot
immutable; removed tasks never fake success; preserved terminal-ok tasks
never re-executed; artifacts survive the swap (registry verify PASS).

## 7. HITL

B008 full lifecycle (request → waiting → approve → Harness resume →
completed); F10 rejection path (fail closed, no alternative graph
generated, replanning stopped for the project).

## 8. HOTL

B009 autonomous-continue under notification (the human is not a workflow
blocker); B010 supervisor pause at a safe barrier + resume; retry
validated and never duplicating completed work (Phase-10 suite T21/T22).

## 9. Crash recovery

Crash while paused → restart executes nothing until RESUME; crash during
PAUSE/RESUME/REPLAN commands → idempotent recovery, each applied exactly
once (F12/F13 + Phase-10 suite T28–T31).

## 10. Provenance

`artifact_lineage_errors = 0`, `provenance_errors = 0` across every case:
registry fingerprints verify, lineage resolves, every artifact carries
producer + provenance; human-input artifacts carry `source_type=human`.

## 11. Determinism

Golden case B011 run 3×: identical task statuses, identical artifact ids
(deterministic commit order), identical eval verdicts, identical
revision. Distinguished explicitly: **semantic determinism** (verified)
vs **runtime metadata variance** (timestamps, event uuids, thread order —
not compared).

## 12. Real LLM smoke

Deterministic acceptance never invokes an LLM. Real-GLM behaviour remains
covered by the pre-existing suites (`evals/agent-benchmark` 33 cases,
`python -m runtime.agent.smoke_test`) and is deliberately excluded from
these contracts — LLM wording variance may not change deterministic
expectations.

## 13. Known limitations

Benchmark scripts are declarative fixtures (deterministic provider
scripts), not free-form natural language; the four-agent golden case has
no A2A messages on the happy path (handoff coverage lives in the Phase 6
suites); `SIGNAL_LONG_RUNNING` reads wall-clock; no token accounting
(budgets are task/replan/repair counts); no external notification
channel (Feishu is a future adapter).

## 14. Final acceptance

```
Benchmark cases: 11/11 PASS      Failure injection: 18/18 PASS
False-pass:      count 0         Parallel consistency: 1.0
Replanning: PASS                 HITL: PASS            HOTL: PASS
Crash recovery: PASS             Provenance: 0 errors  Determinism: PASS
Hard gates: all 0
```
