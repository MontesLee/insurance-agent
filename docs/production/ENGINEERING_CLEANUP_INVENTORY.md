# Engineering Cleanup Inventory — 2026-09-21

Trigger: recursive grep over `tmp/` stalled a Phase 24 session
(34,912 files under tmp/ alone). This inventory records WHAT exists
and WHAT category it falls into — it deletes nothing (deletions and
their justification are in ENGINEERING_CLEANUP_RESULT.md).

## Repository snapshot (working tree clean @ 131cdb1)

| Metric | Value |
|---|---|
| Files (excl. .git) | 41,763 |
| Directories (excl. .git) | 20,251 |
| `tmp/` files | 34,912 (84% of all files) |
| `tmp/` depth-1 entries | 1,788 (2,577 subdirectories + 211 files) |
| Git-tracked files under tmp/ | **0** (everything in tmp/ is untracked) |
| `__pycache__` dirs / `*.pyc` | 42 / 508 |
| `.pytest_cache` | 1 |

## Largest directories

| Directory | Size | Files | Category |
|---|---|---|---|
| tmp/webui-tests/ | **887 MB** | 31,286 | GENERATED (test run roots; regenerable) |
| web/node_modules/ | 116 MB | ~5,300 | cache (dev dependency; retained by purpose) |
| tmp/agent-benchmark/ | 7.7 MB | 254 | HISTORICAL_EVIDENCE (last-run case states; canonical results committed in evals/) |
| tmp/full-agent/ | 997 KB | 32 | HISTORICAL_EVIDENCE (referenced) |
| tmp/demo/ | 433 KB | 21 | HISTORICAL_EVIDENCE (referenced) |
| tmp/e2e/ | 376 KB | 10 | HISTORICAL_EVIDENCE (referenced) |
| tmp/acceptance/ | 181 KB | 38 | HISTORICAL_EVIDENCE (cited by docs/eval/independent-acceptance-report.md) |
| tmp/harness_test_* (×20) | small | ~240 | GENERATED (tempfile.mkdtemp run roots) |
| tmp/a2a_* (×2) | small | ~30 | GENERATED (tempfile.mkdtemp run roots) |
| remaining tmp subdirs | small | ~350 | mixed: GENERATED / debug (see result doc) |

No individual file >512 KB exists outside .git, web/node_modules and
the directories above (verified with `find -size +512k`).

## tmp/ structure (depth 1)

```text
tmp/
├── webui-tests/          2,806 rt-* run roots (one per make_client() call,
│                         recreated by every WebUI suite run)      GENERATED
├── agent-benchmark/      33 bm-* case-state dirs                  EVIDENCE
├── acceptance/  full-agent/  demo/  e2e/                          EVIDENCE
├── harness_test_*  a2a_*  agent-loop-test/                        GENERATED
├── agent-smoke*  p2-trace-test/  case005-debug/  p15probe*/       TEMPORARY
├── __pycache__/                                                 CACHE
├── run_regression.py                                            ACTIVE (README-referenced)
├── *_log.txt (suite logs, rewritten each run)                   EVIDENCE
├── chat-1..6-*.png, *_report.json, family-insurance-report.html,
│   p19_walkthrough.json, p24_live_eval_report.json              EVIDENCE
├── _probe_out.txt, _probe_rec_out.txt, test_layout.txt,
│   catalog_probe.txt, final_*.txt, final_counts.txt,
│   build_family_report.py, acc_env_*.env                        EVIDENCE/UNKNOWN → retained
└── _*.txt / git-*.txt / commit-*.txt (~70 files)                TEMPORARY (session scratch)
```

## Reference set (what code/docs actually cite under tmp/)

Extracted with a TARGETED grep over runtime/ tests/ scripts/ demo/
demos/ evals/ knowledge/ docs/ README.md AGENTS.md (never a recursive
grep of tmp/ itself):

```text
tmp/_probe_out.txt            cited by docs/eval/independent-acceptance-report(.zh-CN).md
tmp/_probe_rec_out.txt        same family (acceptance evidence)
tmp/acceptance/probe.py       cited by the same report
tmp/test_layout.txt           cited by docs/dev-notes/step4-audit.md
tmp/catalog_probe.txt         cited by docs/dev-notes/step4-audit.md
tmp/acceptance  tmp/demo  tmp/e2e          referenced by eval/test code
tmp/backup-pre-refactor-20260911-   backup-code prefix (restore evidence)
tmp/business_eval_report.json  tmp/knowledge_eval_report.json   eval outputs (active)
tmp/p19_walkthrough.json  tmp/p24_live_eval_report.json        phase evidence
tmp/run_regression.py                                           regression runner (README)
```

Everything NOT in this set and not matching an evidence pattern is a
deletion candidate only if it additionally satisfies a T-rule
(§5 of the cleanup spec: temporary debug / stale backup / generated
duplicate / regenerable cache / python cache).
