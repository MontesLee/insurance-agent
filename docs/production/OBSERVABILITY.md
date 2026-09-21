# Observability Architecture — Phase 25 (as implemented)

> Supersedes the Phase 21 design note that lived here. The Phase 21
> metric vocabulary (case/task duration, llm tokens/cost by provider,
> governance decisions by rule, abstention, error rate) is implemented
> by the internal `runtime/obs` abstraction below — deliberately
> WITHOUT Prometheus/Grafana exporters (deferred: no deployment needs
> them yet; OpenTelemetry was evaluated and NOT introduced). The
> historical design table is in git history (commit de8282a and
> earlier).

## What exists

`runtime/obs/` — one observation-only package (it must never change
business results; verified by E25-15 / failure-injection invariance):

| Module | Answers | Key surface |
|---|---|---|
| `context.py` | WHO / WHERE | request_id / correlation_id / trace_id / project / case / task / skill / tool, contextvar-scoped, one prefix convention (`req_` `corr_` `trc_`) |
| `log.py` | WHAT / HOW LONG / OUTCOME / WHY FAILED | JSONL structured log (`tmp/obs/agent.jsonl`), redaction by construction |
| `errors.py` | can we retry? who acts? | 17-class taxonomy, deterministic exception-type table, `retryable` / `safe_to_retry` / `operator_action` / `user_visible` |
| `metrics.py` | how much / how fast | declared counters + latency percentiles (min/median/p95/max), UNKNOWN-honest tokens |
| `health.py` | alive? ready? | liveness (process) vs readiness (mode-aware dependency checks → READY / NOT_READY / DEGRADED) |
| `diagnostics.py` | who am I / on what | version, git commit (file-read, no subprocess), mode, backends, uptime, dependency status — scrubbed |

HTTP surface (runtime/server.py):
`GET /api/health` (liveness) · `GET /api/ready` (readiness; 503 when
NOT_READY) · `GET /api/diagnostics` (OPERATOR role; includes the
metrics snapshot) · `GET /api/metrics` (OPERATOR role). Every response
carries `X-Request-Id` from the request middleware.

## How the trace flows

```
Request ─► middleware: start_request() ─► req/corr/trace ids
         ─► RunManager worker: span narrowing per task/skill
         ─► KnowledgeService.search  (instrumented: duration, allow/
           deny/abstention counters, structured log)
         ─► LLMGateway.generate → _log/_observe (the Phase-23 single
           choke point: attempt/max_attempts/error_type/usage/tokens)
         ─► run completion: task/skill metrics from the finished state
Logs / metrics / diagnostics all join on the same id fields.
```

## Logs ↔ metrics ↔ trace correlation

Every log line carries the context ids; every metric is aggregate-only
(no ids — by design, see isolation); the per-request story is the log,
the per-run story is the case trace (`trace.jsonl`, unchanged), and
the aggregate story is `/api/metrics`. `knowledge.search` /
`llm.call` / `run.completed` / `http.request` are the operator
entry-points for grepping.

## Health vs readiness (never conflated)

Liveness answers "is the process alive" — TRUE whenever the endpoint
answers; downstream outages never kill the process. Readiness answers
"can I take production workload NOW": in strict modes PostgreSQL and
the real WeKnora are REQUIRED (NOT_READY when missing/unconfigured);
optional dependencies that fail degrade to DEGRADED, not death.
Readiness checks are short-timeout probes + config-shape checks and
never mutate state.

## Error taxonomy in one line each

CONFIG/AUTH/VALIDATION (do not retry — fix input/config) ·
PROVIDER/NETWORK/TIMEOUT/RATE_LIMIT/LLM/KNOWLEDGE (retryable; safe to
retry only for NETWORK/TIMEOUT/RATE_LIMIT) · GOVERNANCE/EVIDENCE/
PROVENANCE (never retry — review the data) · PERSISTENCE (retryable,
check PostgreSQL) · CONCURRENCY (retry after lock release) · INTERNAL
(investigate) · USER_INPUT (surface to user) · CANCELLED (no action).
`classify(exc)` is a pure function over the exception type — the same
exception always classifies identically (E25-06).

## What is honest UNKNOWN

LLM token totals when the provider reports no usage stay `UNKNOWN`
forever (a missed measurement makes the running total unknowable);
empty latency histograms report UNKNOWN, never 0; unmeasured
production-scale numbers are NOT_MEASURABLE (see the baseline note).

## Engineering baseline (NOT a production SLA)

N=30 per surface, single host, mock LLM/knowledge where applicable
(`tmp/p25_perf_baseline.json`): health 3.6ms · readiness 3.7ms ·
diagnostics 5.6ms · simple request 3.9ms · knowledge 0.6ms · LLM
0.04ms · full agent run 348ms (median; p95 470ms).

## Limitations (documented, not hidden)

- In-process metrics/log sinks (no exporter yet — Phase 26+ candidate;
  OpenTelemetry was NOT introduced: nothing here needs it yet).
- Retry idempotency of business effects is not proven by the gateway
  (each retry is a new provider call) — duplicate-execution safety
  beyond checkpointing is a LIMITATION, unchanged by Phase 25.
- The middleware assigns request ids for HTTP traffic only; offline
  CLI runs have empty request context (skill/task metrics still flow
  via run completion).
