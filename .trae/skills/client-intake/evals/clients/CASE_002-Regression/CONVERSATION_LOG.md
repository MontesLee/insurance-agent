# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| Q001 | P0 | 家庭结构 | 在推荐之前我想先了解一下，您现在家里是什么情况？比如爱人、孩子这些 | R1 | unanswered |  |  | R1 |
| Q002 | P0 | 城市 | 另外您常驻在哪个城市？ | R1 | unanswered |  |  | R1 |
| Q003 | P0 | 家庭年支出 | 还有一年大概的开销，您心里有个数吗？ | R1 | unanswered |  |  | R1 |

---

## 2. Round History

### Round 1

- 客户原文：

```text
你好，直接给我推荐个重疾险吧，要性价比高的。
我42岁，在银行上班，一年收入大概50万。
```

- 本轮新增 confirmed：年龄、职业、本人收入
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q001、Q002、Q003
- Completion Check：intake_complete = False

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- [空]

