# The Insurance Domain (reference workload)

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](insurance-domain.zh-CN.md)

Insurance is the **reference domain** used to demonstrate the Agent Runtime
architecture — not a pasted-on example. The domain's hard questions (what
is a fact, what may influence a recommendation, where does evidence come
from) are exactly what shaped the runtime's boundaries (contamination
checks, provenance gates, catalog invariants).

## 1. The analysis pipeline

Implemented as the workflow `runtime/insurance-analysis.yaml` (9 stages +
1 shared service); each stage is a Skill in `.trae/skills/` with its own
contract and evals:

```text
FACT          client-intake            client-profile          (dialogue/provided)
   ↓
REQUIREMENT   requirement-analysis     requirement-analysis     (dialogue/provided)
   ↓
RISK          risk-analysis            risk-assessment          (dialogue/provided)
   ↓
GAP           coverage-gap-analysis    coverage-gap-analysis    (deterministic engine)
   ↓
SOLUTION      solution                 solution-plan            (deterministic engine)
   ↓
EVIDENCE      knowledge-search         knowledge-evidence       (shared RAG service)
PRODUCT       product-candidate-provider  product-candidates    (deterministic engine)
   ↓
RECOMMEND     product-recommendation   product-recommendation   (deterministic engine)
   ↓
REPORT        report-generation        insurance-report         (deterministic engine)
```

Responsibilities in one line each: **FACT** collects client facts as
four-tuples (value/status/source/confidence) without judgment;
**REQUIREMENT** turns facts into prioritized needs (product-agnostic);
**RISK** identifies and prioritizes exposures; **GAP** quantifies
unprotected amounts; **SOLUTION** designs a strategy-level plan
(product-agnostic by contract); **EVIDENCE** retrieves sourced knowledge;
**PRODUCT** filters catalog candidates; **RECOMMEND** maps solution
directions to concrete products; **REPORT** synthesizes the final
analysis report.

## 2. Solution vs product recommendation — a deliberate separation

`solution-plan` and `product-recommendation` are separate artifacts,
separate skills and separate eval gates (ADR-006). The analysis layer
(requirement/risk/gap/solution) is **contamination-checked**: eval fails
if any concrete product, company or product id leaks into it. Only the
catalog-backed layer ever names products. This is what keeps "analysis"
honest and makes the recommendation traceable to catalog entries rather
than to LLM invention.

## 3. Product catalog safety

`catalog/product-catalog.v0.1.json` is a **demo catalog** and says so
structurally:

- `is_demo: true` at catalog and product level; insurer names are
  fictional (`demo-insurer-A` …); a `notice` field states the demo basis.
- Versioned: `catalog_version`, per-product `product_version`,
  `effective_from`/`effective_to` dates, premium basis declared.
- The candidate provider only proposes catalog entries; eval invariants
  (`catalog_exists`, `catalog_has_primary_product`) fail any product id
  not in the catalog, and repair action `DROP_INVALID_PRODUCTS` removes
  them from the input side before re-running.

> This repository does **not** contain live insurer product data. All
> products are fictional demo entries with explicit versioning.

## 4. Knowledge / RAG (fail-closed)

```text
query → normalize → retrieve → RRF fuse → over-retrieval → rerank → evidence
```

- The engine (`knowledge/rag/engine.py`) hard-codes no judgment: scoring
  weights, source-quality mapping, thresholds and conflict keys come from
  rules JSON inside the knowledge-search skill.
- The **shared Evidence Provider** (`knowledge/evidence/provider.py`) is
  the single seam any skill uses to obtain evidence; requests and
  responses are contract-validated (`knowledge-query` /
  `knowledge-evidence` schemas).
- **Fail-closed**: when retrieval abstains (insufficient evidence), the
  empty result propagates verbatim — nothing is fabricated, downstream
  stages stop rather than consume invented knowledge, and the eval gate
  `required_non_empty` fails empty evidence artifacts.
- The corpus is a **small local demo knowledge base**
  (`.trae/skills/knowledge-search/evals/fixtures/kb`). No external or
  live insurance database is connected; provenance fields point into this
  local corpus.

## 5. Where the domain meets the runtime

| Domain rule | Runtime mechanism |
| --- | --- |
| Analysis must not name products | `contamination` eval check |
| Recommendations must be catalog-backed | `invariant` eval checks + repair |
| Evidence must be sourced | `provenance` eval checks + evidence contract |
| Facts come from the client, not the LLM | dialogue adapters + four-tuple provenance |
| Report must be traceable | artifact lineage (report → … → client facts) |
| Missing/conflicting client facts stop the case | client-information gate → `WAITING_FOR_USER` |
