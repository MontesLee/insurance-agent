# ADR-011: LLM Gateway

## Status: APPROVED (design only — implementation in Phase 23)

## Context

Current system has ZERO LLM calls on the deterministic path.
The R-05 provider-policy gate BLOCKS real client data from reaching
any external provider until operator verification. The existing
`runtime/agent/model.py` is the LLM client (httpx), unused in the
deterministic business chain.

## Decision

Introduce an LLM Gateway layer between Skills and Model Providers.

```
Agent Skill (tool-calling)
    ↓
LLM Gateway
    ↓
Model Router
    ↓
Provider (OpenAI / Anthropic / Zhipu / etc.)
```

## Gateway Responsibilities

| Responsibility | Design |
|---|---|
| Provider abstraction | Same pattern as KnowledgeProvider; skills never see provider SDK |
| Model selection | Per-skill model configuration; structured output support |
| Timeout | Per-request timeout with circuit breaker |
| Retry | Transient only (network, 5xx); never retry on content |
| Circuit breaker | Trip after N consecutive failures; half-open probe |
| Rate limit | Per-user, per-org, per-provider token bucket |
| Token budget | Per-request, per-day; hard-stop at limit |
| Cost tracking | Input/output tokens × provider pricing; per-org billing |
| Structured output | Schema-validated responses (existing jsonschema approach) |
| Prompt version | Recorded in call log for reproducibility |
| Request/Trace ID | Correlation with observability |
| PII policy | R-05 gate integration; REDACTED fields never sent |
| Provider policy | R-05 check per-request (existing data_policy.py) |

## Fallback Policy

Default: **UNKNOWN → FAIL CLOSED** (no silent fallback).

If a fallback is ever configured, it MUST log:
- fallback reason (circuit breaker trip, provider 5xx)
- original provider + model
- fallback provider + model
- policy reference (which approved this fallback)
- trace ID

Silent fallback is architecturally forbidden.

## Where it sits

The LLM Gateway is a library, not a separate service. It lives in
the agent runtime process, wrapping the existing httpx client. Skills
call it through the existing tool-calling interface; the gateway
adds governance before the HTTP call goes out.
