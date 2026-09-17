# Chat UI — Phase 2.5/2.6: Chat-first Agent System UI (V0.1)

> The default face of the app is now a **chatbot**, not a test console — but it is a
> *chat-first Agent System UI*, not a chat product. One runtime, one run, one event
> stream, one artifact set; two views (User Mode chat, Developer Mode console).
>
> **Chat UI does not own Agent execution state. Runtime remains the source of truth.**

## Phase 2.6 — Real LLM Agent Mode (side by side with Demo Mode)

The chat header carries a mode switch: **Agent**（默认，真实 LLM 理解与决策）/ **演示 Demo**
（结构化 case → deterministic runtime，即 Phase 2.5 的 Portfolio Demo Mode）。没有 LLM key
时 Agent 模式 **fail closed**（503 + 横幅引导切换演示模式），绝不静默回退成 demo。

```text
Chat UI ── POST /api/chats/{id}/messages ──▶ Agent Loop (runtime/agent/)
                                                │  LLM: understand / decide / tool-call
                                                │  (native tool calling, JSON-Schema validated)
                                                ▼
                                    ToolRegistry (runtime/agent/tools.py)
                              record_client_profile / record_requirement_analysis /
                              record_risk_assessment   ← dialogue skills via EXISTING
                                                        adapters + CaseState + Eval
                              coverage_gap / solution / candidates / recommendation /
                              report                   ← EXISTING engines via
                                                        orchestrator._execute_stage
                                                        (existing Eval + Repair inside)
                              knowledge_search / check_catalog_product
                                                ▼
                       Artifacts → deterministic Eval → (Repair ≤2) → Report
                                                ▼
                       RuntimeEvents (agent_step_started / agent_decision /
                       tool_* / stage_* / eval_* / artifact_* / run_*)
                                                ▼
                       SAME EventBus / SSE / artifacts endpoints as Mode A
```

Boundaries (spec §55): the LLM never judges evals, never invents products
(`check_catalog_product` / catalog-only candidates), never sees its decisions
bypass CaseState; client facts from the conversation carry
`source=conversation:user_message` provenance and are frozen once downstream
analysis starts. Hard limits: 12 agent steps / turn, 2 retries on malformed
structured output, eval-FAIL-after-repair ⇒ stop & NEEDS_REVIEW. Provider config
is env-only (`LLM_PROVIDER/LLM_MODEL/LLM_API_KEY[/LLM_BASE_URL]`, any
OpenAI-compatible endpoint); keys never appear in events/trace/artifacts/logs.
`python -m runtime.agent.smoke_test` runs the real provider path when configured
(it is NOT part of regression; all tests use `FakeLLMProvider`).

```text
Chat UI ── POST /api/runs ──▶ Existing Agent Runtime
   ▲                              │
   │                        RuntimeEvents (SSE)
   └──────────────────────────────┘
```

The chat never adds a second execution engine: sending a message maps to a demo
case and calls the SAME `POST /api/runs`; every progress pixel comes from that
run's SSE RuntimeEvents folded through `runReducer` (the explicit event→UI
transition table). **Honest scope:** the current demo uses structured Client State
upstream (`Portfolio Demo Mode` is disclosed in the welcome screen and on every
activity card); raw natural-language intake remains outside the primary execution
path.

## Layout & modes

```text
┌──────────────┬──────────────────────────┬───────────────┐
│ Chats        │ Conversation             │ Agent         │
│ (history,    │ user / assistant /        │ Inspector     │
│  新对话)      │ AGENT ACTIVITY card /    │ RUN · PIPELINE│
│              │ artifact card · composer  │ · EVAL · TRACE│
└──────────────┴──────────────────────────┴───────────────┘
   lg ≥1024px: 3 columns · <xl: inspector drawer · <lg: sidebar drawer
```

* **User Mode (default)** — `ChatLayout`: history (localStorage, versioned
  `{version, chats}` envelope shaped for future backend persistence), conversation,
  composer (Enter send / Shift+Enter newline; while running the only action is
  **停止查看** — an honest VIEW disconnect, the runtime keeps running; 重新连接
  re-attaches from the persisted cursor).
* **Developer Mode** (`⚙ Developer Mode`) — the Phase 2 Cases / Runtime console,
  unchanged; `← 返回 Chat`.

## Message model (`types/chat.ts`)

`user | assistant | activity | artifact` — activity is never persisted as content:
the stored message is only a `{runId}` reference, and the live card is re-derived
from the runtime's events on every attach (page refresh rebuilds it identically
via `after_event_id` replay). Finalize is idempotent (`fin-<runId>`).

## Agent Activity card (`components/chat/AgentActivity.tsx`)

Stage checklist (Chinese labels) + eval summary + latest activity line — all
derived from `RunUiState`, never invented. Wording is a **pure mapping**
(`state/activity.ts`): `stage_started → 正在识别家庭风险`, `eval_failed → 风险分析校验未通过`,
`repair_exhausted → 修复次数用尽，转人工复核`… **No chain-of-thought is ever shown** —
only observable actions/outcomes (a test asserts the absence of 思考/猜测/我认为
phrasing). Terminal states are honest: completed / 需要人工复核 / 等待补充客户信息 /
运行失败, and a failed analysis delivers an explicit refusal ("没有把握的推荐不会出现在结果里").

## Demo Case Adapter (`state/chatState.ts`)

`mapPromptToCase` maps the prompt to a benchmark case (医疗→006, 意外→007,
高风险→highrisk-001, default→complete-001); the composer shows the mapped case in a
selector the user can override. Sending = `POST /api/runs`; a **409
case_already_running** renders a banner offering to open the conversation that owns
the active run (when local) — the runtime's Phase 1.1 guard, surfaced honestly.

## Tests

* Unit (vitest): chat-state reducer/persistence/mapping, activity wording for all
  event types (+ no-CoT guard), AgentActivity rendering from reducer-built state,
  Composer keys & stop/resume, Welcome fill-not-send, transcript/conflict/stale-run
  rendering.
* E2E (`E2E_RUNTIME=1`): real python backend — prompt → mapped case → POST /api/runs
  → SSE → same reducers → 8-stage pipeline / evals / artifact card / report content,
  run_id identity, finalize idempotency, and the 409 contract.
* Developer Mode regression: its components' tests plus the Phase 2 E2E
  (`runtime-chain.e2e.test.ts`) continue to pass unchanged.

## V0.1 limitations

Local-only chat history (no backend persistence), fixed honest assistant scripts
(no LLM turn-taking — the runtime is deterministic and the UI does not fake
conversational intelligence), demo-case mapping only (no NL intake), single
backend process (in-memory runs; a restart makes old chats show an honest
"历史运行已结束" note instead of a fake timeline).
