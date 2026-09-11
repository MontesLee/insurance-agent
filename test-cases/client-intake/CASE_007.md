# CASE_007 — Pending 生命周期分支测试

> 难度：中等
> 目标：分别验证 `pending -> received`、`pending -> declined`、`pending -> expired` 与 `related_qid` 同步

---

## Round 1

### 客户输入

```text
保单我晚点找一下发给你。
```

### Assertions

```yaml
must_have:
  - pending: 保单待补

must_not_have:
  - 新建多个重复 Pending Item

must_update_profile:
  - Profile 不把保单细节写成 confirmed

must_update_log:
  - 对应问题状态变为 pending

must_update_pending:
  - 创建带 related_qid 的 Pending Item

completion_expectation:
  intake_complete: false
  reason: 这是 Pending 生命周期测试
```

---

## Branch A / Round 3 — 客户提供资料（received）

### 客户输入

```text
这是保单照片，你先看一下。
```

### Assertions

```yaml
must_have:
  - pending_item_status = received

must_not_have:
  - 继续保持 pending

must_update_log:
  - related_qid 状态同步为 answered

must_update_pending:
  - Pending Item 更新为 received

completion_expectation:
  intake_complete: false
  reason: 这是 Pending -> received 状态同步测试
```

---

## Branch B / Round 3 — 客户明确拒绝（declined）

### 客户输入

```text
我找不到了，先不发了。
```

### Assertions

```yaml
must_have:
  - pending_item_status = declined

must_not_have:
  - 继续保持 pending

must_update_log:
  - related_qid 状态同步为 declined

must_update_pending:
  - Pending Item 更新为 declined

completion_expectation:
  intake_complete: false
  reason: 这是 Pending -> declined 状态同步测试
```

---

## Branch C / Reminder Path — 超过提醒次数失效（expired）

### Round 3

```text
最近比较忙，先聊别的吧。
```

### Assertions

```yaml
must_have:
  - pending_item_status = pending
  - reminder_count = 1

must_not_have:
  - 创建新的 QID

must_update_log:
  - related_qid 继续保持 pending

must_update_pending:
  - Pending Item 已提醒 1 次
  - next_reminder_round = R5

completion_expectation:
  intake_complete: false
  reason: 这是 Pending 提醒节奏测试的第 1 个节点
```

---

### Round 5

```text
这个先放一下，咱们继续聊收入和支出。
```

### Assertions

```yaml
must_have:
  - pending_item_status = pending
  - reminder_count = 2

must_not_have:
  - 创建新的 QID

must_update_log:
  - related_qid 继续保持 pending

must_update_pending:
  - Pending Item 已提醒 2 次
  - next_reminder_round = R7

completion_expectation:
  intake_complete: false
  reason: 这是 Pending 提醒节奏测试的第 2 个节点
```

---

### Round 7

```text
还是没找到，咱们先继续别的内容吧。
```

### Assertions

```yaml
must_have:
  - pending_item_status = expired
  - reminder_count = 3

must_not_have:
  - 第 4 次主动提醒

must_update_log:
  - related_qid 状态同步为 ignored

must_update_pending:
  - Pending Item 更新为 expired
  - next_reminder_round 为空或标记停止提醒

completion_expectation:
  intake_complete: false
  reason: 这是 Pending 超过提醒上限后的自动失效测试；客户仍未提供资料，也未形成明确拒绝
```
