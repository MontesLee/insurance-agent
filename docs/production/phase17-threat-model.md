# Phase 17 Threat Model (T01–T15)

Each threat maps to the EXISTING control (code), its test, and the
expected fail-closed behavior. "—" = no control: recorded as a
finding, never papered over.

| ID | Threat | Existing control | Test | Expected behavior |
|---|---|---|---|---|
| T01 | Unauthenticated user calls a privileged action | runtime/auth.py authenticate() + server._current_identity (401); strict-mode startup refuses to boot without identities (server.py:633-644) | auth cases A01-A05 + M-AUTH-01/02/03/06 | deterministic 401/reject; NO default-OWNER fallback; no business action executes |
| T02 | Wrong-role user performs an action | Identity.rank + has_role + _require_role (OPERATOR<REVIEWER<OWNER) | authorization matrix + M-AUTH-04/05/08/09 | deny with reason; approval NOT auto-granted to OPERATOR |
| T03 | Cross-project READ | artifacts/state live under <root>/<project_id>; API paths scope by project; load_project validates | isolation cases (forged project_id payloads) | DENY / not-found; no side-channel via project_id forgery |
| T04 | Cross-project WRITE/MUTATE | same namespace isolation + R-01 locks are per-root index; retention/delete validate project_id charset | isolation + retention cases | DENY; charset-rejected ids raise |
| T05 | Unauthorized APPROVAL | approval models.can_resolve_actor: only "human"/"human:*" may resolve; agents/planners structurally denied | approval cases + M-AUTH-05 + forged-APPROVED | forged actor rejected; REQUESTED→forged APPROVED never executes |
| T06 | Unauthorized CANCEL/control | control plane commands require identity+role (server control endpoints) | authorization matrix (pause/resume/cancel/replan rows per current policy) | deny outside matrix |
| T07 | Sensitive-data access | R-04 encryption-at-rest (IA1: ciphertext in strict modes) + deny-list redaction for logs/events | PII/redaction cases + encryption cases | no plaintext strict-mode persistence; sensitive fields never enter logs |
| T08 | Audit-log tampering | events.jsonl / erasure.log / restore.log are append-only files; artifact fingerprints (sha256) + checkpoint validation detect content tampering | audit tamper cases (delete/modify/actor/ts/pid) | tamper DETECTED by fingerprint/validators or preserved-immutable evidence; absence of cryptographic chain = recorded finding F-18 |
| T09 | Event-data leakage | dataprotection.redact deny-list on every _append_jsonl; artifact content stays out of events | PII leak cases across events/errors | redacted-in-place (event kept, value dropped); never whole-event deletion as the mechanism |
| T10 | Provider-policy bypass | R-05 data_policy gate (fail-closed; env opt-in only after operator verification) | provider cases (missing/unknown/unverified) | real client data BLOCKED; no fallback to another provider |
| T11 | CORS bypass | auth.cors_origins(): allowlist from env; `*` only in explicit dev mode | CORS cases (unknown/wildcard/missing/malformed origin) | strict mode never wildcard; unknown origins not allowed |
| T12 | Runtime-state tampering | R-01 atomic writes + FileLock; checkpoint validate re-hashes; transitions fingerprint artifacts | state-tamper + M-OBS-06/07 | tamper detected (CHECKPOINT_INVALID / fingerprint mismatch) |
| T13 | Evidence/Provenance tampering | Phase-14 content_hash anchors + validate_provenance | provenance cases + M-OBS-05 | hash mismatch rejected; invalid provenance never accepted |
| T14 | Approval-state bypass | approval store terminal-state rules (no double-resolve); status enum schema checks | approval lifecycle cases | REQUESTED→APPROVED only via human actor path; double-resolve rejected |
| T15 | Retention/erasure bypass | Stage-1 retention: terminal-only sweep, backup-first, dry-run default, erasure.log append-only audit | retention cases E01-E05 | active project never swept; delete removes state+events+index; erasure audited |

Gaps recorded (see report Findings): F-18 (P2) audit logs are
append-only by convention and detected-by-hash for artifacts, but
events.jsonl itself has no cryptographic chaining — tampering with a
raw event line is not intrinsically detectable; F-19 (P3) identities
env parsing skips malformed entries silently (fine — never trusted).
