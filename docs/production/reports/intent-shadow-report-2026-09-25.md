# Intent Shadow Report

Generated: 2026-09-24T16:59:16.916904+00:00 · Phase 28.A-1 · SHADOW mode (no dispatch; actual execution unchanged)

## 请求数量

- corpus requests: **22** (labeled corpus; live traffic accumulates in tmp/intent-shadow/shadow.jsonl once the server restarts with the module wired)

## Intent 分布

| intent | count | ratio |
|---|---|---|
| insurance_qa | 6 | 27% |
| product_qa | 5 | 23% |
| insurance_plan | 5 | 23% |
| modify_existing_plan | 3 | 14% |
| unknown_insurance_intent | 3 | 14% |

## Confidence 分布

| bucket | count | source |
|---|---|---|
| 1.0 (rule) | 19 | {'rule': 22} |
| 0.8-1.0 | 0 | {'rule': 22} |
| 0.6-0.8 | 0 | {'rule': 22} |
| <0.6 | 3 | {'rule': 22} |

## 关键比例

- unknown 比例: **3/22 (14%)**
- modify 缺 active-case context 比例: **3/3** (all forced clarification_required=true per ADR-019 M1 — expected until ADR-024 persistence lands)
- corpus 正确率 (predicted vs expected v1 label): **22/22**
- 与现有执行路径一致率 (legacy-mapped labels): **19/19 (100%)**

## Known limitations

- Corpus-based shadow run (deterministic, offline). Live traffic agreement (shadow record legacy_intent, filled by runtime/intent/shadow.annotate after each real agent turn) starts accumulating after the next server restart.
- LLM candidate path not exercised (rules-only fast path; provider wiring deferred — see phase-28a1-report.md).
- Conversation context is passed through but not yet used as classification signal (message-only rules in v1).
