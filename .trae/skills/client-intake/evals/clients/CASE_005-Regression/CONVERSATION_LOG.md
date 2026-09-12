# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| Q001 | P0 | 家庭结构 | 先了解一下，您现在家里是什么情况？比如爱人、孩子 | R1 | ignored |  |  | R2 |
| Q002 | P0 | 家庭结构 | 对了，您结婚了吗？有孩子的话大概多大？ | R2 | unanswered |  |  | R2 |
| Q003 | P0 | 家庭年支出 | 另外一年大概花销是多少？ | R2 | unanswered |  |  | R2 |

---

## 2. Round History

### Round 1

- 客户原文：

```text
我35，北京，收入80万。
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
房贷200万，对了之前买过保险。
```

- 本轮新增 confirmed：房贷余额、商保概况
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q002、Q003
- Completion Check：intake_complete = False

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- [空]

