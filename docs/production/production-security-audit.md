# Security & Privacy Audit

## Authentication / Authorization

**Authentication: none.** The FastAPI server has no login, session, token
or API-key verification for any endpoint; CORS is `allow_origins=["*"]`.
Default bind is 127.0.0.1 — safe only while the pilot stays strictly
localhost with trusted users on the machine. Any LAN/VPN exposure makes
every endpoint (including approve/reject and control commands) publicly
callable.

**Authorization: no human role model.** There are no users, roles, case
ownership or per-case read permissions. Concretely today:

- Who can create a case? Anyone who can reach the server (chat/demos) or
  run the harness library.
- Who can read a case/artifacts? Anyone with filesystem access to the
  harness root (all plaintext).
- Agent cross-case access? Agents receive an isolated CaseState copy per
  task; no cross-case path exists in the runtime (good).
- Tool scopes? Yes — registry-enforced per agent (runtime-internal, solid).
- Who can approve? Anyone who can POST `/api/approvals/{id}/approve` with
  `actor: "human"` — the actor string is client-supplied; the allowlist
  trusts the claim.
- Who can view audit logs? Anyone with filesystem access.

## Data privacy

Measured on a real benchmark run: sensitive client-attribute terms appear
**156× in events.jsonl and 312× in case_state.json** (client profile,
income, age, marital status — the full client-profile artifact is part of
durable state and event payloads by design, since artifacts are the source
of truth).

- Data minimization: not reviewed against any collection policy; the
  client-profile contract collects a broad family/financial/health-adjacent
  field set (`notes_for_unknown` includes health_status).
- Logging of sensitive data: artifacts ARE the record — unavoidable at
  some level, but there is no field-level classification, no redaction
  layer for events, no encryption at rest.
- Retention: none defined; project dirs persist indefinitely.
- Right-to-erasure: manual directory deletion only (undeveloped).

## LLM provider privacy

Provider default is GLM via `open.bigmodel.cn`. **Data-retention,
training-usage, region and privacy-policy evidence: NOT FOUND in the repo
— UNKNOWN / NEEDS VERIFICATION.** Sending real client income/family/health
-adjacent data to any external LLM without a verified data-processing
position is a P0-class privacy blocker for real client data.

## Secrets

Good posture measured: `.env` gitignored; `describe()` exposes no key; no
api_key strings in event/trace/checkpoint write paths; `.env.example`
contains placeholders only. No secret rotation story (acceptable at this
scale).

## Blast-radius summary

| Threat | Today | Severity |
| --- | --- | --- |
| Network-reachable server | all endpoints open, CORS `*` | P0 if exposed / P1 localhost-pilot |
| Forged "human" actor on approvals/commands | actor string trusted | P1 (same-trust network) |
| Client data at rest | plaintext, unencrypted, no retention policy | **P0 for real client data** |
| Client data to LLM provider | policy unverified | **P0 for real client data (UNKNOWN)** |
| Secrets | handled well | — |
