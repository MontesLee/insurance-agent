# Phase 10 — Human-on-the-loop Control Plane V0.1

> 🌐 Language: 🇺🇸 English · 🇨🇳 [中文版](human-on-the-loop.zh-CN.md)

Source of truth: `runtime/control/` (models, store, monitor, policy,
manager), `runtime/harness/harness.py` (control section + gates),
`runtime/server.py` (supervisor API), `tests/runtime/test_human_on_loop.py`.

## 1. HITL vs HOTL — the distinction that defines this phase

```text
HITL (Phase 9): a specific action/graph REQUIRES a human decision.
    Task → Approval gate → WAITING_HUMAN → human decides → continue.

HOTL (Phase 10): the human SUPERVISES from above the workflow DAG.
    Agents keep executing autonomously; a deterministic monitor watches
    runtime health; only deterministic thresholds notify or pause.
```

**The human is outside the DAG.** Normal execution never waits for a
human; the human can always observe, and can intervene whenever
deterministic runtime policies say intervention is warranted.

## 2. Architecture

```text
                         HUMAN (supervisor)
                           │
                   ┌───────┴────────┐
                   │ Control Plane  │  observe / pause / resume / retry /
                   │                │  replan / cancel / information /
                   └───────┬────────┘  approve / reject
                           ↓ (commands are AUDITED and applied BY THE HARNESS)
                     ┌───────────┐
                     │  Harness  │
                     └─────┬─────┘
                    DAG scheduler (sequential / bounded-parallel)
                           ↓
                      Agents → Artifacts → Eval → Replan
                           ↓
                  RuntimeMonitor (deterministic observation ONLY)
                           ↓
               signals → runtime risk → InterventionPolicy
                           ↓
             NONE / NOTIFY / PAUSE / WAIT_APPROVAL
```

Separation upheld: Planner = WHAT · Agent = HOW · Harness = execution +
control + recovery · Eval = quality · Artifact = truth · MessageBus =
coordination · Approval (Phase 9) = explicit human approval boundary ·
Monitor = observe runtime health · ControlPlane = human intervention
boundary · Human = supervisor.

## 3. Monitor (deterministic; the LLM is never consulted)

`RuntimeMonitor.observe(project, events)` is a pure function of durable
state + the event log. Signals (V0.1):

| Signal | Severity | Deterministic source |
| --- | --- | --- |
| `SIGNAL_TASK_FAILURE` | MEDIUM | task FAILED / NEEDS_REVIEW (incl. failed replans) |
| `SIGNAL_REPAIR_EXHAUSTED` | MEDIUM | failed task with attempts ≥ 3 |
| `SIGNAL_REPLAN_EXHAUSTED` | HIGH | replan budget consumed with non-accepted attempts |
| `SIGNAL_REPLAN_NO_CHANGE` | MEDIUM | replan reproduced the same graph |
| `SIGNAL_BUDGET_EXCEEDED` | MEDIUM | task/repair counts over configured budgets |
| `SIGNAL_LONG_RUNNING` | MEDIUM | task RUNNING beyond a staleness threshold |
| `SIGNAL_REPEATED_FAILURE` | HIGH | ≥ N `task_failed` events for one task (event log) |
| `SIGNAL_GRAPH_CHANGE_HIGH_IMPACT` | HIGH | reuses the Phase 8 graph diff verbatim |
| `SIGNAL_INTEGRITY` | CRITICAL | dangling dependency / no active revision matching `current_graph_revision` / unknown task status |

Runtime risk roll-up: LOW < MEDIUM < HIGH < CRITICAL (max severity).
**These are runtime execution risks, not insurance business risks** —
unrelated to the domain's R1–R5 client risk categories.

Dedup / event-storm prevention (§34/§35): each signal has a stable
fingerprint (project, type, task, graph revision, relevant state). An
OPEN alert with the same fingerprint is never duplicated and never
re-notified; alerts whose condition clears are RESOLVED; historically
true signals (an applied graph change) stay OPEN until a human
acknowledges them by resuming. Resuming records the acknowledged
fingerprints durably — a persistent-but-reviewed signal cannot re-pause
the runtime, while a genuinely changed state produces a new fingerprint
and fires again.

## 4. Intervention policy (deterministic)

