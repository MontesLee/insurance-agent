# Phase 28.0 — Insurance Chat-first Multi-Agent Architecture & Migration Plan

Date: 2026-09-24 · READ-ONLY（本阶段仅允许 Audit / Dependency & Runtime Mapping /
Knowledge Architecture Audit / Migration Design / Test Strategy / ADR Proposal /
Documentation；未修改任何代码/UI/Runtime/API/Schema/数据库/WeKnora 集成）。

Evidence base：Phase 27.9 三次全库探索（chat 管线 / agent 架构 / artifact 链路）
+ 本阶段两次深审（knowledge/WeKnora/catalog 全链；conversation→case→run→artifact
身份链 / registry 数据模型 / continuation 路径）+ live API 实测 + 前序审计
（27.7.7 / 27.7.8 / 27.8 / 27.9）。所有断言带 file:line。

> **STATUS: Architecture Audit + Migration Plan only — STOP after this
> document. 未实施；六项 ADR 仅为提案（ADR-019..024 编号已预留）。**

---

## 1. Current Architecture

### 1.1 As-built（三条互不相交的执行路径 + 一个共享确定性内核）

```
[路径 1 · Chat 世界] runtime/agent/（单数目录）
  Chat UI（默认 chatMode="agent", ChatLayout.tsx:30-32）
    → POST /api/chats/{id}/messages {text}（server.py:975）
    → create_agent_run：case_id="agentcase-<run hex>" ← 每轮一个全新 case
      （server.py:489, 533-534 "fresh canonical CaseState (no demo seeding!)"）
    → run_agent_turn 单 LLM Agent（agent.py:36, MAX 12 步）
      意图= prompt 内 5 枚举（schemas.py:20-25; prompts.py:12-41）
      工具=10 个，stage 工具直调 orch._execute_stage（tools.py:298）
      跨轮=仅消息回放 ~8 轮（server.py:546-557）

[路径 2 · Demo/Pipeline 世界] orchestrator
  POST /api/runs {case_id}（RunRequest 仅 case_id, server.py:623-624）
    → _worker → orch.run()（server.py:406-416, 无 LLM）
    seeds= benchmark 变异工件（server.py:400-408;
      manifest=evals/agent-benchmark/manifest.json,
      seeds=tests/e2e/fixtures/case-full-chain.json）

[路径 3 · Harness 世界] runtime/agents/（复数目录）+ LongRunningHarness
  4 专家（registry.py:15-121）确定性 TASK_AGENT_MAP（:124-128 "NOT
  LLM-decided"）+ MessageBus（A2A 记录, handoff.py:7 "NEVER starts an
  agent"）+ Phase 7 并行调度（harness.py:1128）
  入口：demos/benchmark（B011 四专家 DAG golden）+ 审批恢复
  （server.py:1099-1110）+ REPLAN/APPROVAL/PROVIDE_INFORMATION 控制命令

[共享确定性内核 —— 三条路径的真正交汇点]
  insurance-analysis.yaml 8 阶段 9 技能图 + CaseState 黑板 + eval_engine
  （唯一 PASS/FAIL 裁判）+ repair 环（≤2 次）+ artifact_registry
  （ART-NNN, per-case）+ trace.jsonl → EventBus → SSE
```

### 1.2 七个并存的运行追踪存储（fragmentation 实测）

| # | 存储 | 作用域 | 证据 |
|---|---|---|---|
| 1 | RunManager._runs | 进程内存（webui run 注册表） | server.py:122 |
| 2 | ChatManager._chats | 进程内存（chat+runs 链接，重启即失） | chats.py:22 |
| 3 | EventBus._history | 进程内存（每 run 事件史） | event_bus.py:56 |
| 4 | tmp/webui-runs/<run_id>/<case_id>/ | 磁盘真身：case_state.json(含 artifact_registry+checkpoints)/trace.jsonl/artifacts/（重启后只读恢复 restored:true, server.py:259-286, 1191-1280） | store.py:41-57 |
| 5 | harness-projects/<project_id>/ | 磁盘，harness 世界（跨进程可 resume, harness.py:2395-2406） | server.py:648-652 |
| 6 | PG queue_tasks+agent_runs | Phase 26 队列世界（仅 worker/测试写入，与 server 完全未链接） | run_control.py:75-88 |
| 7 | tmp/demo/<case_id>/ | demo 脚本世界（无 run 层，重跑覆盖） | demo.py:139 |

---

## 2. Runtime Dual-world Analysis（含第三世界）

27.9 判定维持并细化：**不是两个世界，是"1 个对话前端 + 1 个确定性内核 +
1 个只在内部使用的多 Agent 编排层"**。

| 维度 | Chat 世界 | Harness 世界 | 判定 |
|---|---|---|---|
| 意图 | prompt 内枚举 | 无 | chat 独有 |
| Agent 选择 | LLM 选工具 | 确定性 task→agent | 两种范式并存 |
| 工具边界 | 全局 10 工具（agent.py:49-52） | allowed_tools 裁剪+越权拒绝（executor.py:89-96,158-168） | harness 更严 |
| A2A 通信 | 不上 MessageBus（tools.py:463-465） | MessageBus 5 类消息但从不启动 agent | 形式在 harness |
| continuation | ❌ 每轮新 case | ✅ replan/approval-resume/cp.resume 全套 | **只在 harness** |
| eval 所有权 | 经工具产出的 artifact 仍过 eval（harness.py:2519-2534 同一裁判） | 同 | 已统一 ✅ |
| 执行原语 | orch._execute_stage（tools.py:298） | SpecialistAgentExecutor 或回退 orch._execute_stage（harness.py:756-784） | **已统一于 _execute_stage** ✅ |

关键洞察（迁移设计的地基）：**eval、artifact、trace、SSE、_execute_stage 已经
是三条路径的公共下沉**。割裂的是①意图/路由层（不存在）②case 生命周期
（chat 每轮新 case vs harness project 持续演进）③Agent 身份（chat 无 persona
vs registry 有 persona）。因此统一=补身份与生命周期层，**不是重写执行内核**。

---

## 3. Insurance Product Positioning（§二 再确认）

从代码而非愿望确认：本系统**是且始终是保险垂直领域 Agent 产品，不是通用
Chatbot**：

- system prompt 即保险域（"You are an insurance assistant", prompts.py:9），
  且有硬边界条款"保险相关问题 ≠ 客户咨询任务"（prompts.py:68-72）；
