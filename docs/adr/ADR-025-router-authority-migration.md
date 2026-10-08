# ADR-025 — Router Authority Migration

## Status

**APPROVED（2026-09-25，Phase 28.B6 Owner 批准记录；原 PROPOSED 立案
于 28.B3）**。批准事实与范围（Owner 决策记录，技术内容未改动）：

- **decision = APPROVED**：ADR-025 所载 Router Authority Migration
  治理框架（权威归属/阶段 M0..M5/开关/回滚/兼容/观测）整体批准。
- **approval scope**：治理框架与后续各阶段的**准入方式**——每阶段
  （M2 灰度、M3 planning 切片、M4 全量、M5 清理）仍须**各自独立
  授权**并过本 ADR §7/§8 之门；本批准**不等于**任何阶段开工许可。
- **prerequisite status（批准时点）**：B4 等价门 GREEN（14/14）；
  M1 已达成；M2 机制经灰度+回滚演练验证；model-fit 校准完成
  （citation 3/4、超时有界）；backend 703/0 · web 148+2 · tsc clean；
  governance 一致性审计 PASS（phase-28b6 终报告）。
- **rollback requirement**：任何阶段切换必须保持本 ADR §6 回滚契约
  （env+重启单位、无破坏性写、演练先行）——不可回滚的迁移不得执行。
- **M3 remains separately gated**：Planning 切片开工需 M3 preflight
  全绿（prompt freeze / planning baseline / E1 契约 / 回滚预检——
  见 docs/production/phase-28b6-adr025-m3-preflight.md）+ 独立开工
  授权。Router Authority 在 M4 前保持 OFF。

本 ADR 承接 28.0.3 评审 O-1 裁决（"ADR-025 于 28.B 前立案"）并闭合
其开放项：**权威迁移不新建运行时**（One Runtime / Principle 5）——
"统一运行时"即**现有 server+orchestrator 脊柱 + Router 分发的行为
单元**，不存在平行执行核（见 Decision §3）。
依赖：ADR-019/020/021（APPROVED，已实施至切片级）；关联：ADR-022
（QA grounding）、ADR-024（continuation 段仍 BLOCKED）。

## Context

现状（代码实证，2026-09-25）：

- **当前执行路径**见 Decision §1：chat 轮经 shadow 意图分类后，仅
  insurance_qa（28.C-1 D4，默认 ON）与 product_qa（28.C-2，默认 OFF）
  两切片真实路由；insurance_plan / modify_existing_plan / unknown 仍走
  既有 chat agent（LLM 工具自选，agent_state 粘滞意图）。
- 治理与等价基础已备：意图契约+影子路由+校准报告（28.A 系列）、
  grounding 切片与 AnswerContext（28.C 系列）、web 事件契约双端同步
  与守护测试（28.B prep）、迁移清单 P-1..P-9（phase-28b-router-
  migration-checklist.md）。
- 缺口：权威迁移无 ADR（本文件补）；B4 行为等价门未建（设计已出：
  router-equivalence-gate-design.md）；planning 路由目标行为未实施
  （28.D）；live shadow 样本薄、HD-1 阈值未裁定。

## Problem

"Message → Intent → Router → Agent 唯一生产入口"是 PRODUCT_VISION 的
用户入口链，但切换本身是高风险生产行为：若无成案的权威归属、阶段
划分、开关与回滚契约、兼容与观测要求，切换将变成不可审计的一次性
动作——违反本仓库确定性优先与 fail-closed 传统。

## Decision

### 1. 当前执行路径（as-built）

```
Chat 轮（POST /api/chats/{id}/messages → create_agent_run → _agent_worker）
  → Intent Layer 分类（runtime/intent；规则确定性 + 可选 LLM 提案）
  → Router 查表（runtime/router；registry_lookup/fallback/blocked）
  → 切片分发：
      insurance_qa  → Insurance QA Agent（grounding 闭环）   [默认 ON]
      product_qa    → Product QA Agent（目录+合格证据）      [默认 OFF]
      其余意图      → 既有 chat agent（run_agent_turn 工具自选）[未切换]
  → 全程 shadow 记录（actual_execution 三态如实）+ intent_classified/
    qa_answered 事件
非 chat 路径（POST /api/runs 演示/管线）→ orchestrator 8 阶段（不动）
Harness 4 专家世界（demos/benchmark/approval-resume only）→ 不在迁移面
```

