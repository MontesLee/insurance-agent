# Pilot Protocol — Phase 27 Controlled Internal Pilot

Baseline: phase26c-productionization-v1.0 (c7ed9c6), frozen. Pilot
rule: NO runtime/test/skill/knowledge/gateway changes — findings
are recorded, classified and kept, never fixed mid-pilot.

## Objective

Answer, with real evidence: is the productionized runtime useful,
stable, auditable and controllable in real insurance-business
scenarios? NOT to prove "the agent is good".

## Data policy (hard)

* Allowed: SYNTHETIC + DE-IDENTIFIED_REAL cases only; every case
  records data_type. REAL_CUSTOMER is forbidden (provider data
  policy NOT VERIFIED — PA-26C5-P1-03; the runtime gate blocks
  real client data at the LLM boundary by default and stays ON).
* No real names/phones/IDs/addresses/accounts/policy numbers/
  contacts — even in de-identified cases.

## Case population (round 1 = 12 synthetic cases)

C01 child-protection · C02 single-adult · C03 married-no-child ·
C04 dual-income · C05 mortgage-family · C06 existing-insurance ·
C07 underinsured · C08 incomplete-info (income/budget/existing
UNKNOWN) · C09 gap≈0 evidence-sensitive · C10 complex family
(3 kids + 4 elders) · C11 knowledge-unavailable (empty KB) ·
C12 empty-requirements. Mechanism: benchmark mutation vocabulary
(set_unknown/set_value/set_risk/keep_requirements/kb-empty) on the
full-chain seed; executed through the FULL productionized path
(RunControl lifecycle+deadline, RunBudget, AgentTaskWorker, queue,
gates) — see tools/run_pilot.py.

## Human review protocol

Per pilot-review-template.md: an Owner/reviewer examines each
case's artifact chain (requirement/risk/gap/solution/product/
evidence/report) and records APPROVE / REJECT / NEEDS_CHANGE +
structured fields. The round-1 machine pass used MECHANICAL
operator approvals (actor `pilot-operator`, audited in
queue_ops_events) to carry cases past gates for runtime
observation — these are NOT business review results. Every case's
review_status is PENDING_HUMAN_REVIEW until the Owner completes
this protocol.

## Severity & stop conditions

P0 (immediate pilot stop): cross-case/user leak, fake
recommendation/evidence, approval bypass, UNKNOWN→SUCCESS, secret
exposure, state corruption. P1: pause the affected path. P2/P3:
recorded as pilot debt. Full stop list: PRODUCTION_ACCEPTANCE.md.

## Exit criteria (round 1)

≥10 cases executed (12 ✓) covering normal / incomplete-info /
existing-insurance / complex-family / evidence-sensitive /
knowledge-unavailable; P0 = 0; per-case auditability answers
(§19); Top recurring failure patterns documented (honest count).
Human review completion is REQUIRED before any exit decision
other than CONTINUE PILOT.
