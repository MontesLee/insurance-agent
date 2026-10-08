# Phase 28.C-0 — First Production QA Agent: Architecture & Contract Design

Date: 2026-09-25 · 性质：**DESIGN ONLY**（零代码；本文件为 28.C 实施前的
契约与边界设计）。依据：PRODUCT_VISION / ARCHITECTURE_PRINCIPLES
（FROZEN v1.0）· ADR-022（APPROVED：grounding required，fail-closed）·
ADR-019（APPROVED）· ADR-011（APPROVED design-only，已实现未接线）·
phase-28-implementation-plan §5 · phase-28-implementation-gates（ADR-022
栏）· phase-28c-readiness.md（28.A-2 就绪评估）。

所有者决策（本阶段输入）：**QA Agent 先于 Router 全量权威切换（28.B）
实施**——与 ADR-020 迁移策略一致："28.C 起 QA 意图真实路由"是**首个
权威切片**，其余意图保持 shadow/现路径。

---

## 0. Audit findings（现状实证，2026-09-25 逐项复核）

| # | 面 | 现状 | 对 QA Agent 的含义 |
|---|---|---|---|
| A1 | KnowledgeService | provider→governance→evidence 单一组合（knowledge/service.py:223-391）；K001-K004 不变量在测；strict 模式强制 weknora+PG registry（HG-24-02/03、RV-P2-01 启动 fail-fast） | **QA Agent 唯一取证入口已存在**——`search()/build_evidence()/governed_output()` 三层 API 直接复用，无需新检索层 |
| A2 | WeKnora 集成 | 纯检索端点 `POST /api/v1/knowledge-search`（query+kb_id，X-API-Key；weknora.py:194-231）；WeKnora 不提供治理字段——注册表 stamps 投影补齐；F-24 规范内容重锚（前缀规则，失败=HASH_MISMATCH fail-closed）；WeKnoraLiveProvider 套用 agent 自有 SparseRetriever+DefaultReranker+外置阈值（weknora.py:357-402）——abstention 语义与 mock 完全一致 | 检索/治理/重锚**零改动**即可服务 QA；QA 不得绕过 KnowledgeService 直连 WeKnora（K001） |
| A3 | 证据模型 | KnowledgeHit 规范模型（chunk_id/document_id/content_hash/分数）；治理 R1-R9（版本/权威/时效窗/辖域/许可/哈希/内容非空，governance.py:85-142，STATUS_FUTURE/EXPIRED/CURRENT/UNKNOWN）；build_evidence_item 产出**全引用元组**（source/version/window/authority/jurisdiction/license/hash，additive 于契约） | 证据自带可引用性与时效性——AnswerContext 的 evidence_map 直接取此元组 |
| A4 | 证据契约 | contracts/knowledge-evidence.schema.json（9 类 artifact 枚举含 knowledge-evidence；payload.status 四值 success/partial/insufficient/retrieval_error；conflict 布尔；item 级 additionalProperties 开放=容纳 14.3/14.5 增量字段）；knowledge-query.schema.json（domain 枚举 medical/critical_illness/accident/life/savings/general） | 契约不动；QA 新增的只是**消费侧**契约（AnswerContext） |
| A5 | LLM Gateway | runtime/llm/gateway.py **已实现**（Phase 23/ADR-011）：policy R-05→PII 门→限流→熔断→预算→有界瞬时重试→错误规范化为 LLMError 族→元数据日志+obs 咽喉点——**未接线**（chat 路径走 runtime/agent/model.py 直连 httpx，R6 债） | QA 的 LLM 调用是唯一新增 LLM 调用点：**推荐经网关接线**（偿清 R6；ADR-022 §4 附带修正 #2），见 §9 D2 |
| A6 | 答案生成流 | 结构性缺陷三件套：证据不进上下文（tools.py:402-404 只回 "N items stored"）；答案零代码门（agent.py:96-100 无 tool call 的纯文本直接成为最终答案）；工具描述谎言（schemas.py:163-165 承诺返回 chunk 而实现不返回） | 正是 28.C 要修的三件事：AnswerContext 受控通道 + 引用闭环门 + 描述同步修正（修后冻结同步） |
| A7 | Catalog | 12 demo 产品/19 字段；waiting_period/exclusions/health_declaration **数据与 schema 双缺**；check_catalog_product 只回 id/名称/公司/版本（tools.py:420-422） | 产品事实线在目录 schema 决策+数据工程落地前，Scenario D 只能诚实拒答（fail-closed 正确行为，价值待数据） |
| A8 | 属性级 grounding | knowledge/evidence/attribute_grounding.py：产品属性→SUPPORTED/UNSUPPORTED/CONFLICT/**NOT_CHECKABLE**（第三态，绝不并入 SUPPORTED）；确定性规则驱动；属性集有界（renewal_period/coverage_type/eligibility_age/deductible/coverage_term） | 冲突检测与"不可查≠已核查"语义已有先例——AnswerContext 的 grounding_status 沿用同款三态诚实语义 |

---

## 1. QA Agent 责任边界（Responsibility Boundary）

**QA Agent（`insurance-qa-agent`，registry 已声明：supported_intents
= [insurance_qa, product_qa]，risk_level=low）拥有：**

1. **知识型问答**（insurance_qa）：保险概念/条款理解/监管知识——
   WeKnora 治理证据 grounding + 引用闭环的合成答案。
2. **产品事实问答的应答面**（product_qa）：按 ADR-022 判定规则做
   事实型/知识型分流（§7），事实型走 Catalog 确定性查表并**如实转述**。
3. **澄清**：问题歧义/指代不明时追问（一次，不连环）。
4. **诚实拒答**：无证据/无数据/服务不可用/冲突——宁可拒答不编造
   （PRODUCT_VISION 最高行为准则）。

**QA Agent 不拥有（Forbidden）：**

- 产品推荐/方案规划/风险分析（Planning Agent 域）；
- 修改已有方案（modify_existing_plan → Planning，continuation 模式）；
- 路由决策（Router 域，ADR-020）；
- 任何 workflow/stage/skill 编排知识（prompt 内不得出现工作流语义）；
- 证据治理判断（治理在 KnowledgeService/Governance，QA 只消费
  ALLOWED 项——K002）；
- 无证据事实输出（Principle 4，代码级强制，见 §5）。

**执行形态（One Runtime 约束下的设计承诺）**：QA Agent 不是新执行引擎
——它是现有 runtime 内的一个**chat 轮作用域执行单元**（复用既有
provider/gateway、KnowledgeService、artifact registry、EventBus/SSE），
由 Router 按 IntentResult 查表分发（28.C 起 insurance_qa/product_qa
两意图权威化；其余意图保持现路径+shadow）。

## 2. Input Contract（QAQueryInput）

```json
{
  "$id": "qa-query-input.schema.json", "schema_version": "1.0",
  "message":          "用户当前消息原文（非空）",
  "conversation_context": ["最近 ≤8 轮消息（role+content），可为空数组"],
  "intent_result":    "IntentResult（schema/intent-result.schema.json 校验通过；intent_id ∈ {insurance_qa, product_qa}）",
  "clarification_history": ["本轮会话内已发生的澄清问答（≤2 条，防连环追问）"],
  "context_refs":     "{conversation_id, message_id, run_id（审计锚点）}"
}
```

规则：

- **intent_result 是必要输入且必须已验证**——QA Agent 不重新分类意图
  （Intent ≠ Prompt；Router 只消费已验证 IntentResult）。收到
  clarification_required=true 或表外意图 → 立即转澄清路径，不进回答流程。
- conversation_context 仅用于指代消解与追问判断；**不是证据源**。
- 契约闭合（additionalProperties:false，沿 28.A-0 风格）；输入校验失败
  → fail-closed 澄清，不猜。

## 3. WeKnora Retrieval Contract

QA Agent 永远经 **KnowledgeService**（K001/K004），本节定义其调用契约：

| 项 | 契约 |
|---|---|
| **query** | v1 确定性构造：用户问题规范化文本（去空白/保中英）+ 规则映射 domain（knowledge-query.schema 枚举六域）。**v1 不用 LLM 改写查询**（可回归、可审计）；LLM 辅助查询改写列为 §9 开放项 D4 |
| **top_k** | 外置规则文件默认（建议 8）；不硬编码 |
| **as_of / jurisdiction** | 由 KnowledgeService 单点默认（now/CN）；测试可注入 |
| **retrieved evidence** | 仅 `build_evidence()` 的 **ALLOWED 项**（K002：治理拒绝的命中绝不成为证据）；evidence_id = chunk_id（确定性身份，无随机 UUID）；content = 注册表规范 chunk（F-24 重锚后） |
| **source metadata** | 全引用元组随证据自带：source_id/source_name/version_id/effective_from-to/authority_level/jurisdiction/license_status/canonical_uri/content_hash + retrieved_at + governance 块（R1-R9 决策码） |
| **confidence** | **只来自检索分数的有界映射**（min(1, score)，与 build_evidence_item 现行语义一致）；**绝不使用模型自报数字**；整体 grounding 置信 = 全部引用证据 confidence 的确定性聚合（min），只报告不决策路由 |
| **abstention** | insufficient_evidence/partial_evidence 状态**原样传播**（沿 evidence loop 的诚实戒律：loop.py 不改写状态；QA 同样不得把 insufficient 粉饰成 partial） |
| **stale** | STATUS_EXPIRED/SUPERSEDED 证据治理层已拒（R2/R2b）——QA 无需二次判断，但答案须携带所引证据的时效窗标注 |

## 4. AnswerContext Schema（新契约，28.C 首个交付物）

```json
{
  "$id": "qa-answer-context.schema.json", "schema_version": "1.0",
  "type": "object", "additionalProperties": false,
  "required": ["answer", "evidence_refs", "grounding_status",
               "failure_reason", "evidence_map", "intent_ref",
               "retrieval", "generated_at", "generation"],
  "properties": {
    "answer": {
      "type": "string",
      "description": "最终用户可见答案文本。grounded 时行内引用 [E1][E2]；refused 时为统一拒答模板文本"
    },
    "evidence_refs": {
      "type": "array", "items": {"type": "string", "pattern": "^E[0-9]+$"},
      "description": "答案中实际使用的引用标签（闭合门校验对象）"
    },
    "evidence_map": {
      "type": "object",
      "additionalProperties": false,
      "description": "标签 → 证据锚点（只含本次 ground 所用的 ALLOWED 证据）",
      "additionalProperties": {"引用元组子集": "evidence_id/chunk_id/document_id/source_name/version_id/effective_from/effective_to/authority_level/content_hash"}
    },
    "grounding_status": {
      "enum": ["grounded", "partial_grounding", "refused"],
      "description": "grounded=关键句全带引用且 cited⊆evidence；partial=证据仅覆盖部分论断（答案须明示未覆盖部分）；refused=未生成事实性回答"
    },
    "failure_reason": {
      "enum": [null, "kb_unavailable", "insufficient_evidence",
               "conflicting_evidence", "llm_unavailable",
               "catalog_missing_fact", "citation_gate_rejected",
               "invalid_input"],
      "description": "refused/partial 时的机器可读原因；grounded 时必须为 null"
    },
    "intent_ref":   "IntentResult 摘要（intent_id/confidence/created_at）",
    "retrieval":    "{query, domain, top_k, provider, governed_status, allowed_count, denied_count}",
    "generated_at": "ISO-8601",
    "generation":   "{provider, model, prompt_version, gateway: bool, usage}——经 ADR-011 网关时 request_id/correlation_id 一并记录"
  }
}
```

**设计裁决（本文件提出，实施前需所有者确认，见 §9 D3）**：AnswerContext
v1 是 **run 作用域 schema 校验记录**（审计/回归用），**不**新增为
contracts artifact_type——避免 eval.rules/risk-rules/contracts 白名单
三处联动与 Review Card "零检查即红" 的连锁（28.0.1 隐耦 #8）。chat 内
交付由既有 knowledge-evidence artifact（工具已存）背书；升格为正式
artifact 类型 + 卡面政策 = 试点数据后的独立裁决。

## 5. Grounding Rules（代码级，非 prompt 自律）

**最高规则（ADR-022）：无证据保险事实 = FAIL CLOSED。**

### 5.1 事实分类与来源约束

| 事实类 | 判定（规则驱动） | 唯一合法来源 | 缺失行为 |
|---|---|---|---|
| 产品事实（某产品保额/保费/**等待期**/**免责**/**健康告知**/资格/期限/版本） | 问题含特指产品引用（28.A 意图规则的 product_specific 标记/P0xx）或事实名词命中目录字段词表 | **Catalog 确定性查表**（版本钉死） | **"目录暂无该数据"**——禁止 WeKnora/LLM 补位（诚实缺失） |
| 保险知识（概念/区别/条款理解/监管规则） | 定义式/概念式措辞（definition_markers） | **WeKnora 治理证据**（仅 ACTIVE） | 拒答模板 + 可选澄清/转人工标记 |
| 推理/解释/表达 | — | LLM（**不产出事实**） | — |

