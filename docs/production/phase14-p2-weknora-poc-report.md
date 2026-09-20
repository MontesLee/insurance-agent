# Phase 14.2 — WeKnora POC + Adapter Boundary Validation Report

Date: 2026-09-20 · Scope: POC ONLY — not a production cutover.

## 1. Executive Summary

```text
Stage 14.2 = BLOCKED (INFRASTRUCTURE BLOCKED)
```

**Real WeKnora integration was NOT verified.** The hosting environment
cannot run WeKnora at all (no Docker, no podman, WSL not installed, no
local checkout, no remote endpoint/credentials provided) and WeKnora's
documented deployment REQUIRES Docker + Docker Compose. Per the stage
rules (§四/§十七) the adapter was NOT faked, no success was simulated,
and no untested HTTP client was written into production code.

Everything verifiable WITHOUT a live service was completed and is
green: adapter boundary validation at fake-transport level (failure
matrix, canonical contract, provider equivalence, Ask/ReAct isolation
with request recording), the F-03 tool-level fail-closed behavior
test, an env-gated LIVE integration suite that skips honestly, and the
full regression battery. **No production code changed in this stage.**

## 2. Environment

| Item | Value |
|---|---|
| WeKnora version researched | v0.8.0 (official GitHub README, MIT, Tencent/WeKnora) |
| Documented deployment | `git clone` + **Docker Compose** (mandatory); Web UI :80; **Backend API :8080**; scoped API-Key auth (`WEKNORA_API_KEY`/`WEKNORA_HOST` for headless) |
| Retrieval surface (documented) | exists — the official DeepSeek-plugin description separates `weknora_search` ("hybrid retrieval returning source passages VERBATIM, each with a reusable knowledge_id") from `weknora_ask` ("WeKnora's own composed answer … over the RAG or the ReAct pipeline"). This independently CONFIRMS the Stage-14 split: retrieval hits in, LLM answers out of bounds. |
| Local container runtime | docker: NOT FOUND · podman: NOT FOUND · WSL: NOT INSTALLED |
| Local WeKnora / remote endpoint | none / none provided |
| POC documents ingested | **0** (ingestion impossible without a service) |
| Integration availability | **NOT AVAILABLE** |
| Secrets | none used, none recorded |

## 3. Architecture Path (and how far each hop is verified)

```text
Tool ──✓ verified (mock default + fail-closed branch, W2/F-03)
  ↓
KnowledgeProvider ──✓ verified (contract tests, C01–C11)
  ↓
WeKnoraAdapter ──✓ mapping/validation verified at FAKE level (W1/W5)
  ↓
transport ──✗ NOT BUILT (refused: would be an untested client against
  ↓            an unconfirmed endpoint — §四 forbids guessed APIs)
WeKnora Retrieval API ──✗ NOT REACHED (no service)
  ↓
Canonical Result ──✓ shape/schema verified for both backends (W4)
  ↓
Existing downstream consumer ──✓ verified (to_canonical + contract)
```

## 4. Gate Results

| Gate | Result | Evidence |
|---|---|---|
| G1 Real WeKnora retrieval | **NOT VERIFIED — infrastructure blocked** | no container runtime; integration suite skips |
| G2 Adapter mapping | PASS (fake-transport level) | W1 Case A: fake response → canonical, schema-valid |
| G3 Canonical contract | PASS | W4: mock and fake-WeKnora emit identical canonical shapes; one downstream consumer serves both |
| G4 Tool integration | PASS (fail-closed branch behaviorally; live happy path pending G1) | W2/F-03: ProviderError → tool `_fail`, no artifact, no mock continuation; mock-default tool path covered by the 408-test battery |
| G5 Fail-closed | PASS | W1 Cases C/E + W2 |
| G6 No Mock fallback | PASS | W2: configured-WeKnora failure ends in tool failure; no path substitutes mock |
| G7 Ask/ReAct isolation | PASS | W3: request payload allowlist (query/top_k/kb_id/filters only), verbatim DOC-prefixed passages, no ask/chat/react/answer/llm/prompt/model in any outbound payload; source inspection; README confirms retrieval surface exists separately from ask |
| G8 Invalid response handling | PASS | W1 Case C (4 shapes) + E (one malformed hit rejects the WHOLE response — documented semantics: no partial trust) |
| G9 Provider equivalence | PASS (contract compatibility, not quality) | W4: same keys/field sets/identifier presence/shared retrieval_method enum/score semantics/metadata compat |
| G10 Regression | PASS | 408 / 12 / 51-0-1 / 42-42 / compileall (below) |

