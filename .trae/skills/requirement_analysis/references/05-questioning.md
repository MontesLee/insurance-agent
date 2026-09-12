# 05 — 主动追问（Questioning）

> 来源：原 QUESTIONING.md。
> 本文件定义把 `information_gaps` 转成少量、高价值、自然口语化问题的策略。规则数据见 `resources/config/question-generation.rules.json`。

---

## 1. 链路

1. `information_gaps` → 2. `question priority` → 3. `ask user` → 4. `update context` → 5. `re-check sufficiency`。

当前实现不写回 `client_intake`，只更新 `requirement_analysis` 自己的 `question_context`。

## 2. Question Priority

评分构成：`importance` / `impact` / `gap_type` / 信息获取难度 / 重复询问惩罚。

配置文件：`resources/config/question-generation.rules.json`。

### 2.1 默认策略

1. 默认每轮最多问 `2` 个问题
2. 优先选择高影响、低获取成本的问题
3. `CONFLICTING_INFORMATION` 优先于普通缺口
4. 已回答字段不能重复问
5. 已问未答字段允许再次问，但会施加重复惩罚

## 3. 问题生成原则

每个问题必须：简单、口语化、非审问式、明确告诉用户为什么问、尽量允许大概数字。

字段级模板配置在 `resources/config/question-generation.rules.json`。

## 4. 不重复询问

`question_context` 负责保存 Requirement Analysis 自己的提问上下文：

```json
{ "asked_questions": [], "answered_fields": [] }
```

规则：

1. `answered_fields` 中的字段绝不重复问
2. `asked_questions.status = answered` 的字段绝不重复问
3. `ignored` 可以重问，但会触发重复惩罚，并优先换模板

## 5. 多轮补充

若一轮中存在多个 gap：本轮只问最有价值的少量问题；用户回答后通过 `scripts/update-requirement-analysis-context.ps1` 更新 `facts` / `question_context.asked_questions` / `question_context.answered_fields`；再重新运行 sufficiency / questioning，下一轮自动看到剩余 gap。

## 6. 冲突确认

对于 `gap_type = CONFLICTING_INFORMATION`：不生成普通补缺问题，生成 `conflict_confirmation` 类型问题，优先请用户确认当前以哪个说法为准。

## 7. 输出

Phase 3 在 Output 中新增：`question_plan.question_status` / `question_plan.selected_questions` / `question_plan.deferred_fields`。

- 无需继续追问：`question_status = NOT_NEEDED`
- 存在冲突确认需求：`question_status = CONFLICT_CONFIRMATION_REQUIRED`
- 否则：`question_status = READY_TO_ASK`
