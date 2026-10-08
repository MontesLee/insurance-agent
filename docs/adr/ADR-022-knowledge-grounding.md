# ADR-022 — Knowledge Grounding

## Status

**APPROVED (2026-09-25, Phase 28.0.5 owner ruling — 保持原文，无修改)**.
裁定：**Insurance fact grounding required**——product fact / coverage /
waiting period / exclusion / policy term 等一切保险事实必须来自 Catalog
或 WeKnora evidence；**缺失即 fail closed**。依赖 ADR-019/020/021
（均已 APPROVED）。

## Context

现状（代码实证）：知识底座已生产形态——KnowledgeService
（provider→governance→evidence，fail-closed K001-K004，
knowledge/service.py:223-391）、治理 R1-R9 + PG 注册表 + 三锚点哈希 +
仅 ACTIVE 可 ground（knowledge/governance/）、WeKnora live 纯检索
（weknora.py:175-431，"不使用LLM总结"，Ask/ReAct 结构性禁止）、
evidence/provenance 契约（contracts/knowledge-evidence.schema.json）。
**结构性缺陷**：chat 工具 `_knowledge_search` 只向 LLM 回报
"N items stored"+artifact_id（tools.py:402-404），证据从不进入上下文；
答案文本零代码门禁（agent.py:96-100 接受任意文本）；工具描述承诺
返回 chunk 而实现不返回（schemas.py:163-165）。产品事实侧：目录仅
12 demo 产品，waiting_period/exclusions/health_declaration 数据与
schema 双缺；check_catalog_product 只回 id/名称/公司（tools.py:420-422）。

## Problem

产品承诺"保险知识必须 grounding"，但今天（a）grounded answer 结构上
不可能（证据不进上下文）、（b）无证据输出的拦截只有 prompt 自律、
（c）知识（WeKnora）与产品事实（Catalog）职责无契约边界——Scenario
D（"等待期多久"）无任何代码路径可答。

## Decision

### 1. 保险知识边界（三方职责）

| 知识源 | 职责 | 形态 |
|---|---|---|
| **WeKnora** | regulations（监管法规）、concepts（保险概念）、clauses（条款文本）、cases（案例/FAQ） | 治理证据：KnowledgeService → R1-R9 → evidence+provenance；LLM 可引用 |
| **Catalog** | products（产品档案）、parameters（参数：coverage/premium/waiting period/eligibility/exclusions/health requirements/version） | 结构化事实：确定性查表、版本钉死；LLM 只做格式化表述，不做来源 |
| **LLM** | reasoning（综合多证据推理）、explanation（解释条款/概念）、communication（自然语言表达） | **不产出事实**：一切保险事实断言必须可溯源到证据或目录记录 |

**判定规则**：事实型问题（某产品参数/费率/期限/健康要求）→ Catalog
查表优先，查不到 **FAIL CLOSED**（明说"目录暂无该数据"），禁止
WeKnora/LLM 补位；知识型问题（概念/区别/条款如何理解）→ WeKnora
证据 grounding。

### 2. 代码级 grounding 门（不止 prompt）

- **AnswerContext 受控通道**：治理证据（chunk 正文+溯源戳）经
  KnowledgeService 新接口进入 LLM 上下文——QA Agent 唯一取证入口。
- **确定性引用闭环门**：答案行内引用 `[E1][E2]`↔evidence_id；代码
  校验 `cited ⊆ evidence` 且关键句带引用；任一失败 → 拒答/降级
  （fail-closed）。LLM 不自查。
- **无证据保险事实 = FAIL CLOSED**（本 ADR 的最高规则）。

### 3. 四类故障路径（全部映射既有机制）

retrieval failure → 拒答+明示不可用（Provider 错误族，无回退）；
insufficient evidence → 明示"知识库暂无可靠依据"+可选澄清/转人工
标记；conflicting evidence → 双方并陈+冲突标记（不平均不择一，冲突
检测已内建 等待期/免赔额/赔付比例）；stale knowledge → EXPIRED/
SUPERSEDED 版本不得 ground（R2/R2b），答案标注时效。

### 4. 附带修正（gate 隐耦 #2/#6）

- 同步修正 knowledge_search 工具描述与实现一致（消除"描述谎言"）。
- QA 的 LLM 调用经治理网关（ADR-011 接线，偿清绕行债）；若届时网关
  未就绪，显式记 debt 走现路径并在此 ADR 修订记录。
