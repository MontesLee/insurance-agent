# ARCHITECTURE PRINCIPLES — 六条不可违反原则

> **Governance baseline v1.0 — FROZEN 2026-09-25**（Phase 28.0.4）。
> 本文件是架构原则的**唯一权威版本**（`docs/ARCHITECTURE_PRINCIPLES.md`
> 为导航桩）。违反任一原则的实现视为架构缺陷：必须显式 ADR 豁免，
> 不允许默许。配套：PRODUCT_VISION.md（本目录）· ADR-004/005/017/018
> （在册）· ADR-019..024（PROPOSED，批准前其主题=设计不是许可）·
> AGENTS.md（Skill 层约定，继续有效）。

## Principle 1 — Chat is the Product Surface

任何新功能必须回答：**"用户是否通过 Chat 使用它？"**

- 答案为是 → User Space 能力，走 Chat 交付。
- 答案为否 → 必须属于 Operator Space 或 Developer Space，且不得
  冒充产品能力。
- 只出现在 Dashboard/Developer 面的业务功能视为**未交付**。
- Chat 对治理动作只做回链与状态呈现，不内嵌控制（承 ADR-017）。

## Principle 2 — Intent ≠ Prompt

**Intent 必须来自：schema + rules + runtime event。Prompt 只能辅助表达。**

- 意图词表=schema 契约；判定逻辑=外置规则（可离线回归）；每次裁决
  =runtime 事件（可审计）。
- Prompt 不得成为意图/业务规则的真理来源；Intent Layer 上线后
  prompt 的意图条款降级为展示辅助（ADR-019-M1 语境）。
- 识别不了 → 澄清（fail-closed），不猜。

## Principle 3 — Router is Deterministic

Router **可以**：lookup（查表）· validate（校验 IntentResult）·
dispatch（分发到 Registry 声明的 Agent）。

Router **禁止**：

- LLM 自由选择 Agent（LLM 永不参与路由）
- 保险业务逻辑 / workflow 编排 / 知识检索 / 产品推荐

同时禁止：**Agent 自己调用其他 Agent**（Agent 间协作必须经编排器/
注册声明的机制，不得点对点私联）。分工是：**Router 决定交给谁，
Agent 决定怎么做**（Agent 拥有自己的 workflow/skills/tools/knowledge
usage/artifact generation——workflow 属于 Agent，不属于 Router）。

## Principle 4 — Insurance Fact Requires Evidence

所有保险事实——**产品条款、保障责任、等待期、免责、保额**（及费率、
健康要求、资格等一切事实断言）——必须来自：

- **Product Catalog**（结构化产品事实，确定性查表，版本钉死），或
- **WeKnora evidence**（治理后的知识证据，仅 ACTIVE 版本可 ground）

**禁止模型补全**：LLM 负责理解、推理、表达；无证据时 fail-closed
拒答（统一模板：无法核实，不能无依据回答），绝不以参数记忆充当
保险事实。产品事实缺失=诚实缺失（"目录暂无该数据"），禁止知识源/
LLM 补位。（承创始 ADR-005 与 ADR-022 裁决：证据必须性无条件 YES。）

## Principle 5 — One Runtime

**禁止新增**：

- parallel workflow engine（平行工作流引擎）
- parallel artifact storage（平行产物存储）
- parallel agent execution model（平行 Agent 执行模型）

所有能力必须复用：**orchestrator + event + artifact**（canonical
执行核：orchestrator 脊柱 + EventBus/SSE + artifact 注册表）。
新执行入口、新 run 注册表、新检索协议同理——先问能否挂到既有内核，
答案为否时需要 ADR 豁免。（对照漂移基线：当前 7 个运行追踪存储是
**存量债**，方向是收敛，不允许再增。）

## Principle 6 — Human Review is Escalation

**Human 不是默认审核者，而是 AI 无法安全判断时的升级路径。**

- 默认路径：确定性质量门 + AI Review → 自动通过或升级（27.7.8/27.8
  既定方向：Decision Router → 仅 NEEDS_HUMAN_ESCALATION 进人）。
- 人负责：最终责任决策、不可自动确认的事实核验、高影响变更确认
  （ADR-017 域，审批状态机冻结）。
- 反馈=证据不是控制（ADR-018）；人工环节的设计目标是**减少**而非
  增多——每个新的人工节点都要回答"为什么 AI 不能安全地做这件事"。
