# Phase 13 P0 Acceptance Matrix

Every row is machine-verified: positive tests prove the fix works, negative
tests prove it cannot be bypassed, regression proves frozen semantics held.
Reproduce: `pytest tests/runtime/test_p0_r0{1..6}.py -q` (43 tests).

| ID | Finding | Before | Fix | Positive Test | Negative Test | Regression | Status |
| -- | ------- | ------ | --- | ------------- | ------------- | ---------- | ------ |
| R-01 | projects.json index: silent lost updates (8→3) + reader JSONDecodeError crash on partial writes | FAIL | `runtime/state/durable.py`: atomic write (temp+fsync+os.replace, bounded retry on Win32 reader-held files), cross-process file lock + per-path thread lock around read-modify-write, tolerant read; `Project._save`/`_index_upsert` wired through it | T-R01-01..06: 16 concurrent saves → 16 entries; concurrent readers never crash; interrupted write leaves the previous doc; corrupt file raises loudly; stale lock doesn't block; **6 cross-process saves → 6 entries** | T-R01-05 (corrupt file must NOT return garbage), T-R01-04 (no partial JSON ever observed) | 357 runtime + 51/0/1 runner unchanged | **PASS** |
| R-02 | No human-review gate on the final deliverable; B001 completed with zero approval events | FAIL | `require_final_review` mode: deliverable task types (report/recommendation) trigger an `APPROVAL_FINAL_REVIEW` approval (WAITING_HUMAN) before `completed`; `approve_final_review` → `ready_for_delivery` (MANUAL delivery — never auto); rejection fail-closes; gate blocks run() start, retry, replan, resume, and survives crashes; flag off preserves Phase 7–12 benchmark semantics | T-R02-01, T-R02-09: normal flow stops at waiting_review; only approve yields ready_for_delivery; deliverable task itself PASSED (gate = delivery, not execution) | T-R02-02..08: agent actor, tool actor, API (401/403 + identity-derived actor), replan, resume_approval, crash restart, retry — every bypass attempt fails; forged body actor ignored | 357 runtime incl. all HITL/HOTL suites; benchmark 11/11 (flag-off compat test included) | **PASS** |
| R-03 | Demo catalog not real-recommendation grade (no effective_to; missing waiting period/exclusions/limits/health/occupation) | FAIL | `runtime/catalog_governance.py`: demo/production mode separation (env-selected catalog; production mode refuses demo products and rejects catalogs missing governance fields or evidence); expiry BLOCK; missing evidence fail-closed; provenance chain record (candidate → catalog version → evidence); wired into the eval invariant so every candidate gets a governance check | T-R03-01,07,08: valid governed product PASSes end-to-end through the real eval engine; provenance chain complete | T-R03-02..06: expired → BLOCK; missing evidence → FAIL; missing governance field rejects the catalog; version mismatch detected; demo-in-production rejected | 357 runtime; benchmark 11/11 (demo-mode unaffected) | **PASS** |
| R-04 | Client data plaintext at rest (156/312 sensitive hits); no retention/deletion | FAIL | `runtime/state/dataprotection.py`: deny-list event redaction (logs carry no sensitive field values); optional Fernet at-rest encryption for the case store via env/keyfile OUTSIDE the tree (lazy import — plaintext mode runs without the package); complete erasure (`delete_project`, index entry under the R-01 lock); malformed key fails closed | T-R04-01..06: redaction drops name/phone/email/income/health; encryption round-trip; backup carries ciphertext only; plaintext-mode compat; erasure + index removal; wrong key fails closed without PII in errors | T-R04-02 (sensitive VALUES absent from events.jsonl), T-R04-06 (error paths leak nothing) | 357 runtime (plaintext default unchanged for benchmark) | **PASS** |
| R-05 | LLM provider data policy UNKNOWN (no evidence in repo) | UNKNOWN → BLOCK | `runtime/agent/data_policy.py`: client-data mode gate — synthetic (default) open; **real + unverified provider policy → BLOCKED fail-closed**; opens only on the operator's explicit post-verification opt-in; wired at the server's agent-turn boundary; evidence record + operator procedure in provider-policy-verification.md | T-R05-03: real+verified allowed (explicit opt-in path works) | T-R05-02,04: real+unverified BLOCKED at the gate and at the HTTP boundary (451); no silent fallback exists; T-R05-05 record states NOT VERIFIED honestly | 357 runtime (synthetic default = all existing suites unaffected) | **PASS** (gate enforces the audit rule: UNKNOWN → BLOCK) |
| R-06 | No authentication; CORS `*`; client-supplied actor trusted | FAIL | `runtime/auth.py`: static API keys (env/keysfile, `key:role:user`), roles OWNER/REVIEWER/OPERATOR, bearer authn fail-closed 401/403; CORS allowlist (`*` only with explicit INSURANCE_AGENT_DEV=1, dropped otherwise); approval/control endpoints derive the ACTOR from the authenticated identity (body actor ignored); approval allowlist accepts `human:<user>` identities | T-R06-01,06: identities/roles resolve; dev-mode (no keys) compatibility preserved | T-R06-02..05: 401 unauthenticated/unknown key; 403 OPERATOR-on-approve; forged body actor never recorded; `*` ignored outside dev mode | 357 runtime; 12 portfolio; all server/SSE suites | **PASS** |

## Verdict

```text
P0 = 0  (all six blockers cleared, each with positive + negative + regression evidence)
```


---

## P0.1 hardening addendum (2026-09-19 — matrix rows above preserved as of the P0 round)

| ID | Hardening delta | Evidence |
| --- | --- | --- |
| R-02 | Final review now MANDATORY in CONTROLLED_PILOT/PRODUCTION — `require_final_review=False` cannot disable it; missing config = mandatory; all 8 bypass protections unchanged | `test_p01_hardening.py` H-02 (3 sections) + `runtime/mode.py` |
| R-04 | Encryption now MANDATORY in strict modes — no key → save BLOCKS (ENCRYPTION_REQUIRED); invalid key BLOCKS; demo plaintext preserved | H-04 (4 sections) |
| R-06 | Authentication now MANDATORY in strict modes — keyless production STARTUP BLOCKS; request-level 401/403 fail-closed; wildcard CORS blocked outside dev | H-06 (5 sections) + server `_validate_production_defaults` |

Runtime total after hardening: 370 (357 + 13). Everything else unchanged.
