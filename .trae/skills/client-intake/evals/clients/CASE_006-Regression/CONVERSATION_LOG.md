# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| Q001 | P0 | 家庭结构 | 方便先说一下您家里的情况吗？比如有没有爱人、孩子 | R1 | ignored |  |  | R2 |
| Q002 | P0 | 家庭结构 | 明白，那就按 60 万和 80 万记。家里这边呢，结婚了吗？ | R2 | unanswered |  |  | R2 |

---

## 2. Round History

### Round 1

- 客户原文：

```text
我去年收入80万。
```

- 本轮新增 confirmed：去年收入
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q001
- Completion Check：intake_complete = False

---

### Round 2

- 客户原文：

```text
不是，刚才说错了，去年其实60万，今年预计80万。
```

- 本轮新增 confirmed：去年收入、今年收入预估
- 本轮新增 inferred：无
- 本轮新增 pending：无
- 本轮新增 QID：Q002
- Completion Check：intake_complete = False

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- R1 旧说法被 R2 修正：去年收入 80万 -> 60万（客户主动更正）

