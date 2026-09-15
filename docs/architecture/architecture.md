> 🌐 **Language:** 🇨🇳 [中文版](architecture.zh-CN.md) · 🇺🇸 English

# Architecture Overview

> Audience: interviewers / new contributors. This document answers three questions: **what the
> system looks like**, **who executes each layer**, and **why it is layered this way**.
> Companions: `README.md` (entry point), `docs/adr/` (design decisions),
> `docs/architecture/orchestration.md` (orchestration details),
> `docs/architecture/execution-trace.md` (observability),
> `docs/architecture/failure-taxonomy.md` (failure taxonomy).

---

## 1. One Diagram

```text
                              Customer
                                 │  (dialogue / form, executor: provided)
                                 ▼
                        ┌──────────────────┐
                        │   Orchestrator   │  runtime/orchestrator.py
                        │ (the only loop)  │  + runtime/insurance-analysis.yaml (declarative single source of truth)
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │     CaseState    │  runtime/state/case_state.py   ← the single source of truth across Skills
                        │ artifacts/tasks/ │  runtime/state/transitions.py  ← monotonicity / preconditions / freezing
                        │ registry/evals/  │  runtime/artifact_registry.py ← lineage + fingerprints
                        └────────┬─────────┘
                                 │
                        ┌────────▼─────────┐
                        │   Skill Graph    │  8 Specialist Skills (one artifact per layer)
                        └────────┬─────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
  Business Skills          Evidence / RAG            Product Catalog
  (gap/solution/report)    (knowledge-search)        (demo, versioned)
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 ▼
                            Artifacts
                                 │
                                 ▼
                           Eval (deterministic, 6 check families)
                          ↙                        ↘
                       PASS                        FAIL
                        │                            │
                        │                         Repair (localized rerun)
                        │                            │
                        │                          Rerun
                        └─────────────┬──────────────┘
                                      ▼
                                 Checkpoint  (persist + validate; never resume from a corrupted state)
                                      │
                                      ▼
                                   Report
                                      │
                                      ▼
                          Benchmark / Trace / Demo
```

**Executor markers** (required by §27):

| Marker | Meaning | Where it lands |
|---|---|---|
| `Deterministic` | Pure rule engines; same input always yields same output; unit-testable | engines of `coverage-gap-analysis` / `solution` / `product-candidate-provider` / `recommendation` / `report-generation`; `eval_engine` / `repair` / `checkpoint` / `transitions` |
| `LLM` | Produced by conversational Skills (no model call is embedded in this repo; artifacts are injected as files) | the three upstream stages `client-intake` / `requirement_analysis` / `risk-analysis` (`executor: provided`) |
| `RAG` | Shared Evidence Provider (`knowledge/rag/` storage + `knowledge/evidence/loop.py` controlled loop) | `knowledge-search` (a non-linear Provider in `services:`, not a stage) |
| `External Data` | External product data source; currently a demo catalog, replaceable | `catalog/product-catalog.v0.1.json` (`is_demo=true`), isolated behind the Product Provider abstraction |

---

## 2. Skill Graph (8 layers, one-way data chain)

```text
FACT ─► REQUIREMENT ─► RISK ─► GAP ─► SOLUTION ─► PRODUCT ─► REPORT
```

| # | Skill | Answers | Artifact | Executor | Key constraints |
|---|---|---|---|---|---|
| 01 | client-intake | What **facts** does the client have? | ClientProfile | LLM (provided) | FactValue = value/status/source/confidence; UNKNOWN is never written into answered_fields |
| 02 | requirement-analysis | What **problems** to solve? | RequirementAnalysis | LLM (provided) | coverage_gaps are **hints** only, not the final gap list |
| 03 | risk-analysis | What **risks** is the client exposed to? | RiskAssessment | LLM (provided) | Three states IDENTIFIED/NOT_IDENTIFIED/UNDETERMINED; UNDETERMINED is never promoted to a Risk |
| 04 | coverage-gap-analysis | Where is existing coverage **insufficient**? | CoverageGapAnalysis | Deterministic | **Independent judgment layer**: does not copy severity/likelihood, references `risk_id` only; **carries no monetary fields** |
| 05 | solution | What **strategy** to adopt? | SolutionPlan | Deterministic | No concrete product names / company names (strategy ≠ product) |
| — | knowledge-search | What **evidence** is available? | KnowledgeEvidence | RAG (shared service) | Non-linear Provider; the loop is read-only (`source_unchanged`) |
| 06 | product-candidate-provider | Which products **qualify**? | ProductCandidates | Deterministic | Candidate generation only (type/direction/eligibility/evidence checks); **no ranking, no primary pick** |
| 07 | product-recommendation | Which **products** implement the strategy? | ProductRecommendation | Deterministic | Hard-rejects any candidate that fails product validation; never disguises a strategy as a product |
| 08 | report-generation | Aggregate / normalize / render | InsuranceReport | Deterministic | Reports only, makes no autonomous insurance judgments; canonical-first |

