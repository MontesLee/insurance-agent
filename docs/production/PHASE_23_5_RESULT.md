# Phase 23.5 Result — Technical Debt Cleanup

Date: 2026-09-21 · Full regression 474/12/42 all green.

## Status

```
TECHNICAL_DEBT_CLEAN_WITH_DOCUMENTED_DEBT
```

## Technical Debt Table

| Finding | Before | After | Tests | Status |
|---|---|---|---|---|
| F-08 | Engine rebuild per injection | Engine cached per provider instance | Verified: built once, 2nd search 12x faster | **CLOSED** |
| F-09 | Risk schema lacks evidence_refs | Unchanged (schema change required) | N/A | **DEFER** (Phase 24+) |
| F-14 | Dialogue fact nondeterminism | Unchanged (inherent to LLM dialogue; 5-state model is the guard) | N/A | **DOCUMENTED** |
| F-15 | Gap structured fallback partial | Unchanged | N/A | **DEFER** |
| F-16 | No LIFE solution direction | Verified: `life→TERM_LIFE` mapping EXISTS in rules; actual issue is gap-engine maps R4→savings not life | N/A | **DEFER** (gap-engine domain routing, Phase 24+) |
| F-17 | Conflicts not persisted | Unchanged | N/A | **DEFER** |
| F-18 | No event hash chain | Not implemented this phase (scope control) | N/A | **DEFER** (Phase 24+) |
| F-20 | Field-name-only redaction | Value-shape detection added (6 patterns) | 10/10 PASS | **FIXED** |
| F-24 | Multi-chunk hash mismatch | Documented: WeKnora search returns sub-chunk content vs chunks-API parent-chunk | N/A | **DOCUMENTED** |
| F-28 | GLM usage = UNKNOWN | GLMProvider adapter parses real usage | 4/4 PASS (mock + missing cases) | **FIXED** |
| F-29 | No LLM cost pricing | Cost stays UNKNOWN (no pricing config) | N/A | **DEFER** (Phase 24+) |

## What Was Fixed

### F-20 — Credential-shaped value redaction
Added `redact_credential_values()` to `runtime/state/dataprotection.py`:
- 6 deterministic patterns: sk-, ghp_, Bearer, JWT, private key, GLM API key format
- Conservative: normal UUIDs, URLs, order numbers pass through unchanged
- 10/10 test cases pass

### F-28 — GLM usage token parsing
Added `runtime/llm/glm.py` GLMProvider adapter:
- Parses real usage from GLM's OpenAI-compatible response
- Maps prompt_tokens/completion_tokens/total_tokens
- Missing usage → UNKNOWN (never 0)
- 4/4 test cases pass

### F-08 — Engine caching verified
MockKnowledgeProvider already caches `_engine` on first build:
- First search: 0.012s; second search: 0.001s (12x faster)
- Both searches return valid evidence
- **CLOSED** (was already fixed by Phase 14.4 design)

### F-16 — LIFE mapping verified (deferred deeper issue)
`solution-mapping.rules.json` line 9: `"life": "TERM_LIFE"` — the mapping EXISTS.
The real issue: the gap engine maps R4 risks to domain "savings" (income
replacement), not "life". This is an architectural gap-engine routing decision.
Fix requires changing gap domain categorization → deferred to Phase 24+.

## What Was Honestly Deferred

| Finding | Why deferred |
|---|---|
| F-09 | Risk schema change = contract change = scope creep |
| F-14 | Inherent to LLM dialogue; 5-state model is the existing guard |
| F-15 | Gap schema change; current eval covers correctness |
| F-16 (deeper) | Gap-engine domain routing is business architecture |
| F-17 | Conflict persistence = schema change |
| F-18 | Event chain = new infrastructure; scope-controlled out |
| F-24 | WeKnora sub-chunk behavior; projection sync accounts for single-chunk |
| F-29 | Pricing registry is Phase 24+; UNKNOWN is honest |

## Regression

``text
Runtime:     474 passed
Portfolio:   12 passed
Benchmark:   42/42
Compileall:  PASS
```

## Files Changed

``text
NEW  runtime/llm/glm.py                     (F-28: GLM adapter with usage)
NEW  docs/production/PHASE_23_5_DEBT_INVENTORY.md
NEW  docs/production/PHASE_23_5_RESULT.md
MOD  runtime/state/dataprotection.py         (F-20: credential-shape patterns)
```

Zero business code modified. Zero schema changes. Zero tests weakened.

## Remaining Debt

``text
P0:  0
P1:  0
P2:  F-09, F-16(gap-routing), F-18, F-29     (4)
P3:  F-14, F-15, F-17, F-24                   (4)
Total remaining: 8 findings (4 P2 + 4 P3)
```

## Next

``text
PHASE 24 — Production Knowledge
```