### 5.2 引用闭环门（citation-closure gate，确定性代码）

生成后、交付前执行（**LLM 不自查**）：

1. **标签闭合**：解析 answer 中全部 `[Ex]` 引用 → `cited ⊆ evidence_map`
   （引用了不存在的证据 = 拒）。
2. **关键句覆盖**：确定性分句 + 规则驱动的事实句探测（事实名词词表
   外置于规则文件，沿 attribute-grounding 词表纪律）→ 每个事实句必须
   携带 ≥1 引用；无引用的事实句 = 拒。
3. **拒绝梯度**：一拒 → 携带门禁反馈的有界重生成（1 次）；二拒 →
   `citation_gate_rejected` 拒答（诚实失败优于无据答案）。
4. **目录转述完整性**：catalog 事实句的引用指向目录记录（版本钉死键），
   数值与目录逐字一致（确定性比对）。

### 5.3 禁止项（结构性）

- LLM 输出中的新事实（不在证据/目录中的数字、期限、条款表述）无法过
  5.2-2 门——**幻觉在交付面结构性不可达**（对齐 agent benchmark
  幻觉率 0.0 基线）。
- prompt 只承担表达风格指引；**规则、词表、门禁全部外置可回归**
  （AGENTS.md §5）。

## 6. Failure Modes（四类 + 补充，全部映射既有机制）

