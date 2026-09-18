# Specialist Agents

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](agents.zh-CN.md)

Source of truth: `runtime/agents/registry.py`, `runtime/agents/executor.py`,
`runtime/agent/tools.py`.

## 1. Positioning

Agents are **executors, not controllers**. An agent receives one assigned
task, runs its own bounded LLM tool-calling loop against a scoped tool set,
and produces artifact candidates. It cannot:

- decide parallelism, create tasks or agents, modify the graph or dependencies
- skip eval, mark itself PASS, or touch harness state, checkpoints, scheduler

## 2. Agent Registry — four specialists

| agent_id | Allowed task types | Allowed tools (besides `send_agent_message`) |
| --- | --- | --- |
| `insurance_analyst` | client_profile, requirement_analysis, risk_analysis, coverage_gap, solution | record_client_profile, record_requirement_analysis, record_risk_assessment, coverage_gap_analysis, solution |
| `knowledge_specialist` | knowledge_search | knowledge_search |
| `product_specialist` | product_candidates, recommendation | product_candidate_provider, recommendation, check_catalog_product |
| `report_specialist` | report_generation | report_generation |

Assignment is **deterministic** (`TASK_AGENT_MAP`, derived from the
registry) — the LLM never chooses who executes a task. Before execution the
Harness validates the assignment (`validate_assignment`); an invalid
assignment blocks the task without running it.

## 3. The executor loop (`SpecialistAgentExecutor`)

```text
assigned task
 ↓ load agent definition + validate assignment
 ↓ expected artifact contract from the PLANNER REGISTRY (trusted)
 ↓ build agent-scoped tool registry (allowed tools + send_agent_message)
 ↓ LLM loop, MAX_AGENT_STEPS = 8:
      tool call → authorization check → JSON-Schema argument validation
                → execute via ToolContext (skip_eval=True)
                → structured result fed back to the LLM
 ↓ validate output against the artifact contract
 ↓ ARTIFACT_READY   (the artifact exists; eval has NOT run)
```

Key properties:

- **`skip_eval=True`**: tools store artifacts without evaluating; the
  artifact candidate is the executor's only product.
- Every limit fails closed (`AGENT_FAILED` with an error code — step limit,
  empty response, LLM error, output contract violation). There is no path
  where the executor declares success.
- Events emitted are actions/summaries only (`agent_step_started`,
  `agent_tool_call`, `agent_tool_completed`, `agent_output_validated`) —
  never hidden reasoning.

## 4. Tools (agent-facing capability interface)

Tools are thin, schema-validated wrappers over existing skills and the
deterministic runtime (`runtime/agent/tools.py`):

- **Dialogue tools** (`record_client_profile`, `record_requirement_analysis`,
  `record_risk_assessment`): canonicalize user-stated facts through the
  existing adapters; the LLM only supplies candidate facts.
- **Stage tools** (`coverage_gap_analysis`, `solution`,
  `product_candidate_provider`, `recommendation`, `report_generation`):
  invoke the deterministic workflow stages through
  `orchestrator._execute_stage` — the LLM cannot override an eval verdict
  there either.
- **Knowledge tools** (`knowledge_search`): RAG through the shared Evidence
  Provider; empty results fail closed (no fabricated evidence is stored).
- **Catalog tool** (`check_catalog_product`): read-only catalog lookup.
- **Communication tool** (`send_agent_message`): validated A2A messaging —
  see [a2a.md](a2a.md). The tool schema has no `from_agent` parameter:
  sender identity comes from the executor context, never from the LLM.

In parallel mode, workers run this same executor on an isolated CaseState
copy with a capture-only project proxy (see
[parallel-scheduler.md](parallel-scheduler.md)).

## 5. The chat agent (a different layer)

`runtime/agent/agent.py` (`run_agent_turn`) is the **interactive** loop the
web chat uses: ≤ 12 steps, LLM retry ≤ 2, structured `agent_decide`
decisions (intent routing, `ask_user`, `call_tool`, `finish`), optional
fast-model cost tier. It shares the tool registry and the same fail-closed
discipline, but it is not part of the harness task pipeline.
