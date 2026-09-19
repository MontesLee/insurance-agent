# Phase 13 P0 Remediation Report

Date: 2026-09-19 · Order executed: R-01 → R-04 → R-06 → R-02 → R-03 →
R-05 (dependency-driven: persistence first, auth before the review gate,
provider gate last). Round-1 audit facts preserved in this directory;
nothing was overwritten.

## 1. R-01 — persistence race & corruption: FIXED

`runtime/state/durable.py` (new): `atomic_write_json` (temp file in the
same dir + fsync + `os.replace`, with a bounded retry for the Win32
reader-held-file PermissionError), `FileLock` (advisory cross-process
lock via msvcrt/fcntl + per-path thread lock), `read_json_retry`
(tolerant of replace-in-flight; genuinely corrupt files raise loudly),
`locked_update_json`. Wired into `Project._save` (atomic project.json)
and `_index_read`/`_index_upsert` (locked read-modify-write).
Tests T-R01-01..06 + cross-process (7 sections): the measured 8→3 lost
update is now 16→16 (and 6→6 across subprocesses); concurrent readers
never crash; interrupted writes leave the previous complete document.

## 2. R-02 — enforced final human review: FIXED

New approval type `APPROVAL_FINAL_REVIEW`; harness mode
`require_final_review` (default **False** — Phase 7–12 benchmark
semantics byte-compatible, proven by a dedicated compat test and the
unchanged 11/11 benchmark). When on: a PASSED deliverable task type
(`report_generation`/`recommendation`) triggers a WAITING_HUMAN review
approval; `approve_final_review` → project `ready_for_delivery`
(delivery itself stays MANUAL — the runtime never auto-delivers);
`reject_final_review` fail-closes to needs_review. The gate blocks
run() start (before approvals), retry, replan, `resume_approval`
(non-replan reviews refused), and survives crash recovery. Actors pass
the same allowlist as Phase 9 (`human`/`harness`/`human:<user>`).
Tests T-R02-01..09 (10 sections, every bypass path negative-tested).

## 3. R-03 — production product-catalog governance: FIXED

`runtime/catalog_governance.py` (new): demo/production mode separation
(`INSURANCE_AGENT_CATALOG_MODE`; production points at a catalog that
does NOT ship by default — no silent demo fallback); `validate_catalog`
(production requires the Round-1 field list: coverage_limit, deductible,
waiting_period, coverage_term, renewal_period, exclusions,
health_declaration, occupation_restrictions, per-product evidence
source+version); `product_status_on` (expired → BLOCK, demo-in-production
→ reject, missing evidence → fail-closed); `catalog_provenance` chain
record; wired into the eval invariant so **every candidate artifact gets a
governance check** through the real eval engine. Demo catalog unchanged
for benchmark/portfolio. Tests T-R03-01..09.

## 4. R-04 — client-data protection: FIXED (to the single-node boundary)