| # | 故障 | 检测点（既有信号） | failure_reason | 用户面行为（统一模板族） |
|---|---|---|---|---|
| F1 | **KB 不可用** | ProviderUnavailable/ProviderConfigError（KnowledgeService/transport fail-closed 族；启动 RV-P2-01 已 fail-fast） | `kb_unavailable` | 拒答："知识服务当前不可用，暂时无法给出有依据的回答"——**不降级、不猜、不静默换源**（K003 无回退） |
| F2 | **证据不足** | governed status=insufficient_evidence / ALLOWED=0（abstention 诚实传播） | `insufficient_evidence` | 拒答："知识库暂无可靠依据，无法确认……"；可选澄清问题或 `needs_human_escalation` 标记（Principle 6） |
| F3 | **证据冲突** | governed.conflict / attribute-grounding CONFLICT（等待期/免赔额/赔付比例检测已内建） | `conflicting_evidence` | **双方并陈**（各自带引用与时效）+ 冲突标记；**不平均、不择一** |
| F4 | **LLM 不可用** | 网关 LLMError 族（超时/熔断/限流/5xx——gateway.py 已规范化） | `llm_unavailable` | 拒答（v1）；"逐字呈现治理证据摘录+引用"降级形态列为 §9 D5 开放项（需 UX 裁决） |
| F5 | 时效风险 | 证据 effective window（R5） | 答案内标注 | EXPIRED/SUPERSEDED 已被治理拒绝；在窗证据答案携带时效标注 |
| F6 | 目录缺数据 | 事实型问题 + 目录查无 | `catalog_missing_fact` | "目录暂无该数据"（诚实缺失；目录 schema 决策+数据工程落地前为 Scenario D 常态） |

