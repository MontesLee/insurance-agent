# Data & Knowledge/Product Audit

## Client data (insurance domain)

What a real case touches: name/identifier, family structure, income,
existing coverage, health-adjacent notes (`notes_for_unknown` includes
health_status), dependents/parents, planned mortgage. All of it flows into
the durable client-profile artifact and, transitively, into events.

Findings (all measured):

1. **Plaintext at rest, no encryption, no field classification** —
   events 156 / state 312 sensitive-term hits in one probe run.
2. **No retention/erasure policy** — project dirs live forever.
3. **No data-minimization review** — the contract's breadth is a product
   decision that has not been re-examined against a real-collection basis.

## Product catalog (governance probe)

Present: `catalog_version`, per-product `product_version`,
`effective_from`, `is_demo: true` + notice — demo labelling is honest and
the eval catalog invariant prevents non-catalog products.

Absent (measured from the catalog JSON): `effective_to` (no end-of-life),
waiting period, exclusions, coverage limits, coverage term, health
declaration requirements, occupation restrictions. Deductible/renewal
appear only as free-form feature text, not structured, governable fields.

Consequence: the runtime **cannot verify a product is currently in force
or fit for a specific client's constraints** — the recommendation path
would rely on demo-grade data for real advice. Combined with the absent
human-review gate on the final deliverable, this fails the "product
recommendation has reliable evidence" hard gate **for real cases**.

## Knowledge

Local demo corpus + RAG with per-item provenance (document/chunk ids) and
fail-closed empty behavior. For a pilot whose recommendations are human-
reviewed and manually delivered, demo knowledge is survivable; real
knowledge sourcing remains P2.

## Cost data

Per-turn token usage is captured (input/output/latency, per-model) — but
only on the in-memory AgentState; durable surfaces contain zero usage
records (probe). A real case's cost cannot be reconstructed after the
fact. Runaway protection is bounded (steps/retries/repairs), so cost is
finite but unobserved.
