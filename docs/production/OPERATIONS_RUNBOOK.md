# Operations Runbook — Phase 25

For each incident shape: Symptoms → Where to inspect → Safe action →
Unsafe action → Escalation. All log greps run over
`tmp/obs/agent.jsonl` (JSONL, one record per line).

Preliminaries:
`GET /api/health` (liveness) · `GET /api/ready` (readiness) ·
`GET /api/diagnostics` (OPERATOR auth when identities are configured) ·
`GET /api/metrics` (counters + latency percentiles).

---

## Case 1 — PostgreSQL unavailable

Symptoms: `/api/ready` → NOT_READY (dependency postgresql, required in
strict modes); business errors `PST-*` (PERSISTENCE_ERROR, retryable).
Inspect: `grep PST- agent.jsonl`; diagnostics → dependency_status.
Safe: wait/restore PostgreSQL; readiness flips back automatically
(probes are stateless). Strict-mode startup fails closed until fixed —
that is correct.
Unsafe: switching `INSURANCE_AGENT_STATE_BACKEND=json` in strict modes
(fail-closed by design, refuses); deleting case data.
Escalation: DBA if not back within the recovery window.

## Case 2 — WeKnora unavailable

Symptoms: `KNW-UNAVAILABLE` (NETWORK_ERROR) on searches; readiness
DEGRADED (non-strict) / NOT_READY (strict); knowledge_search_failure_
total rising.
Inspect: `grep -E "KNW-|knowledge.search" agent.jsonl`; docker ps for
the WeKnora stack.
Safe: restart the WeKnora containers (named volume
`weknora_postgres-data` preserves data); the agent abstains fail-closed
in the meantime — no wrong answers, just no evidence.
Unsafe: pointing `INSURANCE_AGENT_WEKNORA_URL` at a different corpus
without re-registering (registry/backend mismatch → mass DENY);
falling back to the mock provider in strict modes (impossible by
construction).
Escalation: platform owner if the container loop-crashes.

## Case 3 — LLM provider timeout

Symptoms: `LLM-TIMEOUT` / `llm_timeout_total` rising; latency p95 on
`llm_duration` up.
Inspect: `grep "llm.call" agent.jsonl | grep TIMEOUT` (attempt /
max_attempts show whether retries recovered).
Safe: none needed if retries recover (bounded, transient-only); check
provider status; the circuit breaker opens after sustained failures.
Unsafe: raising timeout_s without understanding the provider; retry
storms (the gateway already bounds retries).
Escalation: provider vendor status page; raise budget if systematic.

## Case 4 — LLM 429 rate limited

Symptoms: `LLM-RATELIMIT`; `llm_rate_limit_total` rising; the gateway
raises RateLimitError after its local limiter.
Inspect: metrics `llm_rate_limit_total`; call volume per minute.
Safe: reduce concurrency or raise `rate_limit_per_min` (operator
decision); the token bucket self-heals each window.
Unsafe: disabling the rate limiter.
Escalation: provider quota review.

## Case 5 — Governance DENY surge

Symptoms: `knowledge_governance_denied_total` climbing; business
outputs abstain more (insufficient_evidence).
Inspect: `grep "knowledge.search" agent.jsonl` (allowed/denied per
call); the denial REASONS live in the governed result metadata —
match against the registry (expired window / license / hash / not
ACTIVE).
Safe: verify a corpus re-ingestion did not drift hashes (re-run the
ingestion pipeline — idempotent; ACTIVE drift is refused loudly);
re-register documents that legitimately changed.
Unsafe: loosening governance rules to "get answers through".
Escalation: knowledge owner — a DENY surge after a corpus change is a
registration incident, not a governance bug.

## Case 6 — Agent task failure surge

Symptoms: `tasks_failed_total` / `skill_failure_total` rising;
`run.completed` logs with status failed.
Inspect: per-skill failure counters (labeled `skill_failure_total`);
the case trace for the failing stage; `error.*` fields give class +
operator action.
Safe: repair path is bounded already; re-run failed cases after the
root cause is fixed (checkpoints allow recovery).
Unsafe: skipping the eval gate or approving NEEDS_REVIEW wholesale.
Escalation: runtime owner if INTERNAL_ERROR dominates.

## Case 7 — Latency increase

Symptoms: p95 up on request/task/skill/knowledge/llm duration.
Inspect: `/api/metrics` latency_ms percentiles — WHICH surface moved
narrows the layer; then grep the corresponding event (`http.request`
/ `run.completed` / `knowledge.search` / `llm.call`).
Safe: compare against the engineering baseline (NOT a SLA);
investigate the slowest dependency of the moved surface.
Unsafe: "tuning" caches into correctness-critical paths.
Escalation: platform owner when a dependency's native latency moved.

## Case 8 — Readiness NOT_READY

Symptoms: `/api/ready` 503; load balancers should stop routing.
Inspect: the checks array — which dependency, required or optional,
and the detail string (configuration vs connectivity).
Safe: fix the named dependency (see Cases 1–2); readiness is
stateless and recovers on the next probe.
Unsafe: restarting the process hoping a dependency heals (does not);
editing the readiness checks to pass.
Escalation: per-dependency owner.

## Case 9 — Persistence error

Symptoms: `PST-*` codes; `persistence_failures_total` /
`transaction_failures_total` rising.
Inspect: `grep PST- agent.jsonl`; PostgreSQL logs; the durability
layer's restore/verify tooling (Phase 13) before any manual repair.
Safe: use the verified backup → restore path if data corruption is
suspected.
Unsafe: hand-editing state files or DB rows (breaks hash anchors);
bypassing the lock layer.
Escalation: DBA + runtime owner jointly for any restore.

## Case 10 — Human intervention needed

Symptoms: WAITING_HUMAN approvals; HOTL supervisor alerts;
NEEDS_REVIEW terminal states.
Inspect: `/api/projects/{id}/approvals` and the supervisor endpoints;
the approval payload carries the exact decision context.
Safe: approve/reject through the control plane (audited, idempotent);
reject fails closed by design.
Unsafe: mutating case state directly to "unstick" a run; bypassing
the approval gateway.
Escalation: the accountable business reviewer — never the operator
silently deciding.

---

## Cheat sheet

| Question | Command |
|---|---|
| what failed recently? | `grep '"level": "ERROR"' tmp/obs/agent.jsonl \| tail` |
| one request's story | `grep '<request_id>' tmp/obs/agent.jsonl` |
| LLM retry storm? | metrics `llm_failure_total` vs `llm_calls_total`; grep attempt |
| governance denies? | metrics `knowledge_governance_denied_total` |
| why NOT_READY? | `/api/ready` → checks[].detail |
| who am I running as? | `/api/diagnostics` (mode/backends/commit/uptime) |