### 2. 目标执行路径（to-be）

```
Chat 轮 → Intent Layer（权威真理，schema+rules+event）
  → Router（唯一分发点；查表；LLM 永不参与）
  → Registry 声明的 Agent 行为单元：
      insurance-qa-agent = knowledge-QA + product-QA 行为
      insurance-planning-agent = 既有 8 阶段工作流 ownership（28.D）
      conversation-agent = 澄清/呈现（unknown 兜底）
  → 交付：grounded answer / artifact / 澄清
退役面：chat agent 的意图条款与工具自选路径、前端 demo 关键词映射
```

### 3. Authority Ownership（权威归属）

| 权力 | 唯一所有者 | 禁止 |
|---|---|---|
| 意图真理 | Intent Layer（schema+外置规则+runtime 事件，ADR-019） | prompt 作为来源；LLM 自裁 |
| intent→agent 分发 | Router（纯查表，ADR-020） | 业务条件/工作流知识/LLM |
| Agent 身份与能力 | Agent Registry（config+启动校验，ADR-021） | 运行时动态注册 |
| 工作流/skills | 各 Agent（planning 拥有 8 阶段图） | Router 编排；Agent 私联 |
| 执行核 | **现有 server+orchestrator+EventBus+artifact 脊柱**（O-1 闭合：无新运行时/存储/注册表） | 平行执行模型 |
| 保险事实 | Catalog（结构化）/WeKnora（治理证据）（ADR-022） | 无证据输出 |

### 4. Migration Stages（迁移阶段；每阶段独立门+可回滚）

| 阶段 | 内容 | 等价要求 | 状态 |
|---|---|---|---|
| M0 准备 | 本 ADR + B4 门设计 + golden 清单 + 契约同步 | — | 本阶段（docs-only） |
| M1 QA 权威 | insurance_qa 切片 | E2 契约等价（见 §7） | **已达成**（D4） |
| M2 product 灰度 | flag ON + 流量校准 | E2 | 待授权 |
| M3 planning 切片（28.D） | insurance_plan/modify → planning 行为单元 | **E1 字节级等价**（B4 门） | 未实施 |
| M4 全量权威 | 总开关分段全开；legacy 工具自选与 demo 映射退役 | E1+E2 全绿 | 未实施 |
| M5 清理 | prompt 意图条款全退、shadow 对照面收编为审计 | — | 未实施 |

顺序不可颠倒（plan 类等价门先行；ADR-024 continuation 段维持 BLOCKED，
modify 在 case 持久化落地前由 planning 行为单元内澄清承接）。

### 5. Feature Flags（开关契约）

- 既有：`INSURANCE_AGENT_QA_SLICE`（默认 ON，D4 裁决例外）、
  `INSURANCE_AGENT_PRODUCT_QA_SLICE`（默认 OFF）、
  `INSURANCE_AGENT_INTENT_LLM`（默认 OFF）、
  `INSURANCE_AGENT_INTENT_SHADOW_DIR`。
- 新增（M3/M4 实施）：`INSURANCE_AGENT_PLAN_SLICE`（默认 OFF）、
  `INSURANCE_AGENT_ROUTER_AUTHORITY`（分段值：`slices`（默认，=现状）→
  `no-plan`（QA 类全权威）→ `full`）。
- 纪律：新切片一律默认 OFF；开关只选择路径不改变语义；actual_execution
  如实记录；开关清单集中一页文档（checklist F-1）。

### 6. Rollback Strategy（回滚策略）

- **单位**：单 env 值 + 进程重启；无数据迁移、无破坏性写（AnswerContext/
  shadow/审计均为增量记录）。
- **层级**：切片开关（粒度最细）→ AUTHORITY 总开关分段回退 → 代码回滚
  （git，规则/registry 版本化）。
- **不可回滚面**：无（chat 消息历史语义不变；QA 轮产出的已答内容不撤回，
  仅后续轮回到 legacy 路径）。
- **演练**：M2 前完成一次 ON→OFF→ON 演练（checklist B-4）；回滚决策线
  与观测告警联动（§8）。

