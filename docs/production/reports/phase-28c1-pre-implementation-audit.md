# Phase 28.C-1 Pre-Implementation Audit — QA Agent Minimal Production Loop

Date: 2026-09-25 · 性质：开工前置审计（本文件先于一切代码）。依据：
phase-28c0-qa-agent-design.md（28.C-0 设计）+ 所有者裁决 D1/D2/D3/D4/D6 +
ADR-022（APPROVED）+ PRODUCT_VISION/ARCHITECTURE_PRINCIPLES（FROZEN）。

## 1. KnowledgeService APIs（确认可用，零改动）

- `KnowledgeService.search(query, top_k, as_of, jurisdiction)` →
  (governed_result, decisions, ctx)；`build_evidence(...)` → **(items,
  governed, decisions, ctx)**——items 为 ALLOWED 证据 dict（K002：治理
  拒绝项绝不成证据），自带全引用元组（source/version/window/authority/
  license/hash，knowledge/governance/governance.py:188-228）。
- `governed_output()` 引擎兼容 dict（本切片不需要）。
- 注入缝：`set_default_service / reset_default_service`（测试）；生产用
  `default_service()`——组合由环境选择（非 strict 默认 mock+fixtures；
  weknora env → live；strict 强制 weknora+PG，HG-24-02/03）。
- **离线实证（本审计 live probe）**：`build_evidence("重疾险的等待期是
  什么", top_k=5)` → status=success，3 条 ALLOWED（健康告知/重疾/医疗
  语料，30ms）——Scenario A 的离线链路成立。

## 2. WeKnora retrieval path（经 KnowledgeService，零触碰）

- QA 唯一取证入口 = KnowledgeService（K001/K004）；`knowledge/provider/
  weknora.py` 一行不改（禁改承诺）。
- 生产组合：INSURANCE_AGENT_WEKNORA_URL/API_KEY/KNOWLEDGE_BASE_ID +
  registry backend 选择（service.py:269-305）。非 strict 且未配 weknora
  env 时组合为 mock（治理仍全量）——**部署注意项**（见 §6 风险 R2）。

## 3. LLM Gateway usage（D2：必须经网关）

- `runtime/llm/gateway.py::LLMGateway.generate(LLMRequest) -> LLMResponse`
  ——policy R-05→PII→限流→熔断→预算→有界瞬时重试→LLMError 族规范化→
  元数据日志（Phase 23 全能在位，未接线）。
- Provider 侧已有适配先例：`runtime/llm/glm.py::GLMProvider` 包装
  OpenAICompatProvider；`runtime/llm/mock.py::MockLLMProvider` 确定性
  +故障注入（测试用）。
- **QA 新增一个薄适配器**（GLMProvider 同款模式）在 `runtime/qa_agent/`
  内包装 server 已配置的 provider 对象（同 key/endpoint，不重复读 env）；
  `runtime/llm/*` 零修改。网关进程级单例（熔断/限流状态跨轮保持，
  provider 身份变化时重建）。
- LLMError 族（types.py:18-90）→ 映射 `llm_unavailable` 拒答。

## 4. AnswerContext integration point（D1：run 作用域记录，非 artifact）

- 构建者：`runtime/qa_agent`（新包）；**不进 contracts/ 九类枚举、不进
  artifact registry**——满足"DO NOT modify artifact contracts"。
- 三个落点：①返回值（调用方消费 answer 文本）②`qa_answered` 事件
  （EVENT_TYPES 增词，data 只带元数据：grounding_status/failure_reason/
  evidence_refs/retrieval/generation 摘要/answer_len——答案全文不入
  事件，沿 events 元数据纪律）③`run_dir/qa-answer-context.json` 全量
  审计记录（run_dir 是既有运行存储，非第二 artifact store）。
- chat 交付：复用 `chats.add_assistant_message`（现有机制）。

## 5. Existing agent execution boundary（切片接线点）

- `_agent_worker`（runtime/server.py:521-679）：shadow 分类块（:542-569）
  之后、CaseState 创建（:571）之前是**唯一接线缝**——
  `_qa_slice = qa_slice_enabled() and intent==insurance_qa and not
  clarification_required and router→insurance-qa-agent`；切片触发时走
  QA 路径并 early return（finally 清理块 :671-679 照常执行：tap 移除/
  active 槽位释放/bus finish）；未触发 → 现有路径**逐字节不变**。
- shadow 记录：QA 切片轮 `actual_execution="insurance-qa-agent"`（如实
  记录），其余轮保持 "existing-agent"；intent_classified 事件 data.shadow
  按切片如实置 False。
- 意图输入：复用 28.A 分类结果 `_ir`（规则快路径，insurance_qa 命中为
  高精度定义式/概念式措辞）；`INSURANCE_AGENT_QA_SLICE=0` 为运维逃生
  开关（默认开）。
- 防御：QA 轮意外异常 → 包装捕获 → 退回现有 agent 路径（轮永不死）。

## 6. Risks（本阶段特定）

- **R1 切片误触发**：insurance_qa 规则误命中会把本应走通用 agent 的
  消息送进 QA。缓解：规则高精度（定义式措辞+保险概念词）；QA 拒答/
  澄清模板兜底（错误答案不可能——无证据即拒）；逃生开关；shadow
  记录持续可比（legacy 对照不再运行——mismatch 分母变化已知）。
- **R2 非 strict 服务器未配 weknora env**：QA 会以 fixtures 合成语料
  作答（有引用、有治理，但非生产语料）。缓解：文档明示部署要求
  （pilot 配 weknora env 或 strict mode）；与平台既有 K003 无回退纪律
  一致。
- **R3 网关单例与重试叠加延迟**：gateway 有界重试（默认 2）+ QA 一次
  再生成 → 最坏 3×3 次调用。缓解：QA 网关 max_retries=1；生成
  max_tokens/timeout 由规则文件外置。
- **R4 事件词汇单端**：`qa_answered` 仅后端（web 契约不同步——UI 设计
  性忽略未知类型；与 intent_class web 同步决策记录同批，28.B 前闭合）。
- **R5 回归面**：events/server 为增量编辑（同 28.A 模式）；全量基线
  646/0 不允许下降。

## 7. Implementation plan（顺序）

```
A schema/qa-answer-context.schema.json（闭合 draft-07；grounded⇒failure_
  reason=null、refused⇒字符串+零引用 的 if/then）
B config/qa-grounding-rules.yaml（引用 pattern/事实词表/重生成上限/
  top_k/拒答模板——全部外置）
C runtime/qa_agent/{__init__,context,gate,agent}.py
   context: schema 校验 + anchor/grounded/refused 构建器
   gate:    分句/引用提取/事实句覆盖 → verdict（cited⊆evidence）
   agent:   run_qa_turn 主循环 + 网关薄适配器 + 系统提示词 v1
D runtime/events.py +qa_answered；runtime/server.py 切片接线（含
  actual_execution 如实记录 + early return）
E tests/runtime/test_p28c1_qa_agent.py（A-E 五场景 + 门/契约/切片接线）
F 全量回归（基线 646/0）→ phase-28c1-report.md → 记账
```

**判定：GO**——五项确认全部成立；禁改面（orchestrator/planning/
approval/artifact contracts/WeKnora/全局 Router 权威）零触碰方案已定。
