# Observability Architecture — Phase 21 (design only)

## Current State

- runtime/observability.py: load_trace, summarize, render
- events.jsonl: append-only event log (PII-redacted)
- Evaluator-based trace completeness (M-OBS 8/8)
- Latency measurement in evaluator (N=12, pilot box)

## Target: Metrics

| Metric | Type | Labels |
|---|---|---|
| case_duration_seconds | histogram | case_type |
| task_duration_seconds | histogram | task_type |
| queue_depth | gauge | queue |
| llm_call_duration | histogram | provider, model |
| llm_tokens_total | counter | provider, model, direction |
| llm_cost_total | counter | org_id, provider |
| knowledge_search_duration | histogram | provider |
| governance_decision_total | counter | rule, decision |
| abstention_total | counter | global |
| human_review_pending | gauge | global |
| error_rate | gauge | error_type, component |

## Target: Logs

Structured JSON with correlation: {timestamp, level, request_id,
case_id, task_id, trace_id, message, ...data}. PII redaction at
emission (existing redact()).

## Target: Traces

OpenTelemetry-compatible span tree:
request → case → task → skill → (LLM call | knowledge search |
governance check | evidence build | artifact write).

## What Already Works

The existing trace evaluator proves the data is available from
durable surfaces. Production observability formats it differently;
the data model is the same.
