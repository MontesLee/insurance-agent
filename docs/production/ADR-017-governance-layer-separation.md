# ADR-017: Governance Layer Separation

## Status: APPROVED (implemented in Phase 27.5, commit 7985680)

## Context

Phase 27.5 added a Human-in-the-loop Governance UI (Review Queue →
Review Workspace + Evidence Chain → Human Decision → Pilot
Dashboard) on top of the frozen phase26c productionization
baseline. The UI needed to evolve quickly (forms, dashboards,
feedback loops are coming) while the Agent Runtime (queue, lease,
lifecycle, budget, recovery — 26A–26C) must remain stable and
independently verifiable (596-test battery, closure gates).

Note on numbering: the requesting review draft suggested
"ADR-008"; that number is already taken by production-persistence.
This ADR therefore continues the series as ADR-017.

## Decision

The Governance UI remains architecturally INDEPENDENT from the
Agent Runtime:

1. **Read-mostly projection**: governance views consume existing
   read APIs and render backend state verbatim (no status
   reinterpretation, no local business-state derivation, no
   direct database access).
2. **Single write path**: the only mutations are the two existing
   approval endpoints (POST /api/approvals/{id}/approve|reject),
   whose state machine and REVIEWER role check stay entirely
   backend-side. The UI performs no optimistic state flips.
3. **No control coupling**: the governance layer cannot trigger,
   modify, or re-run agent execution; the runtime never calls into
   the governance layer.
4. **Evidence before decision**: decision affordances sit after
   the evidence chain; missing evidence renders explicitly
   ("No evidence linked") and is never fabricated.

## Consequences

- Governance UI can iterate (27.5-x, feedback loop, dashboards)
  without touching runtime/tests (verified: runtime diff 0 across
  27.5-2..5; backend battery 596/0 at every step).
- Known linkage gaps (project-scoped approvals; no approval→run
  binding; no who-am-I; single-entry decision record) are handled
  by UI-side affordances (persisted selectors, "—") and recorded
  as future BACKEND domain-model work — not by frontend
  invention.
- When the backend adds the missing endpoints (global approvals,
  approval→run binding, identity, audit events), the UI adopts
  them as drop-in replacements for the manual selectors.

## Alternatives considered

- **Governance inside the runtime (server-rendered)**: rejected —
  couples human-workflow iteration with execution-engine release
  cadence and re-opens the frozen 26C baseline.
- **UI-side aggregation service / BFF**: rejected for v0.1 —
  would add a stateful component; frontend aggregation over
  existing endpoints suffices at pilot scale.
