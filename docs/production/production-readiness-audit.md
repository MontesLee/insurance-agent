# Production Readiness Matrix

> Scope: small-scale real production — owner + 1–3 trusted users, real
> cases, human review before any customer delivery, single node.
> Severity: P0 = must fix before any real production; P1 = strongly
> recommended before small production; P2 = post-pilot; P3 = future scale.

| Domain | Current State | Evidence | Production Gap | Severity | Confidence |
| --- | --- | --- | --- | --- | --- |
| Runtime State | Single-writer scheduler per harness; task/graph/approval/control state machines all test-proven | Phase 7–10 suites (326 tests) | None for single-process scope | — (adequate) | High |
| Persistence (per-project) | JSON + JSONL per project dir; append-safe; crash-resumable | probes + Phase 7 recovery suites | No encryption at rest; single-machine only | P1 | High |
| Persistence (index) | `projects.json` read-modify-rewrite, no lock | **probe: 8 concurrent saves → 3 entries** | Lost-update on concurrent multi-project use | **P0** (correctness bug, silent) | High |
| Database | None (by design, documented) | code | Acceptable for scope; not a gap per se | P3 | High |
| Authentication | None anywhere in server | probe: no auth/login/session code; CORS `*` | Any network exposure = open access; localhost-only trusted use is the only safe mode | **P0** for external, P1 for internal-localhost | High |
| Authorization | No users/roles/case ownership; agent/tool/approval actor scopes DO exist (runtime-internal) | probe + approval actor allowlist | No human role model (who may approve/read which case) | P1 | High |
| LLM Provider | OpenAI-compatible, timeout 60s, bounded retry, fail-closed on outage (no silent fallback) | Phase 12 smoke + tests | Provider data-retention/training policy not verified | P1 (verification) | High (code) / UNKNOWN (policy) |
| LLM Reliability | Bounded loops everywhere (agent ≤8/12 steps, retry ≤2, repair ≤2, replan ≤2) | tests | None for scope | — (adequate) | High |
| Rate Limit | None | code | No per-user/case LLM call ceiling beyond loop bounds | P2 | High |
| Cost Control | Token usage captured in memory only; 0 occurrences in durable state | probe | Cannot answer "what did this case cost?" | P1 | High |
| Knowledge | Local demo corpus, fail-closed, provenance per item | code + tests | Real knowledge source absent; fine for pilot with human review | P2 | High |
| Product Data | Demo catalog: versioned, `is_demo`, `effective_from`; **no `effective_to`; missing waiting period / exclusions / coverage limits / health declaration / occupation restrictions / coverage term** | catalog probe | **Not sufficient for real product recommendation evidence** | **P0** for real-case recommendation | High |
| Data Privacy | Client facts + derived analysis written plaintext into events.jsonl (156 sensitive-term hits) and case_state.json (312 hits) | probe on real B001 run | No minimization review, no encryption, no retention policy | **P0** for real client data | High |
| Audit Log | Durable append-only events.jsonl per project; control_commands.jsonl; approvals.jsonl | code | Strong for runtime audit; lacks user identity (no users) | — (adequate) / P2 (identity) | High |
| Provenance | Artifact lineage, fingerprints, evidence refs, human-input provenance; fingerprint tampering fails loudly | tests + tamper probes | Strong; depends on knowledge/catalog quality (see Product Data) | — (adequate) | High |
| Observability | Durable events + trace + SSE; can answer "how was this report generated?" | runtime-trace.md (from real run) | No metrics, no alerting, shallow health check, no structured logs | P2 | High |
| Evaluation (runtime) | Dependency/permission/artifact/provenance/state-transition evals: deterministic, test-proven | benchmark + false-pass suite | None for scope | — (adequate) | High |
| Evaluation (domain) | Report artifact eval is thin: required_fields=`payload` only; **no provenance/invariant checks on insurance-report** | eval.rules probe | Report quality eval materially weaker than candidates/recommendation | P1 | High |
| Human Review (final deliverable) | **No enforced review gate on report/recommendation**; approval policy gates replans only; agent-mode stage tools auto-approve human-review gates (documented V0.1 behavior) | policy probe + tools.py | Required target flow (report → human review → manual delivery) is not enforced by the runtime | **P0** | High |
| Backup | None (no tooling, docs mentions only) | git grep | Real client data with no backup path | P1 | High |
| Recovery (process/crash) | Checkpoint + cross-process resume + idempotent commands: test-proven | Phase 7–10 suites | Machine-loss recovery = copy the JSON tree manually | P2 | High |
| Secrets | .env gitignored; describe() masks key; no key in log paths | probes | Adequate for scope | — (adequate) | High |
| Deployment | Local dev server; no Dockerfile/service/env separation | repo scan | No defined deploy/restart procedure for a pilot host | P1 | High |
| Monitoring | /api/health liveness only; no metrics/alerting | probe | Pilot survivable without; needed before external | P2 | High |
| Testing | 326 tests, 11/11 benchmark, 18/18 injection, false-pass 0 | this round's runs | None for scope | — (strength) | High |
| Security (runtime-internal) | Actor allowlists, scoped tools, validated messages, fail-closed everywhere | tests | Strong internally; external attack surface untested (CORS `*`, no authn) | P1 (external) | High |
