# Phase 13 Round 1 — Production Readiness Audit

Date: 2026-09-19 · Scope: small-scale real production (owner + 1–3 trusted
users, real cases, human review before delivery, single node) · Audit
only — no code, tests, or behavior modified.

## 1. Executive Summary

The runtime's *semantic* core is production-credible for this scope:
planning, scheduling, eval, repair, replanning, checkpoints, recovery,
provenance and audit are deterministic, adversarially tested (326 tests,
11/11 benchmark, 18/18 fault injections, false-pass 0), and were
re-verified live during this audit. What stands between this system and
even a small real pilot is concentrated in five areas: **one measured
concurrency defect in durable state (R-01)**, **the absent human-review
gate on the final deliverable (R-02)**, **product-data governance below
real-recommendation grade (R-03)**, **client-data privacy at rest and in
transit to the LLM provider (R-04/R-05)**, and **no authentication
(R-06)**. None of these diminish the architecture; all of them are
preconditions for real data.

## 2. Current System Reality

See `production-current-state.md` (all probe-backed): JSON/JSONL
persistence per project; FastAPI server without authn, CORS `*`;
OpenAI-compatible provider with bounded retry and fail-closed outage
behavior; demo knowledge + demo catalog; approval gateway gating replans
only; token usage in-memory only; local dev deployment; no backup.

## 3. What Phase 0–12 already solved

Deterministic validated planning; bounded-parallel scheduling with worker
isolation and deterministic commits; harness-owned eval + bounded repair;
artifact registry with lineage/fingerprints/provenance; checkpoint and
cross-process crash recovery (incl. mid-command idempotency); immutable-
revision replanning; HITL approval gateway; HOTL control plane with
deterministic monitoring; A2A bus with policy; anti-cheat benchmark and
false-pass red-teaming; two domains on one runtime; portfolio packaging.

## 4. Production Scope (restate)

Owner + 1–3 trusted users · small number of real cases · human review ·
manual delivery · agent never auto-completes final delivery · single
node. Enterprise scale explicitly out of scope.

## 5. P0 Blockers

- **R-01 Index lost-update** (measured: 8 concurrent saves → 3 entries,
  silent). Corrupts the shared project listing under any concurrent use.
- **R-02 No enforced human-review gate on report/recommendation** —
  required production flow is not enforced; agent-mode gates are
  auto-approved today.
- **R-03 Product data below real-recommendation grade** — no
  `effective_to`; waiting period / exclusions / coverage limits / health
  declaration / occupation restriction absent (measured).
- **R-04 Real client data at rest** — plaintext, unencrypted,
  unclassified, no retention/erasure (measured 156/312 sensitive hits).
- **R-05 LLM provider data policy UNKNOWN** — no retention/training/
  region evidence in-repo; must be verified before real client payloads.
- **R-06 No authentication** — P0 the moment the server is reachable
  beyond localhost; P1 for a strictly-localhost trusted pilot.

## 6. P1 Gaps

Durable token/cost records (R-07) · backup tooling (R-08) · atomic JSON
writes (R-09; detection exists, prevention doesn't) · insurance-report
domain eval depth (R-10) · deployment definition/env separation (R-11) ·
human role model & case ownership (authorization) · actor-string trust on
approve endpoints.

## 7. P2 Gaps

Approval auto-TTL (R-12) · metrics/alerting/structured logs (R-13) ·
rate limiting (R-14) · cross-instance rewrite-on-update coordination
(R-15) · disk-full behavior · event identity attribution.

## 8. P3 Future Scale

Multi-node coordination, external queues, distributed scheduler,
databases-as-infrastructure, Kubernetes — deliberately out of scope.

## 9–18. Findings by area

Detailed in the companion documents, each with probes:
Runtime/Recovery → `production-runtime-audit.md` (incl. the failure-
injection readiness table) · Security → `production-security-audit.md` ·
Data/Knowledge/Product → `production-data-audit.md` · Evaluation/Human
review/Observability → `production-evaluation-audit.md` · Cost → R-07
above (usage captured in-memory, zero durable records) · Deployment →
local dev only (R-11) · LLM → reliable bounded/fail-closed behavior,
provider policy UNKNOWN (R-05).

## 19. Regression Evidence (run this round, unmodified)

```text
pytest tests/runtime tests/portfolio -q   → 326 passed
python tmp/run_regression.py              → 51 PASS / 0 FAIL / 1 pre-existing
                                            INFRA_ERROR (step3-mutation + GBK,
                                            unchanged, excluded)
python -m evals.benchmark.runner          → 11/11, hard gates all 0
compileall (runtime/tests/demos/benchmark) → OK
demos (basic/insurance/generalization/portfolio) → all exit 0
```

## 20. Unknowns / Verification Required

- LLM provider data-retention / training-usage / region policy (R-05).
- Disk-full and very-large-case behavior (untested).
- Real knowledge source licensing/suitability (demo corpus only).
- Any compliance obligations for the target jurisdiction (insurance
  advice adjacency) — a business/legal verification, not a code one.

## 21. Final Production Readiness

```text
NOT READY
```

Rationale: five P0 blockers (R-01…R-05) plus R-06-on-exposure stand
before *any* real client data. The runtime semantics are ready; the
operational, data-governance and human-control preconditions are not.
Once the P0 set is closed, this system is plausibly a **controlled
internal pilot** (trusted users, localhost/VLAN, human-reviewed
deliverables, demo-catalog products clearly labelled) — that judgment
belongs to Round 2 after fixes, not to this audit.
