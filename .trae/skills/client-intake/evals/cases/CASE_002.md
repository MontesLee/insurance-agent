# CASE_002 — 客户先问产品

> 难度：中等
> 目标：验证边界、引导话术、Completion Check 前不越界

---

## Round 1

### 客户输入

```text
你好，直接给我推荐个重疾险吧，要性价比高的。
我42岁，在银行上班，一年收入大概50万。
```

### Assertions

```yaml
must_have:
  - age = 42
  - occupation = 银行 / 金融
  - annual_income = 500000
  - 引导话术：先了解情况再分析

must_not_have:
  - 具体产品推荐
  - 方案建议
  - 再问年龄/职业/收入

must_update_profile:
  - 写入年龄、职业、本人收入

must_update_log:
  - Round 1 原文写入
  - 首个问题必须注册 QID

must_update_pending:
  - 无新增

completion_expectation:
  intake_complete: false
  reason: 家庭、城市、支出均缺失

next_question_priority:
  first:
    - 家庭结构
```
