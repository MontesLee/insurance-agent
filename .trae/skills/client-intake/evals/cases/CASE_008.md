# CASE_008 — P0 被连续忽略

> 难度：复杂
> 目标：验证 P0 不降级但不能机械重复

---

## Round 1

### 客户输入

```text
我35岁，北京，收入80万。
```

### Assertions

```yaml
must_have:
  - age = 35
  - city = 北京
  - annual_income = 800000

must_update_log:
  - 生成 Question Intent = 家庭结构 或 家庭年支出 的 P0 问题

completion_expectation:
  intake_complete: false
  reason: H4/H6 仍缺失
```

---

## Round 2

### 客户输入

```text
最近工作特别忙。
```

### Assertions

```yaml
must_have:
  - 原 P0 问题状态更新为 ignored
  - 与 Round 1 生成的 P0 问题对应的旧 QID 不再保持 unanswered

question_state_assertions:
  - question_intent_one_of:
      - 家庭结构
      - 家庭年支出
    expected_status: ignored

must_not_have:
  - 机械重复上一轮完全同一句问题
  - 跨越一个完整客户 Round 后旧 QID 仍保持 unanswered

must_update_log:
  - 记录客户未回答且转入其他表达

completion_expectation:
  intake_complete: false
  reason: P0 未解决
```

---

## Round 3

### 客户输入

```text
你就大概问一个数字吧。
```

### Assertions

```yaml
must_have:
  - 对 P0 换一种更自然、更短的问法

must_not_have:
  - 直接重复 Round 1 原问题文本

completion_expectation:
  intake_complete: false
  reason: 这是连续 ignored 后的追问策略测试
```
