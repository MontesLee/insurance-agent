# Phase 18 — WeKnora Integration Report

Date: 2026-09-20 · Budget: minimal (WeKnoraProvider / composition /
config / tests / docs). Production changes: **1 composition fix
(HG15/F-02 closure)** — see §13.

## 01 Executive Summary

```text
Phase 18 = BLOCKED (STOP-01: real WeKnora runtime unavailable)
```

The environment still has NO container runtime (docker / podman /
wsl re-verified absent this session) and no WeKnora endpoint — the
same infrastructure blocker measured in Phase 14.2. Per the phase
rules (§4, §34) the LIVE integration gates are honestly BLOCKED, not
faked. Everything provable WITHOUT a live WeKnora was executed and is
green: seam audit, contract normalization, fail-closed matrix
(F03–F06, F14), provider-unavailable propagation with no silent mock
substitution, governance equivalence on WeKnora-shaped hits
(E01–E09), canonical-enum discipline, and a NEW strict-mode
no-silent-mock gate (HG15) that closes the long-standing F-02 finding.
Phase 14–17 regressions are fully green.

## 02 Environment

WeKnora version: — (no instance) · deployment mode: none · endpoint:
none (INSURANCE_AGENT_WEKNORA_URL unset) · dataset: not loadable
into a backend that does not exist · docker: NOT FOUND · podman: NOT
FOUND · WSL: NOT INSTALLED. No secrets involved.

## 03 Architecture (verified at the seam level)

```text
Agent → KnowledgeService → WeKnoraProvider(transport-injected)
  → raw hits → map_weknora_response (strict validation)
  → canonical KnowledgeHit → Agent Governance Registry
  → allow/deny + validity → Evidence → Provenance → Decision
```

Registry-vs-backend truth rule holds: the evaluator proves a
backend-only UNREGISTERED document is DENIED (F06) — WeKnora metadata
can never override the Agent registry.

## 04 Retrieval

LIVE retrieval gates (Q01–Q06, Hit@k): **BLOCKED** — no backend. The
contract-level retrieval behavior is proven via injected transport:
normalization (E01), malformed rejection (F03/F04/F05), empty →
honest abstention (F14/E08). Hit@1/3/5 on real data: NOT_MEASURABLE
(backend absent).

## 05 Governance

Governance engine re-applied over WeKnora-shaped hits — identical
verdicts to the Mock side (same registry, same engine): ALLOW for the
registered current source; DENY for expired (E03), UNKNOWN-license
(E04), authority mismatch (E05), jurisdiction mismatch on a LOCAL
document (E06 — with the national-applies-locally rule respected),
hash mutation (E07), unregistered backend document (F06). Phases
14.3/14.4 suites re-run green (74/74, 52/52).

## 06 Evidence

Evidence path unchanged and untouched: hits (whatever the backend)
flow through the same builder; provenance identity (chunk/document/
version/source + hash + window + retrieved_at) all carried. Live
WeKnora→Evidence chain: BLOCKED (no backend); the chain shape is
proven on WeKnora-shaped hits via the 14.5 validators.

## 07 Provider Equivalence (§14 semantics — contract, not ranking)

E01 canonical contract ✓ (both sides) · E02 governed ALLOW ✓ ·
E03–E07 DENY parity ✓ · E08 abstention parity ✓ · E09 malformed →
FAIL parity ✓ · E10 unavailable → WeKnora fails closed, service
propagates ProviderError, NO mock substitution ✓ (W3).

## 08 Business E2E (Phase 15 regression)

15/15 business cases + suite 23/23 — unchanged (the pilot knowledge
path still runs on the governed mock; the WeKnora seam sits below the
same service boundary).

## 09 Agent Quality (Phase 16 regression)

30/30 quality cases + suite 26/26 — no drift; no evaluator modified.

## 10 Security (Phase 17 regression)

Security eval 98/98 (re-run inside the suite's group checks) + suite
26/26. Provider policy untouched (REAL + unverified → BLOCK); PII
redaction, auth/RBAC, isolation all green.

## 11 Observability

Trace evaluator re-green; retrieval metadata carries the provider
identity ("weknora") confined to retrieval_metadata — queryable
"which provider / how many hits / governance verdict" per the §24
questions (proven at contract level; live latency trace BLOCKED).

## 12 Performance

Live WeKnora latency: **BLOCKED** (no backend). Nothing estimated.

## 13 Production Code Changes (P-18-1 — within budget)

**HG15 / F-02 closure**: `knowledge/provider/__init__.py` — in STRICT
modes (controlled_pilot/production) an UNSET
INSURANCE_AGENT_KNOWLEDGE_PROVIDER now fails closed
(ProviderConfigError) instead of silently defaulting to the offline
mock; an EXPLICIT "mock" remains a documented operator choice. The
strict-mode set is mirrored locally WITHOUT importing runtime.mode
(the provider package must stay free of runtime imports — Phase-14.1
boundary test). Regression: W4 section + full battery green (449
runtime, all 14–17 suites).

## 14 Findings

- F-21 (= F-06/F-11 infrastructure, restated): no container runtime
  on the pilot machine — Phase 18 live gates BLOCKED (P1 blocker for
  THIS phase only; not a code defect).
- F-02: **CLOSED** this phase (strict-mode explicit-provider
  enforcement).
- No new P0/P1 code findings. HG01–HG15: all green at the provable
  level; live-dependent subgates recorded BLOCKED, never claimed PASS.

## 15 Scope

NOT done (by rule): PostgreSQL / Redis / DB migration / Docker
productionization / new Agent / new Skill / new Orchestrator / new
Planner / WeKnora Ask or ReAct usage / real client data / real
insurer APIs. No evaluator modified to obtain green results.

## 16 Unblock Path (operator actions)

1. Provide a Docker-capable host or a running WeKnora v0.8.x
   (backend API :8080) + scoped API key.
2. Ingest the Phase-14.7 real corpus (10 governed documents, scripts
   exist) into a POC knowledge base.
3. Set INSURANCE_AGENT_WEKNORA_URL(+KEY/KB) — the env-gated live
   runner (tests/runtime/test_p14_weknora_integration.py + W7) pins
   the real search endpoint and raw-response contract on first run.
4. Re-grade Phase 18: only the BLOCKED live gates then remain.

## 17 Final Decision

```text
Phase 18 = BLOCKED (STOP-01)
```

The integration surface is contract-proven, fail-closed, and
strict-mode-safe; the missing piece is a real WeKnora runtime, which
no amount of code in this repo can substitute. 宁缺毋滥: not faked.
