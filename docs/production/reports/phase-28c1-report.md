# Phase 28.C-1 Report — QA Agent Minimal Production Loop

Date: 2026-09-25 · 状态：COMPLETE · **首个 Intent→Agent 生产切片上线**
（ruling D4：insurance_qa 意图经 Router 查表真实分发到 Insurance QA
Agent）；其余意图保持既有路径+shadow；orchestrator/planning/approval/
artifact contracts/WeKnora 零改动。

## 1. Completed work（对应 spec 实施 1-4）

- **开工前置审计**（`phase-28c1-pre-implementation-audit.md`）：五项确认
  （KnowledgeService APIs / WeKnora path / Gateway usage / AnswerContext
  落点 / 执行边界）+ 风险 R1-R5 + GO 判定，代码先行零改动。
- **1. QA Agent 模块**（`runtime/qa_agent/` 新包，~500 行）：
  - `agent.py::run_qa_turn` —— 一轮 = 已验证 IntentResult →
    KnowledgeService.build_evidence（治理证据，K001/K002）→ LLM Gateway
    生成（ruling D2）→ 引用闭环门（确定性代码）→ 一次有界再生成 →
    AnswerContext。**永不向调用方抛异常**；全部故障映射诚实拒答。
  - `agent.py::_GatewayProviderAdapter` —— 把 server 已配置的 provider
    适配进网关 LLMProvider 协议（GLMProvider 同款薄包装模式）；
    `build_gateway` 进程级单例（熔断/限流状态跨轮保持），strict 模式
    对齐 R-05。`runtime/llm/*` 零修改——网关就此**首次接线**（偿还
    R6 绕行债）。
  - `gate.py` —— 证据闭环门：cited ⊆ evidence_map（幻觉引用必拒）；
    事实句（外置词表 38 个保险事实标记）必须句内带引用；空/超长拒；
    规则外置 `config/qa-grounding-rules.yaml`（AGENTS.md §5）。
  - `context.py` —— AnswerContext 构建+校验（闭合 schema；非法记录
    在模块内降级 internal_error，绝不外泄）。
- **2. AnswerContext schema**（`schema/qa-answer-context.schema.json`）：
  answer / evidence_refs / grounding_status（grounded·partial·refused）/
  failure_reason（9 值枚举）/ **generation_provenance**（provider/model/
  prompt_version/gateway/request_id/attempts/gate_violations/usage）+
  evidence_map（标签→引用锚点，draft-07 map 惯例：propertyNames 约键 +
  additionalProperties 型值）/ intent_ref / retrieval / generated_at。
  if/then 耦合：grounded/partial ⇒ failure_reason=null 且 ≥1 引用；
  refused ⇒ failure_reason 字符串且零引用。**run 作用域记录，非
  artifact**（ruling D1）：不进 contracts 枚举、不进 artifact registry。
- **3. 证据闭环门**：三规则 + 拒绝梯度（一拒→携反馈再生成 1 次→二拒
  `citation_gate_rejected` 拒答——诚实失败优于无据答案）。LLM 永不
  自查（ruling D3 的代码级实现）。
- **4. 测试**：`tests/runtime/test_p28c1_qa_agent.py` 16 测试，五强制
  场景全落点（详见 §3）。
- **切片接线**（`runtime/server.py` `_agent_worker`）：shadow 块内计算
  `_qa_slice`（qa_slice_enabled[默认开，`INSURANCE_AGENT_QA_SLICE=0`
  逃生] ∧ intent=insurance_qa ∧ 无待澄清 ∧ registry_lookup→
  insurance-qa-agent）→ QA 轮：写 `run_dir/qa-answer-context.json` 审计
  记录 + 发 `qa_answered` 事件（元数据 only，答案全文不入事件）+
  run_completed（result_status QA_ANSWERED/QA_REFUSED）+ chat 应答 +
  early return（finally 清理照常）；**QA 轮意外异常 → 退回既有 agent
  路径（轮永不死）**。shadow 记录如实标注 actual_execution。
  `runtime/events.py` 唯一改动：词汇 +`qa_answered`。

## 2. Architecture impact

- **D4 首个生产切片**：insurance_qa 轮的真实执行从"chat agent 工具
  自选"变为"Router 查表 → QA Agent"。其余意图（plan/modify/product_qa/
  unknown）路径**逐字节不变**；Router 全局权威未切换（28.B 范围）。
- **One Runtime**：无新执行引擎/存储/注册表——QA Agent 是 server 内
  chat 轮作用域执行单元，复用 KnowledgeService、LLM Gateway、
  EventBus/SSE、chats、run_dir。
- **Insurance Fact Requires Evidence（Principle 4）首次成为代码门**：
  事实句无引用/引用不存在 → 生成失败 → 拒答。幻觉在**交付面结构性
  不可达**（幻觉引用 [E9] 用例即证）。
