# Eval & Repair — the Quality Boundary

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](eval.zh-CN.md)

Source of truth: `runtime/eval_engine.py`, `runtime/repair.py`,
`runtime/harness/harness.py` (`_run_eval_and_repair`),
`runtime/resources/config/eval.rules.json`.

## 1. The boundary

```text
Agent → Tool → Artifact candidate → ARTIFACT_READY
        ↓
     HARNESS
        ↓
     Eval ──PASS──▶ continue (checkpoint, next tasks)
        └──FAIL──▶ Repair (≤ 2) → re-run agent → Eval
                       └──exhausted──▶ NEEDS_REVIEW (downstream BLOCKED)
```

- The **Agent** never decides PASS. The **Tool** never evaluates in agent
  mode (`skip_eval=True`). The **Worker** cannot self-pass — in parallel
  mode only the eval branch can yield PASS (regression-tested with an
  executor that tries). The **LLM** never grades anything.
- The **Harness** owns Eval, Repair, Retry and NEEDS_REVIEW. This is the
  single most important ownership rule in the runtime.

## 2. The Eval engine (deterministic, rule-driven)

Every artifact is evaluated by deterministic checks; thresholds, paths and
term lists all come from `eval.rules.json` — the engine hard-codes no
judgment:

| Check family | What it proves |
| --- | --- |
| `schema` | the artifact validates against its declared canonical contract |
| `required_fields` | declared payload paths are present |
| `required_non_empty` | present-but-empty collections fail (e.g. an evidence provider that found nothing) |
| `contamination` | analysis layers contain no concrete product/company leakage |
| `provenance` | recommendation → evidence → document chains resolve |
| `cross_artifact` | references between artifacts (gap→risk, solution→gap) resolve |
| `invariant` | domain invariants, e.g. every candidate `product_id` exists in the catalog |

Honesty rules: a check that cannot be evaluated reports FAIL, never PASS —
there is no MANUAL/UNKNOWN pass. Eval records are appended to
CaseState (`evaluations`) with sequential ids (`EVAL-%03d`).

## 3. Repair (bounded, local, never rewrites artifacts)

```text
eval FAIL
 ↓ failed checks → repair.plan() (rules-driven action map)
repairable (catalog_exists, cross_artifact_orphan_refs)
    → RE-RUN THE AGENT (the artifact is frozen; repair re-produces it)
    → re-eval                                   ── up to 2 repairs
not repairable → NEEDS_REVIEW immediately
budget exhausted (1 initial + 2 repairs) → NEEDS_REVIEW
```

- Repair never edits a produced artifact — artifacts are frozen; repair
  changes the producer path and re-runs it.
- Upstream is never rolled back; only the failed task retries.
- The exact budget (verified in code and tests): **max 2 repairs, 3
  executions per task**.

## 4. Reference mode parity

In the pre-agent deterministic runtime, `_execute_stage` runs the same
eval engine inside the stage runner (dialogue-seeded artifacts are gated
the same way). The agent era moved eval *ownership* to the Harness without
changing eval *strictness* — the same rule file, the same checks.

## 5. Observability

Eval and repair emit a full lifecycle (`EVAL_STARTED/COMPLETED`,
`REPAIR_STARTED/COMPLETED/EXHAUSTED` in trace; `eval_started`,
`eval_passed/failed`, `repair_*` runtime events). Test coverage of the
boundary itself: `tests/runtime/test_eval_boundary.py` (tool does not
evaluate; harness does; exactly one eval per attempt; repair re-evaluates;
repair bounded; agent/tool cannot self-pass).
