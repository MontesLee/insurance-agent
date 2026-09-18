# Architecture

> 🌐 Language: 🇺🇸 English (this file is the Phase-12 entry-point diagram set;
> deep-dives live in [architecture/](architecture/overview.md))

## System architecture

```mermaid
flowchart TD
    U[User Request] --> PL[Planner]
    PL --> GV{Graph Validator<br/>10 checks · fail-closed}
    GV -->|invalid| NR[NEEDS_REVIEW]
    GV -->|valid| HA[Harness — the Runtime Authority]
    HA --> SC[Bounded DAG Scheduler<br/>sequential / parallel rounds]
    SC --> A1[insurance_analyst]
    SC --> A2[knowledge_specialist]
    SC --> A3[product_specialist]
    SC --> A4[report_specialist]
    A1 & A2 & A3 & A4 --> BUS[MessageBus<br/>A2A coordination only]
    A1 & A2 & A3 & A4 --> ART[Artifacts + provenance]
    ART --> EV{Eval — Harness-owned}
    EV -->|PASS| CP[Checkpoint]
    EV -->|FAIL| RP[Repair ≤ 2]
    RP --> EV
    RP -->|exhausted| RP2[NEEDS_REVIEW → Replan]
    CP --> NEXT[Next runnable tasks]
    NEXT --> SC
```

## Control architecture — humans are NOT nodes in the DAG

```mermaid
flowchart TD
    H[Human Supervisor<br/>above the DAG] -->|approve / reject| AP[Approval Gateway · HITL]
    H -->|pause / resume / retry / replan| CPL[Control Plane · HOTL]
    AP --> HA2[Harness]
    CPL --> HA2
    MON[Runtime Monitor<br/>observe only — deterministic] -->|signals / risk| CPL
    HA2 -->|events| MON
    PL2[Planner<br/>plan authority — WHAT] --> HA2
    HA2 --> AG[Agents<br/>execute / request — HOW]
    AG --> HA2
```

```text
Harness  = Runtime Authority (the only scheduler / state mutator)
Planner  = Plan Authority (untrusted output → validated graphs)
Monitor  = Observe Only (deterministic signals, no commands)
Agent    = Execute / Request (never PASS, never control)
Human    = Approve / Intervene (through the control plane, never direct)
```

## Why not just an LLM call?

```text
A normal LLM app:      Request → LLM → Answer

This runtime:          Request → Planner → Task Graph → Multi-Agent
                       → Artifacts → Eval → Repair → Replanning
                       → Human Control → Recoverable Final Result
```

Generic runtime vs domain adapter: see [generalization.md](generalization.md).
The full phase-by-phase architecture lives in
[architecture/overview.md](architecture/overview.md).
