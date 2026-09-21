# Real vs Demo — Phase 19

Capability-by-capability classification. "Documentation Claim >
Actual Capability" is a Finding (F-numbered).

| Capability | Current State | Evidence | Real/Demo/Mock | Production Gap |
|---|---|---|---|---|
| Client Intake | Dialogue-driven PS1 skill; seeded into CaseState; 5-state field model | contracts/client-profile.schema.json | **Real** (contract) + Demo (dialogue depth) | No real client PII ever used |
| Requirement Analysis | Dialogue-driven PS1 skill; boundary=requirement_only | contracts/requirement-analysis.schema.json | **Real** (contract) + Demo (dialogue) | Not deterministically re-derivable (F-14) |
| Risk Analysis | Dialogue-driven PS1 skill; R1–R5 categories | contracts/risk-assessment.schema.json | **Real** (contract) + Demo | Same F-14 |
| Coverage Gap | Deterministic engine; rules-externalized | 14.3 gap quality 4/4; P15 15/15 | **Real** | Coverage depends on risk quality |
| Solution | Deterministic engine; product-NEUTRAL | contamination invariant; P15 B5 | **Real** | No life/R4 direction (F-16) |
| Product Candidate | Deterministic; catalog + eligibility + evidence gating | P15 B009 NO_CANDIDATES; R-03 | **Real** | Catalog is demo-only |
| Recommendation | Deterministic; grounding + evidence refs | P15 15/15; P16 RQ1-RQ6 | **Real** | Depends on demo catalog |
| Report | Deterministic renderer; 10 sections + evidence appendix | P15 report consistency 15/15 | **Real** | — |
| Knowledge Search | KnowledgeService → Provider (Mock or WeKnora) → Governance → Evidence | 14.1-14.7, 15, 16, 18 | **Real** | — |
| WeKnora | v0.8.0 live, official Tencent, Docker, 3 KBs, real HTTP | 18 live 48/48; env doc | **Real** | Single-node pilot only |
| Governance | 9 deterministic rules; registry authority; window/license/jurisdiction/hash | 14.3 74/74; 18 G2 live | **Real** | Registry is manually synced |
| Evidence | Citation-tuple; contracts validated | 14.5 44/44 | **Real** | — |
| Provenance | P001-P010; 4-hop chain; hash anchors | 14.5; 18 G5 live; 3 chains in walkthrough | **Real** | — |
| Evaluation | 6 evaluator suites; 300+ eval cases; mutation testing | 14.6 50/50; 15 15/15; 16 30/30; 17 98/98 | **Real** | — |
| HITL | Approval gateway; REQUESTED→WAITING_HUMAN→APPROVED/REJECTED | Phase 9; 17 AP01-08 | **Real** | Single-node |
| HOTL | Monitor + control commands; pause/resume/cancel | Phase 10; demos | **Real** | Not used in business chain |
| Authentication | API-key identity (OWNER/REVIEWER/OPERATOR); fail-closed | 17 auth 9/9; authz 33/33 | **Real** | No OIDC/SSO |
| RBAC | Rank-based; approve requires REVIEWER+ | 17 authorization matrix | **Real** | No fine-grained permissions |
| Encryption | Fernet at-rest (IA1:); strict modes require key | 17 encryption 3/3; P0.1 | **Real** | Key management is env-var |
| Retention | Terminal-only sweep; backup-first; dry-run default; erasure.log | Stage 1; 17 retention 2/2 | **Real** | Single-node |
| Backup | Locked snapshot; sha256 manifest; fail-closed verify | Stage 1; 50/50 | **Real** | — |
| Restore | Verify-first; staging; atomic commit; rollback | Stage 1; 57/57 | **Real** | — |
| Database | NONE — JSON/JSONL + FileLock | — | NOT_IMPLEMENTED | Phase 19 candidate |
| LLM Provider | Deterministic path: 0 LLM calls; R-05 gate BLOCKED for real data | 17 provider 6/6 | NOT_IMPLEMENTED | Operator verification needed |
| Product Catalog | 12 fictional products (is_demo: true) | catalog/README.md | **DEMO** | Real catalog needs insurer data |
| Deployment | Single-node dev box; loopback only | — | NOT_IMPLEMENTED | No public deployment |
| Observability | Trace from durable surfaces; latency; token honesty | 17 observability PASS | **Real** | No OpenTelemetry |

## Documentation Claims Audit

| Document | Claim | Actual | Consistent? |
|---|---|---|---|
| README.md | "Long-running Multi-Agent Runtime" | Accurate | ✓ |
| README.md | "not production insurance" (line 140) | Honest disclaimer | ✓ |
| README.md | "demo" mentioned 17 times | Honest | ✓ |
| catalog/README.md | "12 个产品全部是虚构的" | is_demo: true on every entry | ✓ |
| WEKNORA_ENVIRONMENT.md | "READY_FOR_PHASE_18" → "INTEGRATED" | Updated after Phase 18 | ✓ |
| Phase 18 report | "PASS" | 48/48 live + all regressions green | ✓ |

**Finding**: No documentation-claim > actual-capability instances
found. The README and catalog are unusually honest about demo status.
