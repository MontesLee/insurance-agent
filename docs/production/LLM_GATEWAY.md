# LLM Gateway Architecture — Phase 21 (design only)

## Position

```
Agent Skill (tool-calling, schema-validated)
    ↓
LLM Gateway (library, in-process)
    ├── Provider policy check (R-05)
    ├── PII filter (existing redact())
    ├── Rate limit (per-user, per-org)
    ├── Token budget (per-request, per-day)
    └── Cost tracking (per-org, per-provider)
    ↓
Model Router (selects provider + model)
    ↓
Provider Adapter (httpx, timeout, retry, circuit breaker)
    ↓
External LLM API
```

## Responsibilities

| Responsibility | Current State | Target |
|---|---|---|
| Provider abstraction | model.py (httpx, single provider) | Multi-provider, same interface |
| Model selection | Hardcoded | Per-skill config, structured output |
| Timeout | 60s fixed | Per-request, configurable |
| Retry | 2 max (LLM_RETRY) | Transient only, backoff, circuit breaker |
| Rate limit | None | Token bucket, per-user/org |
| Token budget | None | Hard stop at limit |
| Cost tracking | In-memory AgentState only | Durable, per-org billing |
| Schema validation | Existing (jsonschema) | Same, enforced at gateway |
| Prompt version | None | Recorded per call |
| Trace ID | None | Correlation with observability |
| PII policy | redact() on events | Same, applied before LLM call |
| Provider policy | R-05 gate (existing) | Per-request check |
| Fallback | None (fail closed) | Fail closed; fallback requires explicit policy + audit |

## What the Gateway Does NOT Do

- Governance decisions (that's the governance layer)
- Evidence creation (that's the evidence builder)
- Business logic (that's skills)
- Provenance (that's the provenance validator)