### 7. Compatibility Requirements（兼容要求）

- **契约冻结**：IntentResult / RouterDecision / agent-registry /
  qa-answer-context v1 词汇与形状不变（增量字段须 additive optional +
  双端契约测试同步）。
- **等价双类**：**E1 字节级**（planning 类：同输入同 seeds 下 artifacts/
  eval 逐字节等价——B4 门强制）与 **E2 契约级**（QA 类：每轮 schema-valid
  AnswerContext、failure_reason ∈ 枚举、引用闭环不变量、幻觉结构性为零；
  输出与 legacy 不同是设计使然，以 shadow 一致性与质量指标对照）。
- **既有系统**：orchestrator/workflow/skills/eval 门/approval 状态机/
  artifact 生命周期零改动（M3 只改"谁被调用"，不改"被调用者"）；restored-
  runs 与 trace 重放确定性不回归；AGENTS.md §4 冻结上游不触碰。
- **基线**：backend battery、web vitest+tsc、语料 22/22、knowledge 离线
  套件、幻觉率 0.0——每阶段全绿。

### 8. Observability Requirements（观测要求）

- 事件：intent_classified（含 route_decision/latency/shadow 标志）+
  qa_answered（grounding 全遥测）已入契约；grounding_started/completed
  与 route_selected 独立发射=reserved 毕业项（M3/M4 同批，runtime 授权）。
- 记录：shadow.jsonl（resolver/mismatch/latency）+ run_dir AnswerContext
  审计 + 校准报告（report.py --shadow）。
- 切换窗口：B4 等价报告 + 每小时校准快照 + 拒答率分型/latency p95/
  mismatch 率告警线（checklist O-7/O-8，切换前定线）。
- 逆纱窗：`/product-audit` 漂移基线 diff 只收敛不增长。

## Alternatives considered

- **A. 一次性全量切换（big-bang）**——否决：无阶段门与回滚粒度；planning
  等价未证；违背渐进可回滚的既有纪律。
- **B. 永久双路径并存（切片即终点）**——否决：双执行真理长期化=漂移
  基线 P0 复活；legacy 工具自选与 demo 映射是显式技术债，方向是收敛。
- **C. 新建统一运行时服务承载 Router 分发**——否决：平行执行核违反
  Principle 5 / O-1；现有脊柱（server/orchestrator/EventBus/artifact）
  足以承载行为单元分发。

## Consequences

- 正：权威归属成案；阶段/开关/回滚/兼容/观测五域契约化；B4 门与 golden
  清单成为客观验收；O-1 以"无新运行时"方式闭合。
- 负：多阶段迁移的持续协调成本；E1 等价门建设投入（工具+基线采集）；
  M4 退役面（chat 工具自选/demo 映射）需双路径测试覆盖至退役完成。
- 合规：不触碰 ADR-004（eval 门）/017（approval）/018（feedback）；
  orchestrator 冻结承诺延续。

## Implementation boundary

- 新增（各阶段授权后）：planning 行为单元（28.D）、B4 门实现、AUTHORITY
  总开关、grounding/route 独立事件发射、开关集中文档。
- 修改：server 切片分发段（增量）；退役时 prompts.py 意图条款与
  chatState demo 映射（M4/M5）。
- 冻结：orchestrator/workflow/skills/eval/approval/artifact 生命周期/
  knowledge/**（WeKnora）/IntentResult 等四契约 v1 形状。
- 实施阶段：M0（本阶段）→M2（灰度）→M3（28.D）→M4→M5。

## Migration strategy

见 Decision §4 阶段表 + phase-28b-router-migration-checklist.md
P-1..P-9 序列；每阶段过 phase-28-implementation-gates 对应栏 +
本 ADR §7 兼容门 + §8 观测包。

## Validation criteria

- 每阶段：B4 等价报告全绿（E1 字节级 / E2 契约级）+ shadow 一致性达
  所有者裁定阈值（HD-1）+ 全量回归基线绿 + 回滚演练通过。
- M4 验收：全意图经 Router 唯一入口；legacy 意图路径与 demo 映射退役
  且测试更新；`/product-audit` 无新增漂移项。
- 负向自检：任一切片 flag OFF 即回 legacy 且行为与切换前逐字节一致。
