# Provenance Walkthrough — Phase 19

Three real WeKnora retrieval chains, manually verifiable. Captured
2026-09-21 against the LIVE WeKnora v0.8.0 fixtures KB (f33d61b2).
Full JSON evidence: `tmp/p19_walkthrough.json`.

---

## Case A — Valid Evidence (ALLOW)

**Query**: 健康保险管理办法 等待期

**Result**: 3 governed evidence items, status = success

The FULL chain for the top hit:

```text
Decision (recommendation artifact)
  ↓ evidence_refs
Evidence (evidence_id = 6b0e45fb-766f…)
  ↓ chunk identity
KnowledgeHit (chunk_id = 6b0e45fb-766f…)
  ↓ registry lookup (content hash match ✓)
WeKnora Chunk (live HTTP retrieval, WeKnora v0.8.0)
  ↓ document identity (knowledge_filename stem)
Document (01_medical_insurance — synthetic fixtures corpus)
  ↓ governance metadata (from Agent Registry)
Version (fixtures-medical-insurance@1)
  ↓
Source (fixtures-medical-insurance)
  ↓
Authority: B (internal test corpus)
License: ALLOWED
Jurisdiction: CN
Effective window: 2023-01-01 → open
Content hash: 89fe30257bd0… (sha256, matches registry ✓)
Retrieved at: 2026-09-21T00:00:00Z
Canonical URI: synthetic://fixtures/kb/01_medical_insurance
```

**Manual verification**:
1. sha256 of the WeKnora-returned chunk content == registry hash ✓
2. effective_from ≤ as_of ≤ effective_to (2023-01-01 ≤ 2026-09-21 ≤ ∞) ✓
3. version_id resolves to source@version in registry ✓
4. jurisdiction CN matches query context CN ✓
5. license ALLOWED ✓
6. authority B matches hit source_level B ✓
7. validate_provenance returns (True, []) ✓

---

## Case B — Rejected Evidence (DENY on tamper)

**Query**: Same as A. Take the SAME valid evidence item, tamper the
content hash to `ffff…` (32 bytes of 0xff), re-validate.

**Result**: validate_provenance → (False, ["P007:hash_mismatch:…"])

```text
Evidence → chunk → registry lookup
  ↓ registry hash = 89fe30257bd0…
  ↓ tampered hash = ffffffffffff…
  ↓ MISMATCH → P007 → DENY
```

**Manual verification**: The one-character difference in the hash
causes the entire provenance chain to fail — the evidence item is
rejected and cannot enter a recommendation. This is the hash-anchor
property: any content tampering (in transit, in storage, or in the
evidence pipeline itself) is detectable.

---

## Case C — Abstention (Insufficient Evidence)

**Query**: 德甲联赛积分榜欧冠名额 (Bundesliga standings — completely
unrelated to insurance)

**Result**: evidence_count = 0, governance_status =
insufficient_evidence

```text
Query → WeKnora backend (returns keyword hits — the backend itself
  does NOT abstain, it returns top-k matches for any query)
  ↓ agent-side rescoring (the SAME SparseRetriever + DefaultReranker
  + min_relevance rules the deterministic engine uses)
  ↓ zero-overlap candidates score below threshold → all dropped
  ↓ insufficient_evidence → ZERO evidence items produced
  ↓ (a recommendation consuming this would go INCOMPLETE_EVIDENCE)
```

**Manual verification**: The agent's OWN relevance policy (not the
backend's) owns abstention. Even though WeKnora returned keyword
matches, the agent-side BM25 trigram overlap with the query is zero
for all candidates, so the min_relevance threshold (0.55) drops them
all. The system honestly says "I don't have relevant knowledge" rather
than fabricating a connection.

---

## Chain Property Summary

| Property | Case A | Case B | Case C |
|---|---|---|---|
| WeKnora returned hits | YES (6 backend hits) | YES | YES (keyword matches) |
| Agent governance allowed | YES (3) | YES (pre-tamper) | NO (0) |
| Provenance valid | YES | NO (P007) | N/A (no evidence) |
| Hash matches registry | YES | NO | N/A |
| Decision can cite | YES | NO | NO |
| System state | success | DENY | insufficient_evidence |
