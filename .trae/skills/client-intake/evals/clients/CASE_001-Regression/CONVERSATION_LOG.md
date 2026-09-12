# Conversation Log

> 角色：保存历史问答、QID 注册表、逐轮原文
> 不作为长期事实源

---

## 1. Asked Questions Registry

| QID | Priority | Question Intent | 问题原文 | 首次出现 Round | 当前状态 | 客户回答原文 | Related Pending ID | 最后操作 Round |
|-----|----------|-----------------|----------|----------------|----------|--------------|--------------------|---------------|
| Q001 | P0 | 家庭年支出 | 想先了解一下，您家一年大概花销是多少？ | R1 | answered | 一年开销大概40万 |  | R2 |
| Q002 | P3 | 保单明细 | 保单您方便时发我就行，不急 | R2 | pending | 保险保单我晚点找一下发给你 | P001 | R2 |

---

## 2. Round History

### Round 1

- 客户原文：

```text
我今年35岁，在北京做互联网，收入大概80万。
老婆暂时没工作，有一个4岁的孩子。
房贷还有200万。
之前买过一点保险，但具体记不清了。
```

- 本轮新增 confirmed：年龄、城市、职业、婚姻状况、配偶职业 / 状态、子女人数、子女信息、本人收入、房贷余额、商保概况
- 本轮新增 inferred：家庭收入主要依赖客户本人、存在需要抚养的未成年子女
- 本轮新增 pending：无
- 本轮新增 QID：Q001
- Completion Check：intake_complete = False

---

### Round 2

- 客户原文：

```text
一年开销大概40万。
保险保单我晚点找一下发给你。
最近几年体检没发现什么问题。
```

- 本轮新增 confirmed：家庭年支出、客户本人健康
- 本轮新增 inferred：无
- 本轮新增 pending：保单
- 本轮新增 QID：无
- Completion Check：intake_complete = True

---

### Round 3

- 客户原文：

```text
我老婆今年33。
房贷大概还有25年吧。
对了，我还有个妹妹，父母在老家，身体还行，目前不用我怎么管。
```

- 本轮新增 confirmed：配偶年龄、父母赡养情况、房贷剩余年限、其他家庭成员
- 本轮新增 inferred：无
- 本轮新增 pending：保单
- 本轮新增 QID：无
- Completion Check：intake_complete = True

---

## 3. Conflict Notes

> 客户前后说法出现冲突时，写在这里，方便后续核对。

- [空]

