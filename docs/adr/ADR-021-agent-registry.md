# ADR-021 — Agent Registry

## Status

**APPROVED (2026-09-25, Phase 28.0.5 owner ruling — 保持原文，无修改)**.
裁定：**Registry v1 = configuration based**（代码内声明 + 启动校验）；
**禁止 runtime dynamic registry**（运行时动态注册）。依赖 ADR-019
（已 APPROVED）；被依赖：ADR-020/022/024 条目。

## Context

现状（代码实证）：runtime/agents/registry.py 的 AGENT_REGISTRY 条目仅
6 键（agent_id/name/description/allowed_task_types/allowed_tools/
system_prompt, :16-121）+ 通信矩阵（:135-150）；分配为确定性
TASK_AGENT_MAP（:124-128 "NOT LLM-decided"）。**缺失字段**：
supported_intents、workflow、输入输出 schema、risk_level、
knowledge_dependencies、artifact_types（28.0 §5.1 gap 表）。另一侧
runtime/agent/（chat 单 Agent）无任何 registry 身份——两个世界互不
知晓（27.9 G-279-01）。

## Problem

Router 需要一个可信的"Agent 是谁/能做什么"唯一真源；今天 Agent 身份
散落在 prompt 文件、planner registry、YAML 图与 harness 代码中，无
单点声明，多 Agent 统一（收编两个世界）无从下手。

## Decision

**单一真源 Agent Registry（代码内声明 + 启动完整性校验）**，条目字段：

```
agent_id, name, description, capability        # 身份与能力概述
supported_intents[]                            # ⊆ ADR-019 意图集
tools[], skills[]                              # 工具/技能边界（越权即拒）
workflow                                       # 本 Agent 拥有的工作流引用
                                               # （如 insurance-planning@v1
                                               #  → insurance-analysis.yaml，
                                               #   引用不复制）
input_schema / output_schema                   # 引用 contracts/*.schema.json
                                               # 与工具入参 schema id
artifact_types{produced[], consumed[]}         # ⊆ contracts 白名单
risk_level                                     # low|medium|high
knowledge_dependencies[]                       # 如 weknora:insurance-kb,
                                               #    catalog:products
communication_policy                           # 沿用现矩阵
internal                                       # true=内部执行策略，不接意图
```

v1 条目：`insurance-qa-agent`（022）、`insurance-planning-agent`
（引用现有 8 阶段图）、`conversation-agent`（澄清/呈现，无业务工作流）；
现 4 专家（analyst/knowledge/product/report）标记 `internal: true` 保留
为 planning 的内部执行策略（executor 代码不动）。

启动校验（fail-closed）：supported_intents ⊆ 意图集；workflow 引用
存在；schema 文件存在；artifact_types ⊆ contracts 白名单；tools 与
allowed_tools 一致性。

## Alternatives considered

- **A. 数据库承载 Registry**——否决：运行时可变=配置漂移入口；启动
  校验弱化；与确定性优先冲突。Registry 是契约不是数据。
- **B. YAML/配置文件声明**——次选保留：可读性好，但失去类型与启动
  校验表达力；若未来引入必须保持 boot-time validation 等价。
- **C. 维持双现状（registry.py 6 键 + chat 无身份）**——否决：双源
  真理，统一无从谈起（漂移 P0-①）。

## Consequences

- 正：Router/审计/文档共用一个身份真源；新 Agent 接入=加条目+过校验；
  专家层收编有明确落点。
- 负：条目维护成本；与 planner registry / YAML 存在**引用关系**需保持
  一致（校验兜底）；启动失败即拒启（fail-closed 的代价，运维需知）。
- 合规：不触碰 eval/approval/feedback 任何 ADR。
- **范围说明（开放项 O-1）**：本 ADR 不裁决"统一运行时如何收编两世界"
  （原提案中的 Unified Runtime 主题）——执行架构仍由 migration-280
  §11（canonical=orchestrator 脊柱）+ phase-28-implementation-plan §5
  承载，如需独立 ADR 另案提出。

## Implementation boundary

- 修改：runtime/agents/registry.py 扩展条目结构 + 启动校验；
  TASK_AGENT_MAP 改为可从条目派生（**保持现行为等价**——harness 与
  其测试依赖它，gate 隐耦 #8）。
- 冻结：SpecialistAgentExecutor 语义、专家 system prompts、
  insurance-analysis.yaml、planner registry 的 task 定义。
- 实施阶段：28.A（契约）/ 28.B（收编执行）/ 28.D（planning 注册）。

## Migration strategy

28.A 落契约与校验（3 产品条目 + 4 internal 条目，行为零变化）→
28.B chat 工具栈挂到 planning 条目（行为等价门）→ 28.D 完成注册与
ownership 声明。

## Validation criteria

- Unit：启动校验全分支（缺引用/越集/未知工具→拒启）。
- Contract：Registry↔Router 接口；条目 artifact_types vs contracts。
- 回归：harness 套件（599 基线含 P7/P8/P9）零变化；行为等价门（28.B）。
