# Production Current State (as measured, 2026-09-19, tag v0.1.0 + 7ef951c)

> Evidence sources: code reading + live probes executed during this audit.
> Every claim carries its probe. UNKNOWN where not verifiable.

## Runtime state & persistence (measured)

- **CaseState / Task / Artifact / Eval / Checkpoint**: per-project JSON +
  JSONL under `<harness_root>/<project_id>/` (case_state.json,
  artifacts/*.json, events.jsonl, checkpoints.jsonl, approvals.jsonl,
  messages.jsonl, supervisor.json, control_commands.jsonl,
  alerts/notifications). No database anywhere.
- **Project index** (`projects.json`): read-modify-rewrite from every
  `Project._save()`, no lock. **Live probe: 8 concurrent saves → 3 index
  entries survived (silent lost update).**
- **Per-project JSONL appends**: single-line append mode; probe (4 threads
  × 50 appends) produced 200 valid lines — appends are safe; the *index
  rewrite* is the race.
- **Crash recovery**: checkpoint validation (5 checks incl. fingerprint
  verify), cross-process resume, RUNNING→PENDING recovery, idempotent
  command recovery — all test-proven (Phase 7–10 suites).
- **Concurrency model**: single process; within one harness the scheduler
  thread is the sole writer (test-proven). Across harness instances /
  projects there is no coordination — only the shared index race above.

## Server & API surface

- FastAPI (`runtime/server.py`) with SSE, chat agent runs, demo runs,
  approval endpoints, supervisor/control endpoints. **No authentication of
  any kind; CORS `allow_origins=["*"]`.** Binds 127.0.0.1 by default.
- Health endpoint exists (`/api/health`) — liveness only, no dependency
  checks. 3 print statements; no structured logging, no log rotation.

## LLM provider

- OpenAI-compatible provider (`glm` via bigmodel.cn by default) with
  `timeout=60s`; agent loop retries provider errors ≤ 2 (LLM_RETRY) and
  fails closed — no silent fallback (test-proven, Phase 12).
- Usage (input/output tokens, latency, per-model) tracked on
  **in-memory AgentState only** — not written to any durable surface
  (probe: `token`/`usage` count = 0 in events.jsonl and case_state.json).
- No prompt-version tracking; prompts live in code modules.

## Knowledge & product data

- Knowledge: local demo corpus (`.trae/skills/knowledge-search/evals/
  fixtures/kb`) + RAG engine, fail-closed on empty evidence.
- Product catalog: single JSON, `is_demo: true`, `catalog_version`,
  `product_version`, `effective_from` present; **`effective_to` absent**.
  Underwriting detail probe: `deductible` and `renewal` appear; **waiting
  period, exclusions, coverage limits, coverage term, health declaration,
  occupation restrictions absent.**

## Human control

- HITL approval gateway gates **high-impact replans only**
  (`ApprovalPolicy.evaluate_replan`); **no approval gate on report /
  recommendation artifacts** (probe: policy source evaluates replans only).
- Deterministic pipeline stage gates exist in `orchestrator.run`
  (gate_policy=stop) but the agent-mode tool path **auto-approves gates**
  (`tools.py`: "V0.1: auto-approve the human-review gate").
- HOTL control plane (pause/resume/retry/replan/information) — full, with
  actor allowlist; **approval TTL is manual-only** (EXPIRED transition
  exists; no automatic expiry — probe: no ttl/expire_at logic).

## Secrets

- `.env` gitignored ✓; `describe()` masks the key ✓; no api_key strings
  in event/trace/checkpoint code paths (git grep probe) ✓. 17 tracked
  files mention `api_key` as identifiers only.

## Testing & regression (measured this round)

326 tests passing · full regression 51/0/1 (pre-existing step3-mutation +
GBK console) · benchmark 11/11 hard gates 0 · compileall OK · demos all
exit 0.

## Deployment model

Local development runs (`python -m runtime.server` + Vite dev UI). No
Dockerfile, no service definition, no environment separation, no backup
tooling (git grep "backup": docs only).