Per §二十: G1 unverifiable ⇒ **Stage 14.2 = BLOCKED**, regardless of
G2–G10.

## 5. F-03 Result

**Covered.** `tests/runtime/test_p14_weknora_poc.py::W2` drives the
REAL tool function (`runtime/agent/tools.py::_knowledge_search`) with
an unconfigured WeKnora as the default provider and asserts
behaviorally: tool returns `status=failed` with the fail-closed
message, NO evidence artifact is written to state, no fabricated
knowledge appears in the failure payload, any ProviderError family
member hits the same seam, and the default is restored afterwards.
The 14.1 review's Type-D gap is closed at the level possible without a
live backend.

## 6. Existing Findings (recorded, NOT fixed — per §十五)

| ID | Status |
|---|---|
| F-01 orchestrator service path → local engine | **unchanged, deferred** (14.5 / production-cutover gate) |
| F-02 provider env missing → silent mock default | **unchanged, deferred** (strict startup enforcement before cutover) |
| F-04 service-locator selection / provider_raw_keys metadata | unchanged |
| F-05 tool comment names providers | unchanged |

New finding from this stage:

| ID | Severity | Finding |
|---|---|---|
| **F-06** | P1 (environmental, not architectural) | No container runtime on the pilot machine — WeKnora cannot be deployed locally; a remote instance or a Docker-capable host must be provided by the operator before the real POC can run. Not fixable in-repo. |

## 7. Scope Audit

CaseState / Scheduler / Planner / HITL / HOTL / Replan / Evidence
contract / Product Catalog / Recommendation / Persistence / R-05:
**NO** — all untouched (this stage changed tests + docs only; the
`tools.py` and `knowledge/provider/` diffs visible in git are the
uncommitted Stage-14.1 work, re-verified unchanged by this stage's
diff audit).

## 8. Test Results (Before → After → Delta)

```text
pytest tests/runtime -q       402 → 408   (+5 POC +1 integration-gate)  PASS
pytest tests/portfolio -q     12  → 12    (=)                            PASS
knowledge contract tests      52/52 (14.1, unchanged) + 33/33 (14.2 POC)
                              + 1/1 integration-skip acknowledgment
full regression (workbuddy)   51/0/1 → 51/0/1 (=; pre-existing GBK INFRA_ERROR)
benchmark                     42/42 → 42/42 (=)                          PASS
compileall                    PASS
integration (LIVE)            SKIPPED — no endpoint; NOT claimed as run
```

## 9. Real vs Fake vs Synthetic

```text
REAL:     nothing — no WeKnora instance existed to call. The API facts
          in §2 come from the OFFICIAL README (documented, not observed).
FAKE:     fake transport in test_p14_weknora_poc.py / 14.1 suite —
          canned responses through the REAL adapter mapping code.
SYNTHETIC: DOC-00x synthetic passages defined inline in the POC tests;
          zero real insurance content anywhere.
```

## 10. Unblock checklist for the real POC (operator actions)

1. Provide a Docker-capable host (or a running WeKnora v0.8.x instance
   + scoped API key). WeKnora's own bundled infrastructure (Postgres/
   Redis/vector) then lives entirely INSIDE WeKnora — still not
   Insurance Agent infrastructure.
2. Create a POC knowledge base; ingest ≤10 SYNTHETIC documents.
3. Set `INSURANCE_AGENT_WEKNORA_URL` (+ key/kb) and run
   `tests/runtime/test_p14_weknora_integration.py` — its first live
   run pins the real search endpoint path and validates the raw
   response contract against `map_weknora_response`'s documented
   assumption (any divergence fails closed, per W5 anti-fabrication).
4. Re-execute the G1–G10 table; only then may Stage 14.2 be re-graded.

## 11. Recommendation

Re-run Stage 14.2 (real POC) as soon as F-06 is unblocked. Do NOT
proceed to 14.3 (real knowledge ingestion) on top of an unverified
retrieval backend. No code changes are required to retry — the
adapter, contract tests, and gated integration suite are in place.