```text
LOW      → NONE        (autonomous continue)
MEDIUM   → NOTIFY      (notification persisted; execution continues)
HIGH     → NOTIFY      (configurable, e.g. high="PAUSE")
CRITICAL → PAUSE       (at the safe barrier)
```

plus **WAIT_APPROVAL** whenever a Phase 9 approval gate is already
waiting — the approval boundary keeps priority over supervisor
notifications. The policy does NOT replace the ApprovalPolicy: the
ApprovalPolicy decides whether a *specific graph/action* needs approval;
the InterventionPolicy decides whether the *runtime's current state*
warrants human attention.

## 5. Control commands (audited, idempotent, Harness-applied)

`ControlPlane.command(...)` persists the command
(`control_commands.jsonl`), then the Harness — the only executor —
validates, mutates state, checkpoints and emits events. Commands never
mutate state directly (§5/§32). The command fingerprint includes the
actor and payload: an identical repeated command returns the original
applied record (idempotent), and an unauthorized actor can never ride an
applied command. Crashed pending commands (persisted, unapplied) are
recovered idempotently on the next harness contact.

| Command | Semantics |
| --- | --- |
| `PAUSE` | supervisor pause; with workers RUNNING it defers to the next safe barrier (PAUSING → PAUSED), never kills mid-commit |
| `RESUME` | PAUSED → RUNNING; acknowledges the alerts that drove the pause (hysteresis) |
| `RETRY_TASK` | validated retry of a terminal-failed task (exists, not RUNNING/PENDING/terminal-ok, deps met) → PENDING; the scheduler decides |
| `CANCEL` | fail-closed project cancellation; all history preserved |
| `REPLAN` | routes through the EXISTING Phase 8 replanner (validator, revisions, diff, budget, no-change guard) |
| `PROVIDE_INFORMATION` | creates a `human-input` ARTIFACT with provenance |
| `APPROVE` / `REJECT` | delegate to the Phase 9 approval manager |

## 6. Runtime statuses & persistence

Supervisor statuses: RUNNING, PAUSING, PAUSED, RESUMING, COMPLETED,
FAILED, CANCELLED, **WAITING_HUMAN** (Phase 9 approval — semantically
distinct from PAUSED). Durable per project:
`supervisor.json` (SupervisorState), `alerts.jsonl`, `notifications.jsonl`,
`control_commands.jsonl`. Checkpoints carry supervisor fields
(status/risk/active alerts/pending interventions/last command id) in the
SAME checkpoint system. No external stores (file JSON only).

## 7. Crash / recovery

- PAUSED at crash → restart executes nothing until RESUME.
- PAUSE persisted but unapplied at crash → idempotent recovery applies it once.
- Same for RESUME / RETRY / REPLAN commands (each idempotent).
- Observations happen only at safe barriers (round boundaries / after
  commit + eval/repair) — never mid-round; Phase 7 worker isolation is
  untouched.

## 8. Permission boundary (§24)

Human → observe + all commands. Harness → internal operations +
command application. Agent → may REQUEST intervention (a signal recorded
as an alert/notification — `request_intervention`; it can never pause or
mutate). Planner → candidate graphs only. Monitor → observe only
(structurally: no command surface). MessageBus → coordination only.
Enforced by the actor allowlist in the Harness command executor, by
construction, and by structural tests.

## 9. API (state via control plane; the Harness applies)

```text
GET  /api/projects/{id}/supervisor | /alerts | /notifications | /control-commands
POST /api/projects/{id}/control/pause | resume | retry | replan | cancel | information
```

Plus the unchanged Phase 9 `/api/approvals/*`. The API only parses and
creates commands — HTTP → ControlPlane → Harness, never direct state
mutation. Agent execution continues in the harness runtime (the API
process applies state-level effects only).

## 10. Current limitations (accepted for V0.1)

Feishu (and any external notification channel) is a future adapter that
will consume the persisted Notification model — not part of Phase 10.
No LLM anomaly detection, no real token accounting (budgets are
task/replan/repair counts), no automatic worker termination, no
TTL-based alerts, no multi-user RBAC, minimal UI (SSE events render the
supervisor state). SIGNAL_LONG_RUNNING reads wall-clock age by nature
(excluded from determinism claims).
