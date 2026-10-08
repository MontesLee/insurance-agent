# ADR-024 — Conversation / Case / Run Lifecycle

## Status

**APPROVED_WITH_CONSTRAINTS (2026-09-25, Phase 28.0.5 owner ruling)**.
批准主体 + 两项批准时补充条款（见 Decision §5/§6，源自 28.0.3 评审
M1/M2）；**约束未满足前相关实现 BLOCKED**（见 §6 明示清单）。依赖：
ADR-021/019（已 APPROVED）；实现依赖 28.D（planning agent 已注册）。

## Context

现状（代码实证）：每轮 chat 创建全新 case——`case_id="agentcase-<run
hex>"`、fresh CaseState（runtime/server.py:489, 533-534）；跨轮只有
~8 轮消息回放（:546-557），facts/artifacts 不跨轮；chat 注册表仅内存
（runtime/agent/chats.py:22，重启即失）。continuation 机制（Phase 8
replan id-based merge / approval-resume / cp.resume / RERUN_FROM_UPSTREAM
repair 语义 / PROVIDE_INFORMATION human-input artifact）**全部存在但
只在 harness 世界**。artifact 血缘 per-case（ART-NNN，
runtime/artifact_registry.py:19-21），跨 run 不存在。Review Card 按
run 目录 glob "one case per run dir" 键控（evaluation/human-review/
review_card_generator.py:63-75）。RunManager `_active[case_id]` 一 case
一活动 run + 409（server.py:159-170）。

## Problem

"把重疾保额从 50 万改成 30 万"（Scenario C）今天必然开新 case 重来——
修改、历史、复审联动都无从谈起；这是 chat-first 产品闭环的最后一块
结构缺口。

## Decision

**生命周期模型**：

```
Conversation（持久化；conversation_id）         ← QA 轮不建 case
  1─N Case（一次保险规划委托 = 稳定 case_id）
    1─N Run（initial / continuation）
      1─N Artifact（case 级注册表；跨 run 血缘）
```

四项机制（全部复用既有语义，不发明新概念）：

1. **Continuation**：conversation 元数据绑定 active case；命中
   `modify_existing_plan` 意图 → 同 case 新 run。
2. **Modification**：修改指令落 **human-input artifact**（带 provenance，
   冲突记 FACT_CONFLICT——复用 PROVIDE_INFORMATION 语义，harness.py:
   2153-2191）；受影响子图按 **RERUN_FROM_UPSTREAM** 语义从当前上游
   重导出（repair.py:83-92）；报告重渲染+与上一版 diff；高影响修改走
   replan/HITL 门（Phase 8 机制）。
3. **History**：会话消息史（持久化）+ case artifact lineage（跨 run
   可追溯）；context loading = 消息回放 + 最新 case artifacts 引用。
4. **Review linkage**：Review Card 键控重构为 case 感知（case 级卡或
   run-dir 布局保留下的 run 级卡+case 聚合视图）；审批/升级照旧锚定
   run/case（ADR-017 不动）。
5. **反馈锚定（批准时补充，2026-09-25）**：一切反馈必须引用
   **run_id + artifact_version（ART-id）**（另携 conversation_id /
   case_id 供纵向关联）；金标集抽取按 run+版本去重。目的：**防止未来
   反馈污染（feedback contamination）**——方案修改产生多版本后，
   未钉版本的反馈会串版本污染金标集（ADR-018"反馈=证据"要求证据
   可定位）。反馈永不直接改动 case 状态。
6. **数据政策边界（批准时补充，2026-09-25）**：客户信息持久化
   （conversation/case 存储落客户事实）**必须先定义**：
   - **retention**（保留期限）
   - **access boundary**（访问边界，与 runtime/agent/data_policy.py
     真实客户数据默认 BLOCKED / server 451 门对齐）
   - **deletion strategy**（删除策略）
   **信息不足即 BLOCKED implementation**：上述三项未定义前，
   conversation persistence 与 data retention 相关实现一律不得开工
   （本 ADR 的 APPROVED_WITH_CONSTRAINTS 约束条件）。已 BLOCKED 项：
   ①会话持久化存储实施 ②客户事实落库/保留/删除路径实施；
   未阻塞项：card 键控重构、槽位语义、modify 工作流（不落客户事实
   持久化的部分）待 28.D 后按门进入。

**持久化后端**：conversation 入 PostgreSQL（对齐 ADR-008/016 目标态；
与 26C agent_runs 的最终单一权威关系在实现期声明）。**存储策略**：
run-dir 布局保留（restored-runs 只读恢复与 trace 重放不动），case 级
注册表为增量叠加，不迁移旧数据、新会话生效。**槽位语义**：case 级
"一个活动 planning run"（同 case 并发修改排队）；QA 轮不占槽。

## Alternatives considered

- **A. 内存 chats + 磁盘续命（现状修补）**——否决：continuation 需要
  跨重启稳定性；重启丢会话直接破坏"第二轮修改"。
- **B. 复用 harness project 当 conversation**——否决：harness=HITL
  执行世界（ADR-017 域），生命周期粒度错误（project=执行非对话）；
  会把对话状态拖进治理冻结域。
- **C. 维持每轮新 case（现状）**——否决：修改/历史/复审联动结构性
  不可能；Scenario C 无法交付。

## Consequences

- 正：修改方案/历史追溯/复审联动成立；chat 获得跨重启稳定性；血缘
  从 run 级升 case 级。
- 负：本 ADR 是六案中**破坏面最大**的（card 键控、RunManager 槽位、
  store 布局三处下游联动——gate 隐耦 #4/#5）；PG 引入会话表（新运维
  面）；并发语义复杂化。
- 合规：审批状态机不动；trace 每 run 重放确定性不动；ADR-008 方向
  一致。

## Implementation boundary

- 新增：conversation 持久化存储；case 级 artifact 注册表（叠加层）。
- 修改：Review Card 键控（**必须先于多 run case 出现**，否则 card 取
  错 state——隐耦 #4）；RunManager 槽位语义（case 级 + QA 豁免）；
  create_agent_run 的 case 绑定逻辑。
- 冻结：store.py run-dir 布局、restored-runs 恢复路径、trace 重放、
  approval 状态机、artifact contracts。
- 实施阶段：28.E（最后实施，依赖 28.D）。

## Migration strategy

conversation 持久化先行（只加不改）→ case 绑定 + modify 语义（新会话
生效）→ card 键控重构 → 槽位语义切换。旧 run 数据零迁移；demo 模式
行为不变。

## Validation criteria

- E2E：Scenario C 全链（首轮规划→修改→diff 报告→history 可查）。
- 血缘断言：跨 run lineage 可查（continuation run 的产物引用前 run
  产物）。
- card 键控专项：多 run case 下卡取数正确。
- 回归：restored-runs 重启恢复 + trace 重放确定性；并发槽位测试
  （同 case 并发修改排队、QA 轮不阻塞）；全部既有基线绿。
