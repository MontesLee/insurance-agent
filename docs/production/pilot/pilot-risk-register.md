# Pilot Risk Register (live constraints carried into Phase 27)

| Risk | Status | Pilot handling |
|---|---|---|
| PA-26C5-P1-01 PG backup automation absent | OPEN | manual daily pg_dump per RUNBOOK (drill verified 2026-09-23); AUTOMATION = NOT IMPLEMENTED |
| PA-26C5-P1-02 object-level isolation absent | OPEN | hard constraint: single-tenant, trusted users, no cross-user expansion |
| PA-26C5-P1-03 provider policy NOT VERIFIED | OPEN | real sensitive customer data BLOCKED at the gate; pilot uses SYNTHETIC only; LLM path not exercised |
| PA-26C5-P2-01 approval MODIFY absent | OPEN | reviews record NEEDS_CHANGE instead; never claim system MODIFY |
| PA-26C5-P2-02 RPO/RTO unmeasured | OPEN | honest UNKNOWN |
| Single-host boundary (marker files, shared run_root) | OPEN | single-node deployment only |
| F27-01 business-status vs run-status conflation | NEW (round 1) | read result payloads; engineering decision pending |
| F27-02 no primary recommendation on demo catalog | NEW (round 1) | recommendation-quality validation blocked on catalog content |
