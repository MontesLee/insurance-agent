# Phase 14.4 — Pre-Change Knowledge Runtime Trace (read-only, 2026-09-20)

Measured BEFORE any 14.4 change. Every entry carries a code citation.

## 1. Tool knowledge path (agent mode)

```text
runtime/harness/harness.py:61        task_type knowledge_search → stage
                                    product-candidate-provider
runtime/agent/tools.py:325-409      _knowledge_search:
  :334  default_provider().search()  ← 14.1 boundary (NO governance — F-07)
  :337-339  empty hits → _fail (fail-closed abstention)
  :348-364  builds evidence dicts MANUALLY from hits (E%03d ids,
            content[:400], no citation tuple)
  :366-385  artifact envelope knowledge-evidence (payload status/query/
            evidence/conflict + provenance[knowledge])
  :387-409  artifact-freeze respect → cs.put_artifact + reg.register
            (skip_eval — Harness owns eval)
```

## 2. Orchestrator knowledge path (stage-service mode) — F-01

```text
runtime/orchestrator.py:168,194,423,453,577,660
        run()/ _execute_stage → _run_stage_services(kb_dir=…)
:194    ev_loop.request_evidence(src, source_kind, purpose, kb_dir)
knowledge/evidence/loop.py:66-78     request_evidence(… engine, kb_dir …)
        → _provider.provide_evidence(query_artifact, top_k, engine, kb_dir)
knowledge/evidence/provider.py:91    eng = engine or build_engine(kb_dir)
:47-49  build_engine → skill invoke script → deterministic engine   ← BYPASS
:92-99  eng.search → to_dict → adapters…to_canonical → contract artifact
```

The orchestrator itself never touches the engine — the bypass lives in
`provide_evidence`. Fixing provider.py closes F-01 WITHOUT touching
runtime/orchestrator.py at all.

## 3. Evidence path (shared)

```text
adapters/knowledge_search_adapter.py:to_canonical  result dicts →
        canonical knowledge-evidence artifact (drops unknown fields —
        no citation passthrough today)
knowledge/evidence/provider.py:validate  jsonschema vs contracts/
        knowledge-{query,evidence}.schema.json (both request & response)
```

## 4. Provider path (14.1 boundary — intact)

```text
knowledge/provider/__init__.py   default_provider / build_named_provider /
        set_default_provider  (env INSURANCE_AGENT_KNOWLEDGE_PROVIDER,
        default mock; unknown → ProviderConfigError; weknora w/o
        transport → ProviderUnavailable at search — no fallback)
knowledge/provider/mock.py       MockKnowledgeProvider (lazy
        knowledge.evidence.provider.build_engine — the seam existing
        empty-engine tests monkeypatch: tests/runtime/
        test_agent_tools.py:162-167, test_knowledge_evidence.py:75-81)
knowledge/provider/weknora.py    adapter seam only (14.2 BLOCKED stands)
```

## 5. Direct deterministic-engine constructions (all call sites)

| Site | Role | Verdict for 14.4 |
|---|---|---|
| knowledge/evidence/provider.py:47-49 build_engine | used by provide_evidence:91 (RUNTIME — F-01) | remove from the runtime path; keep the helper for the mock's lazy build + test-injection seam (14.1 suite asserts its existence) |
| knowledge/provider/mock.py:_build | provider-internal engine reuse | ALLOWED (Mock is a provider implementation) |
| .trae/skills/knowledge-search/scripts/invoke-knowledge-search.py build_engine | skill CLI entry | unchanged |
| domain/insurance/scripts/build_domain_engine.py | domain-pack scripts | test/script infra — out of runtime scope |
| tests (contracts/evidence/agent_tools/knowledge_evidence) | test infra + monkeypatch seam | preserve working |

## 6. kb_dir inventory (who passes what)

| Caller | kb_dir value | Governance impact |
|---|---|---|
| runtime/server.py:318, demo.py:138, evals/agent-benchmark/run_agent_benchmark.py:167, test-cases/e2e/full-agent/run_full_agent_e2e.py:105 | None (default fixtures KB) or kb-empty ONLY | default registry must cover the 6 fixtures docs; empty KB → abstain (unchanged) |
| tests/evidence/run_evidence_dataset.py:83-84 | engine=FakeConflictEngine injection (DOC-A/DOC-B, chunks FAKE-A/B) | needs a governed service injection for the fake docs |

No runtime caller ever passes a third KB directory.

## 7. Governance callers BEFORE 14.4

```text
tests/runtime/test_p14_governance.py   (library-level only)
runtime/: NONE — F-07
```

## 8. Change plan implied by this trace

1. knowledge/service.py — KnowledgeService = provider + registry +
   governance + evidence builder (single implementation, composition
   root for the default governed stack; stamps projection wired here).
2. knowledge/evidence/provider.py — provide_evidence routes through
   the service (kb_dir passthrough); build_engine demoted to a
   provider-internal/test helper, no longer on the runtime path.
3. runtime/agent/tools.py — _knowledge_search uses default_service();
   evidence items become governance-built (full citation tuple,
   chunk-id evidence ids, full content — hash-verifiable).
4. adapters/knowledge_search_adapter.py — ADDITIVE citation-field
   passthrough (absent fields → old behavior byte-identical).
5. Default registry covers the fixtures KB (6 docs, project-authored
   synthetic, B/CN/open-window/ALLOWED) + the 14.3 gov fixtures.
6. tests/evidence/run_evidence_dataset.py — inject a governed service
   for the fake-conflict engine (assertions unchanged).
7. New suite tests/runtime/test_p14_governance_runtime.py — online
   negatives A–E, positive, dual-path consistency, bypass scan,
   invariants K1–K4.

No orchestrator/scheduler/planner/HITL/HOTL/approval/mode/R-05/catalog/
recommendation/report changes. No new governance rules. No schema
file changes.
