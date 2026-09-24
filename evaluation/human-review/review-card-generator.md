# Review Card Generator — Design Spec (Phase 27.7.6 v2)

The generator is OFFLINE tooling over FINISHED runs. It adds a
**Human Review Summary Layer** between the existing eval system and the
human reviewer, so a human reviews a *risk-ranked card* instead of the
full artifact pile.

Scope guard: it lives entirely in `evaluation/human-review/`, imports
NOTHING from `runtime/` (stdlib + PyYAML + jsonschema only), and never
mutates any state. The agent runtime, orchestrator, skills and approval
flow are untouched.

---

## 1. Input dependencies (Phase 1 audit)

Everything the card contains comes from the persisted run state the
runtime already produces — the same files the Web UI reads:

| Source | Fields consumed |
|---|---|
| `<run_dir>/<case_id>/case_state.json` | `status`, `artifacts{type}.payload` (client-profile / requirement-analysis / risk-assessment / product-recommendation), `evaluations[]` (eval_id, artifact_type, status, checks[]{check_id,status,message}), `tasks[]` (status, attempt), `events[]` (type), `waiting_for_user` |
| `<run_dir>/<case_id>/trace.jsonl` | recorded as `source.trace_path` (navigation; not parsed — case events cover the card's needs) |
| `runtime/resources/config/eval.rules.json` (indirectly) | the check vocabulary the eval engine already emits (schema / required_fields / required_non_empty / contamination / provenance_* / cross_artifact_* / catalog_* / invariant / skipped) |

Known input gap (honest limitation): WAITING_FOR_USER runs do not
persist `case_state.json` into the run dir (only trace.jsonl). The
generator handles this **fail-closed**: all checks FAIL with
`case state not persisted`, HIGH flag `case_not_finalized` →
DEEP_REVIEW. It never fabricates a summary from a partial trace.

## 2. Aggregation rules

### 2.1 The four automatic_validation dimensions

Projections of the existing eval records — no new validators invented:

| Card dimension | Underlying eval checks (glob) | PASS rule |
|---|---|---|
| `schema_check` | `schema` | ≥1 matched AND all matched PASS |
| `evidence_check` | `required_non_empty`, `provenance_*` | same |
| `logic_check` | everything else (`required_fields`, `contamination`, `cross_artifact_*`, `catalog_*`, invariant ids, `skipped`) | same |
| `trace_check` | computed from case/tasks/events (see 2.2) | — |

Honesty rule (inherited from `runtime/eval_engine.py` §19): a dimension
with **zero** matched checks reports FAIL ("cannot verify") — there is
no UNKNOWN and no silent PASS. Zero evaluations at all → all four FAIL.

### 2.2 trace_check — execution integrity

Did the case reach an orderly, by-design terminal state?

| case status | PASS when | else |
|---|---|---|
| COMPLETED | every task `status == "PASS"` | FAIL |
| NEEDS_REVIEW | ≥1 FAIL eval or a `STAGE_NEEDS_REVIEW` event (stopped by design) | FAIL |
| WAITING_FOR_USER | `waiting_for_user` non-empty | FAIL |
| anything else / no state | — | FAIL |

Note the deliberate distinction: `trace_check` = the *process* stopped
orderly; the HIGH flag `unresolved_task_failure` = some *task* never
reached PASS. A cleanly-blocked case can have trace PASS and the flag
HIGH at once (both are true, both carry evidence refs).

### 2.3 risk flags

Bindings live in `risk-rules.yaml` (config), predicates live in the
generator (deterministic) — same split as eval.rules.json / eval_engine.

- HIGH flags derive from eval FAILs (`missing_evidence`,
  `false_product_information`), task state (`unresolved_task_failure`)
  or terminal state (`case_not_finalized`).
- MEDIUM flags: `no_primary_recommendation` (business outcome "no
  product" needs a human glance — pilot finding F27-02),
  `insufficient_customer_context` (UNKNOWN/conflict profile fields),
  `high_exposure` (CRITICAL severity or unprotected_amount ≥
  threshold), `repair_used` (task attempt > 1).
- LOW flags (`style_issue`, `formatting_issue`) are `emit: human_only`:
  **no detector exists**, so the generator can never emit them — only a
  human may attach them as feedback. Declaring them in the yaml keeps
  the taxonomy closed without fabricating a capability.

Every flag carries `evidence_ref` (`eval:EVAL-006:required_non_empty`,
`task:TASK-005:status=FAILED`, `risk:R1-001:severity=CRITICAL`, …).

### 2.4 Sampling

`sha1(case_id + ":" + run_id)` first 8 hex digits mod 10000 <
rate × 10000 (rate from `risk-rules.yaml`, default 0.10). Deterministic
and reproducible — the same case always samples the same way.

### 2.5 Decision (strict order, never downgraded)

```
validation FAIL (any of the 4 dimensions)  -> DEEP_REVIEW, validation_status=FAIL
any HIGH flag                              -> DEEP_REVIEW
any MEDIUM flag OR sampling triggered      -> SUMMARY_REVIEW
otherwise                                  -> AUTO_PASS (required=false)
```

`review_action.reasons` lists every trigger that fired, in this order.

## 3. CLI

```
python evaluation/human-review/review_card_generator.py <run_dir> \
    [--out PATH] [--stdout] [--rules PATH] [--schema PATH]
```

- default output: `<run_dir>/human_review_card.json`
- the card is schema-validated against `review-card.schema.json` BEFORE
  being written — an invalid card raises and nothing is written
  (this caught a real bug during development: a stray `status` key).
- `review-card-example.json` is the verbatim output for the real pilot
  run `run_9de5882e` (bm-complete-006-single-medical, AUTO_PASS).

## 4. Self-verification on the real pilot data

Generated for all 6 staged pilot runs (2026-09-24):

| run | case | case status | level | validation | flags |
|---|---|---|---|---|---|
| run_9de5882e | bm-complete-006 | COMPLETED | AUTO_PASS | PASS | — |
| run_84f63c7c | bm-noev-001 | NEEDS_REVIEW | DEEP_REVIEW | FAIL | H:missing_evidence, H:unresolved_task_failure, M×3 |
| run_447ccd4b | bm-highrisk-001 | COMPLETED | SUMMARY_REVIEW | PASS | M:no_primary_recommendation, M:high_exposure |
| run_381c2836 | bm-noev-002 | NEEDS_REVIEW | DEEP_REVIEW | FAIL | H:missing_evidence, H:unresolved_task_failure, M×3 |
| run_48cc028f | bm-insufficient-004 | (not persisted) | DEEP_REVIEW | FAIL | H:unresolved_task_failure, H:case_not_finalized, M:no_primary |
| run_dad25ef1 | bm-nocand-001 | COMPLETED | SUMMARY_REVIEW | PASS | M:no_primary_recommendation, M:high_exposure, sampling hit |

Tests: `tests/eval/test_review_card.py` (dual-mode, plain pytest or
script) covers the four required scenarios plus fail-closed, sampling,
schema conformance, no-fabrication and determinism.