- 9 个 skill 全部保险业务（client-intake→…→report-generation，
  contracts/skill-id-map.json:3-12）；
- 知识域枚举 6 域 7 用途全保险（evidence/request.py:23-32）；
- 产品目录治理/评估不变量（catalog_governance.py）与知识治理
  R1-R9（governance/governance.py:47-142）为保险合规定制；
- 33 个案例全保险规划类目；WeKnora KB 装的是监管/法规文本
  （pilot_law_*/pilot_reg_*）；
- 无任何闲聊/开放域路径（QA 意图也被约束为"knowledge_search if needed →
  answer"，prompts.py:16-17）。

**User Space**（普通用户只看）：Chat / Conversation / Agent 执行状态 /
Workflow Progress / Answer / Insurance Plan / Report / 产物——与现 chat 表面
一一对应，缺 intent 透明与产物完整交付（§14/§15）。
**Operator / Developer Space**（内部）：Dashboard / Review Center / Review
Queue / Evaluation / Trace / Supervisor / Developer Mode / Run Detail /
Technical Logs / Raw IDs / Raw Events——现状全部与 User Space 平铺在同一
shell（App.tsx 4 模式无门禁），26.9 判定不变：Developer Space **不是**产品
主路径，但今天是唯一按 case 发起 run 的地方（DeveloperMode.tsx:24-43）——
这本身就是错位，Phase 28 要把"发起业务"移入 Chat。

---

## 4. Intent Taxonomy（§三 v1 最小可行集）

### 4.1 现状审计结论

| 检查项 | 现状 | 证据 |
|---|---|---|
| 独立 Intent Layer | ❌ 不存在 | 全库 grep：意图只存在于 agent prompt |
| agent_decide | ✅ 存在：5 枚举 + sticky 首轮意图 | schemas.py:20-25; agent.py:106-112 |
| frontend keyword mapping | ✅ demo 模式 5 路关键词→case | chatState.ts:22-31 |
| chat intent enum | ✅ 即 agent_decide 枚举 | 同上 |
| runtime intent | ✅ AgentState.intent + run_completed data + to_public | state.py:19,77 |
| multi-agent benchmark intent | ❌ 无（evals/ 零命中；test-cases 的 "intent" 字段是人类目的注记） | manifest.json |
| 生产级 Intent Recognition（schema 验证/置信度/fallback 契约/独立可测） | ❌ 全缺 | — |

### 4.2 v1 分类（最小可行，每项锚定既有代码路径）

| Intent | 定义 | 来源/依据 | 目标 Agent | 置信度门槛 |
|---|---|---|---|---|
| `insurance_qa` | 保险知识/概念/区别/一般选择思路（"百万医疗险和重疾险有什么区别？""等待期是什么意思？"） | 合并 GENERAL_KNOWLEDGE+GENERAL_GUIDANCE：同一工作流 retrieve→ground→answer，仅答案形态不同（直接答 vs 结构化要点），由 Agent 内部区分，不值得两个意图 | Insurance QA Agent | 低门槛（答错成本低，但无证据必须拒答兜底） |
| `product_qa` | 具体产品事实（"P001 是什么？""这个产品等待期多久？"） | PRODUCT_LOOKUP（prompts.py:35-37） | Insurance QA Agent（catalog-first 路由） | 低门槛 + 事实缺失 fail-closed |
| `insurance_plan` | 个性化方案/配置/推荐（"帮我给孩子做保险方案"） | CLIENT_ADVISORY（prompts.py:26-33） | Insurance Planning Agent | **高门槛**：低于阈值→追问，绝不自动开跑 |
| `modify_existing_plan` | 在已有方案上修改（"把重疾保额从 50 万改成 30 万"） | TASK_EXECUTION 的保险化子集（prompts.py:39-40）；需 §13 continuation | Insurance Planning Agent（continuation 模式） | **高门槛** + 必须命中会话内 active case |
| `unknown_insurance_intent` | 无法可靠分类 | 现 prompt Ambiguity rule（prompts.py:43-47 "ask ONE short clarifying question"） | Conversation 前端（澄清追问） | n/a（就是兜底） |

**明确不进 v1**（防止"看起来完整"）：`coverage_review`（保单分析：无既有
工作流与既有保单结构化数据）、`policy_compare`（无比较工作流；候选引擎是
单客户匹配不是产品对比）、`risk_analysis`（已是 insurance_plan 内部阶段，
非独立用户意图）。进 v2 的条件：出现真实业务频次 + 对应工作流数据齐备。

### 4.3 IntentResult 契约（设计，不实现）

```
IntentResult（schema validated, fail-closed）
{ intent: enum[5]              # §4.2
, confidence: number|null      # 规则命中=1.0；LLM 分类才非空；不可伪造
, matched_rules: [rule_id]     # 确定性命中的规则 id（可审计）
, llm_classification: {...}|null  # LLM 侧原始输出（仅 advisory 记录）
, method: "rules"|"llm"|"fallback"
, clarify_question: string|null   # unknown/低置信时的澄清问句
, conversation_ref / turn_ref }
```

规则硬约束：①schema 校验失败 ⇒ `unknown_insurance_intent`（fail-closed，
绝不猜）；②LLM 只产生候选分类，**不产生路由**——路由由确定性 Router 查表
（§6）；③高风险意图（insurance_plan / modify_existing_plan）在 method=llm
且 confidence < 阈值时**禁止自动路由**，进澄清；④unknown 可识别、可记录、
可评测（进事件流）。

---

## 5. Agent Registry Design（§四）

### 5.1 现状字段 vs 目标字段（实测 gap 表）

现 registry 条目仅 6 键：`agent_id, name, description, allowed_task_types,
allowed_tools, system_prompt`（registry.py:16-49）+ 通信矩阵
COMMUNICATION_POLICY（:135-150）。

