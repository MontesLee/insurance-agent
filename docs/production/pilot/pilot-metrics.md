# Pilot Metrics — definitions + round-1 machine values

Round 1 (2026-09-23, 12 SYNTHETIC cases, machine side only):
completion_rate 12/12=1.00 (task/run SUCCEEDED — but see F27-01:
result_status WAITING_FOR_USER/NEEDS_REVIEW also settle SUCCEEDED;
business completion ≠ run completion) · needs_review_rate(gate)
10/12 defer at ≥1 gate; C08/C11 no gate (finding) ·
approval_rate/rejection_rate/change_rate/review_time = UNKNOWN
until human review (mechanical approvals excluded) ·
requirement/risk/gap/solution/product/report error rates =
pending human review · repairs: 2 total (C11 only) · retries: 0 ·
replans: 0 · runtime_failure_rate 0/12 · recovery events: 0
needed (no crash in round 1) · LLM: calls/case = 0 (REAL —
deterministic path), tokens/case = 0 (real), estimated_cost/case
= UNKNOWN (no LLM metering; nothing sent to any provider) ·
unknown_usage_rate = N/A · elapsed/case ≈ 1.3s (machine).

Baseline honesty: Time Saved = UNKNOWN (no manual baseline yet).
Cost/case = UNKNOWN (0 LLM calls on this path; "Pilot Observed
Cost" for LLM cannot be computed until the LLM path is both
policy-verified and metered).
