# CASE_003 — 创业者与多轮冲突

> 难度：复杂
> 目标：验证多轮状态继承、冲突处理、最小提问

---

## Round 1

### 客户输入

```text
想了解一下保险，你先说说都有什么类型的？
我38，自己开公司的。
```

### Assertions

```yaml
must_have:
  - age = 38
  - occupation = 公司创始人 / 企业主
  - 先解释需要了解情况

must_not_have:
  - 产品推荐
  - 直接讨论保险类型优劣

must_update_profile:
  - 写入年龄、职业

must_update_log:
  - Round 1 原文写入

must_update_pending:
  - 无新增

completion_expectation:
  intake_complete: false
  reason: 家庭、收入、支出都不完整

next_question_priority:
  first:
    - 家庭结构
```
