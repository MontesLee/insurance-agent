# R-06 Security Verification (Phase 13 P0 Remediation)

Scope: single-node controlled pilot (owner + 1–3 trusted users). NOT
enterprise IAM. Verified by `tests/runtime/test_p0_r06.py`.

## Identity

- Static API keys provisioned by the owner: `INSURANCE_AGENT_API_KEYS`
  (`key:role:user`, comma-separated) or `INSURANCE_AGENT_API_KEYS_FILE`
  (one per line). Keys must be ≥16 chars; malformed entries are skipped,
  never trusted. Requests authenticate with `Authorization: Bearer <key>`.
- No keys configured = documented local-development mode (loopback-bound
  server, body actor honored as before). This preserves every existing
  demo/benchmark path.

## Authorization

| Role | May | May not |
| --- | --- | --- |
| OWNER | everything (approve, control, read) | — |
| REVIEWER | read + approve/reject approvals | control commands beyond OPERATOR? (has OPERATOR rank) — approve + control |
| OPERATOR | control commands (pause/resume/retry/replan/information) | **approve/reject** (403) |

Verified: unauthenticated → 401 fail-closed on approval + control
endpoints; OPERATOR-on-approve → 403; REVIEWER approve allowed.

## Actor integrity (the Round-1 forged-actor hole)

The approval/control endpoints now derive the actor from the
**authenticated identity** (`human:<user>`), never from the request body
— verified with a forged `{"actor": "agent:..."}` body: the recorded
`resolved_by` is `human:bob`, and non-human actors remain refused by the
allowlist (extended to accept `human:<user>` while still rejecting
`agent:`/`tool:`/`planner:`/`message_bus`).

## CORS

`INSURANCE_AGENT_CORS_ORIGINS` allowlist; default is the loopback UI
origins. `*` is honored ONLY with explicit `INSURANCE_AGENT_DEV=1`;
outside dev mode a configured `*` is dropped (fail-closed to loopback).

## Secrets posture (re-verified post-remediation)

`.env` gitignored; `describe()` masks the key; no api_key strings in
event/trace/checkpoint write paths; the new data-protection keyfile must
live OUTSIDE the encrypted tree (validated by R-04 tests); malformed keys
fail closed rather than silently degrading to plaintext.

## Remaining security P1s (not in this round)

- No HTTPS/TLS story (reverse proxy out of scope).
- Static keys have no rotation/expiry.
- No per-case ownership granularity beyond roles (any reviewer may review
  any case — acceptable for 1–3 trusted users, documented).
- Rate limiting (P2).
