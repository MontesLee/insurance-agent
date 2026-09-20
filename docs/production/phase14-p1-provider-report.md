# Phase 14.1 — KnowledgeProvider Contract + Mock Report

Date: 2026-09-19 · Scope: 14.1 ONLY. No WeKnora connection, no Docker,
no database, no runtime semantic change, no real knowledge.

## 1. Objective

Establish the stable boundary so agents never see a knowledge backend:

```text
Agent → Knowledge Tool → KnowledgeProvider → ┬ MockKnowledgeProvider
                                              └ WeKnoraKnowledgeProvider
```

Mock serves tests/offline regression over the UNCHANGED deterministic
engine; WeKnora is an adapter seam only (injected transport, no
network). Provider selection lives at the composition boundary
(env/injection), never inside tool logic, and every failure mode is
fail-closed with NO silent fallback.

## 2. Architecture Before

`runtime/agent/tools.py::_knowledge_search` imported
`knowledge.evidence.provider.build_engine` directly and called
`engine.search()` — the tool was hard-wired to the one concrete engine.
(The orchestrator's evidence-service path via `provide_evidence` also
builds the engine; that path is UNTOUCHED in 14.1 — see §14.)

## 3. Architecture After

```text
knowledge/provider/            NEW package (imports nothing from runtime/)
  base.py        Protocol (search only) + canonical model + error taxonomy
  mock.py        MockKnowledgeProvider → EXISTING engine (zero engine change)
  weknora.py     WeKnoraKnowledgeProvider + map_weknora_response (pure) +
                 injected transport; retrieval surface ONLY
  __init__.py    composition boundary: default_provider / set/reset /
                 build_named_provider; env INSURANCE_AGENT_KNOWLEDGE_PROVIDER
runtime/agent/tools.py          +12/−4: default_provider().search() with
                                ProviderError → _fail (fail-closed)
tests/runtime/test_p14_provider.py   5 sections / 52 checks (C01–C11)
```

## 4. KnowledgeProvider Contract

Implemented NOW — `search(query, filters=None, top_k=None) ->
KnowledgeSearchResult` — the only method with a current caller (the
knowledge tool). Evaluated and DELIBERATELY DEFERRED (no caller today;
anti-interface-completeness rule):

| Method | Who would call | Verdict |
|---|---|---|
| `get_source/get_document/get_version` | 14.3 governance/registry | defer to 14.3 |
| `resolve_evidence` (hash+window re-verify) | 14.5 provenance integrity | defer to 14.5 |

Forbidden by design: `save_/update_/delete_document`, `query_database`
(database thinking), and ANY ask/chat/react/answer verb (Ask-isolation).

`KnowledgeFilters` (as_of / allow_history / jurisdiction /
authority_min / source_types / domains) is declared and PRESERVED into
retrieval_metadata — enforcement is 14.4, not smuggled into 14.1.

## 5. Mock Provider

`MockKnowledgeProvider` reuses the EXISTING construction path
(`knowledge.evidence.provider.build_engine` — same rules, same KB) and
translates `RetrievalResult → KnowledgeSearchResult`. It is not a new
engine; determinism is inherited (C10: identical canonical dicts across
instances/queries).

## 6. WeKnora Adapter Seam

`WeKnoraKnowledgeProvider(transport=callable, kb_id=...)` — transport
is INJECTED; 14.1 ships none. `map_weknora_response` is a pure
strict-validating function: the documented raw-response contract
(content/score/metadata{document_id, chunk_id, ...}) is an ASSUMPTION
to verify in the 14.2 POC against the live API; violations raise
`ProviderResponseInvalid`. `retrieval_method` maps into the canonical
contract enum (`hybrid_rrf`) — a first-draft `weknora_hybrid` was
caught by the contract test (C11) and corrected: provider identity
lives in `retrieval_metadata.provider`, never in shared enums.

## 7. Canonical Result

`KnowledgeSearchResult.to_dict()` is shape-compatible with the engine's
`RetrievalResult.to_dict()`, so the EXISTING
`adapters/knowledge_search_adapter.to_canonical` and
`contracts/knowledge-evidence.schema.json` consume mock AND fake-WeKnora
output unchanged (C02/C03/C11). Hits carry provenance anchors
(chunk/document/section/source_level), a RESERVED `version_id` (empty
until the 14.3 registry), and `content_hash` (sha256 of content —
tamper-evidence across external roundtrips).

## 8. Ask Isolation

Structural (C07): no ask/chat/react/answer/agent/llm method exists on
the adapter; no LLM-answer entry point in its source; no network client
imports anywhere in the package. WeKnora's answer mode is unreachable
by construction, not by convention.

## 9. Failure / Fallback Policy