- **冲突处理**：governed.conflict → 确定性双方并陈模板（每句带各自
  [Ex] 引用，过同一闭环门；不平均不择一）。
- **合规复核**：orchestrator ✓零触碰 · planning workflow ✓ · approval
  ✓ · artifact contracts ✓（schema/ 新文件，contracts/ 未动）· WeKnora
  ✓（只经 KnowledgeService）· 全局 Router 权威 ✓未切换。
- **既有测试适配（1 处，行为变更所致）**：`test_agent_api.py` SSE 用例
  的 fixture 消息原为 insurance_qa 措辞——D4 下会路由进 QA 切片而非
  其测试目标的通用 agent SSE 流。改为 insurance_plan 措辞，脚本与断言
  原样（用例测的是 SSE 管道，非 QA 路由）；已在代码内注释说明。

## 3. Tests

- **Before**：646 passed / 0 failed（28.A-2 基线）· **After**：**662
  passed / 0 failed（351.7s）**（646 + 新 16；`pytest tests/runtime
  tests/contract`）——零回归。
- 五强制场景：**A** 知识问题+证据 → grounded（引用⊆evidence、
  schema-valid、provenance gateway=True）✅ · **B** 无依据问题 →
  refused/insufficient_evidence（诚实模板）✅ · **C** 知识服务不可用 →
  refused/kb_unavailable（无静默换源）✅ · **D** LLM 不可用
  （timeout/500/429 三态）→ refused/llm_unavailable ✅ · **E** 幻觉引用
  [E9] → 门拒→再生成→仍坏→refused/citation_gate_rejected（attempts=2，
  violations 落盘）；再生成功路径单测（2 次尝试后 grounded）✅。
- 另覆盖：事实句无引用拒/非事实句免引/未知标签拒已知标签收/空答案/
  分句与引用提取；schema 结构禁令（额外键、grounded带reason、
  refused缺reason/带refs、非标签 evidence_map 键、bogus reason）；
  非法意图输入 fail-closed（product_qa/畸形 intent → invalid_input）；
  冲突并陈（双源齐引、90/180 并存、不平均）；**切片 e2e**（服务器全链：
  run completed + QA_ANSWERED + chat 收到 grounded 答案 + run_dir 记录
  schema-valid + shadow actual_execution=insurance-qa-agent）；**逃生
  开关**（env=0 → 既有路径 + actual_execution=existing-agent）；**非 QA
  意图不进切片**（plan 消息走 agent 路径）。
- 全离线（mock 知识组合+fixtures 语料+MockLLMProvider/FakeLLMProvider）。

## 4. Files changed（28.C-1 增量）

**新增**：`runtime/qa_agent/{__init__,agent,context,gate}.py` ·
`schema/qa-answer-context.schema.json` · `config/qa-grounding-rules.yaml`
· `tests/runtime/test_p28c1_qa_agent.py` ·
`docs/production/reports/{phase-28c1-pre-implementation-audit,
phase-28c1-report}.md`

**修改**：`runtime/events.py`（词汇 +qa_answered，唯一改动）·
`runtime/server.py`（shadow 块切片判定 + QA 轮分支 + early return；
QA 路径意外异常回退既有路径）· `tests/runtime/test_agent_api.py`
（SSE 用例 fixture 消息改 plan 措辞，见 §2）

**零触碰**：orchestrator · skills · approval · artifact registry/
contracts/ · knowledge/**（含 WeKnora）· runtime/llm/**（网关原样）·
runtime/router.py · runtime/agent_registry.py · web/**

## 5. Known limitations

1. 切片仅覆盖 insurance_qa（product_qa 及目录事实线=下一小步，D6
   fail-closed 语义已在 schema/模板就位：catalog_missing_fact）。
2. 非 strict 服务器未配 weknora env 时，QA 以 fixtures 合成语料作答
   （有治理有引用但非生产语料）——pilot 部署须配 weknora env 或
   strict mode（审计 R2）。
3. LLM-down 时 v1 拒答（"证据摘录+引用"降级形态留待 UX 裁决，设计
   文档 D5）。
4. `qa_answered` web 契约未同步（与 intent_classified 同批，28.B 前
   闭合；UI 对未知类型设计性忽略）。
5. conflict 双方并陈为确定性模板（非 LLM 综合表达）——保守但安全；
   升级需 gate 保证下的生成式并陈。
6. 事实句探测为外置中文词表——英文/长尾表达依赖未来校准。

## 6. Next recommended action

- 观察切片真实流量（重启服务器后 insurance_qa 轮即走 QA Agent）；
  按 qa_answered 事件/AnswerContext 审计 grounding/refusal 分布。
- 下一小步候选：product_qa 切片 + 目录事实 fail-closed 路径（D6 已
  裁决）；28.B 前置（ADR-025 + B4 等价门 + web 契约同步）。

**STOP — 实施完成、测试全绿、架构影响已记录；等待下一步授权。**
