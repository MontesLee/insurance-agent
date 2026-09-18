# Roadmap — Future Work (NOT implemented)

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](roadmap.zh-CN.md)

Everything on this page is **future direction**. None of it exists in the
codebase today; the list records where the frozen architecture could
plausibly grow. Each item notes the existing seam it would build on.

| Direction | Status | Natural seam |
| --- | --- | --- |
| ~~Dynamic replanning~~ **IMPLEMENTED in Phase 8 V0.1** — bounded, Harness-controlled, immutable revisions ([dynamic-replanning.md](architecture/dynamic-replanning.md)) | implemented | future: `MISSING_REQUIRED_INFORMATION` triggers, mid-round replanning, human approval gate |
| Graph revision / planner retry on runtime feedback | partially — Phase 8 feeds runtime outcomes (statuses, trigger) back into a validated replan; generic feedback loops remain future work | `ReplanContext` is the seam |
| Durable external queue (Redis/Kafka/…) | not implemented | checkpoint/queue boundaries are already file-shaped; no queue client anywhere |
| Distributed workers | not implemented | worker isolation + scheduler-owned commit are the local precursor; no network layer |
| Human-in-the-loop approval UI for `NEEDS_REVIEW` tasks | partially: `NEEDS_REVIEW` + gates exist; review happens programmatically (`orchestrator.approve`) | task states and events already model review; no approval screen |
| Feishu / external notifications | not implemented | — |
| Long-running production execution (services, watchers) | not implemented | harness is a library; `python -m runtime.server` is the only long-lived process |
| Richer knowledge sources (external corpora, licensed content) | not implemented | Evidence Provider is the single seam; corpus is a local demo KB |
| Additional domains beyond insurance | not implemented | skills/contracts/catalog are the domain pack to swap |

Constraints that should continue to hold for any of the above: the
Planner/Agent/Skill/Tool/Harness/Eval/Artifact separation, Harness-owned
eval, fail-closed validation everywhere, and deterministic commits.
