# Artifacts, Lineage & Provenance

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](artifacts-and-provenance.zh-CN.md)

Source of truth: `runtime/artifact_registry.py`, `runtime/state/case_state.py`
(`put_artifact`), `runtime/state/transitions.py`, `contracts/`.

## 1. Artifact = the durable output boundary

Every stage produces exactly one canonical artifact type, validated against
its JSON Schema in `contracts/` (client-profile, requirement-analysis,
risk-assessment, coverage-gap-analysis, solution-plan, knowledge-evidence,
product-candidates, product-recommendation, insurance-report). Content
lives in `state["artifacts"]` (and one inspectable file per artifact on
disk); the registry stores **metadata + lineage only** — never a second
copy of the content.

## 2. The artifact registry

Each registered artifact records:

```text
artifact_id        ART-001, ART-002 … sequential, deterministic
artifact_type      canonical type
producer_skill / producer_stage
input_artifacts    the artifact ids of declared consumes (lineage edges)
status             VALID
content_ref        artifacts/<type>.json on disk
fingerprint        sha256 of the canonical JSON — the freeze guard
evidence_refs      evidence/document ids declared inside the payload
```

- **Deterministic ids**: `ART-%03d` by registry order. In parallel mode the
  scheduler re-registers merged artifacts through the canonical path, so
  ids follow graph order regardless of thread timing (tested by asserting
  identical id maps across repeated runs).
- **Lineage**: `lineage()` walks `input_artifacts` back to the client
  facts — "where did this recommendation come from?" is answered without
  re-running anything.
- **Freeze**: `put_artifact` refuses an artifact change after completion
  (`guard_immutable`, fingerprint comparison); `verify()` re-checks every
  fingerprint on load — a mutated artifact becomes a loud
  `CHECKPOINT_INVALID`, not a silent corruption.

## 3. Duplicate & conflict handling (fail-closed)

- Re-registering the same type replaces the record **idempotently** (same
  id).
- Re-registering the same type with **different content** is rejected
  (`MERGE_REJECTED` / `ARTIFACT_COLLISION` in the parallel merge). There is
  no overwrite, ignore, or last-write-wins path.
- Duplicate *ids* cannot occur by construction (single-writer sequential
  registration); parallel tests assert uniqueness after concurrent
  execution.

## 4. Artifact vs Message

```text
Artifact = durable truth   (validated, frozen, lineage-traced, checkpointed)
Message  = coordination signal (ids only, validated, ACKed — never truth)
```

Agents communicate by referencing artifact ids; any consumer that needs
content reads the artifact through the registry. Messages never carry
payload copies and can never become a second source of truth.

## 5. Provenance in the domain layer

Beyond registry lineage, domain artifacts carry provenance payloads:
knowledge evidence declares document/chunk ids and confidence; the
recommendation artifact must reference evidence that resolves
(provenance checks in eval); report generation synthesizes only from
existing artifacts. See [insurance-domain.md](insurance-domain.md) and
ADR-003 / ADR-005.
