# Roadmap — Future Work (NOT implemented)

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](roadmap.zh-CN.md)

Everything on this page is **future direction**. None of it exists in the
codebase today; the list records where the frozen architecture could
plausibly grow. Each item notes the existing seam it would build on.

| Direction | Status | Natural seam |
| --- | --- | --- |
| **Dynamic replanning** — revise the Task Graph at runtime based on eval results / new facts | not implemented (Phase 8 candidate) | the graph is already immutable end-to-end; a replanner would be a new, separately-validated stage between Planner and Harness, still unable to mutate an executing graph |
| Graph revision / planner retry on runtime feedback | not implemented | `PlannerResult` + validator already fail-closed; runtime outcomes are not fed back |
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
