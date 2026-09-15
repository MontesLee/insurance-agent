> 🌐 **Language:** 🇨🇳 [中文版](ADR-003-artifact-lineage.zh-CN.md) · 🇺🇸 English

# ADR-003 · Artifact lineage

## Context
After recommending a product, the system must answer "why this one": which requirement it covers,
which risk it targets, what the gap judgment was based on, and where the client facts came from.
If layers pass free text to each other, that chain is broken.

## Decision
Every output is registered as an **Artifact with lineage**: `artifact_id` / `produced_by` (which
stage) / `input_artifacts` (which ARTs it came from) / `fingerprint` (sha256) / `evidence_refs`.
The registry **stores metadata only, never copies content** (content lives in
`state["artifacts"]`). A freezing mechanism makes published artifacts immutable.

## Alternatives
- Store only the final report: intermediate reasoning cannot be traced back.
- Write lineage inside the artifact: pollutes the contract and makes cross-artifact references
  awkward.
- Full snapshots of every intermediate state: storage explosion, and "who depends on whom" becomes
  invisible.

## Why
Lineage turns "conclusions" into "auditable derivation chains". It supports three things at once:
(1) Eval's `cross_artifact` checks (e.g. a gap must reference a really existing `risk_id`);
(2) Provenance in the report (Recommendation → Product → Evidence → Document → Chunk);
(3) Tamper detection (any fingerprint change is `ARTIFACT_MUTATION`).

## Trade-offs
- The registry must be maintained on every read/write; more code.
- The fingerprint is tightly bound to content — any harmless formatting change triggers
  inconsistency; requires strict "write once" discipline.
- Lineage reuse across Cases needs extra design (currently one client = one CaseState).
