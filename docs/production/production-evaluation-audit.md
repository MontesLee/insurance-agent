# Evaluation & Human Review Audit

## Three layers, current coverage

### Runtime eval (strong)

Dependency/permission validation, artifact contracts + registry
fingerprints, provenance resolvability, state-transition legality,
duplicate-execution prevention — deterministic, adversarially tested
(false-pass count 0; tamper testing breaks the benchmark when the runtime
is broken). This layer is production-grade for the stated scope.

### Domain eval (uneven)

Strong for candidates/recommendation (catalog invariants, candidate-known
chains, contamination). **Materially thin for the final deliverable**: the
insurance-report eval requires only `payload` presence — no provenance
checks, no invariants, no cross-artifact consistency rules are registered
for `insurance-report` (rules-file probe). The last artifact a human
receives is the least-evaluated one.

### Human review (missing on the final deliverable — P0)

The target production flow is: Agent → Report → **Human Review** →
Approve/Modify/Reject → Manual Delivery. Measured reality:

- The approval gateway gates **high-impact replans only**
  (`ApprovalPolicy.evaluate_replan` is the only policy hook).
- A project reaches `COMPLETED` with a final report and **no approval
  record is required anywhere** — verified by policy-source probe and by
  the benchmark's own happy path (B001 completes with
  `forbidden_events: approval_waiting`).
- The deterministic pipeline's human-review stage gates are
  **auto-approved** in the agent tool path (`runtime/agent/tools.py`,
  documented V0.1 behavior) and auto-approved under `gate_policy="auto"`.

So the runtime cannot currently enforce "no deliverable without a human".
For the stated scope — agent must never auto-complete final customer
delivery — this is a **P0 blocker**. (The primitives to fix it exist:
the approval gateway, the WAITING_HUMAN project state, and the
artifact-level hooks; noting that fact is not an implementation plan.)

## Bypass check (asked explicitly)

Path for a product recommendation to skip human review: **yes, the
default path** — recommendation artifacts are eval-gated (catalog
invariants) but never human-gated. REJECT-side semantics exist only for
replan approvals.

## Observability (does it answer "how was this report generated?")

Yes, today: durable events (task/agent/tool/eval/repair/replan/approval)
+ artifact lineage + per-artifact provenance reproduce the full chain —
demonstrated in `docs/runtime-trace.md` from a real run. Gaps are
operational, not structural: no user identity on events (no users), no
metrics/aggregation, shallow health check, no structured process logs.
