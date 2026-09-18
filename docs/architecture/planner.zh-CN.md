# Planner 与图校验

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](planner.md)

事实来源：`runtime/planner/`（`planner.py`、`registry.py`、`schemas.py`、
`validator.py`、`prompts.py`）。

## 1. 定位

```text
Planner 产出不可信的计划
        ↓
Validator 把它变成可信的
        ↓
Harness 执行
```

Planner **不是**不受限制的自主 agent。它把用户请求转换成严格 JSON
Task Graph，仅此而已：不执行任务、不调用 skill、不碰 CaseState。凡它
证明不了的，系统一律拒绝（fail-closed）。

## 2. 流水线

```text
用户请求
 ↓ build_planner_prompt
LLM provider（任意 LLMProvider；测试用 FakePlannerProvider）
 ↓ 原始文本 → 剥掉 markdown 代码栏 → json.loads
JSON Schema 校验（TASK_GRAPH_SCHEMA）
 ↓
图校验（validator.validate_graph）
 ↓ 通过
_normalize()：字段从受信注册表填充（绝不用 LLM 输出）
 ↓
TaskGraph {graph_id, tasks[], entry_tasks, terminal_tasks, created_at, source_request}
```

## 3. 受信任务注册表（`registry.py`）

九个人工维护的 task_type —— Planner 可选的封闭词表（未知
`task_type` 直接拒绝）：

| task_type | stage | 产出 |
| --- | --- | --- |
| `client_profile` | client-intake（provided） | client-profile |
| `requirement_analysis` | requirement-analysis（provided） | requirement-analysis |
| `risk_analysis` | risk-analysis（provided） | risk-assessment |
| `coverage_gap` | coverage-gap-analysis | coverage-gap-analysis |
| `solution` | solution | solution-plan |
| `knowledge_search` | product-candidate-provider（service） | knowledge-evidence |
| `product_candidates` | product-candidate-provider | product-candidates |
| `recommendation` | product-recommendation | product-recommendation |
| `report_generation` | report-generation | insurance-report |

每个条目声明 `required_inputs`、`produced_artifacts`、`required_eval`
—— 校验器对照的是这些受信数据，Harness 执行用的也是它们。LLM 自己
声称的输入/输出一律不采用。

## 4. 校验器的 10 项检查（`validator.py`，fail-closed）

1. `task_id` 唯一
2. `task_type` 在注册表中
3. 每个依赖都指向存在的任务
4. **无循环依赖**（Kahn 拓扑排序）
5. 至少一个入口任务（无依赖）
6. 至少一个终端任务（无人依赖它）
7. 每个任务都能到达某个终端（无死分支）
8. **artifact 契约**：每个任务的 `required_inputs` 由其传递上游产出
   （artifact 沿依赖链累积）
9. **eval 契约**：注册表中每个 task_type 都声明了 `required_eval`
10. 未知字段被暴露（`_extra_fields`）但绝不执行 —— 只有白名单
    `task_id / task_type / description / dependencies` 能到达 Harness

## 5. 有界重试，fail-closed

```text
第 1 次尝试 → 解析/schema/图错误？
第 2 次（重试）→ 错误？
第 3 次（重试）→ 错误？
        ↓
PlannerResult(status="needs_review", errors=[...])   # MAX_PLANNER_RETRIES = 2
```

JSON 解析失败、schema 违规、图违规共用同一个有界预算（总共 3 次尝试）。
**没有静默的确定性兜底计划** —— 预算耗尽即 `needs_review` 并带上累计
错误。可观测事件：`planner_started`、`graph_validation_started/passed/failed`、
`planner_completed/failed`。

## 6. Harness 拿到什么

一张已校验的图，字段由注册表填充（`input_artifacts`、
`expected_artifacts`、`required_eval`、`status=PLANNED`、`max_attempts=3`）。
图的 task_id 被保留以便依赖解析；从此图不可变 —— 下游任何一方（agent、
消息、调度器）都不能增删或改接任务。
