# 专家 Agent

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](agents.md)

事实来源：`runtime/agents/registry.py`、`runtime/agents/executor.py`、
`runtime/agent/tools.py`。

## 1. 定位

Agent 是**执行者，不是控制者**。一个 agent 接到一个被分配的任务，
用自己有界的 LLM 工具调用循环、在受控工具集上运行，产出 artifact
候选。它不能：

- 决定并行、创建任务或 agent、修改图或依赖
- 跳过 eval、自评 PASS、触碰 harness 状态 / checkpoint / 调度器

## 2. Agent 注册表 —— 四个专家

| agent_id | 允许的 task_type | 允许的工具（另有 send_agent_message） |
| --- | --- | --- |
| `insurance_analyst` | client_profile、requirement_analysis、risk_analysis、coverage_gap、solution | record_client_profile、record_requirement_analysis、record_risk_assessment、coverage_gap_analysis、solution |
| `knowledge_specialist` | knowledge_search | knowledge_search |
| `product_specialist` | product_candidates、recommendation | product_candidate_provider、recommendation、check_catalog_product |
| `report_specialist` | report_generation | report_generation |

分配是**确定性的**（由注册表派生的 `TASK_AGENT_MAP`）—— LLM 永远不
选择谁来执行任务。执行前 Harness 校验分配（`validate_assignment`）；
非法分配直接阻塞任务，不会运行。

## 3. 执行器循环（`SpecialistAgentExecutor`）

```text
被分配的任务
 ↓ 加载 agent 定义 + 校验分配
 ↓ 从 PLANNER REGISTRY（受信）取期望 artifact 契约
 ↓ 构建 agent 受控工具集（允许的工具 + send_agent_message）
 ↓ LLM 循环，MAX_AGENT_STEPS = 8：
      工具调用 → 授权检查 → JSON-Schema 参数校验
               → 经 ToolContext 执行（skip_eval=True）
               → 结构化结果回喂给 LLM
 ↓ 按契约校验输出
 ↓ ARTIFACT_READY   （artifact 已存在；eval 尚未运行）
```

关键性质：

- **`skip_eval=True`**：工具存 artifact 但不评估；executor 的唯一产物
  就是 artifact 候选。
- 所有上限都 fail-closed（`AGENT_FAILED` + 错误码 —— 步数上限、空响应、
  LLM 错误、输出契约违规）。executor 没有任何"自称成功"的路径。
- 事件只带动作与摘要（`agent_step_started`、`agent_tool_call`、
  `agent_tool_completed`、`agent_output_validated`）—— 绝不带隐式推理。

## 4. 工具（面向 agent 的能力接口）

工具是对既有 skill 与确定性运行时的薄封装，全部经过 schema 校验
（`runtime/agent/tools.py`）：

- **对话工具**（`record_client_profile`、`record_requirement_analysis`、
  `record_risk_assessment`）：经既有适配器把用户口述事实规范化；LLM
  只提供候选事实。
- **stage 工具**（`coverage_gap_analysis`、`solution`、
  `product_candidate_provider`、`recommendation`、`report_generation`）：
  经 `orchestrator._execute_stage` 调用确定性 workflow stage —— LLM
  在这里同样无法推翻 eval 结论。
- **知识工具**（`knowledge_search`）：经共享 Evidence Provider 走 RAG；
  空结果 fail-closed（绝不存储编造的证据）。
- **目录工具**（`check_catalog_product`）：只读目录查询。
- **通信工具**（`send_agent_message`）：受校验的 A2A 消息 —— 见
  [a2a.md](a2a.zh-CN.md)。工具 schema 没有 `from_agent` 参数：发送者
  身份来自 executor 上下文，绝不来自 LLM。

并行模式下，worker 在隔离的 CaseState 副本上运行同一个 executor，
并持有只捕获不写入的 project 代理（见
[parallel-scheduler](parallel-scheduler.zh-CN.md)）。

## 5. 聊天 agent（另一层）

`runtime/agent/agent.py`（`run_agent_turn`）是 web 聊天使用的**交互式**
循环：≤ 12 步、LLM 重试 ≤ 2、结构化 `agent_decide` 决策（意图路由、
`ask_user`、`call_tool`、`finish`）、可选快速模型成本分层。它与专家
执行器共享工具注册表和同样的 fail-closed 纪律，但不属于 harness
任务流水线。
