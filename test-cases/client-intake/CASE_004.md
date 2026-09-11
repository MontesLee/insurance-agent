# CASE_004 — Dirty Input

> 难度：复杂
> 目标：验证模糊输入、inferred 白名单、事实与推断分离

---

## Round 1

### 客户输入

```text
我32，北京的。
收入嘛去年100多，今年估计少点。
老婆30左右吧，具体没问过。
孩子两个，一个小学，一个幼儿园。
房贷反正还有不少。
保险买过，但不知道是不是重疾。
哦对了我去年做过甲状腺检查，应该没什么。
```

### Assertions

```yaml
must_have:
  - age = 32
  - city = 北京
  - last_year_income = 100多万
  - spouse_age 模糊记录
  - children = 2
  - 做过甲状腺检查

must_not_have:
  - spouse_age = 精确数字
  - 甲状腺正常
  - 职业稳定
  - 风险偏好强

must_update_profile:
  - 写入 confirmed 的基础事实
  - inferred 若出现，必须在白名单内且写 basis

must_update_log:
  - Round 1 原文写入

must_update_pending:
  - 无新增，除非客户明确承诺补资料

completion_expectation:
  intake_complete: false
  reason: 多个关键字段仍模糊或缺失

next_question_priority:
  first:
    - 年支出
    - 职业
    - 甲状腺检查结果
```
