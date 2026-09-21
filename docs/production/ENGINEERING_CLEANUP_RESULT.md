# Engineering Cleanup Result — 2026-09-21

Trigger: recursive grep over `tmp/` stalled a Phase 24 session.
Process followed: inventory → classify → reference-check → confirm →
delete → regression (see ENGINEERING_CLEANUP_INVENTORY.md). No blind
deletion; nothing git-tracked was removed; unknown files were retained.

## Sizes

| Metric | Before | After |
|---|---|---|
| Repository files (excl. .git) | 41,763 | 9,670 (+ regenerated caches since) |
| tmp/ files | 34,912 | 3,330 immediately after; 3,570 stable after regression |
| tmp/ size | ~899 MB (887 MB of it tmp/webui-tests) | 35 MB → 40 MB stable |
| `__pycache__` dirs / `*.pyc` | 42 / 508 | 0 (regenerated on next run, now gitignored) |

"Stable" = the scale after the full regression re-created the caches
and run roots it legitimately needs. The target was never an empty
tmp/ — only files with a reason to exist.

## Files

| | |
|---|---|
| Inspected (inventory) | full tmp/ depth-1 census (1,788 entries), all cache dirs, reference set extraction |
| Deleted | ~32,400 files (2,806 webui run roots, ~45 stale test/probe roots, 76 session-scratch captures, 508 .pyc + 42 cache dirs) |
| Retained (evidence/active) | tmp/agent-benchmark (254), tmp/acceptance (38, cited by the independent acceptance report), tmp/full-agent, tmp/demo, tmp/e2e, chat-*.png, *_report.json, family-insurance-report.html, p19/p24 evidence JSONs, *_log.txt suite logs, run_regression.py, _probe_out.txt + _probe_rec_out.txt (cited), test_layout.txt + catalog_probe.txt (cited), final_*.txt, build_family_report.py, acc_env_*.env |
| Retained (by purpose) | web/node_modules + web/dist (gitignored dev/build artifacts, needed for the deferred React UI) |
| Unresolved (retained) | final_counts.txt, build_family_report.py, acc_env_*.env — not referenced by current code, kept as possible historical evidence (UNKNOWN → keep) |

## Deleted categories

| Category | Rule | Items |
|---|---|---|
| cache (regenerable run roots) | T4 | tmp/webui-tests/rt-* (2,806), tmp/harness_test_* (20), tmp/a2a_* (2), tmp/agent-loop-test/ |
| debug (stale, no generator, zero citations) | T1 | tmp/agent-smoke{,2,3}, tmp/p2-trace-test, tmp/case005-debug, tmp/p15probe6_* |
| Python cache | T5 | all __pycache__/, .pytest_cache/ |
| session scratch | T1 | 76 files: `_*.txt/_*.py/_*.json` (except the two cited `_probe*`), `git-*.txt`, `COMMIT_MSG.txt`, `commit-msg.txt`, `commit-status.txt` |
| duplicate | T3 | none found needing action (no identical-file pairs outside caches) |
| stale backup | T2 | none found (no *.bak/*.orig; referenced backup prefix has no live instance) |

## Reference discipline

The reference set was extracted with TARGETED greps over runtime/
tests/ scripts/ demo/ demos/ evals/ knowledge/ docs/ README.md
AGENTS.md only — never a recursive grep of tmp/. Deleted files are
absent from that set; retained evidence files are present (notably
tmp/_probe_out.txt and tmp/acceptance/probe.py, cited by the committed
independent acceptance report — found ONLY because per-file reference
checks were performed before deleting the `_`-prefixed family).

## Changes

| Kind | Change |
|---|---|
| Runtime / business / architecture | **NONE** (git diff of tracked files: zero code changes) |
| .gitignore | +2 minimal rules: `.pytest_cache/`, `*.pyc` (tmp/, __pycache__/, .env, node_modules already covered) |
| New docs | ENGINEERING_CLEANUP_INVENTORY.md, this file |

git status before: clean (post-Phase-24 131cdb1).
git status after: only the two new cleanup docs + .gitignore (committed together).

## Regression (all AFTER deletion)

```
Runtime suite:     494 passed (incl. Phase 14–24 suites)
Portfolio suite:   12 passed
Benchmark:         42/42 ALL GREEN
Compileall:        PASS
Portfolio demo:    A PASS · B PASS (tamper→DENY) · C PASS (abstain)
Broken references: none (no ImportError / missing fixture / file-not-found in any suite)
Knowledge corpus:  untouched (knowledge/ had zero deletions; PG registry + WeKnora unaffected)
Production docs:   all present (PHASE_21..24, KNOWLEDGE_*, ARCHITECTURE*, LIMITATIONS)
```

## Success criteria

```
CLEAN-01  no unnecessary temporary cache remains        PASS (0 pycache; run roots only what regression recreated)
CLEAN-02  no known duplicate artifact remains           PASS (none found)
CLEAN-03  no purposeless stale backup remains           PASS (none found)
CLEAN-04  unreferenced debug artifacts removed          PASS (76 files + stale roots)
CLEAN-05  historical audit evidence preserved           PASS (acceptance/benchmark/phase evidence kept)
CLEAN-06  real knowledge corpus preserved               PASS (knowledge/ untouched)
CLEAN-07  tests/fixtures preserved                      PASS (tests/ untouched; 494 green)
CLEAN-08  git-tracked files preserved                   PASS (0 tracked deletions)
CLEAN-09  no business code changed                      PASS
CLEAN-10  no architecture changed                       PASS
CLEAN-11  no broken references                          PASS (regression green, demos green)
CLEAN-12  full regression passes                        PASS (494/12/42)
CLEAN-13  compileall passes                             PASS
CLEAN-14  portfolio demos pass                          PASS (A/B/C)
CLEAN-15  .gitignore minimal and correct                PASS (+2 lines, no broad rules)
```

## Final status

```
CLEAN_WITH_RETAINED_ARTIFACTS
```

Retained by policy: historical/evaluation/provenance evidence under
tmp/ (~35 MB), the agent-benchmark case states, web/ dev artifacts,
and three UNKNOWN files kept per the "unknown → retain" rule. A
future archival policy for tmp evidence is explicitly OUT OF SCOPE
here (not established by this cleanup).

STOP — awaiting human review of this cleanup result before any
further Phase 24/25 work.
