# Pilot Results — Round 1 (machine side) + Human-Review Packet

Executed 2026-09-23 on phase26c-productionization-v1.0 (c7ed9c6),
12 SYNTHETIC cases, zero runtime/test modifications. Runner:
tools/run_pilot.py (full productionized path: RunControl +
RunBudget + AgentTaskWorker + queue + gates; mechanical operator
approvals only — NOT business review).

## Machine results (all 12; full JSON in data/pilot-machine-results.json)

| Case | type | outcomes | task | run | att | repairs | result_status | elapsed |
|---|---|---|---|---|---|---|---|---|
| C01 | child_protection | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.4s |
| C02 | single_adult | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.3s |
| C03 | married_no_child | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.2s |
| C04 | dual_income | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.2s |
| C05 | mortgage_family | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.4s |
| C06 | existing_insurance | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.3s |
| C07 | underinsured | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.2s |
| C08 | incomplete_info | SUCCEEDED | SUCCEEDED | SUCCEEDED | 1 | 0 | **WAITING_FOR_USER** | 0.3s |
| C09 | gap0_evidence | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.2s |
| C10 | complex_family | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.4s |
| C11 | knowledge_unavailable | SUCCEEDED | SUCCEEDED | SUCCEEDED | 1 | 2 | **NEEDS_REVIEW** | 0.5s |
| C12 | no_requirements | DEFER→SUCCEEDED | SUCCEEDED | SUCCEEDED | 2 | 0 | COMPLETED | 1.3s |

Budget/retries/replans: task_attempts 1–2/case; repairs total 2
(C11); replans 0; budget enforcement observed ACTIVE (it refused
an over-attempt approval during runner bring-up — correct fail
closed). LLM: 0 calls/case (real, deterministic path); cost
UNKNOWN. Recovery: 0 events needed (no crash in round 1).

## Round-1 findings (recorded, NOT fixed — pilot discipline)

**F27-01 (P1, Runtime/Skill boundary)** — business non-completion
settles as run SUCCEEDED. C08 returned WAITING_FOR_USER (agent
correctly asked for missing info, no fabrication) and C11 returned
NEEDS_REVIEW (empty KB; recommendation/report correctly never
produced) — yet both tasks/runs are terminal SUCCEEDED and NO
human gate fired for either. Run state alone cannot distinguish
business completion; the "agent cannot deliver a final outcome
without human review" invariant holds at mid-run gates but not at
repair-exhausted/incomplete finals. Expected: business-terminal
≠ SUCCEEDED, or WAITING_HUMAN park. Evidence: table above +
artifacts under tmp/pilot27/C08, C11. Reproducible: yes (runner
--case=C08 / C11). Engineering area: agent_runtime settle
semantics (map result_status → run outcome), NOT skills.

**F27-02 (P1, Product/business content)** — no primary
recommendation ever, including the UNMUTATED baseline: direct-path
BASE run also yields product-recommendation INCOMPLETE_EVIDENCE,
10/10 candidates not_recommended, primary {}. The evidence rules
never admit a demo-catalog candidate. No fabrication (fail-closed
is correct), but recommendation-quality validation is BLOCKED on
catalog/evidence content. Engineering area: product catalog +
evidence policy content, not runtime. (Also observed: default
knowledge source on this path is the internal fixture KB — obs
provider="mock"; live WeKnora not exercised → F27-04, P3.)

**F27-03 (P2, input validation)** — C12: an EMPTY requirement set
was accepted; the full chain ran and produced a report. No
fabrication, but the deliverable is meaningless and no gate fired.
Engineering area: intake/requirement validation.

**F27-04 (P3, pilot environment)** — default knowledge path uses
the fixture KB, not live WeKnora; live-retrieval quality untested
this round.

## Human-review packet (pending — required before any exit
decision beyond CONTINUE PILOT)

For each case C01–C12: artifacts at tmp/pilot27/<id>/attempt-N/
<id>/artifacts/*.json (+ trace.jsonl). Reviewer: follow
pilot-review-template.md; record into this file's table below.
Special attention: C01–C07/C09/C10/C12 recommendations are all
INCOMPLETE_EVIDENCE (see F27-02 — review whether the report text
communicates that honestly); C08/C11 have NO recommendation/report
(F27-01).

| Case | reviewer | verdict | time_min | notes |
|---|---|---|---|---|
| C01–C12 | — | PENDING_HUMAN_REVIEW | UNKNOWN | — |
