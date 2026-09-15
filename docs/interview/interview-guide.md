> 🌐 **Language:** 🇨🇳 [中文版](interview-guide.zh-CN.md) · 🇺🇸 English

# Interview Guide — Q&A

Ten questions an Agent Developer / Agent PM interviewer is likely to ask, with a 30-second answer,
a 2-minute deep dive, and the exact code location to point at.

---

## Q1 — Why not just a simple workflow / DAG?

**30s:** A static DAG assumes every step always succeeds or fails predictably. Real agents hit
*unknown* inputs, missing evidence, and contradictory facts. I needed a runtime that treats
**state, artifacts, eval, repair, evidence, and checkpoint as first-class concepts**, not nodes in a
graph.

**2min:** The orchestrator does not hard-code a for-loop. Each round it asks the state layer
`next_runnable(state, workflow)` and `can_run(state, stage)`. That means a stage that cannot proceed
(e.g. no seed, missing evidence) genuinely *blocks* rather than being skipped. The DAG's edges are
declared in `insurance-analysis.yaml`; adding/reordering a stage is a YAML change, not a code change.

**Code:** `runtime/orchestrator.py` · `runtime/state/transitions.py` · `runtime/insurance-analysis.yaml`

## Q2 — Why do you need a CaseState?

**30s:** Because "what does the agent know right now" must be an explicit, queryable, immutable
source of truth shared across all skills — not something each skill re-derives from its own memory.

**2min:** `CaseState` is the single shared blackboard: artifacts, artifact registry (lineage +
fingerprint), task ledger, evaluations, checkpoints, events, trace. Three invariants are machine
checked: **monotonicity** (no stage rollback), **preconditions** (a stage's producer must be
`COMPLETED` before it is consumed), and **immutability** (a published artifact whose sha256 changed
= `ARTIFACT_MUTATION`). `UNKNOWN` is a first-class third state — missing data is never silently
treated as `FALSE`.

**Code:** `runtime/state/case_state.py` · `runtime/state/transitions.py`

## Q3 — Why not let the LLM judge its own output (eval)?

**30s:** Because the component that *produces* a result cannot credibly *grade* it. Eval must be
independent of the producer.

**2min:** `eval_engine.py` is a deterministic rule engine: `schema`, `required_fields`,
`contamination` (upstream boundary crossing), `provenance`, `cross_artifact`, and `invariant`
checks. Anything it cannot determine is a **FAIL** — there is no `MANUAL`/`UNKNOWN` pass path. This
is what makes the safety gates (product hallucination = 0, provenance failure = 0, invalid
continuation = 0) trustworthy.

**Code:** `runtime/eval_engine.py` · `runtime/resources/config/eval.rules.json`

## Q4 — Why is repair capped at 2 attempts?

**30s:** Retry budget is an *upper bound, not a quota*. Re-running a fundamentally broken input
forever just amplifies cost and hides the root cause.

**2min:** `repair.py` maps a failed check to an action (`RERUN_FROM_UPSTREAM`,
`DROP_INVALID_PRODUCTS`). It only changes a stage's *inputs*, never a frozen artifact. After 2
repairs the stage is `NEEDS_REVIEW` and the human (or a downstream gate) decides — the agent does not
loop itself into a hallucination to escape failure.

**Code:** `runtime/repair.py` · `AGENTS.md` (`MAX_REPAIR_ATTEMPTS = 2`)

## Q5 — How does the agent prevent a hallucinated product?

**30s:** The product catalog is an explicit trust boundary. A recommended product must exist in the
catalog and be reachable through a validated candidate — no product enters the report by assertion
alone.

**2min:** Three layers: (1) `product-candidate-provider` only *generates* candidates, it does not
rank; (2) `product-recommendation` hard-rejects anything failing `candidate_known` and the additive
`catalog_has_primary_product` invariant (the product ID must exist in `catalog.product_ids`);
(3) the report layer runs a `FABRICATED_PRODUCT` guardrail that refuses any product not in the
candidate set. A hallucinated ID (`C999`, `CATALOG_NON_EXISTENT`) yields `primary = 0`,
`unverified_products = []`, and no product in the report.

