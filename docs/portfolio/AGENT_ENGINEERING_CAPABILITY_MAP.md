# Agent Engineering Capability Map — Phase 19

Capability → Implementation → Evidence → Test → Demonstration.
Every row is machine-verifiable.

## Agent Architecture

| Capability | Implementation | Evidence | Test | Demo |
|---|---|---|---|---|
| Skill decomposition | 9 skills, each with schema-validated contract | `contracts/*.schema.json` (11 files) | 15 I-invariants | `demo_portfolio.py` |
| State management | Canonical Client State, 5-state field model | `client-profile.schema.json` | 15 I1; 16 Q-SUF | Demo B (stops, asks) |
| Tool calling | Agent tools with contract validation | `runtime/agent/tools.py` | 14.1 C01-C11 | `demo_insurance.py` |
| Orchestration | YAML-driven; ordering/freeze/eval per stage | `runtime/insurance-analysis.yaml` | `test_harness.py` | All demos |
| Scheduling | Bounded parallel DAG with worker isolation | `runtime/harness/harness.py` | `test_parallel_scheduler.py` | `demo_parallel.py` |
| Replanning | Deterministic triggers; bounded; id-based merge | `runtime/repair.py` + replan logic | `test_dynamic_replanning.py` | `demo_replan.py` |
| HITL | Approval gateway; human-only actor; state machine | `runtime/approval/` | 17 AP01-08 | `demo_hitl.py` |
| HOTL | Monitor + control commands; pause/resume/cancel | `runtime/control/` | Phase 10 suites | `demo_hotl.py` |

## Reliability

| Capability | Implementation | Evidence | Test | Demo |
|---|---|---|---|---|
| Checkpoint | Per-stage fingerprint + validate + resume | `runtime/checkpoint.py` | `test_cross_process_recovery.py` | — |
| Backup | Locked snapshot + sha256 manifest | `runtime/state/backup.py` | 50/50 (14.1a) | — |
| Restore | Verify-first + staging + atomic commit | `runtime/state/restore.py` | 57/57 (14.1b) | — |
| Retry | Eval→Repair (max 2)→NEEDS_REVIEW | `runtime/repair.py` | `test_failure_injection.py` | — |
| Fail-closed | All providers/governance/eval fail→DENY/ERROR | 14.1-18 all suites | 18 G4 (7 modes) | — |
| Crash recovery | Checkpoint validate + RUNNING→PENDING | `runtime/harness/harness.py` | `test_cross_process_recovery.py` | — |

## Knowledge

| Capability | Implementation | Evidence | Test | Demo |
|---|---|---|---|---|
| Retrieval | BM25 trigram + reranker (agent-side) OR WeKnora hybrid | `knowledge/rag/engine.py` + `weknora.py` LIVE | 14.6 retrieval 6/6; 18 G1 | `demo_insurance.py` task_5 |
| Provider abstraction | KnowledgeProvider protocol; Mock↔WeKnora swap | `knowledge/provider/` | 14.1 C11; 18 G5 equivalence | — |
| Governance | 9 deterministic rules; registry-authoritative | `knowledge/governance/governance.py` | 74/74 (14.3); 18 G2 live | — |
| Evidence | Citation tuple; build_evidence_item | `knowledge/governance/governance.py` | 44/44 (14.5) | — |
| Provenance | P001-P010; 4-hop chain; hash anchors | `knowledge/governance/provenance.py` | 44/44; walkthrough (3 chains) | — |
| Freshness | effective_from/to + as_of; expired→DENY | governance R5 | 14.3 GOV-003/004/005 | — |
| Authority | S/A/B/C/D ladder; registry-canonical | governance R4 | 14.3 GOV-006/007 | — |
| License | ALLOWED/RESTRICTED/UNKNOWN; UNKNOWN→DENY | governance R7 | 14.3 GOV-011/012 | — |

## Evaluation

| Capability | Implementation | Evidence | Test | Demo |
|---|---|---|---|---|
| Deterministic eval | rules-externalized; no LLM judge | `runtime/eval_engine.py` | 42/42 benchmark | — |
| Mutation testing | Inject defects → evaluator must catch | 14.6/16/17 mutation suites | 8/8 + 10/10 + 8/8 | — |
| Golden cases | 10 business + 30 quality cases | `evals/business/` + `evals/agent_quality/` | 15/15 + 30/30 | — |
| Negative cases | 5 business + 5 quality + 98 security | All evaluator suites | All green | — |
| Regression | 456 pytest + 52-suite full regression | `tmp/run_regression.py` | 456 + 51/0/1 | — |
| Adversarial testing | 42 attacks across 4 categories | `ADVERSARIAL_FINDINGS.md` | 42/42 PASS | — |

## Security

| Capability | Implementation | Evidence | Test | Demo |
|---|---|---|---|---|
| Authentication | API-key identity; fail-closed | `runtime/auth.py` | 17 auth 9/9 | — |
| Authorization | OWNER/REVIEWER/OPERATOR rank | `runtime/auth.py` | 17 authz 33/33 | — |
| Project isolation | Per-project dirs; charset-validated ids | `runtime/harness/harness.py` | 17 isolation 5/5 | — |
| PII redaction | Field-based deny-list; 26 sensitive fields | `runtime/state/dataprotection.py` | 17 PII 12/12 | — |
| Encryption at rest | Fernet IA1:; strict modes mandatory | `runtime/state/dataprotection.py` | 17 encryption 3/3 | — |
| Retention | Terminal-only; backup-first; erasure.log | `runtime/state/retention.py` | Stage 1; 17 retention | — |
| Provider policy | R-05 fail-closed; env opt-in only | `runtime/agent/data_policy.py` | 17 provider 6/6 | — |