| Failure | Behavior |
|---|---|
| Provider unavailable (weknora, no transport) | `ProviderUnavailable` → tool `_fail` (task FAIL path) |
| Unknown/empty provider name (env or build) | `ProviderConfigError` — never defaults to mock |
| Invalid backend response | `ProviderResponseInvalid` — malformed data never becomes evidence |
| Any `ProviderError` at the tool | `_fail("knowledge provider failed (fail-closed, no fallback)")` |

C06 proves the negative: a selected-but-unconfigured WeKnora RAISES and
never returns mock results; there is no code path that substitutes
providers on failure.

## 10. Tests (tests/runtime/test_p14_provider.py — 52/52, dual-mode)

C01 protocol conformance · C02 canonical conversion through the REAL
adapter+schema · C03 fake-WeKnora mapping (ids/version preserved) ·
C04 nine invalid-response shapes fail closed (+ empty set =
insufficient_evidence, not error) · C05 unavailable · C06 no silent
fallback / config errors / explicit-injection precedence · C07 Ask
isolation · C09 provenance preservation + hash verification · C10
determinism · C11 interchangeability (same canonical STRUCTURE, both
backends, provider identity confined to retrieval_metadata) · plus
boundary-direction (provider imports no runtime) and tool-wiring
checks. Layers: Unit = mapping; Contract = interchangeability;
Regression = existing suites (below). No network tests.

## 11. Regression (Before → After → Delta)

```text
pytest tests/runtime -q        397 → 402   (+5 provider tests)  PASS
pytest tests/portfolio -q      12  → 12    (=)                  PASS
full regression (workbuddy)    51/0/1 → 51/0/1 (=; the 1 INFRA_ERROR is
                               the pre-existing step3-mutation GBK issue)
  incl. contracts 10/10, evidence-invariants ALL GREEN,
  evidence-dataset ALL GREEN, step4-p7 grounding 24/24
benchmark standalone           42/42 → 42/42 (=)                PASS
compileall (knowledge/runtime/tests)                             PASS
```

## 12. Files Changed

```text
NEW  knowledge/provider/{__init__,base,mock,weknora}.py
NEW  tests/runtime/test_p14_provider.py
NEW  docs/production/phase14-p1-provider-report.md      (this file)
MOD  runtime/agent/tools.py            (+12/−4 — the sanctioned injection
                                        point; only runtime touch)
MOD  evals/agent-benchmark/results.json (1-line timestamp artifact of
                                        re-running the benchmark battery)
(pre-existing untracked: phase14 audit/plan docs from Phase 1)
```

## 13. Runtime Boundary

Scheduler / Planner / Harness / HITL / HOTL / Replan / MessageBus /
Approval / Product Catalog / Recommendation logic / R-05 / persistence
(CaseState, Harness, Approval, Artifact): **UNCHANGED** — verified by
diff scope (one tool function) and the full battery. The deterministic
engine is NOT deleted or modified; `knowledge.evidence.provider.
build_engine / provide_evidence` remain intact for the orchestrator
evidence-service path.

## 14. Known Limitations

- The orchestrator's evidence-service path (`provide_evidence`) still
  acquires the engine directly; it adopts the provider boundary in
  14.5 when the evidence contract is extended (deliberate minimal-diff
  decision — its behavior is identical today since the mock wraps the
  same engine).
- The WeKnora raw-response contract is an assumption until the 14.2
  POC validates it against the live API; the strict mapper makes any
  divergence fail loud, not silent.
- `version_id` is carried but empty (14.3 registry); filters are
  preserved but not enforced (14.4). Both are recorded, not smuggled.
- Provider selection has no auth/TLS/config-file story yet — arrives
  with the real transport in 14.2.

## 15. Exit Criteria (Definition of Done) — all met

Tool→Provider ✓ · Mock→existing engine ✓ · WeKnora seam without service
✓ · PostgreSQL/Redis/VectorDB = 0 ✓ · no runtime semantic change ✓ ·
no silent fallback ✓ · contract tests PASS (52/52) ✓ · existing tests
PASS (402/12/51-0-1/42) ✓ · compileall + git diff --check PASS ✓.

## 16. Recommendation for 14.2

Proceed to the WeKnora POC on this seam: standalone deployment
(operator, docker), ≤10 synthetic documents, real transport wired into
`WeKnoraKnowledgeProvider`, retrieval-API-only verification (Ask path
stays unexposed), id/metadata round-trip validation against the
documented raw-response contract, and the existing retrieval evals run
over WeKnora results (integration tests INFRA-gated). Inputs from
14.1 to carry forward: the canonical enum constraint on
`retrieval_method`, the strict mapper as the divergence detector, and
the no-fallback policy as a deployment invariant.