| 目标字段 | 现状 | 来源/补法 |
|---|---|---|
| agent_id / name / description | ✅ | registry.py:16-18 |
| supported_intents | ❌ | 新增（§4 意图集） |
| workflow | ❌（仅 task_type→stage_id 间接存在） | 新增：workflow 引用（如 `insurance-planning@v1` → insurance-analysis.yaml） |
| skills | 部分（allowed_tools 混入工具名） | 从 planner/registry.py executor/entrypoint 派生声明 |
| tools | ✅ allowed_tools | 保留 |
| input_schema / output_schema | ❌（agent 级缺失；工具级 schemas.py、artifact 级 contracts/ 已有） | agent 级声明=引用 contracts/*.schema.json + 工具入参 schema id |
| risk_level | ❌（仅 supervisor 状态有同名概念） | 新增（low/medium/high；plan/modify=high） |
| knowledge_dependencies | ❌（kb_dir 运行时临时传） | 新增（如 `weknora:insurance-kb`, `catalog:products`） |
| artifact_types | 部分（planner registry produced_artifacts/required_inputs 隐式） | agent 条目显式声明 produced/consumed |
| 通信策略 | ✅ COMMUNICATION_POLICY | 保留 |

### 5.2 目标 Registry（设计）

- **形态**：代码内声明 + 启动时完整性校验（deterministic，校验
  supported_intents ⊆ 意图集、workflow 引用存在、schema 文件存在、
  artifact_types ⊆ contracts 白名单）。不上数据库（避免运行时可变）。
- **v1 条目**（3 个产品 Agent + 保留 4 专家为内部 executor 策略）：
  1. `insurance-qa-agent` — supported_intents [insurance_qa, product_qa]；
     workflow `qa-grounded-answer@v1`（retrieve→ground→answer，§7）；
     tools [knowledge_search, check_catalog_product]；risk low；
     knowledge_dependencies [weknora:kb, catalog:products]；
     output qa-answer（新 artifact 类型，ADR-022 决定）。
  2. `insurance-planning-agent` — supported_intents [insurance_plan,
     modify_existing_plan]；workflow `insurance-planning@v1`（=现有
     insurance-analysis.yaml 8 阶段，**引用不复制**）；tools=阶段工具集；
     risk high；artifact_types=现有 9 类；knowledge_dependencies 同上。
  3. `conversation-agent`（现 runtime/agent 退化角色）— 兜底澄清/交接说明，
     无业务工作流。
  4. 4 专家（analyst/knowledge/product/report）→ 降为
     `insurance-planning-agent` 的**内部执行策略**（executor 保留，注册表
     标注 internal=true，不接意图）。
- **Router 只消费 Registry**（§6 硬约束），Registry 不 import Router。

---

## 6. Router Design

```
IntentResult(已验证) ──查表──► agent_id ──► Registry.load(agent_id) ──► 执行
                    └─unknown/低置信高风险─► conversation-agent 澄清
```

- **纯查表**：`INTENT_AGENT_MAP = {insurance_qa→qa, product_qa→qa,
  insurance_plan→planning, modify_existing_plan→planning(continuation)}`。
  Router 模块**禁止** import workflow/yaml/skill 名（§9 约束的代码化：
  审查规则=router 模块仅依赖 intent schema + registry 接口）。
- **确定性**：无 LLM、无条件分支业务语义；表即策略，策略可审计可测试。
- **fail-closed**：IntentResult 无效/意图不在表内 → 澄清路径，绝不默认
  planning（防"什么都往管线里灌"）。
- **审计**：`intent_classified` + `route_selected` 两类事件进现有 EventBus
  （复用 events.py 机制，新增 event_type 需进词汇表——实现期决策）。
- **不路由到工具/阶段**：路由终点永远是 agent_id（现 chat agent "intent→
  选工具"的范式被显式废弃，工具选择归 Agent 工作流）。

---

## 7. Insurance QA Agent Design（§五）

### 7.1 现状审计（关键发现）

| 要求 | 现状 | 证据 |
|---|---|---|
| WeKnora integration | ✅ live 已接线（env 门控；strict 模式强制 weknora，mock 被禁 HG-24-03） | service.py:248-252,269-305; weknora.py:175-431 |
| knowledge-search Skill | ✅ 完整（模板化 query、外置 ranking 规则、4 态 status） | SKILL.md:17-40; ranking.rules.json |
| retrieval contract | ✅ KnowledgeProvider Protocol + 4 态结果 + fail-closed 错误族 | base.py:45-64,121-157 |
| evidence schema | ✅ knowledge-evidence 契约（证据项含 governance 全量戳记） | contracts/knowledge-evidence.schema.json; governance.py:188-238 |
| provenance | ✅ P001-P010 + 决策 D001-D003 + 三锚点哈希 | provenance.py:51-200; KNOWLEDGE_REGISTRY.md |
| citation | ⚠️ 仅 id 级（chunk_id/document_id），无行内引用格式；**LLM 根本看不到 chunk** | tools.py:402-404 `_ok()` 不带 data; agent.py:232-237 工具结果截断 2000 字符 |
| source ranking | ✅ 外置规则（lexical RRF+确定性 rerank；dense 禁用） | engine.py:30-306; retrieval.rules.json:8 |
| retrieval failure handling | ✅ ProviderUnavailable/ProviderResponseInvalid → fail-closed 无回退 | base.py:22-25; weknora.py:215-231 |
| hallucination gate | ⚠️ artifact 级强（provenance 检查/扫瞄器/基准 0.0 幻觉率）；**chat 答案文本零门禁**，且工具描述承诺返回 chunk 而实现不返回（schemas.py:163-165 vs tools.py:402-404） | eval_engine.py:198-234; run_agent_benchmark.py:338 |
| existing eval | ✅ 离线 50+28 例、live 48 检查（env 门控）、业务 HG-B06..09 | run_knowledge_eval.py; test_p18_live_weknora.py |

**架构级缺陷（本设计要修的根）**：`_knowledge_search` 工具把治理证据存成
artifact 后只向 LLM 回报"N items stored + artifact_id"——**证据从未进入
LLM 上下文**，"grounded answer"在今天结构上不可能成立；答案正确全靠 prompt
自律（prompts.py:53-55）。

### 7.2 目标设计

```
Insurance QA Agent（agent-owned workflow: qa-grounded-answer@v1）
 retrieve → KnowledgeService.search（模板 query + 6 域过滤 + top_k）
 ground   → 治理证据【进入 LLM 上下文】：chunk content + 溯源戳
            （source/version/effective window/authority/license/content_hash）
 answer   → LLM 基于【仅】证据作答，行内引用 [E1][E2] ↔ evidence_id
 gate     → 确定性引用闭环检查（代码，非 LLM 自查）：
            answer.cited_ids ⊆ evidence_ids 且关键句均带引用；
            任一失败 → 拒答/降级（fail-closed）
```

**职责边界**（§五 要求的显式化）：LLM=理解问题/综合证据/解释知识/生成
自然语言；WeKnora=检索/返回证据与 provenance/支撑 grounding；**禁止 LLM
在无证据时输出参数记忆里的保险事实——由引用闭环门代码强制**（不止 prompt）。

**四类故障路径**（全部映射到既有机制，不发明新概念）：

| 故障 | 处理 | 既有依托 |
|---|---|---|
| retrieval failure | 拒答 + 明示"知识检索暂不可用"（fail-closed，无回退） | Provider 错误族 + 4 态 status（base.py） |
| insufficient evidence | `insufficient_evidence` 路径：明示"知识库暂无可靠依据"+ 可选澄清/转人工标记；**绝不生成类答案** | status 枚举已有；SKILL.md:36-40 原则已有 |
| conflicting evidence | 双方并陈 + 冲突标记（不平均、不择一） | 检索冲突检测已内建（等待期/免赔额/赔付比例, engine.py:294-306） |
| stale knowledge | 有效窗 EXPIRED/SUPERSEDED 的版本不得 ground（R2/R2b 已禁），答案标注知识时效 | governance.py:62-79; window_status |

**产物**：建议新增轻量 `qa-answer` artifact（answer + evidence_refs +
citations + intent_ref），让 QA 也进"工件即证据"的既有 eval/审计世界
（新 artifact 类型=契约变更 → ADR-022 决策项 + §17 兼容矩阵标注）。

---

## 8. WeKnora Architecture（§八 现状+目标）

**现状（生产形态已成型）**：WeKnora v0.8.0 单实例 Docker loopback；3 KB
（pilot 真实文档/fixtures/smoke）；`POST /api/v1/knowledge-search` 纯检索
（"不使用LLM总结"，Ask/ReAct 路径结构性禁止, weknora.py:9-17,157-169）；
`X-API-Key` retrieve-capability 键；单 KB id env；agent 侧过度检索后用自家
SparseRetriever+确定性 rerank 重排（与 mock 同一弃权语义）；治理在 agent
侧（"WeKnora owns retrieval; the Agent owns governance" 双身份模型，
KNOWLEDGE_PRODUCTION.md:39-42）；PG 注册表（严格模式强制，生命周期
DISCOVERED→…→ACTIVE，仅 ACTIVE 可 ground，F-24 再锚定）；运维管线
ingest_registry_pg.py（Phase 24A）/sync_weknora_registry.py（Phase 18 投影）。

**目标（沿 KNOWLEDGE_PRODUCTION 既有规划，不另起炉灶）**：HA 双实例、托管
embedding、密钥轮换、多租户 KB（scope 字段已就绪）、上传→webhook→同步自动化。
**本迁移新增的决策点**：①agent 侧 lexical 重排丢弃 WeKnora 语义质量——
保留（确定性优先）或启用 dense 路径（DenseRetriever 目前 interface-only,
engine.py:80-104）→ 列为 Open Question；②多 KB 检索（product 条款 KB/
监管 KB 分域）与 §9 边界的配合。

---

## 9. WeKnora vs Product Catalog Boundary（§六）

### 9.1 现状审计（不假设、按码判定）

| Catalog 项 | 状态 | 证据 |
|---|---|---|
| Product facts（features/directions/constraints） | 数据存在（12 个全 demo 产品） | product-catalog.v0.1.json:21-48 |
| Coverage | 部分：方向/约束有，结构化 coverage_limit 无（仅生产模式必填） | catalog_governance.py:41-45 |
| Premium | 存在但 `basis:demo_reference`（明示非真实价） | json:61-64 |
| **Waiting period** | **缺**：demo 数据与 schema 均无（additionalProperties:false 加不进去） | schema; governance.py:41 |
| Eligibility | 存在（年龄/职业等级三态判定） | json:31-41; engine:210-277 |
| **Exclusions** | **缺**（仅生产必填清单里） | governance.py:42 |
| **Health requirements** | **缺** | governance.py:44 |
| Version/Status | 存在（product_version/effective 窗 + 生命周期判定） | json:14-16; product_status_on |
| 生产目录 | **缺**：product-catalog.production.json 不存在，生产模式加载即 fail-closed | catalog_governance.py:36-37,85-95 |
| 更新/版本化管线 | **缺**：静态文件手工替换 | catalog/README.md:51-56 |

**LLM 与目录的关系现状**：`check_catalog_product` 是存在性/名称校验器——
只回 5 条 slim 记录（id/名称/公司/版本），**不返回任何事实**（等待期/免赔
额/保费都不给，tools.py:420-422）；目录数据只被确定性引擎消费（候选/推荐/
eval/repair）。即"这个产品等待期多久"今天没有任何代码路径能答——而数据
本身也不存在。

### 9.2 边界设计（原则 + 路由）

```
Knowledge Layer
├── WeKnora（非结构化知识·治理证据·LLM 可引用）
│    监管法规 / 保险知识 / 医学知识 / 条款文本 / 案例FAQ
│    → 供 insurance_qa grounding；输出=证据+provenance，走 R1-R9
└── Product Catalog（结构化产品事实·确定性读取·版本钉死）
     coverage/premium/waiting_period/eligibility/exclusions/
     health_requirements/version/status
     → 供 product_qa 事实应答 + 候选/推荐引擎输入
     → 事实读取是确定性查表；LLM 只做格式化表述，不做来源
```

判定规则：**"事实型问题"（某产品的参数/费率/期限/健康要求）→ Catalog
查表优先；查不到 → fail-closed 明说"目录暂无该数据"，禁止 WeKnora/LLM
编造补位。"知识型问题"（概念/区别/条款如何理解）→ WeKnora 证据。**
目录要先补齐 schema 字段（waiting_period/exclusions/health_declaration
进 schema——现在 additionalProperties:false 连加都加不了）与生产数据，
这**前置阻塞**任何真实产品问答（F27-02 的目录内容缺口在 27.7 阶段已定性，
本审计确认仍未关闭）。

---

## 10. Unified Knowledge Service（§七）

**回答规格书的 8 问（现状全部实测）**：

1. **knowledge-search Skill 在哪**：`.trae/skills/knowledge-search/`
   （SKILL.md+双 schema+外置规则）；运行时经 `knowledge/evidence/
   provider.py:88-97` 自 14.4 起强制走 KnowledgeService。
2. **WeKnora 如何调用**：KnowledgeService 组装 WeKnoraLiveProvider
   （service.py:269-305，env URL+API key+KB id）→ HTTP 纯检索端点。
3. **哪些 Agent 能调用**：chat 单 Agent 的 knowledge_search 工具
   （tools.py:325-404）+ 编排服务环（product-candidate-provider 的
   SOLUTION_VALIDATION 服务, yaml:94-99）。**4 专家无人直接调**（只有
   knowledge_specialist 角色语义对应）。
4. **evidence 如何传递**：build_evidence → governed 证据项（全量治理戳）
   → knowledge-evidence artifact（store_as）→ 下游 required_inputs。
5. **provenance 如何传递**：证据项内嵌 source_id/version_id/content_hash/
   governance{...}；adapter 转 DOCUMENT/CHUNK 溯源条目
   （knowledge_search_adapter.py:26-57）；推荐经 evidence_refs 闭环校验。
6. **检索结果如何进 LLM context**：**不进**（§7.1 缺陷）——工具只回
   artifact_id+摘要；这是本迁移必须新增的能力（qa 上下文注入）。
7. **eval 如何验证 grounding**：artifact 级=provenance_* 检查+属性级
   grounding+业务 HG 门+幻觉扫描；**答案文本级=无**（新增项）。
8. **如何避免各 Agent 自建检索协议**：**已经避免**——Provider Protocol +
   KnowledgeService 单组合点（K001-K004, service.py:33-36）+ query 模板化
   （caller 不能注入自由文本, request.py）。新增 Provider（catalog-facts、
   regulation-db）挂同一 Protocol 即可。

**本迁移新增**：`search_for_answer(query, filters) → AnswerContext`（证据
正文+溯源进入上下文的受控通道，供 QA Agent 专用）；catalog-facts 作为只读
Provider 接入（结构化事实→带 product_version 溯源的"事实证据"，复用同一套
引用/审计机制）。**不实现，ADR-023 定契约。**

---

## 11. Unified Production Runtime（§八）

**判定：canonical execution core = orchestrator + insurance-analysis.yaml +
eval_engine + CaseState/artifact_registry + trace/EventBus/SSE。**

依据（全部已实测）：三条路径的执行原语已收敛于 `orch._execute_stage`
（tools.py:298 / harness.py:784 回退 / server.py:409 整跑）；eval 是唯一
裁判（ADR-004，harness.py:2519-2534 是 agent 产物过门的唯一位置）；artifact
注册/血缘/trace/SSE 全在内核。**割裂的从来不是执行，是身份与生命周期。**

**迁移方式（adapter + 收编，绝不重写 Orchestrator）**：

| 现世界 | 迁移去向 | 兼容手段 |
|---|---|---|
| runtime/agent/（chat 单 Agent） | **Conversation 前端**：意图请求（调 Intent Layer）+ 结果呈现 + 澄清；业务执行全部交 Router→Registry→Agent | 其 stage 工具栈原样保留为 planning agent 的工具面（同一 `_execute_stage` 入口不变） |
| runtime/agents/（4 专家+executor+MessageBus） | **Registry 的内部执行策略**：`insurance-planning-agent` 条目声明 internal executors；TASK_AGENT_MAP 保留为确定性实现细节 | executor.py 代码不动，只改被谁发现/调用（registry façade） |
| LongRunningHarness | 保留：HITL/审批/REPLAN/控制面世界（ADR-017 冻结域）；planning agent 的高风险 continuation 可选择走 harness project 形态 | 现有 approval-resume/replan 语义原样（§13 复用） |
| PG 队列（26C） | 未来持久执行面（ADR-016 既定方向）；本迁移不合并存储，仅在 ADR-024 中声明 agent_runs 为最终单一权威的目标态 | 不动 |

**不变式清单（Compatibility Matrix 详表见 §17）**：8 阶段 workflow 图零
改动（被引用而非复制）；9 skills 零改动；eval_engine 零改动且仍是唯一门；
Review Card 生成器零改动（磁盘键控天然兼容）；审批状态机零改动（ADR-017）；
SSE/事件流零改动（新增 intent/route 事件为增量词汇）；restored runs 只读
恢复路径零改动。

---

## 12. Agent Workflow Ownership（§九）

**Router ≠ Workflow** 的代码化约束：

| Intent | Agent | Agent-owned workflow（Router 不知道步骤） |
|---|---|---|
| insurance_qa / product_qa | Insurance QA Agent | retrieve → ground → answer（+ 引用闭环门） |
| insurance_plan | Insurance Planning Agent | client-intake → requirement-analysis → risk-analysis → coverage-gap-analysis → solution → (knowledge-search 服务) → product-candidate-provider → product-recommendation → report-generation（=insurance-analysis.yaml 现图，引用） |
| modify_existing_plan | Insurance Planning Agent（continuation） | delta 解析 → 受影响子图重算（RERUN_FROM_UPSTREAM 语义）→ 报告重渲染 → diff 呈现 |
| unknown | Conversation 前端 | 澄清 → 重分类 |

执行约束：router 模块仅可 import intent-schema 与 registry 接口（评审规则）；
workflow 定义只被 agent 条目与 orchestrator 引用；新增/修改阶段只动 agent
的 workflow 声明与 YAML，router 表不变。

---

## 13. Conversation / Case / Run / Artifact Lineage（§十）

### 13.1 现状身份链（实测）

```
chat_id ──runs[]──► run_id            [仅内存，重启双失]
run_id ─► case_id                    [demo=benchmark id；agent="agentcase-<run hex>"
                                        ——每轮新 case，facts 不跨轮]
run_id ─► <run_root>/<run_id>/<case_id>/  [磁盘真身，重启后只读 restored]
case_id ─► artifact_registry{ART-NNN} [per-case 作用域；血缘=同 case 内 DFS]
artifact 跨 run/case 血缘             [不存在]
用户修改已有方案                       [不存在（grep modify/delta/amend 零业务命中）]
```

continuation 能力判定表：replan ✅（仅 harness；id-based merge，终态任务
与 artifacts 原样保留, harness.py:2336-2377）；approval-resume ✅（仅
harness）；checkpoint resume 机制 ✅/webui 无执行恢复（server 从不调
cp.resume）；repair ✅（局部重导出，复用上游）；**chat continuation=消息
回放而已**。

### 13.2 目标模型（ADR-024）

```
Conversation（持久化：conversation_id）
  1─N Case（一次保险规划委托=一个稳定 case_id；qa 轮不建 case）
    1─N Run（首轮=initial；modify=continuation run）
      1─N Artifact（case 级注册表：跨 run 血缘 ART-id 全局于 case）
Lineage: continuation run 的输入= case 最新 artifacts + 修改指令
         （修改指令落 human-input artifact，冲突记 FACT_CONFLICT
          ——复用 PROVIDE_INFORMATION 语义, harness.py:2153-2191）
```

`modify_existing_plan` 语义（全部复用既有机制，不发明）：①会话→active
case 绑定（conversation 元数据）；②修改指令= human-input artifact（带
provenance）；③受影响子图以 RERUN_FROM_UPSTREAM 语义从当前上游重导出
（repair.py:83-92 语义）；④报告重渲染+与上一版 diff；⑤高影响修改走
REPLAN/HITL 门（Phase 8 机制）。前置：chat 持久化（现内存, chats.py:22）
——ADR-024 决策项（候选：PG，与 26C agent_runs 对齐）。

---

## 14. Workflow Visualization（§十一 复用，不重造）

**复用面**：AgentActivity（SSE+TRANSITIONS 状态机, runReducer.ts:121-228）、
修复徽章、质量校验 X/Y、LLM 流式（agent_stream_delta）、事件计数——27.9
已判定"✓✓●○ 目标体验今天已存在且事件驱动"。

**User View 四步映射**（从既有事件派生，无新协议）：

| 用户可见 | 驱动事件（现有） |
|---|---|
| 正在理解你的问题 | intent_classified（新事件）/ agent_decision |
| 正在检索保险知识库 | tool_started(knowledge_search) / stage_started(knowledge-search) |
| 正在整理相关资料 | artifact_created(knowledge-evidence) / stage_completed |
| 正在生成回答 | agent_stream_delta(kind=content) |

**Developer View**：保留 Agent ID/Run ID/Event/Skill/Tool/Trace/Latency
(duration_ms 已在事件 data)/Repair/Quality——现有 RuntimeInspector
（ChatLayout.tsx:296-306 右栏已内嵌）+ L4 折叠原则（27.8）。技术信息不进
用户首屏（L1-L4 标准 + web 事件契约 22→全量补齐为 C 阶段项）。

---

## 15. Artifact Architecture（§十二）

- **统一表面**：一个 ArtifactViewer（收编现 4 处重复渲染：chat ArtifactCard
  弹窗 / Conversation.ReportBlock / ArtifactInspector / ReviewWorkspace）；
  User Space=human-readable renderer（markdown/报告渲染/结构化摘要）；
  Developer Space=raw JSON+lineage（永久保留，27.8 L4 原则）。
- **格式评估**：text（chat 回答）✅/ markdown（rendered_report）✅/
  insurance-report（结构化+渲染双形态）✅ / HTML ❌（仅 tmp 一次性脚本）/
  PDF ❌（全库零）/ JSON ✅（信封）。目标链：Artifact Store→统一 Renderer
  →Chat；导出：`GET /api/runs/{id}/artifacts/{type}?format=md`（.md 先行，
  HTML=确定性模板复用报告引擎，PDF=浏览器打印优先——避免引重依赖）。
- **规则**：技术 ID 不作用户主内容（ArtifactCard 现泄漏 `artifactType ·
  run {id}`，27.8 已记）；同一 artifact 不允许多套漂移渲染器（现状 4 套
  ——收敛为 1+N（N=raw viewer））。

---

## 16. User Space / Developer Space（§九/§十 落位）

| 空间 | 内容 | 现状差距 |
|---|---|---|
| User Space | Chat（唯一业务入口）：Conversation/Agent Timeline/Answer/Plan/Report/产物 | 缺 intent 透明、全产物展示、导出、URL |
| Operator Space | Review Center（27.8 五区）/ Dashboard / Supervisor | 与用户平铺；无门禁 |
| Developer Space | Evaluation/Trace/Run Detail/Raw events/Developer Mode/Runtime 控制台 | 同上；且"发起 run"唯一入口错位于此 |

分离手段=27.8-A/27.9-E 既定项（URL 路由+空间门禁+身份 who-am-I），本
文档不重复设计，仅声明依赖顺序（§21 28.G）。

---

## 17. Compatibility Matrix

| 现有能力 | 迁移影响 | 保什么/怎么保 | 风险 |
|---|---|---|---|
| 8 阶段 workflow（YAML 单源） | 零改动（被 registry 引用） | 引用不复制；改图仍是改 YAML | 低 |
| 9 Skills | 零改动 | 入口/契约/规则全保留 | 低 |
| eval_engine（唯一门） | 零改动 | 新 qa-answer 若成 artifact 须带契约+检查族（增量） | 中（新检查族设计） |
| repair 环 | 零改动（语义被 §13 复用） | ≤2 次/耗尽 NEEDS_REVIEW 不变 | 低 |
| Review Card | 零改动 | 磁盘键控天然兼容；qa 轮是否产卡=ADR-022 决策 | 低 |
| Approval/HITL/HOTL（ADR-017） | 零改动（冻结） | chat 只回链不内嵌 | 低 |
| SSE/事件流 | 增量词汇（intent_classified/route_selected） | 词汇表+web 契约同步扩展 | 低 |
| restored runs（只读恢复） | 零改动 | run-dir glob 恢复与 trace 重放不变 | 低 |
| chat agent（现单 Agent） | **重构为 Conversation 前端** | stage 工具栈原样保留为 planning 工具面 | **高**（行为等价测试必需） |
| 4 专家/harness | 收编为内部执行策略 | executor/通信矩阵/并行调度代码不动，仅发现方式改变 | 中 |
| demo 模式（关键词映射） | 降级为显式"示例"开关 | 保留（演示/回归价值） | 低 |
| benchmark（11/11+agent 基准） | 零改动 | 剧本 provider 路径不变 | 低 |
| 26C PG 队列 | 零改动（不合并） | ADR-024 声明目标态 | 低 |
| WeKnora 集成 | 增量（AnswerContext 通道） | Provider/治理/再锚定不动 | 中（上下文注入新面） |
| 目录治理 | 增量（schema 补字段+生产数据） | demo 模式 fail-closed 语义保留 | 中（数据工程量大） |

**回归基线**：backend tests/runtime 599/0；web vitest 144/2s+tsc clean；
knowledge 离线 50+28；live 48（env 门控）；business HG 门；agent benchmark。

---

## 18. Real-world Scenarios（§十三 A-F 验证设计）

| 场景 | 意图 | Agent/路径 | 现状支持 | 缺口 |
|---|---|---|---|---|
| A "百万医疗险和重疾险有什么区别？" | insurance_qa | QA Agent→KnowledgeService→WeKnora→证据→LLM 引用作答 | 检索/治理/证据/拒答链全就绪（mock+live）；**证据不进上下文+答案零门禁** | AnswerContext+引用闭环门+qa-answer 契约 |
| B "我35岁，1孩，年入50万，房贷200万，帮我做保险规划" | insurance_plan | Planning Agent→现有 8 阶段→报告 | **全链已存在**（chat CLIENT_ADVISORY 工具链=B011 同图；demo 33 案例实证） | 意图经 Router 而非 prompt；报告进 chat 已有 |
| C "把重疾保额从 50 万改成 30 万" | modify_existing_plan | continuation run（同 case+human-input+子图重导出+diff） | **不存在**（每轮新 case；无跨轮 facts/血缘） | ADR-024 全套（会话持久化/case 绑定/case 级注册表） |
| D "这个产品等待期多久？" | product_qa | Catalog 事实查表优先 | **结构性不可答**：check_catalog_product 不回事实；等待期数据+schema 双缺 | 目录 schema+数据+事实 Provider；查不到=fail-closed 明说 |
| E "帮我买保险。" | insurance_plan（信息不足） | 澄清：ask_user 精准缺失项清单 | **已存在**（prompts.py:49-61 硬规则 5：只问具体缺项、短编号清单；evals 有 insufficient_information 类目 5 例） | Intent 层把"信息不足"与"意图不明"分开（前者已识别意图、缺事实） |
| F WeKnora 无相关证据 | insurance_qa | insufficient_evidence 拒答路径 | **机制已存在**（4 态 status+"绝不凭 LLM 自补事实" SKILL 原则+工具 fail 路径 tools.py:346-351） | 需成为 QA Agent 的标准答案形态（文案+可选转人工标记） |

---

## 19. Test Strategy（§十四）

- **Unit**：意图规则命中/优先级/未知兜底；IntentResult schema 校验失败
  →unknown（fail-closed）；Router 查表+禁路由清单（router 模块依赖审查
  测试）；Registry 启动校验（意图⊆集/workflow 引用/schema 存在）；
  KnowledgeService 4 态与错误族；引用闭环门（cited⊆evidence、无证据拒答、
  冲突并陈、过期版本拒 ground）。
- **Contract**：IntentResult、agent input/output（registry 声明 vs contracts
  实测）、knowledge 检索（KnowledgeHit/KnowledgeSearchResult）、evidence/
  provenance 戳记完整性、artifact 信封（含新 qa-answer 若采纳）。
- **Integration**：intent→router→agent→(mock provider)→LLM（剧本）→
  引用闭环→事件流（intent_classified/route_selected/产物）；live WeKnora
  变体保持 env 门控显式 SKIP（test_p18 模式）。
- **E2E**：Scenario A-F 各至少 1 正向+1 故障注入（provider down/空证据/
  冲突/过期/目录缺数据）；B 复用现有 benchmark 链断言不回归。
- **Regression**：§17 基线全绿硬门（599/0、144/2s、knowledge 50+28、
  live 48 门控、business HG、agent benchmark 幻觉率 0.0）；行为等价专项：
  chat CLIENT_ADVISORY 路径重构前后产物逐字节等价（同 seeds 对比）。

---

## 20. ADR Proposals（ADR-019..024，仅提案）

> **编号重排声明（2026-09-25，Phase 28.0.2）**：本表的临时编号已被
> 正式 ADR 取代——权威版本见 `docs/adr/ADR-019..024`（019=Intent
> Layer，020=Router Contract，021=Agent Registry，022=Knowledge
> Grounding【吸收了本表"WeKnora vs Product Catalog Boundary"主题】，
> 023=Chat Artifact Experience【新主题，原 28.F】，
> 024=Conversation/Case/Run Lifecycle）。本表"Unified Insurance
> Agent Runtime"暂未立独立 ADR（开放项 O-1，见 docs/adr/
> ADR-021-agent-registry.md 范围说明），其执行架构仍由本文 §11 与
> phase-28-implementation-plan.md §5 承载。本表仅作历史提案记录。

| ADR | 决策核心 | 关键取舍 |
|---|---|---|
| **ADR-019 Unified Insurance Agent Runtime** | canonical core=orchestrator 脊柱（图/eval/artifact/trace/SSE）；runtime/agent 降为 Conversation 前端；runtime/agents 收编为 registry 内部执行策略；harness 保留为 HITL 世界；不重写 orchestrator | 统一"身份与生命周期"而非"执行"；避免大爆炸迁移 |
| **ADR-020 Insurance Intent Layer & Deterministic Router** | 规则优先+LLM 兜底（advisory）；IntentResult schema 验证 fail-closed；unknown→澄清；高风险意图置信度地板（LLM 分类低于阈值不得自动路由）；LLM 不能绕过 Router、不决定执行路径 | 与 ADR-004 同构：确定性可测决策点 |
| **ADR-021 Insurance Agent Registry** | 代码内声明+启动完整性校验；字段集（§5.2）；Router 仅消费 registry；内部专家 internal=true 不接意图 | registry=契约不是数据库 |
| **ADR-022 Insurance Knowledge Grounding Architecture** | 证据必须进入 LLM 上下文（AnswerContext 受控通道）；答案行内引用+确定性引用闭环门（代码强制，非 prompt）；qa-answer artifact（进 eval/审计）；四类故障路径（拒答/不足/冲突/过期）标准化 | 把 grounding 从 prompt 自律升级为代码门 |
| **ADR-023 WeKnora vs Product Catalog Boundary** | 知识（WeKnora 证据）与产品事实（Catalog 结构化、版本钉死）分离；事实问答=catalog 确定性查表优先+缺失 fail-closed；catalog-facts 作为只读 Provider 挂 KnowledgeService；catalog schema 补 waiting_period/exclusions/health_declaration 为前置 | 真实产品问答被目录数据工程阻塞（如实声明） |
| **ADR-024 Conversation→Case→Run→Artifact Lineage** | conversation 持久化（候选 PG，对齐 26C agent_runs 目标态）；一次规划委托=稳定 case；case 级 artifact 注册表（跨 run 血缘）；modify_existing_plan=human-input artifact+RERUN_FROM_UPSTREAM 子图重导出+diff+高影响走 HITL | 复用 replan/repair/provide-information 既有语义 |

合规声明：六案均不触碰 ADR-004（eval 唯一门）、ADR-017（治理无控制耦合/
审批冻结）、ADR-018（反馈=证据）；ADR-022 的引用闭环门为**确定性代码**，
非 LLM 自查——与 27.7.8 "AI 只可升级、确定性 combiner" 同一哲学。

---

## 21. Migration Roadmap（§十六 依赖序重排）

**排序原则**：先交付用户可见价值且不动规划脊柱的（QA），再做最深的结构
统一（Runtime），最后做依赖结构统一的（continuation）；ADR 先行。

```
28.0（本阶段）ADR 批准 + 本文档
   │
28.A Intent Layer + Router + Registry 契约      [ADR-020/021]
   │   （一切的前置；纯增量：新模块+事件词汇，chat 前端先并行旧路径灰度）
   ▼
28.C Insurance QA Agent + WeKnora grounding      [ADR-022(+023 契约面)]
   │   （第一个被路由的 Agent；不触碰规划脊柱→风险最低、价值最可见；
   │     AnswerContext+引用闭环门+qa-answer+Scenario A/D/F 落地）
   ▼
28.B Unified Agent Runtime                       [ADR-019]
   │   （registry façade 收编 chat 工具栈与 4 专家；conversation 前端化；
   │     行为等价回归门；此阶段后旧 chat 意图路径退役）
   ▼
28.D Planning Agent migration（注册+workflow ownership 声明；Scenario B
   │   经 Router 全链验证；行为等价门）
   ▼
28.E Conversation continuation                   [ADR-024]
   │   （会话持久化+case 绑定+case 级注册表+modify_existing_plan；
   │     Scenario C 落地）
   │
28.F Unified Artifact Experience（导出端点+统一渲染器+chat 全产物）
   │   ——可与 28.B 之后任意阶段并行（不依赖 C/D/E）
   │
28.G User/Developer Space separation（URL+门禁+身份；27.8-A/27.9-E 合流）
       ——纯前端，可与任何阶段并行，建议靠后统一做
```

**为什么不按 A→B→C…机械顺序**：B（运行时统一）是风险最高的结构变更，
若最先做则用户长期看不到价值且一切耦合于它；C（QA）只依赖 A 的新模块，
能立即兑现"保险问答必须 grounded"的产品承诺，同时为 B 检验 registry 契约。
D 依赖 B（planning agent 要被注册执行）；E 依赖 D+持久化（modify 语义才
有意义）；F/G 独立并行。每阶段独立 STOP-and-wait 授权 + §19 对应测试层。

---

## 22. Risks / Open Questions

| # | 风险/开放问题 | 影响 | 归属 |
|---|---|---|---|
| R1 | **KB 内容覆盖**：pilot 语料仅 10 份监管文本（README"3 份"已过时）；保险条款/医学知识/FAQ 未入库 | QA 答非所问→大量 insufficient_evidence | 28.C 前运营项 |
| R2 | **lexical 重排丢弃 WeKnora 语义质量**（dense 禁用，engine.py:80-104 interface-only） | 召回质量天花板 | 决策：保确定性 or 启 dense（新 ADR） |
| R3 | **目录数据工程**：waiting_period/exclusions/health_declaration schema+数据双缺；生产目录文件不存在 | 真实产品问答/推荐被阻塞（F27-02 延续） | 28.C(D 场景)/目录专项 |
| R4 | chat 持久化后端选择（内存→PG？）与 26C agent_runs 的关系 | E 阶段地基 | ADR-024 |
| R5 | qa-answer 新 artifact 类型 vs contracts 白名单冻结策略 | eval/Review Card 波及面 | ADR-022 |
| R6 | 治理网关 LLMGateway（Phase 23）未接线，Agent 路径走 model.py 直连 | 治理债（27.9 G-279-10 延续） | 独立偿债项 |
| R7 | QA 答案无人工审核面（Review 面向规划产物）；QA 错答的升级策略 | 责任边界 | Open（建议：qa-answer 仅审计抽检，不入审批） |
| R8 | 行为等价风险：chat 前端化重构可能改变 CLIENT_ADVISORY 产物 | 回归门（§19 逐字节等价） | 28.B |
| R9 | 意图规则维护归属（关键词规则由谁演进、防过拟合 benchmark） | 长期质量 | 28.A 运营项 |
| R10 | demo 模式与 agent 模式并存期的用户认知（同一 chat 两种语义） | UX | 28.A 降级为显式示例开关 |

---

## 原则符合性自检（§十八）

| 原则 | 本方案的落实 |
|---|---|
| Chat 唯一业务入口 | §16；发起业务移入 Chat（28.A/B） |
| Intent 决定用户想做什么 | §4 IntentLayer（fail-closed/unknown/置信度） |
| Router 决定交给哪个 Agent | §6 纯查表；LLM 不可绕过 |
| Agent 决定如何完成任务 / Workflow 属于 Agent | §5/§12（router 禁知步骤，代码化） |
| 保险知识必须经知识源 grounding | §7/§10（AnswerContext+引用闭环门） |
| Product Catalog 与 WeKnora 职责明确 | §9（事实=目录确定性查表；知识=证据） |
| LLM 不凭记忆制造保险事实 | §7 引用闭环=代码门，非 prompt 自律 |
| 只进一个 canonical Agent Runtime | §11（orchestrator 脊柱；收编两世界） |
| User/Developer Space 分离 | §16（依赖 28.G 与 27.8/27.9 合流） |
| 本阶段只审计不实现 | ✅ 零改动，STOP |

---

## STOP

本阶段完成：Architecture Audit（§1-§3, §7-§11, §13 现状全部 file:line 实证）
+ Migration Design（§4-§6, §12-§16）+ Test Strategy（§19）+ 六项 ADR 提案
（§20, ADR-019..024）+ Roadmap（§21）+ Risks（§22）。未修改任何业务代码/
UI/Runtime/API/Schema/数据库/WeKnora 集成；未创建 Router/Agent 实现。
**等待 ADR 逐项批准与阶段授权。**
