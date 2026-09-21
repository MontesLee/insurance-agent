# Known Limitations — updated post Phase 23.5

All P2 and P3 findings, honestly documented. None are hidden.
None block the portfolio. All have code/test evidence.
**Remaining after Phase 23.5: 8 findings (4 P2 + 4 P3).**

Resolved in Phase 23.5: F-08 (engine caching — verified already cached),
F-20 (credential-shaped value redaction — 6 patterns added),
F-28 (GLM usage parsing — adapter fixed).

## P2 Findings

### F-09 — Risk/Gap/Solution evidence_refs convention

**Finding**: The evidence_refs convention exists only for
Recommendation artifacts. Risk, Gap, and Solution artifacts don't
declare their evidence dependencies.

**Why**: The convention was built incrementally (P14.5 → P15);
extending to all artifacts wasn't needed for the current eval gates.

**Impact**: Cross-skill evidence binding is enforced for
Recommendation only; upstream stages could theoretically make
unsupported claims that aren't caught until the rec stage.

**Current mitigation**: The contamination invariant checks upstream
artifacts for product leakage (not knowledge grounding).

**Production would require**: Extending evidence_refs to all
analysis artifacts + corresponding eval invariants.

---

### F-16 — Gap-engine routes life/R4 to savings instead of life

**Finding**: `life → TERM_LIFE` mapping EXISTS in
`solution-mapping.rules.json` (line 9), but the gap engine's domain
routing maps R4 risks to "savings" (income replacement), preventing
the solution engine from selecting TERM_LIFE.

**Why**: The gap engine's domain categorization sends R4 to savings;
this is a deeper architectural routing decision than a missing mapping.

**Impact**: Multi-requirement cases including `life` produce SAVINGS
solutions instead of TERM_LIFE.

**Current mitigation**: The gap is still produced; projects with
life requirements are honestly INCOMPLETE_EVIDENCE rather than
silently complete.

**Production would require**: Changing the gap engine's domain
routing for R4 to "life" + corresponding tests.

---

### F-18 — Event log lacks cryptographic chaining

**Finding**: `events.jsonl` is append-only by convention; there is
no hash chain linking each event to the previous one.

**Why**: The event system predates the tamper-evidence requirement;
adding chaining would change the event schema.

**Impact**: A raw-line tamper in events.jsonl is not intrinsically
detectable (unlike artifact tampering, which IS hash-detected).

**Current mitigation**: Artifact tampering IS detected (sha256
fingerprints); the audit evaluator checks for event-line mutations
by file comparison, not by cryptographic proof.

**Production would require**: Append `prev_hash` + `self_hash` to
each event; verify on read.

---

### F-29 — LLM cost pricing not configured

**Finding**: The LLM Gateway returns cost=UNKNOWN because no
ModelPricingRegistry exists.

**Why**: Pricing configuration is Phase 24+ scope; hardcoding a
"reasonable-looking" price would be dishonest.

**Impact**: Cost reporting shows UNKNOWN instead of actual cost.

**Current mitigation**: cost=UNKNOWN (honest); usage IS parsed.

**Production would require**: A pricing registry with provider,
model, input/output price, currency, effective date.

---

## P3 Findings

### F-14 — Dialogue-stage derivation not deterministically testable

**Finding**: Client Intake, Requirement Analysis, and Risk Analysis
are `executor: provided` (dialogue-driven PS1 skills). Their
derivation quality (text → facts/requirements/risks) cannot be
deterministically re-tested in the pytest battery.

**Why**: These stages run via PowerShell dialogue scripts, not
in-process Python.

**Impact**: B1–B3 fact-discipline is verified at the seed-contract
level, not at the dialogue-behavior level.

---

### F-15 — Gap structured fallback partial

**Finding**: Some gap fields remain free-text rather than structured.

**Why**: The gap schema evolved incrementally; a full restructure
would be a schema change.

**Impact**: Limited; current eval covers gap correctness.

**Production would require**: Schema evolution with migration.

---

### F-17 — Conflicts dropped from stored artifact

**Finding**: When a client provides contradictory facts (e.g., age
30 vs 35), the run stops at the intake gate correctly, but the
stored client-profile artifact doesn't retain the conflicts[] detail.

**Why**: The intake stage normalizes the profile on storage; the
conflict escalation is carried in the hand-off response, not in
the artifact.

---

### F-24 — Multi-chunk hash mismatch (search vs chunks API)

**Finding**: For multi-chunk documents, the WeKnora search response
content may differ from the chunks-API content (sub-chunk vs
parent-chunk), causing a hash mismatch between the projection
registry and the search-returned content.

**Why**: The search endpoint may return sub-chunk (matched fragment)
content while the chunks API returns parent-chunk content.

**Impact**: Live provenance validation works correctly for
single-chunk documents (the fixtures KB). Multi-chunk documents
(the pilot KB) show hash mismatch.

**Current mitigation**: The fixtures KB (used for all business E2E)
has single-chunk documents; provenance validation passes.

**Production would require**: Syncing sub-chunk hashes into the
projection, or using the chunks API for content retrieval.

---

## Informational (design decisions, not defects)

### F-22 — WeKnora server-side no-abstention

WeKnora returns top-k keyword matches even for nonsense queries. By
design — the agent-side policy owns abstention.

### F-23 — WeKnora lacks governance metadata

WeKnora v0.8.0 provides no per-hit authority/license/window fields.
By design — the dual-identity model (agent registry = truth source)
handles this.
