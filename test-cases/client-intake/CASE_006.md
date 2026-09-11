# CASE_006 — 客户修正旧信息

> 难度：中等
> 目标：验证 Profile 只保留最新值，历史修正进入 Conversation Log / Conflict Notes

---

## Round 1

### 客户输入

```text
我去年收入80万。
```

### Assertions

```yaml
must_have:
  - last_year_income = 800000

must_not_have:
  - current_year_income = 800000

must_update_profile:
  - CLIENT_PROFILE 中写入去年收入 = 80万

must_update_log:
  - CONVERSATION_LOG 新增 Round 1 原文

must_update_pending:
  - PENDING 保持为空

completion_expectation:
  intake_complete: false
  reason: 信息远未满足 H1-H6
```

---

## Round 2

### 客户输入

```text
不是，刚才说错了，去年其实60万，今年预计80万。
```

### Assertions

```yaml
must_have:
  - last_year_income = 600000
  - current_year_income = 800000

must_not_have:
  - CLIENT_PROFILE 同时保留两个“去年收入”当前值

must_update_profile:
  - 用最新口径覆盖旧收入状态
  - 不在 Profile 保留被覆盖的旧值

must_update_log:
  - Round 2 原文写入
  - Conflict Notes 记录“R1 旧说法被 R2 修正”

must_update_pending:
  - PENDING 保持为空

completion_expectation:
  intake_complete: false
  reason: 这是状态冲突处理测试，不是完成测试
```
