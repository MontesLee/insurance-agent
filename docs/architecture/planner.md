# Planner & Graph Validation

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](planner.zh-CN.md)

Source of truth: `runtime/planner/` (`planner.py`, `registry.py`,
`schemas.py`, `validator.py`, `prompts.py`).

## 1. Positioning

```text
Planner produces UNTRUSTED plans
        ↓
Validator makes them TRUSTED
        ↓
Harness executes
```

The Planner is **not** an unrestricted autonomous agent. It converts a user
request into a strict JSON Task Graph and that is all it does: it does not
execute tasks, call skills, or touch CaseState. Everything it cannot prove,
the system rejects (fail-closed).

## 2. Pipeline

```text
user request
 ↓ build_planner_prompt
LLM provider (any LLMProvider; FakePlannerProvider for tests)
 ↓ raw text → strip markdown fences → json.loads
JSON Schema validation (TASK_GRAPH_SCHEMA)
 ↓
Graph validation (validator.validate_graph)
 ↓ ok
_normalize(): fill task fields FROM THE TRUSTED REGISTRY (never from LLM output)
 ↓
TaskGraph {graph_id, tasks[], entry_tasks, terminal_tasks, created_at, source_request}
```

## 3. Trusted Task Registry (`registry.py`)

Nine hand-curated task types — the closed vocabulary the Planner may choose
from (an unknown `task_type` is rejected):

| task_type | stage | produces |
| --- | --- | --- |
| `client_profile` | client-intake (provided) | client-profile |
| `requirement_analysis` | requirement-analysis (provided) | requirement-analysis |
| `risk_analysis` | risk-analysis (provided) | risk-assessment |
| `coverage_gap` | coverage-gap-analysis | coverage-gap-analysis |
| `solution` | solution | solution-plan |
| `knowledge_search` | product-candidate-provider (service) | knowledge-evidence |
| `product_candidates` | product-candidate-provider | product-candidates |
| `recommendation` | product-recommendation | product-recommendation |
| `report_generation` | report-generation | insurance-report |

Each entry declares `required_inputs`, `produced_artifacts` and
`required_eval` — the trusted data the validator checks against and the
Harness executes with. The LLM's own claims about inputs/outputs are never
used.

## 4. The 10 validator checks (`validator.py`, fail-closed)

1. `task_id` unique
2. `task_type` exists in the Registry
3. every dependency references an existing task
4. **no circular dependency** (Kahn's algorithm topological sort)
5. at least one entry task (no dependencies)
6. at least one terminal task (nothing depends on it)
7. every task can reach a terminal (no dead branches)
8. **artifact contract**: each task's `required_inputs` are produced by its
   transitive upstream (artifacts accumulate along the dependency chain)
9. **eval contract**: every registry task type declares `required_eval`
10. unknown fields are surfaced (`_extra_fields`), never executed — only the
    whitelist `task_id / task_type / description / dependencies` reaches the
    Harness

## 5. Bounded retry, fail-closed

```text
attempt 1 → parse/schema/graph error?
attempt 2 (retry) → error?
attempt 3 (retry) → error?
        ↓
PlannerResult(status="needs_review", errors=[...])   # MAX_PLANNER_RETRIES = 2
```

Malformed JSON, schema violations and graph violations all retry with the
same bounded budget (3 attempts total). There is **no silent deterministic
fallback plan** — an exhausted planner surfaces `needs_review` with the
accumulated errors. Observable events: `planner_started`,
`graph_validation_started/passed/failed`, `planner_completed/failed`.

## 6. What the Harness receives

A validated graph with registry-filled fields (`input_artifacts`,
`expected_artifacts`, `required_eval`, `status=PLANNED`, `max_attempts=3`).
Task IDs from the graph are preserved so dependencies resolve; the graph is
immutable from here on — nothing downstream (agents, messages, scheduler)
may add, remove or rewire tasks.