- qa-answer 是否成 artifact 类型/是否产 Review Card：**留待批准时
  裁决**（触发 eval.rules/risk-rules/contracts 联动与卡面"零检查即红"
  诚实规则；bootstrap 报告开放问题 #4）。

## Alternatives considered

- **A. prompt 自律强化（现状延续）**——否决：结构性不可 grounding
  （证据不进上下文），且 P0-② 漂移就是它造成的。
- **B. 仅事后 eval 门（答案先出、评估后罚）**——否决：用户已见过
  未 grounded 答案；门必须前置在生成时。
- **C. 目录入 WeKnora 统一检索（单知识源）**——否决：混同两套治理
  生命周期（证据治理 vs 产品事实版本钉死）；丢失确定性查表与
  catalog_governance 不变量；Scenario D 的"查不到=没有"语义会被
  检索噪声破坏。

## Consequences

- 正：grounding 从自律变代码门；QA Agent 可成立；目录边界清晰、
  数据工程有了明确 schema 目标。
- 负：上下文注入增加 token 成本与延迟；拒答率上升（诚实代价）；
  目录数据工程量大（waiting_period/exclusions/health 进 schema+
  数据，先决真实产品问答）。
- 合规：引用闭环门=确定性代码（ADR-004 同构）；不动 R1-R9/P001-P010。

## Implementation boundary

- 新增：AnswerContext 接口（knowledge/service.py 缝内）、引用闭环
  门、四故障路径答案形态。
- 修改：tools.py 工具描述；QA LLM 调用路径（网关接线或记 debt）。
- 冻结：Provider Protocol、治理层、provenance、WeKnora transport、
  mock/live 选择语义；目录 schema 字段增补是本案批准内容之一
  （demo 数据兼容：新增字段可选、生产模式必填——沿
  catalog_governance.py:41-45 既有语义）。
- 实施阶段：28.C。

## Migration strategy

mock provider 全链先行（可离线回归）→ live WeKnora env 门控灰度 →
目录 schema 决策先行、数据工程并行（不阻塞代码，阻塞真实产品问答
价值）。

## Validation criteria

- Unit：引用闭环 100%（cited⊆evidence、无引用关键句拒答）；四故障
  路径分支。
- Contract：AnswerContext 证据结构（含 provenance 戳）。
- E2E：Scenario A/D/F（grounded 答/事实 fail-closed/无证据拒答）。
- 既有：knowledge 离线 50+28、business HG 门、agent benchmark
  幻觉率 0.0 不回归；live 套件 env 门控。

## 附裁决 B — Evidence Qualification 语义（2026-09-29 · 28.K.27-RV4-C2 会话 Owner 授权 · 判定法=词项重叠）

**裁定 1（RetrievedEvidence ≠ QualifiedEvidence）**：治理资格
（R1-R9）裁定的是命中来源的可溯源性与时效（provenance），**不是**
该命中与当前 query 的主题相关性。检索命中须再过**相关性资格下限**
方可进入 [E#] 证据集与 evidence_refs。Phase 1 判定法 = 确定性词项
重叠：query ↔ 证据内容（含 source 文本）的 CJK bigram 去停用表
交集 ≥ `retrieval.qualification.min_query_bigram_overlap`；阈值外置
config/qa-grounding-rules.yaml（0 = 直通 = 回滚旋钮）。全部落选 →
复用**既有** insufficient_evidence 诚实拒答（零新拒答路径）。
过滤位置 = 溯源记录之后（retrieval.allowed_hits 保留治理语义）、
证据组装之前；重试/重生成收到的是同一已过滤集合（不可经重试
重扩张回原始检索）。

**裁定 2（Citation Presence ≠ Claim Support）**：引用门
（gate.py 的 marker 句 [E#] 存在性）≠ 支持性判定。claim-support
抽查 = Phase 2（影子先行）；Phase 1 不改门。

**裁定 3（user-fact 免外部引用）**：用户自述事实（如「配偶35岁」）
不属于 insurance fact，不要求外部 [E#] 引用；将用户自述强贴无关
E# = 缺陷（RV4-A 实例）。事实源分类（user_fact / insurance_fact /
product_fact / advice）= Phase 2。

**已知同类边界（记录不实施）**：product_qa 切片未解析产品路径
（match is None → items 直通 [E#]）为同类组装且无本过滤——该切片
DEFAULT OFF；其启用决策（28.C-5）须同步套用资格下限。