四类与 ADR-022 §3 逐条对齐；F4 为本阶段 spec 新增面，复用网关既有
错误族，无需新机制。

## 7. Interaction with Catalog（职责硬边界）

```
事实型问题（特指产品/目录字段词命中）
   → Catalog 确定性查表（版本钉死：product_id + product_version +
     catalog_version 三键，即 check_catalog_product 现返回的 slim 面）
   → 命中：LLM 只做格式化转述（数值逐字一致，5.2-4 门）
   → 未命中：FAIL CLOSED（"目录暂无该数据"）
   ⟂ 禁止：WeKnora 检索补位 / LLM 参数记忆补位 / 跨产品推断

知识型问题（概念/条款/监管）
   → WeKnora 治理证据（§3 契约）
   ⟂ 禁止：以目录记录回答概念问题（目录没有知识语义）
```

- **Catalog = 结构化产品事实**（确定性查表、版本钉死、无治理生命周期
  语义）；**WeKnora = 知识证据**（治理版本/时效/许可/哈希）——两套
  生命周期不混同（ADR-022 否决"目录入 WeKnora 统一检索"的理由保留）。
- **前置依赖（B3）**：目录 schema 决策（waiting_period/exclusions/
  health_declaration 进 schema，demo 可选/生产必填——沿
  catalog_governance.py:41-45 语义）+ 数据工程。决策前 Scenario D
  只能拒答（正确但无价值，运营并行）。

