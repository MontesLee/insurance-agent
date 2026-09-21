# Phase 23.5 Debt Inventory (2026-09-21)

| Finding | Description | Exists | This Phase | Action |
|---|---|---|---|---|
| F-08 | Engine rebuild overhead | NO — already cached | — | CLOSED (verified: `_engine` cached in `MockKnowledgeProvider._build()`) |
| F-09 | Risk/Gap evidence_refs | YES — Risk schema lacks evidence_refs | VERIFY | Gap has refs; Risk does not. Contract change required → DEFER |
| F-14 | Dialogue fact derivation | YES — no deterministic re-derivation | DOCUMENT | Inherent to LLM dialogue; AGENTS.md 5-state model is the guard |
| F-15 | Gap structured fallback | YES — free-text gaps exist | DEFER | Schema change; current eval covers gap correctness |
| F-16 | Life/R4 solution direction | YES — gap engine maps R4→savings not life | DEFER | `life→TERM_LIFE` mapping EXISTS in rules; the gap engine's domain routing is the actual issue → Phase 24+ |
| F-17 | Conflict persistence | YES — conflicts not stored in artifact | DEFER | Schema change; conflicts handled by intake gate |
| F-18 | Event hash chain | YES — no cryptographic chain | DEFER | Event chain is new infrastructure; scope-controlled out → Phase 24+ |
| F-20 | Credential-shaped redaction | PARTIAL — field-name only | FIX | Add value-pattern detection to dataprotection |
| F-24 | Multi-chunk hash mismatch | YES — search vs chunks API content differs | DOCUMENT | WeKnora search returns sub-chunk content; projection sync accounts for single-chunk only |
| F-28 | GLM usage parsing | YES — GLM adapter returned UNKNOWN | FIX | Parse usage in GLM adapter (model.py already parses it) |
| F-29 | LLM cost pricing | YES — no pricing config | DEFER | ModelPricingRegistry is Phase 24+; cost=UNKNOWN is honest |

## Summary
- **FIXED this phase**: F-20, F-28 (2 items)
- **CLOSED (verified)**: F-08 (1 item)
- **DEFER with documentation**: F-09, F-14, F-15, F-16, F-17, F-18, F-24, F-29 (8 items: 4 P2 + 4 P3)
