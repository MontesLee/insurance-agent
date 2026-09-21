# Architecture — Phase 20

Two diagrams: system architecture and evidence flow.

## Diagram 1 — System Architecture

```text
┌─────────────────────────────────────────────────────────────────────┐
│                           User                                      │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Agent Runtime                                │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ Orchestrator │  │  Scheduler   │  │  Checkpoint / Recovery   │ │
│  │ (YAML-driven)│  │ (bounded DAG)│  │  (per-stage fingerprints)│ │
│  └──────┬───────┘  └──────┬───────┘  └──────────────────────────┘ │
│         │                 │                                         │
│  ┌──────┴────────────────┴───────┐  ┌──────────────────────────┐  │
│  │       Replanning              │  │   HITL / HOTL            │  │
│  │  (deterministic triggers,     │  │  (approval gateway,      │  │
│  │   bounded, id-based merge)    │  │   control commands)      │  │
│  └───────────────────────────────┘  └──────────────────────────┘  │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           Skills                                    │
│                                                                     │
│  Intake → Requirement → Risk → Gap → Solution → Knowledge Search   │
│           → Candidate → Recommendation → Report                   │
│                                                                     │
│  Each skill: schema contract (validates input/output),            │
│  produces exactly one canonical artifact, data-chain invariant     │
│  (FACT → REQ → RISK → GAP → SOLUTION → PRODUCT → REPORT)         │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Knowledge Layer                                │
│                                                                     │
│                    ┌──────────────────┐                            │
│                    │ KnowledgeProvider │  ← the ONLY thing         │
│                    │   (Protocol)     │    agents see              │
│                    └────────┬─────────┘                            │
│                             │                                      │
│              ┌──────────────┴──────────────┐                      │
│              ▼                             ▼                      │
│    ┌──────────────────┐          ┌──────────────────┐             │
│    │ Mock Provider    │          │ WeKnora v0.8.0   │             │
│    │ (offline tests,  │          │ (live retrieval, │             │
│    │  deterministic   │          │  Docker, local)  │             │
│    │  engine)         │          │                  │             │
│    └──────────────────┘          └──────────────────┘             │
│              │                             │                      │
│              └──────────────┬──────────────┘                      │
│                             ▼                                      │
│                    ┌──────────────────┐                            │
│                    │  KnowledgeHit    │  document_id, chunk_id,   │
│                    │                  │  content, score, hash     │
│                    └────────┬─────────┘                            │
│                             ▼                                      │
│                    ┌──────────────────┐                            │
│                    │   Governance     │  9 deterministic rules:   │
│                    │                  │  authority, license,      │
│                    │                  │  window, jurisdiction,    │
│                    │                  │  version, hash, registry  │
│                    └────────┬─────────┘                            │
│                             ▼                                      │
│                    ┌──────────────────┐                            │
│                    │    Evidence      │  citation tuple: source,  │
│                    │                  │  version, window, hash,   │
│                    │                  │  authority, retrieved_at  │
│                    └────────┬─────────┘                            │
│                             ▼                                      │
│                    ┌──────────────────┐                            │
│                    │   Provenance     │  P001–P010: hash-anchored │
│                    │                  │  4-hop chain              │
│                    └────────┬─────────┘                            │
└────────────────────────────┼────────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Decision → Report                                │
└─────────────────────────────────────────────────────────────────────┘
```

> WeKnora provides retrieval infrastructure. The Agent owns
> governance, evidence validation, provenance, and decision constraints.

## Diagram 2 — Evidence Flow (the provenance chain)

```text
┌──────────┐     ┌──────────┐     ┌──────────────┐
│ Decision │────▶│ Evidence │────▶│ KnowledgeHit │
│(recommend│     │(evidence │     │(chunk_id,    │
│  -ation) │     │ _id)     │     │ content_hash)│
└──────────┘     └──────────┘     └──────┬───────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │  WeKnora Chunk   │
                                 │ (live retrieval, │
                                 │  POST /api/v1/   │
                                 │  knowledge-search)│
                                 └────────┬─────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │    Document      │
                                 │ (document_id)    │
                                 └────────┬─────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │    Version       │
                                 │ (source_id@ver,  │
                                 │  effective_from  │
                                 │  → effective_to) │
                                 └────────┬─────────┘
                                          │
                                          ▼
                                 ┌──────────────────┐
                                 │     Source       │
                                 │ (authority: S/A/ │
                                 │  B/C/D, license: │
                                 │  ALLOWED/UNKNOWN)│
                                 └────────┬─────────┘
                                          │
                              ┌───────────┼───────────┐
                              ▼           ▼           ▼
                        ┌──────────┐ ┌────────┐ ┌───────────┐
                        │  Hash    │ │  Time  │ │ Authority │
                        │(sha256 of│ │(retriev│ │(S/A/B/C/D)│
                        │ content) │ │ed_at)  │ │           │
                        └──────────┘ └────────┘ └───────────┘

Tamper any byte in content → hash mismatch → P007 → DENY
Expired regulation → window check → DENY
Unknown license → DENY
Wrong jurisdiction → DENY
Unregistered document → DENY
```