## 8. Testing Strategy

### 8.1 Unit（确定性，离线）

- 查询构造：问题→query+domain 映射的确定性回归（外置规则快照）。
- 事实/知识分流：§7 判定词表全分支（含边界：特指产品+定义式措辞）。
- 引用闭环门：cited⊆evidence / 事实句探测 / 一拒重生成 / 二拒拒答
  的完整梯度；幻觉句（无证据数字）必拒。
- 四故障分支：mock provider 抛 ProviderUnavailable → F1 模板；空 ALLOWED
  → F2；conflict=true → F3 并陈；网关 LLMError → F4（FakeProvider 注入）。
- AnswerContext builder：全分支输出 schema 校验通过（closed contract）。

### 8.2 Contract

- `qa-answer-context.schema.json` 闭合契约测试（沿 28.A-0 intent-result
  测试风格：非法字段拒收、枚举冻结、failure_reason×grounding_status
  组合约束——refused⇒failure_reason≠null、grounded⇒=null）。
- evidence_map ↔ KnowledgeService build_evidence 输出一致性（锚点字段
  逐一对齐）；knowledge-evidence 契约回归不动。

### 8.3 E2E 场景（mock provider 全链离线；live env 门控）

| 场景 | 期望 |
|---|---|
| Scenario A（"重疾险和百万医疗险区别"） | grounded 答案，行内引用，cited⊆evidence，AnswerContext 校验通过 |
| Scenario D（"P001 等待期多久"） | 目录缺数据 → `catalog_missing_fact` 诚实拒答（schema 决策后补正向命中用例） |
| Scenario F（KB 空转/无依据问题） | `insufficient_evidence` 拒答 + 可选澄清 |
| 冲突场景（构造双源分歧） | 双方并陈 + 冲突标记，无平均 |
| KB 宕机场景（transport 注入） | `kb_unavailable`，无静默换源 |

### 8.4 回归红线（每阶段通用门）

knowledge 离线 50+28 · business HG 门 · agent benchmark 幻觉率 **0.0**
不回归 · 全量 backend battery · live 套件 env 门控显式 SKIP。

---

## 9. Open decisions（实施前需所有者裁决）与实施序

| # | 决策 | 建议 |
|---|---|---|
| D1 | qa-answer 是否成 artifact 类型 / 产 Review Card | **v1 不升格**（§4 设计裁决：AnswerContext 为 run 记录；避免三处词汇联动+卡面全红）；试点数据后另裁 |
| D2 | QA 的 LLM 调用路径 | **经 ADR-011 网关**（runtime/llm/gateway.py 已实现——接线偿清 R6；否则按 ADR-022 在本 ADR 修订记录债） |
| D3 | AnswerContext 契约位置确认 | schema/ 根目录（沿 28.A-0），闭合 draft-07 |
| D4 | LLM 辅助查询改写 | v1 不做（确定性查询先行）；校准数据后再议 |
| D5 | LLM 不可用时的"证据摘录+引用"降级形态 | v1 拒答；降级形态需 UX 裁决后另案 |
| D6 | 目录 schema 字段增补（B3 第一步） | 新增字段可选、生产必填（沿 catalog_governance 语义）；数据工程并行 |

**实施序建议（28.C-1 起，均需另行授权）**：① schema/qa-answer-context
+ 契约测试 → ② 引用闭环门 + 事实/知识分流规则（外置词表）→ ③
AnswerContext 缝（KnowledgeService 新接口，证据进上下文）+ 工具描述
修正（A6 三件套）→ ④ LLM 网关接线（D2）→ ⑤ QA Agent 执行单元 +
insurance_qa/product_qa 意图权威化切片 → ⑥ e2e 五场景 + 全量回归。
每步过 phase-28-implementation-gates ADR-022 栏三段门。

**禁改承诺（本设计的边界）**：Provider Protocol · 治理层 R1-R9 ·
provenance · WeKnora transport · mock/live 选择语义 · orchestrator ·
Router 契约 · eval 唯一门语义 · approval 状态机——全部零触碰；
WeKnora 集成改动严格限于 AnswerContext 缝（ADR-022 冻结清单原文）。
