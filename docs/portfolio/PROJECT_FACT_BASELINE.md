# Project Fact Baseline — Phase 19 (2026-09-21)

Independent audit baseline. Every claim below is verified against the
CURRENT repository state (git log, live test runs this session).
Categories: REAL / MOCK / DEMO / NOT_IMPLEMENTED / NOT_MEASURABLE.

## Repository state

```text
HEAD:          915c199 (Phase 18 BLOCKED report; live Phase 18 work
               uncommitted — 11 modified + 6 new files, all green)
Commits:       20+ commits, phases 1–18
Runtime code:  ~12,800 lines across 92 Python files (runtime/ +
               knowledge/ + adapters/)
Tests:         80 test files, 456 pytest tests passing
Docs:          38 files in docs/production/ + portfolio docs
Evals:         6 evaluator suites (knowledge, business, quality,
               security, observability, pilot)
```

## REAL (verified this session)

| Claim | Evidence |
|---|---|
| Docker Engine 29.8.0 + Compose v5.5.1 running | `docker info` + `docker compose ps` — 5 containers healthy |
| WeKnora v0.8.0 (commit 1edcd54b) official Tencent/WeKnora | `git remote -v` + `VERSION` file in checkout |
| Real WeKnora HTTP retrieval (POST /api/v1/knowledge-search) | 48/48 live checks ALL GREEN (exit 0) |
| Real governance on live WeKnora hits | G2 section: 12 mutation/governance checks ALL DENY |
| Real provenance chain (fixtures KB) | G5: four-hop chain + validate_provenance + hash match |
| Real provider failures at HTTP boundary | G4: connection/timeout/401/403/malformed — 7 fail-closed |
| Real abstention (agent-side policy) | G6: zero-overlap query → insufficient_evidence |
| 456 runtime tests | `pytest tests/runtime -q` → 456 passed |
| 12 portfolio tests | `pytest tests/portfolio -q` → 12 passed |
| 42/42 benchmark | `test_benchmark.py` |
| Full regression 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR | `run_regression.py` |
| All 14.1–18 suites green (mock mode) | 52/33/74/52/44/25/21/23/26/26/47 |
| Business E2E 15/15 (live WeKnora backend) | `run_business_eval.py` env=weknora |
| Quality eval 30/30 + mutation 8/8 (live) | `run_agent_quality_eval.py` env=weknora |
| Security eval 98/98 (live) | `run_security_eval.py` env=weknora |
| Knowledge eval 50/50 (mock + weknora) | `run_knowledge_eval.py` both modes |
| Pilot eval 26/26 (mock + weknora) | `run_pilot_eval.py` both modes |
| 10 real insurance documents (3 partial + 7 full) | `knowledge/pilot/registry/pilot_registry.json` |
| WeKnora projection registries (3 KBs) | `knowledge/pilot/registry/weknora_*.json` |
| 3 real provenance chains manually verified | `tmp/p19_walkthrough.json` (this session) |

## MOCK (deterministic testing only — NOT production infrastructure)

| Item | Used for | Never described as |
|---|---|---|
| MockKnowledgeProvider | offline regression, unit tests, P15/P16/P17 mock-mode runs | production backend |
| WeKnoraKnowledgeProvider (seam) | contract tests (C01-C11, fake transport) | live service |
| fixtures KB (6 synthetic docs) | business E2E knowledge corpus | real insurance knowledge |
| governed fixtures KB (7 synthetic docs) | governance rule testing | real sources |
| demo product catalog (12 fictional products) | Candidate→Recommendation chain | real products |

## DEMO (portfolio demonstration)

| Item | Nature |
|---|---|
| demos/demo_basic.py … demo_portfolio.py | 10 demo scripts, all exit 0 |
| demo product catalog (is_demo: true on every entry) | fictional, explicitly labelled |
| README 5-minute demo | honest — mentions "demo" 17 times, "not production insurance" |
| business demos A/B/C | full-chain / stops-and-asks / needs-review (all correct under WeKnora) |

## NOT_IMPLEMENTED (explicitly absent)

| Item | Status |
|---|---|
| Production database (PostgreSQL/SQLite for agent state) | NOT — JSON/JSONL + FileLock persistence |
| Public deployment / multi-tenant SaaS | NOT |
| Real customer deployment / real client PII | NOT |
| Real insurance product catalog | NOT — demo only |
| Production LLM provider (real API key, real cost) | NOT — deterministic path has 0 LLM calls; R-05 BLOCKED |
| Production-scale traffic benchmark | NOT |
| Event log cryptographic chaining | NOT — append-only by convention (F-18, P2) |
| Value-pattern credential redaction | NOT — field-based only (F-20, P3) |
| WeKnora production deployment | NOT — single-node loopback pilot |

## NOT_MEASURABLE (honestly declared, never guessed)

| Metric | Reason |
|---|---|
| Token cost (input/output) | LLM calls = 0 on the deterministic path |
| Production latency SLA | Single dev box, convenience cases |
| Hit@1 ranking precision | No relevance-labeled production corpus |
| Requirement/Risk derivation quality | Dialogue-driven stages not deterministically re-derivable |
