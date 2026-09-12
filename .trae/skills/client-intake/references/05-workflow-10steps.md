# 05 — 标准工作流（10 步）与 Gate

## Round 的定义

一次 Round = 一次新的客户输入触发的一次完整 Skill 执行。

Agent 自身的输出、状态写入或 Pending Reminder 不单独增加 Round。

所有 Pending Reminder 的 `+2 / +4 / +6`，均以客户输入 Round 为计数单位。

## Workflow Gate Rule

Step 6 Completion Check 是强制 Gate。

在 Completion Check 完成之前：

- 不得生成 `next_questions`
- 不得进入 Step 7
- 不得进入 Step 8

只有当 `intake_complete = false` 时，才允许：

- Step 7 `Prioritize`
- Step 8 `Generate Questions`

## Step 1：Resolve Previous QIDs

在处理本轮客户输入之前，必须先清算上一轮所有状态为 `unanswered` 的 QID。

处理规则：

1. 客户已明确回答 -> `answered`
2. 客户明确拒绝 -> `declined`
3. 客户承诺后补 -> `pending`
4. 客户未回答且明显转向其他信息 -> `ignored`

完成这一清算后，才允许进入本轮信息抽取。

## Step 2：Extract

逐句提取客户本轮输入中的事实、模糊表述、承诺后补的信息。

## Step 3：Classify

把本轮输入归为：

- confirmed
- inferred
- missing
- pending

说明：

- 模糊但仍可直接记录的客户原话，优先进入 confirmed，并通过原文保留模糊性
- 真正的逻辑推断，才进入 inferred

## Step 3.5：Resolve Overlays（险种扩展层）

确定本次是否需要加载险种专项采集维度。

跑一次确定性解析：

```
scripts/resolve-overlays.ps1 -InputText "<客户本轮原话>" -ConfirmedIds "<已确认的险种 id>"
```

输出三类结果：

| 状态 | 含义 | 处理 |
|---|---|---|
| `ACTIVE` | 已命中，且无需确认或已确认 | 加载 `overlays/<id>/intake-dimensions.md`，A 类维度并入 Step 5 / Step 6 |
| `PENDING_CONFIRM` | 命中但尚未经客户确认 | **不进 required**；生成 1 条确认提问，占用 `next_questions` 配额 |
| 未命中 | 客户未表达该险种意向 | 一律不追问 |

硬约束：

- Overlay 只增加"采集维度"，**不修改** H1-H6、QID 五态、Pending 节奏 —— 这些以通用层为唯一真源
- `requires_confirm=true` 的 overlay，客户确认前其维度只能记为 `missing`，**不得**成为 `intake_complete` 的阻塞项
- Overlay 采集到的事实写入 `CLIENT_PROFILE.md` 的「4. 险种专项信息」小节，四列结构与通用层一致
- 险种 overlay 的定义、协议与新增方式见 `overlays/README.md`

## Step 4：Merge State

把本轮 confirmed / inferred 合并到 `CLIENT_PROFILE.md`。

要求：

- Profile 中只保留当前最新状态
- 同一字段出现更新时，旧值保留在 `CONVERSATION_LOG.md`，新值写入 `CLIENT_PROFILE.md`
- 不允许让旧 Round 的文字停留在 Profile 里形成冲突

> 若新旧值冲突，先走 `resources/interaction-nodes.md` 的「节点 4/7」让用户点选，再继续。

## Step 5：Gap Analysis

检查 7 大类：

1. 基本信息
2. 家庭结构
3. 收入
4. 支出
5. 负债
6. 现有保障
7. 健康与风险

输出：

- 哪些已足够
- 哪些仍是关键缺口
- 哪些只是后补信息

## Step 6：Completion Check（强制 Gate）

先判断是不是已经可以结束 Intake。

如果可以：

- `intake_complete = true`
- 直接进入 Step 9 和 Step 10
- 不再生成一般追问

如果不可以：

- 继续 Step 7 和 Step 8

> 达标 / 未达标两种情况分别触发 `resources/interaction-nodes.md` 的「节点 5/7」与「节点 6/7」。

## Step 7：Prioritize

把剩余缺口按 `P0 / P1 / P2 / P3` 排序。

## Step 8：Generate Questions

只生成本轮最有价值的问题。

## Step 9：Update State Files

必须同时更新：

- `CLIENT_PROFILE.md`
- `CONVERSATION_LOG.md`
- `PENDING.md`

其中：

- 若 `intake_complete = true`，必须执行 `Critical Missing Items -> Follow-up Items` 的状态转移
- 若客户已进入下一轮且旧问题未获回应，必须按状态机把该 QID 更新为 `ignored / pending / declined / answered` 之一，不能继续长期保持 `unanswered`，也不能静默丢失

**Step 9 额外回写 INDEX.md 的规则：**

- 如果本轮是 R1（R0 → R1）→ INDEX 中该行「当前轮次」从 R0 改成 R1，「最近更新」写现在时间
- 如果本轮 Completion Check 结果 intake_complete=true → INDEX 中「Intake 完成状态」从未完成 → ✅ 已完成
- 其他情况：「当前轮次」+1；「最近更新」= now

## Step 10：Output Execution Result

输出本轮执行结果 JSON + 人类可读摘要。

JSON 必须满足 binding 契约：`schemas/execution-output.schema.json`（由 `scripts/validate-execution-output.ps1` 校验）。
