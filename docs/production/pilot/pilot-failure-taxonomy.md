# Pilot Failure Taxonomy (F01–F18) — round-1 entries

F01 Information Understanding — none observed (machine side)
F02 Information Missing — C08: UNKNOWN income/budget/existing
    insurance produced result WAITING_FOR_USER (agent asked, did
    not fabricate — GOOD) but no gate and run=SUCCEEDED → F27-01
F03 Requirement Analysis — C12: EMPTY requirement set accepted;
    full chain ran and produced a report → F27-03 (P2)
F04 Risk Analysis — none observed
F05 Coverage Gap — none observed
F06 Solution Logic — none observed
F07 Knowledge Retrieval — C11 empty KB: status
    insufficient_evidence, 0 evidence (correct fail-closed at the
    knowledge layer) → recommendation/report never produced (no
    fabrication — GOOD); note: default knowledge source on this
    path is the internal FIXTURE KB (obs provider="mock"), not
    live WeKnora → F27-04 (P3 environment)
F08 Evidence Grounding — BASELINE: unmutated case also yields
    product-recommendation INCOMPLETE_EVIDENCE, 10/10 candidates
    not_recommended, primary={}. Evidence rules never admit a
    candidate on the demo catalog → F27-02 (P1-business: blocks
    recommendation-quality validation; no fabrication involved)
F09 Product Governance — no version/authority violations
F10 Recommendation — see F27-02 (no primary recommendation ever)
F11 Report Generation — reports generated only when the chain
    completes; C08/C11 have none (consistent with their outcomes)
F12 Human Review — C11: business NEEDS_REVIEW (repair-exhausted)
    did NOT park the run at WAITING_HUMAN; settled SUCCEEDED →
    F27-01 (shared with C08)
F13 LLM Provider — not exercised (0 calls; policy NOT VERIFIED)
F14 Runtime — 0 failures, 0 recoveries needed in round 1
F15 Persistence — none observed
F16 Observability — run state alone cannot distinguish business
    completion (see F27-01) — operator must read result payloads
F17 Cost/Budget — budget enforcement observed working (refused an
    over-attempt approval during runner bring-up: correct)
F18 Security/Privacy — 0 leaks; synthetic data only
