# Phase 14.4 — Governance Runtime Integration Report

Date: 2026-09-20 · Scope: close F-01 + F-07; single runtime knowledge
path. Pre-change trace: phase14-p4-pre-change-trace.md (read-only,
produced before any edit).

## 1. Status

```text
Phase 14.4 = PASS  (all 12 acceptance gates green)
```

## 2. F-01 Closure

```text
BEFORE:  orchestrator → evidence loop → provide_evidence → build_engine
         (deterministic engine directly; future WeKnora would have left
          this path on a second, local knowledge source)
AFTER:   orchestrator → evidence loop → provide_evidence
         → KnowledgeService (knowledge/service.py)
         → KnowledgeProvider → Governance → evidence
```
`runtime/orchestrator.py` was NOT modified at all — the bypass lived
inside `knowledge/evidence/provider.py:91`, and closing it there closes
the whole stage-service path. `build_engine` survives only as (a) the
mock provider's lazy internal build seam (mock = provider
implementation — allowed) and (b) a test-injection helper that now
carries `_kb_dir` so the service can PAIR the engine with the right
registry.

## 3. F-07 Closure

```text
BEFORE:  governance tested at library level only; the tool built
         evidence items manually from ungoverned hits
AFTER:   governance is the MANDATORY runtime gate:
         tool → default_service().build_evidence() and
         evidence loop → provide_evidence → same service —
         items exist ONLY for governance-allowed hits (K002),
         built by knowledge/governance's single implementation.
```

## 4. Call Graph (as implemented)

```text
composition root: knowledge/service.py (default_service / set/reset;
                  provider priority: explicit injection > env > stamped
                  default mock; registry per KB via registry_for)
   ├─ Tool path:  runtime/agent/tools.py::_knowledge_search
   │                → default_service().build_evidence(query, top_k=5)
   │                → governed items → knowledge-evidence artifact
   │                  (envelope unchanged; items now carry the
   │                   citation tuple + governance block)
   └─ Orchestrator path: knowledge/evidence/loop.py::request_evidence
         → knowledge/evidence/provider.py::provide_evidence
         → service (explicit / kb_dir-paired / default)
         → governed_output → adapters.to_canonical (additive citation
           passthrough) → canonical knowledge-evidence contract
```

## 5. Governance Boundary

ONE implementation: `knowledge/governance/` (untouched semantics —
the 14.3 suite passes 74/74 unmodified). The service DELEGATES
(govern_search_result / build_evidence_item / validate_hit); it
contains no rule copies (asserted structurally). No new rules, no
scores, no LLM.

## 6. Provider Boundary

`KnowledgeProvider.search()` is the only retrieval verb the runtime
sees. Provider selection happens exclusively at the composition
boundary (service + knowledge/provider); the tool/loop never branch on
provider identity. A KB is deployed AS A PAIR with its registry
(`registry_for`): fixtures-KB, gov-fixtures-KB and the domain-pack KB
each have their own table (their filename stems collide — one global
registry would be identity-ambiguous); an EMPTY KB governs to an empty
registry (honest abstention); an UNKNOWN non-empty KB raises — never
auto-registered (fabricating ALLOWED would violate the license
fail-closed rule).

## 7. Negative Tests (online, real entry points)

A expired (2024 edition at today's as-of; plus fixed-date service
check: as-of 2026 → zero V2024 items) · B jurisdiction (CN-BJ rule vs
national query → no evidence) · C license UNKNOWN (gov_web_notes
yields nothing) · D registry conflict (forged provider authority S vs
registry B → that document yields nothing) · E hash mismatch (tampered
registry hashes → document excluded; tool path consistent). All
through `_knowledge_search` / the service — not library shortcuts.

## 8. Bypass Scan (K001)

Function-span-aware scan of runtime/orchestrator.py,
runtime/agent/tools.py, knowledge/evidence/{loop,provider}.py: zero
engine constructions on runtime paths (the legacy `build_engine`
helper body is the sanctioned seam; `from knowledge.rag` never
imported there). Positive proof: the two REAL paths (tool vs
provide_evidence with identical query) agree on every citation field
per shared chunk (K004 dual-path consistency section).

## 9. Regression

```text
full regression (workbuddy)  51 PASS / 0 FAIL / 1 pre-existing GBK
                             INFRA_ERROR — identical to baseline
pytest tests/runtime -q      421 passed (415 + 6 new runtime-integration)
pytest tests/portfolio -q    12 passed
benchmark                    42/42
compileall                   PASS
14.1 provider suite          52/52 (one wiring assertion evolved with
                             the boundary: tool→service; the
                             no-direct-engine invariant unchanged)
14.2 POC suite               33/33 (F-03 test now exercises the service
                             path; caught and fixed a REAL composition
                             gap — service initially bypassed the
                             provider injection seam)
14.3 governance suite        74/74 (semantics untouched)
14.4 runtime suite           52/52 (new)
```

Mid-integration regressions found and fixed (all test-driven): (1)
e2e-product-rec + step4-p8 used the DOMAIN-pack KB through `engine=`
— solved by the KB↔registry pairing, not by weakening governance;
(2) the default service once cached a provider across injection
changes — now rebuilt on injection-identity change; (3) the
fake-conflict evidence dataset needed a governed service injection
(assertions unchanged).

## 10. Remaining Concerns

- F-02 unchanged (env-missing → mock default; strict-mode startup
  enforcement remains the production-cutover gate — NOT this phase).
- F-04/F-05/F-06 unchanged. F-08 (NEW, P2, performance): each
  KnowledgeService instance lazily builds its engine/registry; the
  default service is cached per process, but injection-heavy tests
  rebuild per instance — a composition-level cache is a later
  optimization, measured acceptable (full pytest battery ~4:40).
- `engine=`/`kb_dir=` params on provide_evidence remain as TEST-seams
  with fail-closed semantics (unknown KB → RegistryError; unregistered
  docs → all hits rejected); production callers use the default or an
  explicitly injected service.

## 11. WeKnora Boundary

No WeKnora, no Docker, no external API, no databases. The 14.2 BLOCKED
verdict stands. When WeKnora arrives it plugs in as ONE provider under
the SAME service/governance — nothing in this phase is WeKnora-specific.

## 12. Acceptance Gates

G1 F-01 CLOSED ✓ · G2 F-07 CLOSED ✓ · G3 single provider boundary ✓ ·
G4 single governance ✓ · G5 governance fail→no evidence ✓ · G6 provider
fail→no fallback ✓ · G7 tool/orchestrator consistency ✓ · G8 bypass
scan PASS ✓ · G9 74/74 ✓ · G10 52/52 ✓ · G11 33/33 ✓ · G12 full
regression PASS ✓
