# Intent Calibration Report

Generated: 2026-09-24T17:18:27.504182+00:00 · Phase 28.A-2 · SHADOW traffic (no dispatch; actual execution unchanged)

## 请求数量

- shadow records: **8** (annotated: 0; legacy-comparable: 0)

## Confidence 分布（按 source）

| source | 1.0 | >=0.8 | >=0.6 | <0.6 | total |
|---|---|---|---|---|---|
| rule | 3 | 0 | 0 | 5 | 8 |
| llm | 0 | 0 | 0 | 0 | 0 |
| hybrid | 0 | 0 | 0 | 0 | 0 |

## Resolver 结果分布

- (pre-28.A-2): **8**

## 关键比例

- unknown 比例: **5/8 (62%)**
- clarification 比例: **5/8 (62%)**
- 新旧一致率 (legacy-comparable): **0/0 (0%)**

## Latency（classify+route，毫秒）

- 无 latency 记录（28.A-2 前的旧记录无此字段）

## Disagreement 类型（annotated 记录）

- 尚无 annotated 记录（annotate 覆盖率待 live 流量）

## 阈值口径

- externalized floor (config/intent-rules.yaml): **0.75** — provisional (HD-1) until calibrated on live traffic；本报告只测量分布，不在此定阈值。
