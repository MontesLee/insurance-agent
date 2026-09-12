# 03 — Intake 最低完成标准

## 4.1 Hard Required

进入 Needs Analysis 的最低要求：

| 编码 | 内容 | 最低要求 |
|------|------|----------|
| H1 | 年龄 | 明确数字 |
| H2 | 城市 | 到市级 |
| H3 | 职业 | 足够判断职业类别 |
| H4 | 家庭责任结构 | 已明确婚姻/子女等主要家庭责任；并能够判断是否存在他人明显依赖本人收入。若不存在相关责任，也可明确记录“当前未发现明显家庭经济依赖关系” |
| H5 | 收入 | 本人收入，配偶如有收入也需大致知道 |
| H6 | 家庭年支出 | 至少有范围 |

## 4.2 Soft Required

这些尽量收，但不阻塞结束 Intake：

- 配偶详细信息
- 父母健康与赡养细节
- 负债细节
- 现有保障细节
- 客户本人健康细节
- 核心风险关注点

### 4.2.1 H4 判定规则

H4 不要求机械收集完整家庭成员信息。

只要当前信息足以判断：

1. 是否存在配偶
2. 是否存在需要承担主要经济责任的子女
3. 是否存在明显依赖本人收入的家庭成员

即可满足。

若客户明确表示：

- 未婚
- 无子女
- 无需赡养父母

则可以视为 H4 满足。

H4 不是单一事实字段，而是基于 Confirmed Facts 与允许的家庭责任关系 inferred 的综合判断。

H4 满足时，必须在 `Completion Status` 的说明中写明判断依据。

## 4.3 Completion Check

每轮完成 Gap Analysis 后，必须先执行 Completion Check，再决定是否继续追问。

满足以下条件时，`intake_complete = true`：

1. H1-H6 已达到进入 Needs Analysis 的最低要求
2. 不存在完全空白的重大阻塞项
3. `CLIENT_PROFILE.md` 已经足够支撑下一阶段做需求分析

一旦 `intake_complete = true`：

- 停止继续追问一般信息
- `next_questions` 可为空
- 输出 `"基础信息收集已完成，可以进入 Needs Analysis"`
- 把仍待补的项目写入 `follow_up_items`，而不是继续强追

## 4.4 Intake 完成后的 Missing 转移规则

当 `intake_complete = true` 时：

1. 所有仍会阻塞 Needs Analysis 的 `Critical Missing Items` 必须为空
2. 原属于 Soft Required 的未获取信息：
   - 不再记录在 `Critical Missing Items`
   - 统一转入 `Follow-up Items`
3. `CLIENT_PROFILE.md` 中：
   - `Critical Missing Items` 应为空
   - `Follow-up Items` 保存后续可补充的信息
