# Finding Decision Matrix — Phase 27 Review Gate (2026-09-23)

| Finding | Evidence | Severity | Root cause | Action | Phase |
|---|---|---|---|---|---|
| F27-01 | C08/C11 traces + source trace (f27-01-root-cause.md) | P1 | agent result classification + settle semantics gap; run.SUCCEEDED = execution-only (design semantic gap vs 26C-2 authority split) | FIX IN NEXT ENGINEERING PHASE (executor business-status classification + settle_success run-transition consults result status) | 28 |
| F27-02 | diag A/B (f27-02-root-cause.md, data/diag-f2702.json) | P1 (pilot value; NOT a runtime bug) | demo catalog single-domain + fixture KB lacking coverage backing (content) | CATALOG FIX (+evidence content); optionally re-scope pilot to pre-recommendation stages | 28 (content track) |
| F27-03 | C12 full chain + report produced | P2 | input validation: empty requirement set accepted | FIX in later input-validation engineering (not this gate, not next-phase-blocking) | backlog |
| F27-04 | invoke-knowledge-search.py DEFAULT_KB = skills fixture KB; obs provider="mock" | P3 | pilot configuration gap: live WeKnora is an existing optional provider, not wired into the pilot/benchmark default path | PILOT CONFIGURATION FIX in round 2 (wire kb_dir/provider per Phase 24 mechanism); runtime unchanged | pilot round 2 |

Security re-check (this gate): cross-case/user leakage 0 (each
case isolated run_root/task; synthetic data); secret leakage 0;
approval bypass 0 (no recommendation delivered without a gate;
C08/C11 delivered nothing); UNKNOWN→SUCCESS 0 (evidence/
knowledge layers fail-closed everywhere; content of runs verified
from artifacts, not claims). Pilot audit-row hygiene note: runner
deletes its queue/audit rows per case — export before cleanup in
round 2.

Provider policy: NOT VERIFIED (unchanged). "No provider data
exposure" (0 LLM calls, synthetic data) ≠ "provider safe". Real
sensitive customer data remains BLOCKED. External Pilot remains
BLOCKED (P1-02 isolation NOT IMPLEMENTED, P1-03 policy NOT
VERIFIED).
