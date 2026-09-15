> 🌐 **Language:** 🇨🇳 [中文版](ADR-005-evidence-provenance.zh-CN.md) · 🇺🇸 English

# ADR-005 · Evidence provenance

## Context
Agents easily state insurance knowledge "from model memory" (e.g. "this product guarantees renewal
for 20 years") — plausible-sounding but possibly wrong. In insurance, an unsourced conclusion is
equivalent to misleading the client.

## Decision
Knowledge must enter the system as **Evidence**, each piece carrying
`evidence_id / document_name / chunk / source`.
- A shared Evidence Provider (currently at `knowledge/evidence/` + `knowledge/rag/`); queries are
  generated from `(domain, purpose)` templates and the loop is read-only;
- **V0.2 attribute-level grounding**: key claimed product attributes (`coverage_type /
  eligibility_age / renewal_period / deductible / coverage_term`) are checked against evidence one
  by one, yielding `SUPPORTED / UNSUPPORTED / CONFLICT / NOT_CHECKABLE`;
- **NOT_CHECKABLE is an explicit third state**, never folded into SUPPORTED;
- Product candidates must come from the Catalog; recommendations must be traceable to evidence.

## Alternatives
- Answer directly from model knowledge: unverifiable — a license for hallucination.
- Document-level provenance only (the Step 2 status quo): proves "a document in this domain was
  consulted", not "this attribute was supported".
- Require evidence to cover the entire product system: O(attributes × products) effort —
  unrealistic at this stage.

## Why
"Having a source" turns speakability into checkability. Attribute-level grounding answers the most
fatal question: "We claim this product guarantees renewal for 20 years — which evidence says that
sentence?" If no chunk mentions it, it is UNSUPPORTED.

## Trade-offs
- Attribute matching uses "searchable variants of the claimed value" (with amount-unit
  normalization, e.g. `10000元` vs `1 万元`); it is still **string hit**, not semantic entailment —
  it under-detects (false negatives), so the design says "when uncertain, judge NOT_CHECKABLE /
  UNSUPPORTED, never SUPPORTED".
- V0.2 covers only 5 key attributes; other attributes do not participate in the judgment.
