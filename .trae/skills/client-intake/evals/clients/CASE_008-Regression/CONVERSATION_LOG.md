# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| Q001 | P0 | 家庭结构 | 想先了解一下，您现在家里是什么情况？比如爱人、孩子这些 | R1 | ignored |  |  | R2 |
| Q002 | P0 | 家庭结构 | 理解，那我长话短问：您结婚了吗？ | R2 | ignored |  |  | R3 |
| Q003 | P0 | 家庭年支出 | 好，一个数就行：一年大概花多少万？ | R3 | unanswered |  |  | R3 |

---

## 2. Round History

### Round 1

- 客户原文：

```text
我35岁，北京，收入80万。
```

- 本轮新增 confirmed：年龄、城市、本人收入
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q001
- Completion Check：intake_complete = False

---

### Round 2

- 客户原文：

```text
最近工作特别忙。
```

- 本轮新增 confirmed：无
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q002
- Completion Check：intake_complete = False

---

### Round 3

- 客户原文：

```text
你就大概问一个数字吧。
```

- 本轮新增 confirmed：无
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q003
- Completion Check：intake_complete = False

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- [空]

