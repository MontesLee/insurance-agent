# RV-P2-01 Hotfix Result

Date: 2026-09-21 · Baseline de8282a (review), Phase 24 code 131cdb1.

## Problem

Independent review finding RV-P2-01 (P2): in strict modes
(CONTROLLED_PILOT/PRODUCTION) with
`INSURANCE_AGENT_KNOWLEDGE_PROVIDER=weknora` but a missing
`INSURANCE_AGENT_WEKNORA_URL`, `KnowledgeService` CONSTRUCTED
successfully (falling through to the Phase-14.1 no-transport seam
provider) and the failure surfaced only at the first search as
`ProviderUnavailable` — a startup-timing gap. Fail-closed behavior
and the no-mock-fallback property were intact; only the timing was
wrong.

## Root Cause

`knowledge/service.py` checked the provider NAME in strict mode
(HG-24-03) but not the completeness of the WeKnora configuration:
with the URL unset, composition skipped the live branch and reached
`build_named_provider("weknora")`, which deliberately constructs the
transport-less seam (a 14.1 decision: selected-but-unconfigured fails
at search, never degrades to mock).

## Change

`knowledge/service.py`:
- NEW `_validate_weknora_config()` — single validation function.
  Pure env-shape check (URL present, non-empty after strip, http/https
  scheme, host present). It NEVER opens a network connection.
- ONE call site: `KnowledgeService.__init__`, immediately after the
  HG-24-03 name check, guarded by `strict and name == "weknora"`.
  Missing/empty/whitespace/invalid URL → `ProviderConfigError`
  naming RV-P2-01 at construction.

Behavior boundary preserved (spec §4): configuration validation ≠
health check. A valid-but-unreachable URL still constructs; retrieval
still fails closed with `ProviderUnavailable`. KEY/KB completeness
continues to be enforced where it already was (the live composition
branch). NON-strict modes are unchanged by design (the 14.1 seam
semantics remain for non-strict weknora-without-URL).

## Tests

`tests/runtime/test_p24_governance.py` — new section
`test_s5_rv_p2_01_fail_fast` (15 checks; suite 45 → 60):

```
T1  strict + weknora + missing URL        -> construction refused  PASS
T2  strict + weknora + empty URL          -> construction refused  PASS
T3  strict + weknora + whitespace URL     -> construction refused  PASS
T4  strict + weknora + invalid URL
    (no-scheme / ftp:// / no-host)        -> construction refused  PASS
T5  strict + weknora + valid URL          -> constructs; provider is
                                             WeKnoraLiveProvider   PASS
T6  evaluation + mock, no URL             -> constructs            PASS
T7  valid URL + unreachable server        -> constructs (NO network
                                             at startup); retrieval
                                             fails closed
                                             (ProviderUnavailable)  PASS
+   production AND controlled_pilot both refused on missing URL     PASS
+   non-strict weknora missing URL unchanged (14.1 seam, still
    fails closed at search) — hotfix changes STRICT mode only       PASS
```

Independent confirmation: the review probe program
(tmp/review24/audit_probes.py, §8.1 rows) previously recorded
"constructed without error" for both strict modes; after the hotfix
the same probes record construction REFUSED with the RV-P2-01
message.

## Regression

```
Runtime:     495 passed (494 + 1 new test function carrying the 15
             hotfix checks; script-mode suite 45/45 -> 60/60 checks)
Portfolio:   12 passed
Benchmark:   42/42 ALL GREEN
Compileall:  PASS
(p18/p24 live suites unaffected — no live-path code changed;
 the hotfix only adds a construction-time env check in strict modes)
```

## Scope Audit

`git diff --name-only` (this hotfix): exactly three files —

```
knowledge/service.py                    (validation fn + 1 call site)
tests/runtime/test_p24_governance.py    (T1–T7 + guards)
docs/production/KNOWLEDGE_GOVERNANCE.md (1 bullet)
+ docs/production/RV_P2_01_HOTFIX_RESULT.md (this file)
```

No Skill / Orchestrator / Governance rules / Evidence / Provenance /
KnowledgeHit schema / retrieval algorithm / canonical re-anchor /
F-24 / F-16 / Recommendation / LLM Gateway / PostgreSQL schema
changes. No new abstraction, no configuration framework. No scope
creep.

## Remaining Findings

RV-P3-01: OPEN (live F-24 A/B assertion hit-mix flakiness)
RV-P3-02: OPEN (backup restore verification absent)
RV-P3-03: OPEN (document_hash informational anchor, unverified)
RV-INFO-01: OPEN (full compose down/up not exercised)

None were modified, masked, or reclassified by this hotfix.

## Final Status

```
RV_P2_01_CLOSED
```

STOP — no other findings touched, no Phase 25 work.
