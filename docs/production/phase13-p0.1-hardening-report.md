# Phase 13 P0.1 — Production Safety Defaults Hardening Report

Date: 2026-09-19 · Scope: exactly the three Round-P0-review findings
(R-02/R-04/R-06 production defaults). No P1/P2 implemented.

## 1. What changed

One explicit mode selector instead of inferred intent —
`runtime/mode.py` (new):

```text
INSURANCE_AGENT_MODE = DEMO | EVALUATION | CONTROLLED_PILOT | PRODUCTION
default: DEMO
typo / unknown value → RuntimeError (never a permissive fallback)
legacy "local" alias → DEMO
```

Strict modes (`CONTROLLED_PILOT`, `PRODUCTION`) now carry a hardening
contract enforced at the existing boundaries — each is mandatory and
cannot be weakened by forgetting a flag:

### R-02 — final review MANDATORY (impossible to disable)

- `mode.final_review_required(flag)`: strict → always True.
- The harness constructor routes `require_final_review` through it, so
  `LongRunningHarness(..., require_final_review=False)` in production
  still yields `require_final_review=True`.
- Missing configuration = mandatory (there is no off switch — only not
  being in a strict mode).
- All P0-round bypass protections unchanged (agent/tool/API/retry/
  replan/resume/crash — the 10 R-02 sections still pass unmodified);
  `APPROVED` still only ever yields `READY_FOR_MANUAL_DELIVERY`.

### R-04 — encryption MANDATORY (no plaintext fallback)

- `store._data_key()`: strict mode + no key → `RuntimeError
  ENCRYPTION_REQUIRED` at the first save (write blocked, nothing written
  in plaintext).
- Invalid key → fails closed (Fernet validation raises; no silent
  plaintext), unchanged from P0.
- Valid key → encrypted save + clean round-trip (ciphertext on disk).
- Backup continues to carry ciphertext only; `delete_project` still runs
  under R-01 locking; key never in repo/logs (unchanged, re-verified).

### R-06 — authentication MANDATORY (no implicit dev fallback)

- New `_validate_production_defaults()` runs at `create_app()` STARTUP:
  strict mode + no API keys → `RuntimeError AUTHENTICATION_REQUIRED`
  (the app refuses to start); strict mode + no data key →
  `ENCRYPTION_REQUIRED` (same).
- `_current_identity`: the no-keys → None path is now reachable ONLY in
  DEMO/EVALUATION (strict modes never start keyless — verified by
  construction + tests).
- With keys configured, missing/unknown bearer → 401 fail-closed;
  insufficient role → 403; actor still derived from the authenticated
  identity (body actor ignored); wildcard CORS still blocked outside
  explicit `INSURANCE_AGENT_DEV=1`.

## 2. New tests (no existing test touched)

`tests/runtime/test_p01_hardening.py` — 13 sections:

- M-01 mode selection: all four modes; typo → BLOCK; legacy alias.
- H-02 (production): flag=False cannot disable; pilot same contract;
  DEMO honors both flag values (benchmark compatibility).
- H-04: production no-key save BLOCKS; invalid key BLOCKS; valid key
  passes with ciphertext on disk; DEMO plaintext preserved.
- H-06: production startup without auth BLOCKS; without data key BLOCKS;
  request-level 401/403/authz-pass; wildcard CORS blocked; DEMO keyless
  startup + open health preserved.

## 3. Compatibility proof

```text
pytest tests/runtime -q      → 370 passed (357 + 13 new hardening tests)
pytest tests/portfolio -q    → 12 passed
benchmark                    → 11/11 RESULT: ALL GREEN
full regression              → 51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR
compileall                   → OK
demos basic/insurance/generalization/portfolio → all exit 0
temp-dir leaks               → 0 (fixed the harness-dir leaks the new
                               tests themselves introduced; re-verified)
```

DEMO/EVALUATION execute with byte-identical Phase 7–12 semantics (every
pre-existing suite passes unmodified; the hardening only adds paths that
strict modes take).

## 4. Test-count reconciliation (§5 of the brief — accounting only)

The previous report's "326 baseline + 43 = 357" mixed collection scopes:

```text
Round-1 baseline:  tests/runtime = 314 collected; tests/portfolio = 12
                   (the '326' figure was runtime+portfolio COMBINED,
                    as the Phase-12 battery ran them together)
New P0 tests:      43 (R-01:7, R-02:10, R-03:9, R-04:6, R-05:5, R-06:6
                    — collected under tests/runtime)
P0 runtime total:  314 + 43 = 357  ✓ (portfolio stayed 12)
This round:         +13 hardening tests → tests/runtime = 370;
                   portfolio = 12; full regression runner = 52 suites
                   (its own count, unchanged since Round 1)
```

Suite definitions differ by design: `pytest tests/runtime` collects the
pytest-collectible runtime suites; `tests/portfolio` is the Phase-12
acceptance suite; `tmp/run_regression.py` runs the 52 standalone
script-mode suites under the workbuddy python. No test was moved,
deleted, renamed or weakened.

## 5. Updated acceptance status

```text
R-01 PASS   (unchanged from P0 round)
R-02 PASS   (now MANDATORY in strict modes — cannot be disabled)
R-03 PASS   (unchanged)
R-04 PASS   (now MANDATORY in strict modes — no plaintext fallback)
R-05 PASS / OPERATOR VERIFICATION PENDING (unchanged; gate ships BLOCKED)
R-06 PASS   (now MANDATORY in strict modes — no implicit dev fallback)

Production safety defaults: PASS
Phase 11 regression: PASS (benchmark 11/11; all runtime suites green)
Phase 12 regression: PASS (12 portfolio tests; all demos exit 0)
```
