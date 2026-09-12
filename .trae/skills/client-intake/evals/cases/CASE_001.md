# CASE_001 — 标准三口之家

> 难度：简单
> 目标：验证基础信息提取、Completion Check、最小问题集

---

## Round 1

### 客户输入

```text
我今年35岁，在北京做互联网，收入大概80万。
老婆暂时没工作，有一个4岁的孩子。
房贷还有200万。
之前买过一点保险，但具体记不清了。
```

### Assertions

```yaml
must_have:
  - age = 35
  - city = 北京
  - occupation = 互联网行业
  - annual_income = 800000
  - spouse employment = 暂时无工作
  - child age = 4
  - mortgage_balance = 2000000

must_not_have:
  - gender = 男
  - spouse_age = 任意数字
  - 产品推荐
  - 医学判断

must_update_profile:
  - CLIENT_PROFILE 中写入年龄/城市/职业/本人收入/家庭/房贷余额
  - CLIENT_PROFILE 中记录商保概况，但不写具体险种

must_update_log:
  - CONVERSATION_LOG 新增 Round 1 原文
  - 所有本轮新生成的问题均注册 QID

must_update_pending:
  - PENDING 保持为空

completion_expectation:
  intake_complete: false
  reason: H6 家庭年支出尚未满足；健康信息虽未触达，但属于 Soft Required，不阻塞 Intake 完成

next_question_priority:
  first:
    - 家庭年支出
```

---

## Round 2

### 客户输入

```text
一年开销大概40万。
保险保单我晚点找一下发给你。
最近几年体检没发现什么问题。
```

### Assertions

```yaml
must_have:
  - annual_expense = 400000
  - pending: 保单待补
  - health = 近几年体检没发现问题

must_not_have:
  - 保单具体险种
  - 配偶健康正常

must_update_profile:
  - 写入家庭年支出
  - 写入客户本人健康概况
  - Completion Status 更新为已完成
  - Critical Missing Items 置空
  - 将剩余 Soft Required 转入 Follow-up Items

must_update_log:
  - 与“家庭年支出”对应的 QID 变为 answered
  - Round 2 原文写入

question_state_assertions:
  - question_intent: 家庭年支出
    expected_status: answered

must_update_pending:
  - PENDING 新增保单条目

completion_expectation:
  intake_complete: true
  reason: H1-H6 已满足，剩余信息属于 Soft Required，可进入 Needs Analysis

next_question_priority:
  first: []
```

---

## Round 3（Intake 完成后的补充信息测试）

### 客户输入

```text
我老婆今年33。
房贷大概还有25年吧。
对了，我还有个妹妹，父母在老家，身体还行，目前不用我怎么管。
```

### Assertions

```yaml
must_have:
  - spouse_age = 33
  - mortgage_years = 25
  - parents support = 目前不是主要负担

must_not_have:
  - gender = 男

must_update_profile:
  - 更新配偶年龄
  - 更新房贷年限
  - 更新父母赡养概况

must_update_log:
  - Round 3 原文写入
  - 已回答问题状态同步

must_update_pending:
  - 保单 pending 仍保留

completion_expectation:
  intake_complete: true
  reason: Intake 已在 Round 2 完成；本轮用于测试客户后续补充信息时 Profile 是否正确更新

next_question_priority:
  first: []
```