**Code:** `runtime/resources/config/eval.rules.json` (`candidate_known`, `catalog_has_primary_product`,
`catalog_exists`) · `tests/workflow/test_step4_phase13_guardrails.py`

## Q6 — Why does provenance need `document_id` + `chunk_id`?

**30s:** A claim backed only by "the knowledge base" is not auditable. You must be able to point at
the exact sentence that supports it.

**2min:** The eval requires every evidence reference to carry `evidence_id` + `document_id` +
`chunk_id`. Attribute-level grounding then checks a specific product attribute against a specific
chunk. This is what turns "we think this covers outpatient" into "chunk #X of document #D states
outpatient is covered." It is also why a missing/empty `chunk_id` is rejected, not forgiven.

**Code:** `knowledge/evidence/` · `runtime/resources/config/eval.rules.json` (`provenance` rule)

## Q7 — How is the orchestrator actually "state-driven"?

**30s:** It decides the next step by *querying case state every round*, not by executing a fixed
sequence of calls.

**2min:** Evidence: seed an empty case and it **blocks at `client-intake`** (no upstream seed → it
does not invent a client). Inject `INSUFFICIENT`/`CONFLICTING` client info and it transitions to
`WAITING_FOR_USER` rather than guessing values. After a repair exhausts, it stops at `NEEDS_REVIEW`.
The transitions (`next_runnable`, `can_run`, `guard_*`) are unit-tested independently of any
specific skill.

**Code:** `runtime/state/transitions.py` · `runtime/orchestrator.py` (`run()` main loop)

## Q8 — How does checkpoint/resume avoid re-execution?

**30s:** A completed stage is recorded with a fingerprint; on resume, only non-`PASS` tasks run, and
the system *reports* any `PASS`ed task it would otherwise re-run (normally zero).

**2min:** `checkpoint.py` saves `case_state.json` + `checkpoints[]` after every stage, then
`load()` performs 5 validations (existence, parse, `case_id` match, schema, registry fingerprint,
task→stage integrity). Any failure → `CHECKPOINT_INVALID`; the run never silently continues on
corrupted state. Resume re-runs only unfinished work.

**Code:** `runtime/checkpoint.py`

## Q9 — Why aren't all skills autonomous agents?

**30s:** Because for a reliability-critical pipeline, determinism beats autonomy at the layer that
produces structured artifacts.

**2min:** The upstream three stages (`client-intake`, `requirement-analysis`, `risk-analysis`) are
`executor: provided` — they arrive as structured artifacts (in this portfolio, seeded from curated
fixtures). The five downstream stages (`coverage-gap`, `solution`, `product-candidate`,
`product-recommendation`, `report`) are `executor: python` — deterministic, rule-driven, offline,
regression-testable. This keeps the *verifiable* part of the system fully machine-checkable and
removes LLM nondeterminism from the safety-critical path.

**Code:** `runtime/insurance-analysis.yaml` (`executor:` per stage)

## Q10 — What is the single biggest limitation?

**30s:** The current portfolio validates the Agent Runtime from **Structured Client State** onward.
Raw natural-language → Client State intake is **not** part of the executed boundary yet.

**2min:** Concretely: the demo's upstream stages are seeded fixtures, not a live NL→state model. I
deliberately do **not** present this as a full conversational agent, because doing so would overstate
the system. Other honest limits: the catalog is `is_demo=true` (12 fictional products), only
`coverage_type` is a blocking grounding attribute (others are reported/non-blocking), and there is
no production infra (Redis/Kafka/K8s/multi-tenant). These are scope choices, not hidden defects.

**Code / Docs:** `docs/eval/independent-acceptance-report.md` → "Honest Limitations" ·
`README.md` → "Honest Limitations"
