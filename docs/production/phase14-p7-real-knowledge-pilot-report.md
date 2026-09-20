# Phase 14.7 — Real Insurance Knowledge Pilot Report

Date: 2026-09-20 (initial) · 2026-09-20 (same day, ENRICHED from the
user's local knowledge base) · Scope: small-scale REAL public-document
pilot over the existing 14.1–14.6 architecture. Zero architecture
changes.

## 0. ENRICHMENT UPDATE (2026-09-20) — supersedes the initial BLOCKED verdict

The user's local corpus (C:/Users/aubor/WorkBuddy/保险/
insurance-knowledge-base — 567 catalogued documents with full crawl
metadata) was scanned read-only, classified, and gap-analyzed:

- 7 additional REAL_OFFICIAL documents verified as COMPLETE verbatim
  texts on official gov.cn pages (article structure + 施行 closing
  checked mechanically) and converted mechanically into pilot
  fixtures. **Original 3 → Final 10 real documents — G1 met.**
- Honestly REJECTED candidates: 保险法(2015修正) PDF is a
  scanned/image copy (18 chars extractable — no OCR guessing);
  保险销售行为管理办法/DIP 2.0/3.0/交强险条款/示范条款 pages are
  JS-rendered landing or attachment pages, not document texts;
  医保药品目录/罕见病目录 pages are index pages.
- STILL MISSING (recorded, not faked): a genuine CN-BJ Beijing LOCAL
  medical-insurance policy (the 18 "北京" corpus hits are university
  reports, portal homepages, and national rules republished on
  Beijing news pages — none is a Beijing local policy), a real
  old/new version PAIR, and a full-text commercial product clause
  (for a non-mutated UNKNOWN-license negative). Beijing jurisdiction
  behavior remains covered by the existing governance semantics +
  registry mutations.

Re-run after enrichment (all existing pipelines, zero evaluation
rewrites): pilot harness **26/26 + HARD GATES CLEAN (exit 0)**; 14.7
suite 21/21; 14.6 harness 50/50 CLEAN; 14.1–14.5 suites 52/33/74/52/44;
runtime 433 · portfolio 12 · regression 51/0/1 (=) · benchmark 42/42 ·
compileall PASS.

```text
Phase 14.7 = PASS (pending human confirmation of the re-grade)
```

The sections below document the INITIAL 3-document run that the
enrichment built upon (evidence chain, mutations, and gates — all of
which were re-verified on the 10-document corpus by the same
harnesses).

---

## 1. Executive Summary (initial run — superseded by §0)

```text
Phase 14.7 = BLOCKED (G1: 3 real documents loaded < the 10-doc minimum)
```

BLOCKED is a DATA-ACQUISITION verdict, not an architecture one: the
complete real-knowledge chain — real documents → metadata → chunk →
retrieval → governance → evidence → provenance → decision binding →
evaluation — was VERIFIED END-TO-END on the three real official
documents that could be reliably and verifiably obtained from this
environment, with every hard gate clean. What is missing is DOCUMENT
COUNT, and the reason is honest: automated retrieval from this
environment truncates long official texts (each document would arrive
as a partial copy) and the network policy blocks direct fetches of
most government domains; hand-reconstructing the missing articles
would be fabrication, which the phase explicitly forbids.

**What was proven (G2–G16, on REAL data)**: real metadata complete
(license grounded in《著作权法》第五条, authority S/A per the existing
ladder, real effective dates, real jurisdiction); real sha256 anchors
(13 chunks over 3 documents, computed by the EXISTING chunker);
real-window governance (as-of 2021-01-01 → all three REAL documents
correctly FUTURE-denied; today → CURRENT-allowed); retrieval hits the
right real document for real regulatory queries; irrelevant queries
abstain; UNKNOWN-license mutation denied; five real-item mutations
(hash/version/license-forgery/jurisdiction/authority) all detected at
the precise rule; full provenance chain resolves to the real
source_id/canonical_uri; decisions bind to real evidence; provider
failure fails closed; synthetic and pilot corpora are isolated in
BOTH directions. Pilot harness: 21/21 cases, HARD GATES CLEAN, exit 0.

## 2. Scope

3 real public documents (all official, all partial-verbatim copies):

| # | Document | Instrument | Authority | Jurisdiction | Window | License |
|---|---|---|---|---|---|---|
| 1 | 医疗保障基金使用监督管理条例 | 国务院令第735号 | S (行政法规) | CN | 2021-05-01 → ∞ | ALLOWED(著作权法§5) |
| 2 | 零售药店医疗保障定点管理暂行办法 | 国家医保局令第3号 | A (部门规章) | CN | 2021-02-01 → ∞ | ALLOWED(著作权法§5) |
| 3 | 医疗机构医疗保障定点管理暂行办法 | 国家医保局令第2号 | A (部门规章) | CN | 2021-02-01 → ∞ | ALLOWED(著作权法§5) |

Document types covered: 行政法规 + 部门规章. NOT covered (not
obtainable verifiably this round): 法律全文 (保险法 — retrieval tool
cannot fetch wikisource URLs with parentheses; gov.cn mirror pages
not reliably located), 2026《实施细则》(no official full-text URL
found — third-party mirrors rejected as non-canonical), 地方政策
(CN-BJ — no verified page), 商业产品公开资料 (no verifiable
license), 行业协会文件. A real old/new version PAIR was therefore
NOT obtainable — temporal correctness was instead proven on the real
pre-effective window (2021-01-01) of all three documents.

