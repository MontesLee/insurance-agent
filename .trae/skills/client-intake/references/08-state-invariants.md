# 08 — 自检清单与状态不变量

## 十、自检清单

输出前必须确认：

- `CLIENT_PROFILE.md` 已作为唯一长期状态源读取
- `CONVERSATION_LOG.md` 与 `PENDING.md` 已读取并更新
- 已执行 Completion Check，而不是直接先出问题
- 没有用 JSON 代替状态文件
- inferred 仅来自白名单且写明 basis
- 没有产品推荐、医学评价、保额保费建议
- `next_questions` 不超过 3 个
- 若 `intake_complete = true`，`next_questions` 可以为空，且 `follow_up_items` 已写明

> 其中可确定性判定的条目由 `scripts/check-state-invariants.ps1` 自动检查，不依赖 LLM 自觉。

---

## 十一、状态不变量（State Invariants）

每轮执行完成后必须满足以下条件。

### I1. Confirmed 唯一性

`CLIENT_PROFILE.md` 中同一 confirmed 字段只能存在一个当前值。

### I2. Source 完整性

每个 confirmed 字段必须包含：

- value
- source_round
- source_text

### I3. QID 状态闭环

所有已经进入下一客户 Round 的旧 QID，不得继续保持 `unanswered`。

### I4. Pending 一致性

状态为 `pending` 的 QID，必须存在对应的 Pending Item。

反之，每一个状态为 `pending` 的 Pending Item，必须关联一个状态为 `pending` 的 QID。

### I5. Intake 完成一致性

当 `intake_complete = true` 时：

- `Critical Missing Items` 必须为空
- H1-H6 必须全部满足
- `next_questions` 必须为空
- 剩余 Soft Required 信息只能存在于 `Follow-up Items`

### I6. 历史与当前分离

`CLIENT_PROFILE.md` 不保存已经被覆盖的旧值。

旧值只能存在于：

- `CONVERSATION_LOG.md`
- `Conflict Notes`

### I7. JSON 非状态源

JSON 输出中的数据不得成为下一轮唯一输入来源。

下一轮必须重新读取三份状态文件。

### I8. 多客户数据隔离

执行客户 C00{aa} 时，任何读写操作不得触碰 C00{bb}（bb≠aa）的目录，哪怕 C00{bb} 的内容和本轮话题很像。
