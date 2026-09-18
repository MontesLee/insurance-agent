# Phase 9 — Human-in-the-Loop Approval Gateway V0.1

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](human-in-the-loop.zh-CN.md)

Source of truth: `runtime/approval/` (models, store, policy, manager),
`runtime/harness/harness.py` (approval section + `resume_approval`),
`runtime/server.py` (approval API), `tests/runtime/test_approval.py`.

## 1. Why approval exists

Autonomous execution needs a reliable way for a human to keep final
control over high-impact decisions. Phase 9 adds a **Runtime control-plane
capability** — not a Skill, not an Agent feature:

> Agents may request judgement; the Planner may propose plans; the
> Harness is the only layer that pauses and resumes; a human is the final
> authority for high-impact changes.

Approval is **not** Eval: an approval can never turn an eval FAIL into a
PASS. Approval gates *structural changes* (graph activation), never
*quality verdicts*.

## 2. Who may do what (permission boundary)

| Layer | Request | Approve/Reject | Resume/Activate |
| --- | --- | --- | --- |
| Human (via API/manager) | — | ✔ (actor allowlist: `human`) | — |
| Harness | ✔ (creates requests) | — | ✔ (`resume_approval` only) |
| Agent / Tool | ✔ (request-only; no agent-originated requests are produced in V0.1) | ✘ refused by actor allowlist + no code path | ✘ |
| Planner | ✘ | ✘ refused | ✘ |
| MessageBus | coordination messages only | ✘ no code path | ✘ |

Enforced by the deterministic actor allowlist (`RESOLVE_ACTORS`) in the
manager, by construction (no importing path in agent/planner/bus code),
and by tests (T4–T7).

## 3. Approval state machine (fail-closed)

```text
PENDING → WAITING_HUMAN → APPROVED → RESUMED        (Harness-only resume)
                        → REJECTED                  (terminal: fail closed)
                        → EXPIRED                   (terminal: never continues)
```

- `EXPIRED` exists but V0.1 sets no TTLs — expiry is explicit only.
- Invalid transitions are refused (`PENDING → APPROVED` directly,
  approve-after-reject, approve-after-resume).
- Approve is idempotent on `APPROVED`; every terminal state is terminal.

## 4. The deterministic policy

`ApprovalPolicy.evaluate_replan(diff, project) → AUTO | HUMAN_APPROVAL`.
Pure function of the machine-computed graph diff — the LLM never decides
"this needs a human". High-impact means any of:

- more new tasks than `replan_added_threshold` (default 2)
- any removed task
- any changed dependency edge
- re-routing the continuation of already-completed tasks

The two other request types are **reserved, not produced** in V0.1:
`APPROVAL_EXTERNAL_ACTION` (send_email / submit_application /
call_external_api) and `APPROVAL_HIGH_IMPACT` (final product
recommendation, major plan changes, sensitive data operations).

**Default is OFF**: with no `approval_policy` installed, every outcome is
AUTO — Phase 8 behaviour is preserved exactly (tested).

## 5. Replan + approval flow

```text
replan trigger (Phase 8 semantics unchanged)
   → Planner → Graph Validator (fail-closed)
   → ApprovalPolicy
        AUTO   → revision APPROVED-by-policy → ACTIVE → execute
        HUMAN  → revision PENDING_APPROVAL (candidate persisted immutably)
                 → ApprovalRequest WAITING_HUMAN
                 → project status waiting_approval — NOTHING executes
                 → human APPROVE  → Harness resume_approval
                                     → validate approval + revision
                                     → activate → checkpoint → execute
                 → human REJECT   → revision REJECTED, replan ledger rejected;
                                    replanning stops for the project
                                    (fail closed — no alternative graph)
```

An **unapproved graph can never become active**: the candidate lives in
the revision lineage as `pending_approval`; activation happens only in
`resume_approval` after a validated `APPROVED` decision.

Graph revision lifecycle now: candidate → validated → `PENDING_APPROVAL`
→ `APPROVED` → `ACTIVE` (or `REJECTED`); the AUTO path records
`approved_by: policy:auto`, the human path `policy:human`.

## 6. Persistence, checkpoint, recovery

- `approvals.jsonl` per project (append + rewrite, like the MessageBus).
- Checkpoint records carry `approval_id` / `approval_status`; the pause
  writes an explicit `WAITING_HUMAN` checkpoint.
- Crash while waiting: a restart detects the blocking approval and
  executes **nothing** — no task runs, no graph activates
  (`run()` returns `waiting_approval`).
- Approved-but-not-resumed also blocks a plain `run()`: the explicit
  Harness resume is the only path onward.
- Rejections made in another process (via the API) are synced into the
  replan ledger and graph lineage on the next harness contact.

## 7. Parallel-scheduler compatibility

Approval is evaluated at exactly the Phase 8 replan barrier — after a
parallel pass returns (all workers joined, committed, eval/repair done).
Workers can never execute against an unapproved graph because nothing
executes at all while the project waits (tested at `max_concurrency=2`).

## 8. Observability & API

Events: `approval_requested → approval_waiting → approval_approved |
approval_rejected | approval_expired → approval_resumed` (+`
approval_failed` for refused operations), all carrying `project_id`,
`approval_id`, `graph_revision`, `timestamp` — structured data only, no
chain-of-thought. The existing SSE event stream can render them.

Minimal API (state only; execution resumes via the Harness):

```text
GET  /api/projects/{project_id}/approvals
GET  /api/approvals/{approval_id}
POST /api/approvals/{approval_id}/approve   {"actor": "human"}
POST /api/approvals/{approval_id}/reject    {"actor": "human", "reason": "..."}
```

Projects are looked up under `INSURANCE_AGENT_HARNESS_ROOT` (default
`<run_root>/harness-projects`). Approve/reject are idempotent; non-human
actors are refused with 409.

## 9. Current limitations

- V0.1 auto-produces only `APPROVAL_REPLAN` requests; external-action and
  high-impact request types are reserved shells.
- No TTLs / automatic expiry.
- Reject stops the path — no "reject → planner alternative" loop.
- The API is decision-only; resume is a library call
  (`LongRunningHarness.resume_approval`) — no UI button yet.
- **Feishu (and any external notification channel) is a future adapter,
  not part of Phase 9.**
- Phase 9 hardening note: the sequential path now performs crash-recovery
  (`RUNNING → PENDING`) and skips terminal-ok tasks that have evidence of
  completed work (completed stage or output artifacts) — closing a latent
  duplicate-execution hole that agent-mode re-runs exposed.
