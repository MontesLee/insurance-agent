# ADR-015: Production Observability

## Status: APPROVED (design only — implementation in Phase 25)

## Context

Current: stdout logs, trace files (runtime/observability.py),
evaluator-based trace completeness. No metrics, no distributed
tracing.

## Decision

Three pillars:

### Metrics
- Prometheus-compatible /metrics endpoint
- Request latency, task latency, queue depth, LLM latency, knowledge
  retrieval latency, error rate, retry rate, abstention rate,
  human-review rate, token usage, cost, throughput

### Logs
- Structured JSON logging (replaces print)
- Correlation: request_id + case_id + task_id + trace_id
- PII redaction (existing redact() applied at log emission)

### Traces
- OpenTelemetry-compatible spans
- Span hierarchy: request → case → task → skill → LLM call →
  knowledge search → governance check → evidence build
- Propagated via context (not HTTP headers for in-process)

## Key Metrics (with ASSUMPTION labels)

| Metric | Type | Cardinality |
|---|---|---|
| case_duration_seconds | histogram | project_type |
| task_duration_seconds | histogram | task_type |
| queue_depth | gauge | queue_name |
| llm_tokens_total | counter | provider, model, direction |
| llm_cost_dollars_total | counter | org_id, provider, model |
| knowledge_search_duration | histogram | provider |
| governance_decisions_total | counter | decision (allow/deny) |
| abstention_rate | gauge | (global) |
| human_review_pending | gauge | (global) |
| error_rate | gauge | error_type |
