# 28.K.28-II-DESIGN · Claim → Evidence Support 生产设计审计

Date: 2026-09-29 · Baseline: e306118（Intent SEALED·C1/C2 SEALED·
candidate OFF·authority unchanged）· Mode: **DESIGN AUDIT ONLY
（零生产代码修改）** · Status: **READY_FOR_OWNER_REVIEW**

## 1. Executive Summary

本设计回答一个问题：**一条 QualifiedEvidence 是否真的足以支持模型
生成的具体 Claim？** 现状（代码实证）：C2 在证据**准入**层关闭了
「无关证据进场」（RV4 农业条例已 seal）；但**答案层**的 grounding
门仍是 **citation-presence**（gate.py:82——marker 句内 [E#]∈
evidence_map 即过），RV4-A 的 15×[E1] stuffing 证明「引用存在≠
主张被支持」。Phase 2 = 在 C2 之后、Delivery 之前增加
**Claim↔Evidence Support 判定层**，fail-closed 方向，且最大程度
复用两个既有机制：K.26 句级 segmenter（held-if-fail 天然=逐句
support 评估边界）与 evidence item 的完整 provenance 链（document/
chunk/section/source_level/window 皆在库）。本报告给出 claim
taxonomy/原子性/support 语义/四策略比较/流式边界三方案/矛盾与时间
效度审计/金标语料与指标设计/最小生产 scope/回滚，并把 13 项不可由
现行 ADR 推出的决策列为 Owner Decision。**不选 winner、不写代码。**

## 2. Current Architecture Audit（真实仓库·file:line 在案）

```
Intent(SEALED e306118) → Router → QA slice
  → KnowledgeService.build_evidence（WeKnora vector_search）
  → 治理 R1-R9（registry/authority/R5 时间窗 as-of/jurisdiction/hash）
  → C2 资格（qa_agent/agent.py:_qualified_evidence·bigram≥2·
    retrieval.qualification 外置·0=直通回滚）
  → QualifiedEvidence → evidence_map{E#: anchor}
  → generate_grounded（K.26 句级 segmenter·逐段 gate.check·
    held-if-fail·残段终局 flush）→ 引用门（gate.py: presence）
  → regen×1 → 仍败=citation_gate_rejected 拒答
Planning 另路：tools.py:325 knowledge_search → canonical evidence
  ARTIFACT（无 generate_grounded/无引用门·RV4-B Q2 已证）
Product QA：resolution.py:100 pr.qualifies（产品 evidence_refs 链接
  或指名产品）+ catalog_record（目录确定性锚）·DEFAULT OFF
```

## 3. C2 Boundary（§2 九问·代码回答）

| 问 | 事实 |
|---|---|
| 1 Retrieved 如何产生 | WeKnora vector_search top_k→build_evidence |
| 2 Qualified 如何判定 | 查询↔内容+source 的 CJK bigram 去停用表交集≥`retrieval.qualification.min_query_bigram_overlap`(2) |
| 3 阈值位置 | config/qa-grounding-rules.yaml `retrieval.qualification`（Owner 可调·0=直通） |
| 4 provenance | AnswerContext.evidence_map{E#:anchor} + item 级 evidence_id/document_id/document_name/chunk_id/section/source_level/provenance[]/conflict（contracts/knowledge-evidence.schema.json） |
| 5 不合格处理 | 静默移出 E 集；retrieval.allowed_count 保留治理计数 |
| 6 all-rejected | 复用既有 insufficient_evidence 拒答（C2-LIVE 实证 attempts=0） |
| 7 product_qa bypass | 未解析产品路径 items→E# 无 C2（ADR-022 附裁决 B 已记录·切片 DEFAULT OFF·启用时须同步套用） |
| 8 Planning 共享 | **否**——工件路径独立（弱形态喂分析·RV4-B 定论） |
| 9 Catalog vs KB | product_qa：catalog_record=目录确定性锚 + pr.qualifies=KB 文档产品归属；QA 切片 E#=KB Qualified（目录不进 E 集） |

**边界保持**：C2=证据资格（不动）；Phase 2=主张支持（C2 之后新层）。

## 4. Claim Taxonomy（§3·对齐 ADR-022 附裁决 B 既有分类）

| 类型 | 定义 | Evidence 要求 | 对齐 |
|---|---|---|---|
| **C-FACT** | 可验证保险/产品/制度事实（等待期=X/保额=X/免责含X/适用年龄） | **必须** Qualified Evidence 支持 | insurance_fact/product_fact |
| **C-USER** | 用户自述（40岁/房贷100万） | **NOT_APPLICABLE**（免外部引用——附裁决 B 裁定3） | user_fact |
| **C-RECOMMENDATION** | 建议（建议补充医疗险） | 本身 N/A；**其事实前提**若为 C-FACT 仍须支持 | advice |
| **C-CALCULATION** | 确定性计算（保额缺口=收入×5−现有） | 输入可溯源（C-USER/既有 artifact）+公式确定性→N/A；**非确定性推导**→按 C-DERIVED | — |
| **C-DERIVED**（Planning） | 风险分析推导（单收入支柱→收入中断风险） | 推导链可审计（输入+规则），不绑 WeKnora | §12 |
| **C-UNCERTAIN** | 模型自认不确定（无法确认/需核实） | 不计为事实主张（不触发支持要求，但不得伪装成确定表述） | — |

## 5. Claim Atomicity（§4）

- **主原子=句**（`gate.split_sentences` 既有分隔符切分——与 K.26
  segmenter 同一函数族，零新切分语义）。
- **子句拆分**：仅当句内命中≥2 个**异构事实锚**（数字+事实 marker
  组合，如「等待期90天，重疾保额100万」）→ 按 deterministic
  并列标记（，/、/；/+「而且/并且/同时」）切 sub-claim；**不做
  语义拆分**（CJK 无词边界+同义陷阱=C-5A 实证教训）。
- 类型示例：「这款产品等待期90天」=1×C-FACT；「…而且适合你现在的
  家庭情况」=1×C-RECOMMENDATION（前提句独立评估）。
- Compound=多原子共引一句（允许，逐原子评估）。

## 6. Evidence Support Semantics（§5）

| 状态 | 定义 |
|---|---|
| SUPPORTED | Claim 的全部事实要素均有证据明确覆盖 |
| PARTIALLY_SUPPORTED | 证据覆盖部分要素（「等待期90天+所有重疾覆盖」而证据只有等待期→不得 SUPPORTED） |
| UNSUPPORTED | 有 Qualified Evidence 但不覆盖该主张（同主题≠支持） |
| NOT_APPLICABLE | C-USER/C-CALC(确定性)/C-RECOMMENDATION 本体/C-UNCERTAIN |

强度维度：**DIRECT**（数值/实体逐项对应）·**ENTAILMENT_LIKE**（
非字面但无新增事实要素——需语义层，shadow 先行）·**PARTIAL**·
**CONTRADICTORY**（见 §10）·**IRRELEVANT**。

## 7. Support Relationship 判定法比较（§6·证据驱动）

| 法 | 证据 | 结论 |
|---|---|---|
| A 确定性词法/结构化 | gate.fact_markers 存在性已实测（C-4：结构句 63% 误判面/纯泛词仅 3%）；C-5A shadow 40/40 零绕过但有损（bold 剥离丢 claim+封闭谓词漏「不影响」）；**数字/实体锚定未测**（等待期90天 vs 证据文本90日=已知缺口） | 可解释/稳定/可审计，但同义（天/日·重大疾病/重疾）与隐含语义盲 |
| B Embedding | **110/304 chunks 无嵌入**（28.H 债）+ 相似≠支持（无判别面） | 现不可作判据；仅检索侧已用 |
| C LLM Judge | K.28-I 候选实测 **8/18 稳定**·治理=仅 shadow 可行（§20）·prompt-injection/judge-hallucination 无防线实证 | 不得入 production authority |
| **D Hybrid（建议候选）** | 分层：①确定性表面（数字/实体/marker 锚定→DIRECT/PARTIAL/数值矛盾）→②候选支持关系的**语义校验仅 shadow**→③**确定性终门**（shadow 期=①独立生效） | 唯一同时满足可审计+渐进+fail-closed 的形态 |

## 8. Claim→Evidence 最小 Schema（§7·Runtime Gate 实需）

```json
{"claim_id","claim_text","claim_type","source_span":[s,e],
 "support_status","evidence_refs":["E#"],"support_type",
 "support_reason","provenance_ref":"artifact/answer-context"}
```
**不加** confidence 数值字段（确定性层无可信度语义；shadow 语义层
的证据记 obs 侧不进 gate 契约）——防过度设计。

## 9. Citation ≠ Support（§9·核心区分）

现行：`[E1]` 存在 + marker 句 → 过门。Phase 2：`Support(C,E)`
独立判定——引用是**模型的行为**，支持是**系统的判定**。RV4-A
15×[E1]（把用户自述+通用建议全部强贴 E1）= 该区分的原始案例。
回归锚：`citation-only attack`（§16 负例类）。

## 10. Unsupported Claim Policy（§10·四策略对现行架构兼容性）

| 策略 | 与现行兼容性 |
|---|---|
| A 整答拒绝 | =现行 citation_gate_rejected 终局；安全但过度（1 句坏→全拒） |
| B 删除未支持句 | **与 K.26 held-segment 机制同构**（held 段已实现不流出）——句级删除/扣留天然契合 |
| C 重写 | =现行 regen×1（violations 反馈）——已有，扩展反馈为 support violations |
| D 标记待核实 | 需要 Consumer 契约新文案类（「待核实」标记）——新 UI 语义 |

**兼容性结论（材料非决定）**：B+C 复合（句级扣留→regen 带支持
违规反馈→终局 A 拒绝）与现行三机制逐一同构，改动面最小；D 需
Consumer 契约裁决。

## 11. Streaming Compatibility（§11·K.26 审计）

现链：provider stream→segmenter（句级 gate.check→PASS 才 emit·
FAIL held→final 门裁决→PASS flush residual）。T_first<T_final 已
live 实证（K.26）。三边界方案：

| 方案 | 延迟 | 安全 | 证据完备 | 误收 | UX | 复杂度 |
|---|---|---|---|---|---|---|
| S1 句级 | +确定性判定（~ms 级·A 层） | 高（held 同构） | 句内完备（跨句主张少见） | 低-中 | 流式保持 | 中（挂在既有 segmenter） |
| S2 段落级 | +批判定 | 更高 | 更完备 | 更低 | 流式保持（块粗） | 中高（新缓冲边界） |
| S3 终答 | 0 增量 | 最高 | 全局 | 最低 | **破坏 T_first**（K.26 回退） | 低 |

**注意**：语义层（若未来引入）任何方案都只能 S3/离线（延迟不可控）
——故 A 层=S1 候选、语义层=shadow 的组合是唯一不伤 K.26 的路径。

## 12. Planning Compatibility（§12）

Planning 输出=风险分析/缺口/建议——不适用「每句绑 WeKnora」。分类：
C-USER（会话/工件输入）·C-DERIVED（deterministic 推导链·输入+
规则可审计即 N/A）·C-RECOMMENDATION（本体 N/A·事实前提须支持）·
C-FACT（若 Planning 陈述具体产品/制度事实——**仍须支持**，例如
「重疾险通常有90-180天等待期」）。Planning 证据路径=工件（非 E#）
——Phase 2 对 Planning = **标注+审计层**（claim 类型分布+escape
率观测），不新增 Planning 生产门（OD-9）。

## 13. Product QA Compatibility（§13·最严场景）

目录/KB→pr.qualifies/catalog_record→Qualified→Claim Support→
SUPPORTED。产品参数主张（等待期/保额/免责）=DIRECT 判定的主场景
（数字锚定）。**RV4 回归映射**：agri-reg 案例=C2 层已 seal（检索
准入）；其 15×[E1] stuffing=Phase 2 层案例（presence 绕过）——
金标语料必含。product_qa 未解析路径的 C2 缺口（附裁决 B 记录）
在 Phase 2 落地时一并套用（OD-10）。

## 14. Contradiction（§14）

既有机制：governed.conflict 标志 + `conflict_answer` 确定性
both-sides（loop.py:212）——**答案层已有冲突处理**。Claim 层新增
CONTRADICTED 强度：数字/实体直接冲突（90天 vs 180天）确定性可判。
优先级现状：governance authority（source_level/registry）+ R5
窗口已存在检索侧；**产品版本 vs KB 更新 vs 监管新旧**的裁决优先级
现行无规则→**不发明，列 OD-5**。

## 15. Temporal Validity（§15）

R5 effective window（as-of）已在**检索资格**层执行（governance.py
:98-101·effective_from/to）。Claim 支持层**复用同字段**：支持判定
时按 answer 时间复核命中 chunk 的窗口（同源字段·不造新 temporal
governance）。产品版本字段：catalog/evidence 有 version 字段
（fixture 实证）——跨版本冲突=OD-5 子项。

## 16. Golden Corpus 设计（§16）

**tests/golden/claim-support-corpus.v1.json**（冻结纪律沿 intent
语料先例·expected 由本设计 §4-6 规则推导）：
- Positive（~40）：DIRECT 数值/实体·多证据合成·Catalog+KB·
  user-fact 免引·确定性计算·建议前提链
- Negative（~60）：同主题不支持·部分支持（等待期例）·矛盾对·
  过期证据·错产品·错版本·**citation-only（15×[E1] stuffing
  形态）**·语义近邻陷阱（重疾/重疾险定义差）·结构句误判反例
  （C-4 教训）
- Regression（~20）：RV4 全链两案例·C2 正负例复用·K.26 held-segment
  边界·gate 现行 fact-marker 正负例（防 Phase 2 误伤现行门）

## 17. Metrics（§17·测量法先行·阈值 OD-12）

Claim Extraction 准确率（拆分 vs 人工标注）·Support Precision/
Recall（vs 金标）·**False Support Rate**（未支持判 SUPPORTED 比例
——最重）·Unsupported Claim Escape Rate（进入 delivery 比例）·
Contradiction Detection·Citation-Support Consistency（引用集与
支持集差）·Grounding Safety（现行门零回归）·Latency（A 层增量）
·Streaming First Delta（T_first 不回归）。

## 18. Business Safety Metric（§18）

**Unsupported Insurance Fact Escape Rate** = 最终 Consumer-visible
答案中实际 unsupported 的保险事实主张成功进入 delivery 的比例
（分子=人工/shadow 标注确认 unsupported 且已交付的 C-FACT；分母=
全部已交付 C-FACT）。shadow 期即开始测量（不设产线阈值）。

## 19. Production Scope（§21·从仓库审计推出）

- **必改（Phase 2 实施时）**：`runtime/grounding/`（新
  claim_support 模块：类型标注/原子切分/A 层判定）·rules 外置
  （qa-grounding-rules.yaml 新 claim_support 块或独立 yaml）·
  `schema/`（claim-support 契约·**additive 新文件**不动现行）·
  `tests/`（金标语料+单测）
- **可选（分阶段）**：loop.py segmenter 挂接（S1）·qa_answered
  AnswerContext 扩字段·product_qa 套用·Planning 观测层
- **禁改**：Intent/Router/C1/C2 资格逻辑/gate.py 现行 presence 语义
  （Phase 2 与其**串联**不替换）/WeKnora/Gateway/SSE/UI/schema 现行
  契约/ownership/auth

## 20. Rollback（§22）

`claim_support.enabled=false`（rules/env·沿 C2 threshold-0 先例）→
行为逐字节回现状（串联层旁路）。ON/OFF 均不动 Intent/Router/C1/C2/
ownership/Consumer auth。

## 21. LLM Shadow Policy（§20）

candidate 保持 OFF。若语义校验层立项：仅 `claim_support.shadow=on`
记录 disagreement（deterministic vs LLM 判定差异+稳定性+false-support
双向分析）——零 production authority；数据齐后 Owner 裁决（沿
28.A-1 shadow→authority 迁移先例）。

## 22. Owner Decisions（§24·13 项）

1. Claim taxonomy 终版（§4 六类）
2. 原子性规则（句主原子+确定性子句拆分·§5）
3. Support 状态集（4 态+强度维度·§6）
4. 判定法路线（A-only 先行 vs D-hybrid 立项·§7）
5. 矛盾裁决优先级（产品版本/KB/监管新旧·§14）
6. 时间效度复核点（检索已 R5·支持层是否复核·§15）
7. Unsupported 策略（B+C 复合建议 vs A/D·§10）
8. Streaming 边界（S1 建议材料·§11）
9. Planning 政策（观测层先行·§12）
10. Product QA 政策（含 C2 缺口同步套用·§13）
11. LLM shadow 是否允许开启（§21）
12. 验收阈值（§17-18 指标·shadow 数据后再定）
13. 上线策略（QA 切片先行→product_qa→Planning 观测）

## 23. Risks

- CJK 同义盲区（天/日）使 A 层 False Support 偏低但 Escape 偏高
  ——shadow 量化后再裁决层级
- 结构句误判反例（C-4 63%）若带进 claim 切分→复用 C-5A 剥离
  方案红线
- 确定性层过严→拒答率上升（G-1 语料缺叠加·Owner 预期管理）
- span 未封（40M+191??）上继续叠加——建议 Phase 2 前先续封
- 语义层永远不上的可能（A 层天花板=词法）——接受诚实边界

## 24. Recommended Next Phase

**K.28-II-SHADOW**（零生产 authority）：落地金标语料+A 层判定器
离线跑全量+（若 OD-11 允许）LLM shadow 对照→产出 False Support/
Escape 实测分布→Owner 据 OD-4/7/12 裁决后才进入 K.28-II-IMPL
（生产串联·S1 边界·B+C 策略）。

---

## Design Acceptance（§23 十八项核对）

①taxonomy✓ ②atomicity✓ ③support 语义✓ ④evidence 关系✓
⑤citation≠support✓ ⑥unsupported 策略✓ ⑦矛盾（规则列 OD）✓
⑧时间效度审计✓ ⑨流式边界✓ ⑩Planning✓ ⑪ProductQA✓ ⑫C2 边界
保持✓ ⑬LLM authority 不变✓ ⑭rollback✓ ⑮语料设计✓ ⑯metrics✓
⑰安全指标✓ ⑱最小 scope✓ → **K.28-II-DESIGN STATUS:
READY_FOR_OWNER_REVIEW**
