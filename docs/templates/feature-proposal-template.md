# Feature Proposal Template

> 任何新功能提案必须填写本模板（Phase 28.0.4 起生效）。模板本身是
> 治理工具：填不出来的字段=设计不完整，先补设计再开工。填写后随
> 阶段文档归档；触及 ADR 领域的行必须引用具体 ADR 编号。
> 参照：PRODUCT_VISION / ARCHITECTURE_PRINCIPLES（docs/production/
> architecture/，FROZEN v1.0）· CLAUDE.md 守门条款 · docs/adr/。

---

- **Feature**: （一句话：做什么）
- **User Problem**: （普通保险消费者的什么问题？没有用户问题的功能
  属于 Operator/Developer Space 或不该做）
- **User Space / Operator Space / Developer Space**: （三选一并说明
  理由；User Space 功能必须回答"用户如何从 Chat 使用它"）
- **Chat Entry**: （用户在 Chat 中的入口与体验路径；非 User Space
  填 N/A + 所属空间入口）
- **Agent**: （挂在哪个 Agent 名下？新增 Agent 需 Registry 条目 +
  ADR 依据；无 Agent 归属的"游离能力"需显式豁免理由）
- **Intent**: （涉及哪些意图？新增意图需 Intent Layer 词表变更说明；
  高风险意图注明置信度策略）
- **Router**: （路由表是否变化？Router 逻辑本身禁止变化——若本功能
  需要改 Router 行为，设计已经越界，回到 ADR）
- **Workflow**: （属于哪个 Agent 的 workflow？步骤增删是否引用共享图
  而非复制？）
- **Artifact**: （产出什么 artifact 类型？契约/血缘/渲染器归属；禁止
  平行产物存储；用户面渲染走统一 renderer）
- **Evidence Source**: （保险事实来自 Catalog 还是 WeKnora 证据？
  无证据事实=FAIL CLOSED；非事实类功能填 N/A）
- **ADR Impact**: （触碰哪些 ADR？001-007 / 008-018（在册）/
  019-024（PROPOSED）——列出编号与影响方式；无影响填"无"）
- **Risk**: （主要风险：行为等价/回归面/数据工程/治理边界…；
  对应的验证门）

---

填写守则：①每行都必须有答案（N/A 需理由）；②"Router/ADR Impact"两行
是最常暴露越界设计的哨兵行；③本模板与
docs/DEVELOPMENT_CHECKLIST.md Step 0/1 配合使用（模板=单功能视角，
Checklist=阶段视角）。
