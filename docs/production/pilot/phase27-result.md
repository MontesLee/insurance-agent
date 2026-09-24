# Phase 27 Result — Controlled Internal Pilot (Round 1)

Date: 2026-09-23 · Baseline phase26c-productionization-v1.0
(c7ed9c6) FROZEN — zero runtime/test/skill/knowledge/gateway
changes this phase. Deliverables under docs/production/pilot/.

## Status

```
CONTINUE PILOT
```

Reason: round 1 delivered the full machine-side evidence set (12
synthetic cases through the productionized path, 0 runtime
failures, 0 security events, 2 P1 findings recorded) — but the
human review dimension is still pending (12 ×
PENDING_HUMAN_REVIEW), and two P1 findings require an engineering
decision before the pilot can progress to a business-meaningful
round 2.

## Answers available so far (§29 subset — machine-observable only)

1. Reduced manual work? UNKNOWN (no manual baseline; artifact
   chains are complete and traceable for 10/12 cases).
2. Most common business issue: no primary recommendation ever
   (F27-02 — 12/12 including unmutated baseline).
3. Most common runtime issue: business-status conflation
   (F27-01 — 2/12 cases settle SUCCEEDED on WAITING_FOR_USER /
   NEEDS_REVIEW finals).
4. Most common knowledge issue: fixture-KB default (F27-04);
   empty-KB behavior itself is correctly fail-closed.
5. Recommendation reliability: NOT DEMONSTRABLE on the demo
   catalog (fail-closed everywhere — no fabricated output, but
   nothing to validate either).
6. Review time: UNKNOWN (human review pending).
7. LLM cost/case: UNKNOWN — 0 real LLM calls on this path
   (deterministic); nothing sent to any provider (policy gate
   stays BLOCKED per PA-26C5-P1-03).
8. Runtime problems: F27-01 (settle semantics).
9. Skill/Knowledge problems: F27-02 (catalog/evidence content),
   F27-03 (empty-requirement acceptance), F27-04 (KB source).
10. Not worth solving (yet): none identified — all findings map
    to concrete engineering areas.

## Problem → engineering mapping

| Finding | Category | Freq | Sev | Area | Next action |
|---|---|---|---|---|---|
| F27-01 business-final ≠ run-final | F12/F16 | 2/12 | P1 | Runtime (agent_runtime settle) | design result_status-aware settle (WAITING_FOR_USER/NEEDS_REVIEW → waiting/failed, never SUCCEEDED) — engineering phase |
| F27-02 no primary recommendation (incl. baseline) | F08/F10 | 12/12 | P1 | Product catalog + evidence content (NOT runtime) | populate production catalog/evidence or scope pilot to pre-recommendation stages |
| F27-03 empty requirements accepted | F03 | 1/12 | P2 | Skill/input validation | reject/park empty-requirement intake |
| F27-04 fixture-KB default | F07 | 12/12 | P3 | Pilot environment | wire live WeKnora KB for round 2 |

## Safety / security (round 1)

P0 = 0 · data leakage 0 · approval bypass 0 (no recommendation
was ever delivered without a gate; C08/C11 delivered NOTHING) ·
UNKNOWN→SUCCESS 0 (fail-closed held at knowledge/evidence layers)
· secrets 0 · budget/deadline enforcement observed active ·
auditability: every case traceable (run/task/budget/ops-audit +
per-case artifact chain + trace.jsonl).

## Regression (baseline untouched)

Runtime battery 596/0 (unchanged — pilot added docs/data/tools
only, no tracked code) · Portfolio 12/12 · Benchmark 42/42 ·
compileall targeted PASS.

## Exit decision

CONTINUE PILOT. Prerequisites for the next decision point:
(1) Owner completes the human-review packet (pilot-results.md);
(2) engineering decision on F27-01/F27-02 (fix cycle or scope
change). READY FOR EXTERNAL PILOT additionally requires the
PA-26C5 P1 gates (isolation, provider policy) — unchanged.
