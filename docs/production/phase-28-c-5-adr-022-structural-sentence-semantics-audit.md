# Phase 28.C-5 · ADR-022 Structural Sentence Semantics Design Audit

Date: 2026-09-28 · DESIGN AUDIT ONLY（零生产改动·对抗样本经当前 gate
纯函数实测·非猜测）。

## Status

**DESIGN_READY**（gate 语义完整厘清·taxonomy 定案·逃逸风险实测·
三方案 trade-off·40-case 验证集定义）。

## 1. Current Gate Semantics（Q1·代码实证）

```text
gate.check（grounding/gate.py:82）
→ split_sentences（:60·sentence_separators 字符类切分·**不含 \n**）
→ is_fact_sentence（:76·"任一 fact_marker(38) 子串命中"=纯词法启发）
→ extract_citations（:69·\[E\d+\] 正则）→ evidence_map 成员校验
→ violations（4 类词表·≤10 条）→ generate_grounded 内 max_regen=1
  重生成 → 仍违例 → citation_gate_rejected 拒答（fail-closed）
```

**语义缺口定位**：`is_fact_sentence` 是"句子含领域词"判定——
①无 sentence-type/claim-type 概念；②纯词法非语义分类；③**切分符不含
\n → heading 与后续 claim 粘连为同一 gate 句**（实测
`'## 医疗险\n百万医疗险通常存在免赔额'` = 1 句）。
ADR-022 冻结的是**断言层契约**（"一切保险事实断言必须可溯源"）；
marker 句子级判定是实现细节——语义重定义不违反 ADR，但改判定语义
需 ADR-022 附裁决（详见 §7）。

## 2. Root Semantic Gap

Gate 把「承载事实的容器判定」（句子含领域词）当作「事实断言判定」
（存在可溯源命题）。C-4 实测 63% 违规来自结构容器；同时该粗判定
换取了**零逃逸**（§4 实测）。缺口=缺"命题存在性"层，而非 marker 词表。

## 3. Sentence Taxonomy（20 样本当前 gate 实测）

| 类 | 定义 | 当前 gate 实测 | 判定归属建议 |
|---|---|---|---|
| S0 纯结构 | heading/表头/纯标签 | **误报**（`## 一、免赔额`→violation） | 豁免候选 |
| S1 结构过渡 | 组织性句子 | 分裂：无 marker 过渡句 PASS；带 marker 过渡句（`接下来重点说明免赔额。`）**误报** | 豁免候选（模板化） |
| S2 实质事实 | 独立可溯源命题 | 正确 violation（未引）/正确 PASS（`[E1]`） | 维持强制引用 |
| S3 混合 | 结构+事实同句 | 整句 violation（保守·粘连使然） | **不豁免**——事实部分不得绕过（实测粘连即防线） |
| S4 建议/解读 | 条件性建议 | **误报**（`…可以重点关注免赔额和续保条件`） | 归属待裁决：保险解读按 ADR-022 精神应可溯源（建议句含产品机制断言时=引用）·纯通用建议可豁免——**边界模糊·DESIGN 上先保守维持引用要求** |
| S5 元叙述 | 过程/自述 | 多数 PASS（无 marker）；带 marker 元句误报 | 豁免候选（元模板） |

S3 最小策略答案：**不拆分、整句维持引用要求**（拆分引入命题边界的
LLM 依赖与逃逸面；粘连实测本身就是防线）。

## 4. Bypass Risk 实测（6+ 对抗样本·当前 gate 全部 fail-closed）

```text
## 医疗险\n<claim>      → violation ✓（粘连保护）
### 重要提示\n<claim>   → violation ✓
**免赔额：**<claim>      → violation ✓（S3 整句）
<前缀>，<claim>          → violation ✓
关于免赔额：\n<claim>    → violation ✓（粘连）
## 免赔额\n<反事实claim> → violation ✓
bullet/bold/表格包裹 claim → violation ✓✓✓
```

**核心结论：当前 gate 经由 marker 包含式判定获得零格式逃逸——任何
豁免方案都在重开此面。** 设计硬约束：豁免必须满足"剥离结构外壳后
剩余文本不含可独立成立的命题"或"豁免对象无法承载命题"。

## 5. Design Options（trade-off·不选型）

| 维度 | A·Markdown 结构豁免 | B·命题抽取判定 | C·混合（先结构剥离→再命题判定） |
|---|---|---|---|
| 实现复杂度 | 低（正则/行级） | 高（命题检测需 LLM 或新启发式） | 中 |
| false negative（漏拦） | **高**（S3/对抗粘连若误豁免即放走 claim） | 中（判定器漏检） | 低-中（结构剥离确定性+命题层兜底） |
| false positive（误拦） | 大降（消 63% 结构类） | 大降 | 大降 |
| 可测试性 | 强（确定性） | 弱（LLM 判定不可复现） | 强+弱混合 |
| fail-closed 兼容 | 需"纯结构才豁免"守则（剩余文本无命题） | 依赖判定器保守度 | 结构层确定+命题层需保守默认=引用 |
| LLM 依赖 | 无 | **有**（或重启发式） | 仅命题层 |
| 延迟 | ~0 | +1 LLM call 或规则成本 | ~0+规则 |
| 回归风险 | 中（豁免面控制） | 高 | 中 |

共同前置：**任何方案都必须先处理 \n 粘连**（heading 前缀剥离或把
纯结构行在切分层先行分离），否则 S3/对抗样本在豁免后立即逃逸。

## 6. Minimal Change Boundary（未来实施时）

**不改变**：fail-closed 拒答语义·evidence_map 契约·`[E#]` 格式·
retry 语义（max_regen=1）·QA/Planning 边界·WeKnora 检索契约·
Product Catalog·LLM 路由·生产模型·现行 prompt。
**ADR-022 附裁决项（最多）**：`is_fact_sentence` 语义从"marker 句子级"
升级为"结构剥离后的命题级"（一句裁决+引用本审计）；sentence_separators
与结构剥离规则进 gate rules（config 外置·非代码硬编码）。

## 7. Validation Plan（40 cases·未来实施配套）

- Positive 10（S2 未引事实）：期望 violation；当前=violation ✓；未来=violation
- Negative 10（S0/S1/S5 纯结构）：期望不触发；当前=误报（8-9/10）；未来=豁免
- Mixed 10（S3 结构+事实）：期望 violation；当前=violation；未来=**必须仍 violation**（验收红线）
- Adversarial 10（§4 格式伪装+表格/bold/bullet+反事实）：期望 fail-closed；当前=10/10 ✓；未来=**必须 10/10**（验收红线）
纯确定性可跑（无 LLM·gate 单元级）——未来实施 PR 必须附带该 40-case
全绿证明。

## 8. C-3 / C-5 Relationship

正交双线：C-3=知识覆盖（evidence 深度·A 型/V5·BLOCKED@JWT）；
C-5=引用语义（结构句判定·B 型/V2）。耦合点=C-4 实测 37% 散文违规
与 ev≤1 强相关——**C-3 完成不会消解 C-5 的 63% 结构类违规；C-5 豁免
也不会补出证据**。两线各自推进，收益叠加但在 40-case 与 probe 上
分别验收。

## 9. Evidence

§3/§4 表=本次对当前 gate 纯函数实测（脚本未留存·确定性可复现）；
C-4 197 句分布·C-4A 负向影子=前序实测；ADR-022 原文引用。
生产改动：**NONE**。
