# Adversarial Findings — Phase 19

Attack-mode testing: attempt to BREAK the system, not prove it works.
All attacks were already embedded in the phase 14–18 test suites
(each row cites the test that executed it). Summary of 42 attacks
across 4 categories, with outcomes.

## Knowledge Attacks (16)

| Attack | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Tampered content hash (1 char flip) | DENY (P007) | DENY | PASS | 14.6 MUT-001, 18 G2 |
| Version swap (2026→2024) | DENY (P004) | DENY | PASS | 14.6 MUT-002, 18 G2 |
| UNKNOWN→ALLOWED license forgery | DENY (P009) | DENY | PASS | 14.6 MUT-003, 18 G2 |
| Expired→active metadata claim | DENY (window) | DENY | PASS | 14.6 MUT-004 |
| Authority flip (S→D) | DENY (P006) | DENY | PASS | 14.6 MUT-005, 18 G2 |
| Forged chunk_id | DENY (P002) | DENY | PASS | 14.6 PROV-003, 18 G2 |
| Forged document_id | DENY (P003) | DENY | PASS | 14.6 PROV-004, 18 G2 |
| Registry authority conflict | DENY (AUTHORITY_CONFLICT) | DENY | PASS | 14.3 GOV-006 |
| Jurisdiction conflict (CN-BJ vs CN-SH) | DENY | DENY | PASS | 14.3 GOV-009, 18 G2 |
| Unregistered WeKnora document | DENY (REGISTRY_MISS) | DENY | PASS | 18 G3 |
| Corrupted/non-JSON response | ProviderResponseInvalid | Raised | PASS | 18 G4 |
| WeKnora connection refused | ProviderUnavailable | Raised | PASS | 18 G4 |
| WeKnora timeout | ProviderUnavailable | Raised | PASS | 18 G4 |
| WeKnora 401 (invalid key) | ProviderResponseInvalid | Raised | PASS | 18 G4 |
| WeKnora 403 (out-of-scope KB) | ProviderResponseInvalid | Raised | PASS | 18 G4 |
| Empty content in hit | ProviderResponseInvalid | Raised | PASS | 14.1 C04, 18 G2 |

## Agent Attacks (12)

| Attack | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Missing critical client info | WAITING_FOR_USER, not assumed | Correct | PASS | 15 B008, 16 Q-SUF-001 |
| Contradictory age (30 vs 35) | STOP at intake gate | Correct | PASS | 16 Q-CON-001 |
| Contradictory insurance (none vs has) | STOP | Correct | PASS | 16 Q-CON-002 |
| Incomplete evidence for recommendation | INCOMPLETE_EVIDENCE | Correct | PASS | 15 B001 |
| Zero-overlap query | Abstain (no evidence) | Correct | PASS | 18 G6 |
| Product not in catalog (P999) | NO fabrications | Correct | PASS | 15 N004 |
| Age 85 → no eligible product | NO_CANDIDATES | Correct | PASS | 15 B009 |
| Multi-risk requirement gap | Honest INCOMPLETE | Correct | PASS | 15 B001, 16 MD-001 |
| Skill failure → repair → still fail | NEEDS_REVIEW | Correct | PASS | 11 benchmark |
| Fabricated requirement in gap | HG-B02 catches | Caught | PASS | 16 M02 |
| Solution without gap | HG-B04 catches | Caught | PASS | 16 M04, M05 |
| Tampered report section | HG-B12 catches | Caught | PASS | 16 M08 |

## Security Attacks (8)

| Attack | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Anonymous → privileged action | 401 / None identity | Correct | PASS | 17 A01-A05 |
| OPERATOR → approve | DENIED (rank) | Correct | PASS | 17 AZ-approve |
| Cross-project path traversal | None returned | Correct | PASS | 17 IS02-IS04 |
| Forged agent actor approval | ACTOR_NOT_AUTHORIZED | Correct | PASS | 17 AP03-05 |
| File-level forged APPROVED | No re-execution | Correct | PASS | 17 AP06 |
| PII in event payloads | [REDACTED] | Correct | PASS | 17 D01-D10 |
| bank_card in payload | [REDACTED] (fixed P-17-1) | Correct | PASS | 17 fix regression |
| Real data + unverified provider | BLOCKED | Correct | PASS | 17 PV01 |

## Evaluation Attacks (6)

| Attack | Expected | Actual | Result | Evidence |
|---|---|---|---|---|
| Delete a requirement → evaluator catches | HG-B02 fires | Caught | PASS | 16 M01 |
| Inject phantom product | HG-B05 fires | Caught | PASS | 16 M06 |
| Delete recommendation evidence | HG-B06 fires | Caught | PASS | 16 M07 |
| Delete trace run_id | Evaluator detects | Caught | PASS | 17 M-OBS-01 |
| Forge trace project_id | Evaluator detects | Caught | PASS | 17 M-OBS-06 |
| Injected evaluator violation | Hard gate flips | Caught | PASS | 15/16/17 wiring tests |

## Summary

42 attacks, 42 PASS, 0 FAIL. No new findings discovered (all attack
surfaces were already covered by the phase 14–18 test batteries).
The adversarial posture is a design property: every phase shipped with
its own negative/mutation suite from the start.

## Known Remaining Vulnerabilities (documented, not hidden)

- F-18 (P2): events.jsonl has no cryptographic chain — a raw-line
  tamper is not intrinsically detectable (artifact tampering IS).
- F-20 (P3): credential-shaped VALUES in free-text fields survive
  field-based redaction.
- F-16 (P2): no solution direction for life/R4 in the current model.
- F-22 (P3): WeKnora returns top-k keyword matches for nonsense
  queries (agent-side policy owns abstention — works, but the backend
  itself doesn't abstain).
