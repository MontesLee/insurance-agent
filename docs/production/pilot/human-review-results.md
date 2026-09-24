# Human Review Package — Phase 27 Round 1 (machine-observable facts only)

Generated 2026-09-23 from tmp/pilot27/<case>/attempt-N/<case>/artifacts +
data/pilot-machine-results.json (runtime_version phase26c-productionization-v1.0 (c7ed9c6)).
Business judgment fields are deliberately PENDING_OWNER_REVIEW —
machine eval statuses are NOT human review.

**2026-09-23 update:** the per-case review WORKBENCH now lives in
`owner-review/` (README.md = instructions + PENDING status grid +
OF/EH registries; C01.md–C12.md = full per-section review forms
with machine evidence). The compact machine-facts table below
remains the quick index; record all judgments in owner-review/.

Artifacts root per case: `tmp/pilot27/<id>/<attempt>/<id>/artifacts/*.json`
(evidence: requirement/risk/gap/solution/knowledge-evidence/
product-candidates/product-recommendation/insurance-report) + trace.jsonl.
NOTE (evidence hygiene): the pilot runner deletes its queue/audit rows
after each case; durable per-case evidence = this JSON + artifacts +
traces. Round 2 should export audit rows before cleanup.

## Machine facts table

| Case | type | att | Req | Risk | Gap | Sol | KnowledgeEv | Cands | Rec status | Primary | Report | Task | Run | result_status | mech-approvals | s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| C01 | child_protection | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.44 |
| C02 | single_adult | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | C001 | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.28 |
| C03 | married_no_child | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | C001 | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.22 |
| C04 | dual_income | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.23 |
| C05 | mortgage_family | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.39 |
| C06 | existing_insurance | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.31 |
| C07 | underinsured | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.22 |
| C08 | incomplete_info | 1 | NOT_PRODUCTION | NOT_PRODUCTION | NOT_PRODUCTION | NOT_PRODUCTION | NOT_PRODUCTION(0) | NOT_PRODUCTION | NOT_PRODUCTION | NONE | NOT_PRODUCTION | SUCCEEDED | SUCCEEDED | WAITING_FOR_USER | 0 | 0.35 |
| C09 | evidence_sensitive_gap0 | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.25 |
| C10 | complex_family | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.37 |
| C11 | knowledge_unavailable | 1 | n/a | n/a | COMPLETE | COMPLETE | insufficient_evidence(0) | NOT_PRODUCTION | NOT_PRODUCTION | NONE | NOT_PRODUCTION | SUCCEEDED | SUCCEEDED | NEEDS_REVIEW | 0 | 0.49 |
| C12 | no_requirements | 2 | n/a | n/a | COMPLETE | COMPLETE | success(5) | 10 | INCOMPLETE_EVIDENCE | NONE | success | SUCCEEDED | SUCCEEDED | COMPLETED | 1 | 1.27 |

Reading notes: Rec status INCOMPLETE_EVIDENCE on C01-C07/C09/C10/C12 is
the F27-02 content gap (all candidates poor-fit on the demo catalog;
single-requirement diagnostic produced primary C001 — see
f27-02-root-cause.md). C08/C11 produced NO candidates/recommendation/
report (F27-01: business finals settled as run SUCCEEDED).

## Per-case review forms (Owner to fill)

### C01 (child_protection) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C02 (single_adult) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C03 (married_no_child) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C04 (dual_income) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C05 (mortgage_family) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C06 (existing_insurance) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C07 (underinsured) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C08 (incomplete_info) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: NOT_PRODUCTION  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: NOT_PRODUCTION  Notes:
8. Report: NOT_PRODUCTION  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C09 (evidence_sensitive_gap0) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C10 (complex_family) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C11 (knowledge_unavailable) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: NOT_PRODUCTION  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: NOT_PRODUCTION  Notes:
8. Report: NOT_PRODUCTION  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

### C12 (no_requirements) — PENDING_OWNER_REVIEW

Reviewer: ______  machine-facts row above; artifacts path as noted.

```
1. Requirement: UNKNOWN  Notes:
2. Risk: UNKNOWN  Notes:
3. Coverage Gap: UNKNOWN  Notes:
4. Solution: UNKNOWN  Notes:
5. Product Candidate: UNKNOWN  Notes:
6. Evidence: UNKNOWN  Notes:
7. Recommendation: UNKNOWN  Notes:
8. Report: UNKNOWN  Notes:
9. Decision: (APPROVE/REJECT/NEEDS_CHANGE/UNABLE_TO_REVIEW)
10. Review time: UNKNOWN
11. Reviewer changes: —
12. Finding IDs: —
```

## Human review summary

| Case | R | Rk | G | S | P | E | Rec | Rep | Decision | time_s |
|---|---|---|---|---|---|---|---|---|---|---|

| C01 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C02 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C03 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C04 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C05 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C06 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C07 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C08 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C09 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C10 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C11 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |

| C12 | - | - | - | - | - | - | - | - | PENDING_OWNER_REVIEW | UNKNOWN |
