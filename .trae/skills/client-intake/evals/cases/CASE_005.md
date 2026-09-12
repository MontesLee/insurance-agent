# CASE_005 — 客户跳着回答

> 难度：中等
> 目标：验证 ignored 状态、跳答处理、Priority 重算、避免机械重复提问

---

## Round 1

### 客户输入

```text
我35，北京，收入80万。
```

### Assertions

```yaml
must_have:
  - age = 35
  - city = 北京
  - annual_income = 800000
  - 至少生成一个 P0 问题
  - 首个问题主题 = 家庭结构 或 家庭年支出

must_not_have:
  - 产品推荐

must_update_profile:
  - 写入年龄、城市、本人收入

must_update_log:
  - 所有本轮新生成的问题均注册 QID

must_update_pending:
  - PENDING 保持为空

completion_expectation:
  intake_complete: false
  reason: 家庭责任与支出均未满足

next_question_priority:
  first:
    - 家庭结构
    - 家庭年支出
```

---

## Round 2

### 客户输入

```text
房贷200万，对了之前买过保险。
```

### Assertions

```yaml
must_have:
  - mortgage_balance = 2000000
  - 商保概况 = 已买过
  - 原 Round 1 未回答的问题转为 ignored，并在本轮重新判断优先级

must_not_have:
  - 机械原文复读上轮同一问题

must_update_profile:
  - 写入房贷余额
  - 写入商保概况

must_update_log:
  - 记录客户跳答
  - 问题状态发生更新

must_update_pending:
  - 无新增，除非客户明确承诺补保单

completion_expectation:
  intake_complete: false
  reason: 家庭结构和家庭年支出仍是阻塞项

next_question_priority:
  first:
    - 家庭结构
    - 家庭年支出
```
