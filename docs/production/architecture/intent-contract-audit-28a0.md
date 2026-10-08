# Intent Contract Audit — Phase 28.A-0 Step 1

Date: 2026-09-25 · 只读审计（本阶段零 runtime/web 改动；本文件与三份
schema + 契约测试为全部产出）。依据：PRODUCT_VISION / ARCHITECTURE_
PRINCIPLES（docs/production/architecture/，FROZEN v1.0）· ADR-019（APPROVED
含 M1）/ ADR-020 / ADR-021（APPROVED）。

## 1. 当前意图来源（chat message flow 实测）

| 来源 | 位置 | 形态 | 问题（vs ADR-019） |
|---|---|---|---|
| agent_decide 工具参数 | runtime/agent/schemas.py:20-25 | 5 枚举 `GENERAL_KNOWLEDGE / GENERAL_GUIDANCE / CLIENT_ADVISORY / PRODUCT_LOOKUP / TASK_EXECUTION` | 枚举藏在工具参数里，非独立契约；词表≠保险意图分类 |
| system prompt 分类规则 | runtime/agent/prompts.py:12-41 | 每意图直接写死工具链（意图+工作流知识混层） | **prompt 是当前唯一的意图真理来源——ADR-019 规则 8 明令禁止的形态** |
| sticky 首轮意图 | runtime/agent/agent.py:106-112 → AgentState.intent（state.py:19） | 首个决策粘滞 | 无 schema 校验、无置信度、无 reason 记录 |
| 前端关键词映射（demo 模式） | web/src/state/chatState.ts:22-31 mapPromptToCase | 意外/医疗/高风险/证据 4 组关键词→5 演示 case，兜底=基准 case | 客户端真理；静默换义（兜底直接映射）；28.A 后降级为示例开关、28.B 退役 |
| 澄清规则 | prompts.py:43-47 Ambiguity rule | "ask ONE short clarifying question" | 语义正确但靠 prompt 自律，无 fail-closed 契约 |

**结论：不存在独立 Intent Layer。** 意图= prompt 内枚举+规则；无
IntentResult 契约、无 confidence/confidence_source、无 context_refs 输入、
无 reason_codes 审计、无 unknown 兜底契约（unknown 的行为取决于模型）。

## 2. 当前任务分类（task_type）

- **planner registry**：9 个 task_type（client_profile…report_generation），
  TASK_REGISTRY（runtime/planner/registry.py:11-94）——这是**工作流步骤**
  分类，不是用户意图分类；LLM Planner 只能发这 9 种（planner/schemas.py:
  14-16）。
- **专家分配**：TASK_AGENT_MAP 确定性 task_type→agent（runtime/agents/
  registry.py:124-128，"NOT LLM-decided"）——**执行分派**，且不在 chat
  路径上。
- 两个体系（chat 意图枚举 / planner task_type）**互不认识**：意图→
  工具链的映射只存在于 prompt 文本里。

## 3. 当前执行入口（workflow selection）

- 无 workflow "选择"：单一共享图 insurance-analysis.yaml:26（8 阶段），
  两个产品入口都进同一图——`POST /api/runs {case_id}` 整跑（server.py:
  406-416，orch.run 直调）；`POST /api/chats/{id}/messages {text}` →
  agent 工具命令式调 orch._execute_stage（tools.py:298）。
- **无 Router**（全库无 intent→agent 分发组件；"路由"=单 Agent prompt
  内自选工具）。
- runtime agent config：`GET /api/agent/config`（server.py:959）只报
  provider 状态（live glm，configured:true）——与意图/路由无关。

## 4. 与 ADR-019 的差距清单（本阶段契约已覆盖项 ✓）

| ADR-019 要求 | 现状 | 本阶段（28.A-0） | 后续阶段 |
|---|---|---|---|
| IntentResult schema validated | ❌ | ✅ schema/intent-result.schema.json | 28.A-1 规则模块产出实例 |
| v1 五意图词表 | ❌（旧 5 枚举是通用意图非保险意图） | ✅ 冻结金清单+测试 | — |
| confidence + confidence_source | ❌ | ✅ 字段+枚举 rule/llm/hybrid | 影子期校准 HD-1 |
| 上下文输入（M1：message+conversation+active case） | ❌ | ✅ context_refs + if/then 强制（无 case 的 modify 必须 clarification） | 28.A-1 接真实上下文 |
| unknown fail-closed | ⚠️ prompt 自律 | ✅ unknown 为合法值+澄清路径 | 28.A-1 |
| prompt 永不作为 intent source | ❌（现状唯一来源） | ✅ 契约层面（意图结构里无执行细节；词表不在 prompt） | 28.B prompt 条款退役 |
| 意图≠执行细节（无 workflow/tool） | ❌（prompt 每意图写死工具链） | ✅ additionalProperties:false 结构性排除+测试 | — |
| 事件 intent_classified | ❌ | 未做（事件词汇属实现期） | 28.A-1 |

配套契约：router-decision.schema.json（ADR-020：decision_source 仅
registry_lookup/fallback/blocked，**结构上无 llm 值**；validation_result
回链）与 agent-registry.schema.json（ADR-021 v1 声明子集：8 字段、
configuration based、additionalProperties:false 封禁执行字段混入——
workflow/tools 等留待 28.A-1+ 的版本化修订，不静默加入）。

## 5. 明确不做（本阶段红线复核）

未连接真实 Router（无 runtime 改动）；未改变任何现有执行路径（chat/
demo/harness 三路径零触碰）；schema/ 与 tests/contract/ 为纯增量；
意图规则模块、事件词汇、prompt 退役、影子模式全部留待 28.A-1。