## 3. Source Inventory

See knowledge/pilot/registry/pilot_sources.json (12+ metadata fields
per source, incl. canonical_uri, retrieved_at=2026-09-20,
copy_status=PARTIAL_VERBATIM, publisher, license_note) and
manifests/pilot_manifest.json (per-file sha256, byte counts, chunk
counts). Integrity: file hashes — 条例 9af970c8578f…, 药店 c6d8777d03d4…,
医疗机构 d85c4916346b….

## 4. Ingestion Result

accepted 3 / rejected 0 (all three sources carried complete,
verifiable metadata; the ingestion is offline, one-time, idempotent —
13 chunk anchors). Honest note: no document was rejected at ingestion
because every candidate that COULD NOT be verified (实施细则, wikisource
law texts, third-party mirrors) was refused BEFORE ingestion — the
fail-closed decision was made at acquisition time, not pushed into
the pipeline.

## 5. Governance Result (pilot harness, denominators explicit)

true_allow: every CURRENT-window case (P-TMP-002, P-JUR-001,
P-LIC-001) — allowed. true_deny: P-TMP-001 (3/3 docs FUTURE at
as-of 2021-01-01), P-LIC-002 (UNKNOWN-license mutation), all five
mutations. **false_allow 0 · false_deny 0.**

## 6. Retrieval Result

hit@5 = 3/3 positive cases (骗保罚款→条例; 药店执业药师条件→3号令;
医疗机构申请条件→2号令). Abstention: 1/1 (irrelevant query → zero
evidence). hit@1 ranking benchmark = NOT MEASURABLE (F-10, unchanged
— needs a relevance-labeled corpus).

## 7. Evidence Result

complete_evidence: every governance-built item from the real corpus
carries the full citation tuple (source_id/version/window/authority/
jurisdiction/license/hash/retrieved_at + governance block).
incomplete 0 · invalid 0 (P-PROV-001).

## 8. Provenance Result (one real chain, verbatim from the run)

```text
Decision(payload.evidence_refs=[chunk id])          P-DEC-001 ok
  → Evidence: evidence_id = pilot_law_medical_fund_2021_000
  → KnowledgeHit: knowledge_hit_id = same chunk id (deterministic)
  → Chunk: registered hash == item content_hash (real sha256)
  → Document: pilot_law_medical_fund_2021 (file sha 9af970c8578f…)
  → Version: cn-state-council-order-735@2021, window 2021-05-01→∞
  → Source: 医疗保障基金使用监督管理条例, S, CN, ALLOWED,
    https://www.gov.cn/zhengce/content/2021-02/19/content_5587668.htm
```

## 9. Mutation Result (on REAL evidence items)

| Mutation | Expected rule | Actual | Verdict |
|---|---|---|---|
| flip 1 hash char | P007 | P007 detected | PASS |
| version 2021→2020 | P004 | P004 detected | PASS |
| UNKNOWN→ALLOWED forgery | P009 | P009 detected | PASS |
| jurisdiction swap CN-SH | P008 | P008 detected | PASS |
| authority S→D flip | P006 | P006 detected | PASS |

## 10. 14.6 Regression (all re-run after the pilot)

```text
14.1 provider 52/52 · 14.2 POC 33/33 · 14.3 governance 74/74
14.4 governance-runtime 52/52 · 14.5 provenance 44/44
14.6 knowledge evaluation harness 50/50 HARD GATES CLEAN (unchanged)
14.7 pilot harness 21/21 HARD GATES CLEAN (new) + suite 20/20
pytest runtime 433 (430→433) · portfolio 12 · regression 51/0/1 (=)
benchmark 42/42 · compileall PASS
```

## 11. Findings

- **F-11 (P2, this phase's blocker)**: real-document acquisition from
  this environment is unreliable (WebFetch policy-blocked on gov.cn/
  github; the working retrieval channel truncates long texts;
  wikisource URLs with parentheses rejected by the tool). Consequence:
  G1 count unmet; a real old/new version pair and real CN-BJ local /
  commercial-UNKNOWN sources not obtained. Not an architecture issue.
- **F-12 (P3)**: partial-copy documents mean retrieval/provenance is
  proven on a SUBSET of each official text; before any production use
  the operator should re-ingest complete texts (pipeline-ready).
- F-02/F-04/F-05/F-06/F-08/F-09/F-10 unchanged (not addressed here,
  per the phase rules).
- No P0/P1. No false-allow/unsafe-accept/fabrication of any kind.

## 12. Known Limitations (explicitly carried, unchanged)

F-10 ranking corpus · F-09 evidence_refs convention · F-08 cache ·
F-02 startup provider enforcement · F-06 WeKnora infra. Plus F-11/F-12
above.

## 13. What unblocks Phase 14.7 → PASS

Operator-provided document package: 7+ additional official documents
(法律/监管/医保/地方/一份商业 UNKNOWN 负例) saved as files with their
URLs/文号/dates — dropped into knowledge/pilot/documents with a
metadata table. The pipeline, registry, evaluation and gates are
already in place and require ZERO code changes (re-run
ingest_pilot.py + the pilot harness).

## 14. Verdict

```text
Phase 14.7 = BLOCKED (document-count gate G1; chain proven on real data)
```

All hard gates PASS; all tests PASS; no scope violations; no
fabrication. Waiting for the operator document package or explicit
approval of the current 3-document scope.
