# ADR-019 — Insurance Intent Layer

## Status

**APPROVED (2026-09-25, Phase 28.0.5 owner ruling; M1 amendment
applied at approval)**. 转化自 unified-chat-multi-agent-migration-280.md
§20 提案；28.0.3 评审 MODIFY（M1）→ 本阶段所有者批准并落笔。关联：
ADR-020（Router 消费本层产出）、ADR-021（Registry 提供意图→Agent
映射对象）。

## Context

现状（代码实证）：意图识别只存在于单 chat Agent 的 prompt——枚举
`["GENERAL_KNOWLEDGE","GENERAL_GUIDANCE","CLIENT_ADVISORY","PRODUCT_LOOKUP",
"TASK_EXECUTION"]`（runtime/agent/schemas.py:20-25），分类规则写死在
system prompt（runtime/agent/prompts.py:12-41），首个决策粘滞于
AgentState.intent（runtime/agent/agent.py:106-112）；demo 模式另有前端
5 路关键词映射（web/src/state/chatState.ts:22-31，用户文本不发送）。
无 intent schema 契约、无置信度、无独立可测单元、无 fallback 契约
（27.9/28.0 审计；漂移基线 P0-②）。产品定位（PROJECT_VISION）要求
Intent before Agent（ARCHITECTURE_PRINCIPLES §2）。

## Problem

意图是路由的唯一输入，但今天它（a）不可独立测试、（b）由 LLM 自裁且
直接决定执行路径（违反 Principle 2/3）、（c）与 demo 关键词表双源真理、
（d）失败模式未定义（识别不了会怎样取决于模型行为）。

## Decision

建立独立 **Intent Layer**：每条用户消息先经确定性规则分类（规则外置
`resources/config/*.rules.json`，可离线回归——合 AGENTS.md §5），规则
未命中时由 LLM **提案**分类（advisory），由确定性层做最终裁决与发布。

**IntentResult（schema validated，fail-closed）核心字段**：

```json
{ "intent": "insurance_qa | product_qa | insurance_plan |
            modify_existing_plan | unknown_insurance_intent",
  "confidence": 1.0,            // 规则命中=1.0；LLM 提案=模型报告值；不可伪造
  "evidence": ["rule:qa-diff-01"],  // 命中依据（规则 id 或提案理由引用）
  "source": "rules | llm | fallback",
  "requires_confirmation": false,   // 高风险低置信 → true → 澄清，不路由
  "matched_rules": ["..."], "clarify_question": null }   // 扩展字段
```

规则：

1. **LLM may propose, deterministic layer decides**——LLM 输出仅是候选与
   置信度；最终 IntentResult 由确定性代码产出并校验。
2. **Router 只消费已验证的 IntentResult**（见 ADR-020）；LLM 不能绕过
   Router、不能直接决定最终 Agent 执行路径。
3. Schema 校验失败或无法分类 ⇒ `unknown_insurance_intent`（fail-closed，
   绝不猜），进入澄清路径。
4. 高风险意图（insurance_plan / modify_existing_plan）当 source=llm 且
   confidence 低于阈值，或 requires_confirmation=true 时**禁止自动路由**，
   必须澄清确认。
5. 意图分类记为事件 `intent_classified`（进现有 EventBus，可审计）。
6. 意图分类 v1 最小集为上述 5 值；coverage_review / policy_compare /
   risk_analysis 不进 v1（无工作流与数据支撑，防止"看起来完整"）。
7. **意图输入（M1 批准裁决）** = 当前 message **+ 最近会话上下文
   （recent conversation context）+ active case 上下文（active case
   context）**。确定性规则可引用上下文信号（如 active_case_present 且
   命中修改动词 ⇒ modify_existing_plan 候选）。**上下文不可得（新会话/
   重启后失联）时：modify 类意图不可成立 → 澄清（clarification）**，
   不得凭单句猜测。
8. **Prompt 永不作为 intent source**（批准裁决显式化）：Intent Layer
   是唯一权威；prompt 的意图条款仅辅助表达（presentation only）。

## Alternatives considered

- **A. 维持 prompt 内分类（现状）**——否决：不可测试、LLM 自裁执行
  路径、与 demo 关键词表双源真理；正是漂移基线 P0-②。
- **B. 纯 LLM 分类服务**——否决：第一跳即非确定，违反确定性优先
  （ADR-004 同精神）；无法离线回归；置信度不可复现。
- **C. 扩展前端关键词映射为正式意图层**——否决：客户端持有真理、无
  审计事件、语义兜底（默认落基准 case）本身就是静默换义反例。

## Consequences

- 正：意图可单测/可审计/fail-closed；Router 获得纯净输入；prompt 可
  大幅瘦身（意图条款退役为展示辅助）。
- 负：规则集需要维护归属（谁演进关键词规则、防过拟合 benchmark——
  风险 R9）；影子期需双跑比对成本；LLM 提案质量依赖 provider 稳定性。
- 合规：不触碰 ADR-004（eval 门）、ADR-017、ADR-018。

## Implementation boundary

- 新增：意图规则模块（规则外置文件+确定性分类器）、IntentResult
  schema、事件词汇 `intent_classified`（后端词汇表与 web 事件契约
  **双端同步**——隐耦 #3：不同步则 UI 静默吞并）。
- 修改：runtime/agent/prompts.py 意图条款降级为"展示辅助"（**双源
  真理裁决：Intent Layer 是唯一权威**——gate 隐耦 #1）。
- 冻结：eval engine、orchestrator、Router（不在本层做任何路由）、
  工作流定义。
- 实施阶段：28.A（影子模式先行）。

## Migration strategy

影子模式（只记录不裁决，与旧 prompt 分类并行产出一致性报告）→
QA 意图切换为权威（28.C）→ 全意图权威 + prompt 意图条款退役（28.B）。

## Validation criteria

- Unit：规则命中/优先级/未知兜底；schema 校验失败→unknown；高风险
  低置信→requires_confirmation。
- Contract：IntentResult schema 双端契约测试。
- 影子一致性报告（分歧率+归因）达标后方可切权威。
- 负向自检：歧义/超域输入必落 unknown→澄清；全部既有回归基线绿。

## 附裁决 A — Conversation Continuation 语义（2026-09-29 · 28.K.27-RV4-C1/C2 会话 Owner 授权）

**裁定**：意图层新增 conversation 域延续信号 `pending_clarification`。
派生规则（server 从既有状态派生，零新存储）：同 chat 上一 run 终态
WAITING_USER 且其意图 = insurance_plan。classify 接受该参数并在
规则 4.5（plan 规则后、qa 规则前）裁决：当前消息**无新意图信号**
（无规划动作词 / 无问句标记 / 无定义词 / 无产品评价词；裸产品名词
**不是**切换信号）→ insurance_plan（continuation · conf 1.0 ·
reason=[rule:plan_continue:pending_clarification,
context:pending_clarification]）。topic-switch 信号正常落原规则链；
混合歧义 → clarification_required=True（fail-closed）。

**边界（显式冻结）**：conversation-scope 标志即可，不依赖 ADR-024
case 生命周期；modify / product_qa 的 pending 未覆盖（不扩大）；
进程内派生（后端重启丢 chat/run 内存态 → 同会话跨重启延续信号
丢失 = V0.1 已知限制，ADR-024 线解决）；ack-only（≤6 字符）→
insurance_plan + clarification_required=True 走 legacy 环追问；
continuation 场景的检索 query 重写 = Deferred。