> **Candidate Generation and Recommendation must be separated** — no single stage may "think of a product → generate the product → recommend the product."

---

## 3. Control Plane (Agent Runtime)

| Component | File | Responsibility |
|---|---|---|
| Orchestrator | `runtime/orchestrator.py` | The main loop `next_runnable → run → eval → PASS/FAIL → repair → checkpoint`; gate policy `stop` |
| Workflow declaration | `runtime/insurance-analysis.yaml` | **Single source of truth** for stage order / artifact production-consumption / executors / gates |
| CaseState | `runtime/state/case_state.py` | `artifacts / artifact_registry / tasks / evaluations / checkpoints / services / events / trace` |
| Transitions | `runtime/state/transitions.py` | Three invariants: **monotonicity** (NON_MONOTONIC) / **preconditions** (MISSING_INPUT_ARTIFACT + INPUT_NOT_RELEASED) / **freezing** (ARTIFACT_MUTATION, sha256) |
| Artifact Registry | `runtime/artifact_registry.py` | ART-ID / lineage / fingerprint / evidence_refs; stores metadata only, never copies content |
| Eval Engine | `runtime/eval_engine.py` | 6 deterministic check families: schema / required_fields / contamination / provenance / cross_artifact / invariant (+ required_non_empty) |
| Repair | `runtime/repair.py` | Failed checks → action mapping (RERUN_FROM_UPSTREAM / DROP_INVALID_PRODUCTS); modifies **inputs** only, never a frozen artifact |
| Checkpoint | `runtime/checkpoint.py` | save / load / validate (5 checks) → any corruption is `CHECKPOINT_INVALID`; never resumes silently |
| Trace | `runtime/trace.py` | Structured execution trace (13 event types + `duration_ms`), externalized to `<case_dir>/trace.jsonl` |
| Observability | `runtime/observability.py` | per-skill latency / call counts / repair counts / knowledge-search counts — answers "how many Skill calls does one case take" |

---

## 4. Upstream/Downstream Boundaries (Data Plane)

```text
ClientProfile ─► RequirementAnalysis ─► RiskAssessment ─► CoverageGapAnalysis
      ─► SolutionPlan ─► (KnowledgeEvidence) ─► ProductCandidates
      ─► ProductRecommendation ─► InsuranceReport
```

- **One-way**: no layer may overstep (`risk-analysis` recommends no products and re-produces no requirements).
- **Explicit boundaries**: each Skill's input key names / shapes differ; they are declared centrally in the YAML `input_map` (`{artifact_type: {key, shape}}`) — **not left to convention**.
- **Adapter boundary**: the `report-generation` engine returns its **native Skill result** (not a canonical envelope); `post_adapter: adapters.report_generation_adapter.to_canonical` wraps it. All other stages call `make_envelope` inside their invoke scripts.

---

## 5. Why This Layering (maps to README §"Why designed this way")

| Design | One-line rationale |
|---|---|
| Skills never call the next Skill directly | Direct calls burn "who needs what" into code; the Orchestrator reads declarative YAML instead, so adding/reordering stages touches no Skill |
| An Orchestrator is required | You need a hub with **zero business judgment**: it only moves artifacts, validates contracts, enforces order, and stops at gates |
| Artifacts are required | Layers communicate via **structured contracts** rather than free-text dialogue — only then can results be validated, diffed, and audited |
| Eval is independent of Skills | A Skill grading itself "passed" means nothing; validation must be executed by a component that did not produce the result |
| Evidence must carry provenance | An insurance conclusion without `document/chunk` traceability is a hallucination; attribute-level grounding further demands "which evidence supports this claimed product attribute" |
| Candidate and Recommendation are separated | Generation and selection are split so a product cannot "recommend itself" (self-certification) |
| UNKNOWN is not FALSE | Missing information ≠ the fact being false; folding UNKNOWN into PASS is a **fabricated pass**, hence it is an explicit third state |
| Failure is not infinite retry | The budget is an upper bound, not a quota (`max_attempts=3`); exhaustion escalates to `NEEDS_REVIEW` for a human |

---

## 6. Run Artifacts on Disk

```text
<root>/<case_id>/
  case_state.json          # snapshot of the single source of truth (incl. trace[] / evaluations[] / checkpoints[])
  artifacts/<type>.json    # one file per artifact, diffable
  trace.jsonl              # structured trace (aggregatable across runs)
```

> Run artifacts under `tmp/` (the regression run directory) are **not part of the baseline**;
> the repo baseline contains only code, contracts, datasets, and documentation.