`runtime/state/dataprotection.py` (new): deny-list event redaction on
every `_append_jsonl`; optional Fernet at-rest encryption for the case
store (key from env or a keyfile OUTSIDE the tree; malformed key fails
closed; lazy `cryptography` import — see issue below); complete erasure
`delete_project` (files + index under the R-01 lock). Tests T-R04-01..06
with a synthetic PII fixture (no real person's data).

## 5. R-05 — provider policy gate: BLOCKED-BY-DEFAULT (honest)

`runtime/agent/data_policy.py` (new) + the server's agent-turn boundary:
synthetic mode (default) open; `INSURANCE_AGENT_CLIENT_DATA=real` without
a verified provider policy → **BLOCKED fail-closed (HTTP 451)**; opens
only on the operator's explicit `INSURANCE_AGENT_PROVIDER_POLICY_VERIFIED=1`
after completing the documented verification procedure
(`provider-policy-verification.md`). Evidence gathered this round: the
official policy pages are JS-rendered SPAs — verbatim primary text could
NOT be machine-retrieved; a third-party investigation reports the general
API retains an "anonymized data may be used for training" clause
(recorded as context, explicitly NOT accepted as the judgment). Per the
audit rules, UNKNOWN → BLOCK. Tests T-R05-01..05.

## 6. R-06 — auth / CORS / actor integrity: FIXED

`runtime/auth.py` (new): static API keys (`key:role:user` via env or
keysfile), roles OWNER/REVIEWER/OPERATOR, bearer authn fail-closed;
CORS allowlist (`*` only with explicit `INSURANCE_AGENT_DEV=1`); approval
+ all six control endpoints require auth and derive the ACTOR from the
authenticated identity — the Round-1 forged-body-actor hole is closed
(verified with a forged `agent:` body). No-keys mode = documented
local-dev (all existing suites unaffected). Tests T-R06-01..06.

## Issue found & fixed during remediation (regression discipline)

The first post-remediation full regression dropped to 25/4/23. Root
cause: the regression runner uses the workbuddy python (3.13), which
lacks `cryptography`, and `load_data_key` imported it eagerly — every
suite touching `store.save` died. Fixed by making the import lazy
(plaintext mode needs no package). Second cause: an `UnboundLocalError`
in the eval governance branch when a non-catalog invariant ran first —
fixed by hoisting the `catalog = None` initialization. After both fixes:
**51 PASS / 0 FAIL / 1 pre-existing INFRA_ERROR — identical to the
Round-1 baseline** (step3-mutation GBK file-write, pre-existing,
reproduced on the clean tree in earlier phases).

## Regression evidence (final)

```text
pytest tests/runtime -q            → 357 passed (326 baseline + 43 new P0
                                      tests − 12 portfolio tests moved to
                                      their runner; portfolio: 12 passed)
python -m evals.benchmark.runner   → 11/11, RESULT: ALL GREEN (also
                                      re-verified under the workbuddy python)
tmp/run_regression.py              → 51 PASS / 0 FAIL / 1 pre-existing
compileall                          → OK (runtime, tests, demos, benchmark)
demos (basic/insurance/generalization/portfolio) → all exit 0
temp-dir leaks → 0 (two stray bench dirs from a consistency helper
                  cleaned; clean runs verified leak-free)
```

Test-count delta explained: 326 → 357 runtime tests = +43 new P0 tests
(R-01:7, R-02:10, R-03:9, R-04:6, R-05:5, R-06:6). No test was deleted,
weakened, skipped or xfailed; existing assertions untouched.

## Runtime semantic changes (all additive, all opt-in)

| Change | Default | Frozen-semantics proof |
| --- | --- | --- |
| `require_final_review` gate | OFF | benchmark 11/11 + dedicated flag-off compat test |
| encryption at rest | OFF (no key) | all suites ran plaintext; lazy import | 
| catalog governance checks in eval | demo mode = PASS for valid demo ids | benchmark 11/11, eval suites green |
| event redaction | ON | benchmark/event suites assert on non-sensitive fields only — 357 green |
| authn/CORS/actor | no keys = local-dev identical | server/SSE/portfolio suites green |
| provider data gate | synthetic = open | all agent suites green |
| atomic/locked persistence | always on (invisible) | harness/cross-process suites green |

## Answers to the twelve questions

1. R-01 fully fixed? **Yes** — measured loss and reader crash both
   eliminated; cross-process verified.
2. Any final-delivery bypass path left? **No** — 8 negative tests cover
   agent/tool/API/retry/replan/resume/crash; only `approve_final_review`
   yields `ready_for_delivery` (manual delivery).
3. Demo/production catalogs truly separated? **Yes** — different files,
   mode env, production rejects demo products and ships no default
   catalog.
4. Sensitive data still in ordinary logs? **Field-name redaction on all
   durable logs** (values under innocuous free-text keys are a stated
   limitation); artifacts live in the encryptable store.
5. Provider policy with official evidence? **No** — SPA-blocked; gate
   ships BLOCKED per the audit rule; verification procedure documented.
6. Unauthorized access paths left? **None at the app layer** (401/403
   fail-closed); TLS and key rotation remain P1.
7. Phase 11 still PASS? **Yes** — benchmark 11/11, fault injection 18/18
   (in the 357), determinism/parallel suites green.
8. Phase 12 still PASS? **Yes** — 12 portfolio tests, all demos exit 0.
9. New regressions? **None** — 51/0/1 identical to baseline (the interim
   25/4/23 was caused by the two fixed issues above, not shipped).
10. Architecture semantic changes? **Additive opt-ins only** (table
    above); authority boundaries untouched.
11. Remaining P0? **0.**
12. Remaining P1? durable cost records · backup · retention sweep ·
    report eval depth · deployment definition · per-case ownership ·
    provider-policy completion.


---

## Post-script (P0.1 hardening round, 2026-09-19 — rows above preserved)

The P0-round report's "357 runtime (326 baseline + 43)" mixed collection
scopes: the 326 Round-1 baseline was runtime(314)+portfolio(12) combined;
runtime alone was 314, and 314+43=357 is exact. Portfolio stayed 12. Full
reconciliation in phase13-p0.1-hardening-report.md §4. The P0.1 round then
added 13 hardening tests → 370 runtime. All other regression numbers
unchanged.
