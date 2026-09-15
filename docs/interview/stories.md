# Interview Stories — Real Engineering Incidents

Five short stories you can tell to show *how you actually think about agent reliability*. Each is
grounded in this project's real artifacts/tests.

---

## Story 1 — The False Pass

We had a benchmark metric that reported `product_hallucination_rate = 0%`. It looked great. Then I
noticed the observation path was wrong: the product was nested under `product.product_id`, but the
metric read a shallower path. The check was green because it never actually inspected the product —
it returned "nothing found" and treated that as "nothing wrong."

**Lesson:** a green test that doesn't look at the right field is worse than a red one. After fixing
the observation, a genuinely missing product surfaced. I now treat "0 failures" as a hypothesis to
attack, not a result to celebrate. The eval engine therefore forbids `MANUAL`/`UNKNOWN` pass paths
and requires every assertion to target a real, present field.

**Where to point:** `runtime/eval_engine.py` (no `MANUAL` pass) · `tests/workflow/test_step4_phase13_guardrails.py`.

---

## Story 2 — When the Eval Engine Crashed

Mid-run, the eval engine threw `TypeError: unhashable type: 'list'`. A list-valued field was being
hashed for a set-membership check. The dangerous part: an exception in eval looks identical to "the
check didn't fire." If we had swallowed it, a corrupt artifact would have sailed through as PASS.

**Lesson:** *Eval crashing must never be confused with eval passing.* I added symmetric `_flatten` /
`_scalar` helpers so list/dict-valued fields are normalized before any set operation, and the engine
returns `FAIL`/`ERROR` on anything unexpected instead of throwing. A crash is a failed check, never a
silent pass.

**Where to point:** `runtime/eval_engine.py` (`_flatten`, `_scalar`, `evaluate()` returns FAIL on
unexpected input).

---

## Story 3 — Missing Evidence (Demo B)

We seeded a case with an empty knowledge base. A naive agent would either stall forever or, worse,
invent a justification. Ours failed the evidence eval, attempted `RERUN_FROM_UPSTREAM` twice, still
found nothing, and then **stopped at `NEEDS_REVIEW`** — with no product recommended and no claim in
the report.

**Lesson:** bounded repair + safe failure is the product. The valuable outcome is not "it recovered";
it's "it refused to lie." The repair budget (max 2) is an upper bound, not a quota — exhausting it
escalates to a human instead of looping into hallucination.

**Where to point:** `docs/demo/demo-b.md` · `tmp/demo/bm-noev-001/.../trace.jsonl`.

---

## Story 4 — The Hallucinated Product

We fed the agent a recommendation request naming a non-existent product (`C999` / unknown ID). The
candidate layer, recommendation layer, and report layer each independently refused it. Final state:
`primary = 0`, `unverified_products = []`, and the report named no product.

**Lesson:** the catalog is an explicit trust boundary. Generation and selection are separated
(`product-candidate-provider` generates, `product-recommendation` selects), so a product can't
"recommend itself." A hard invariant (`catalog_has_primary_product`) plus the report-level
`FABRICATED_PRODUCT` guardrail make hallucination a *structural impossibility*, not a hope.

**Where to point:** `runtime/resources/config/eval.rules.json` · `tests/eval/test_recommendation_catalog_guard.py`.

---

## Story 5 — Independent Red-Team

The developer's own tests passed. That is not acceptance. I ran a separate independent review that
did not trust the README, the history, or the author-written eval: I inspected code, injected
failures (F1–F6), mutated artifacts, read the trace, chased provenance to `chunk_id`, and actively
hunted for false passes (`all([])` vacuous truths, swallowed exceptions, unimplemented checks).

**Lesson:** developer tests answer "did I build what I meant?" Independent acceptance answers "should
anyone trust this?" The red-team found **0 false passes** and confirmed `30/30` regression, `71/71`
E2E, `33` benchmark cases, `9/9` golden — but it also forced an honest `PARTIAL E2E` disclosure
(raw NL intake is not in the executed boundary). That honesty is the deliverable.

**Where to point:** `docs/eval/independent-acceptance-report.md`.
