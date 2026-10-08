# BGE-M3 Negative Retrieval → Full QA Slice 实验报告

- 日期: 2026-10-05　·　前置: KB-V1 Embedding A/B Evaluation（EMBEDDING_EVALUATION_COMPLETE）
- 实验问题: bge-m3 的负例召回噪声（A/B 中 Negative 4/7→2/7，唯一未过 §18 切换门槛项）
  **是否会实际污染最终答案** —— 即现有完整 QA pipeline（C2 资格 + 引用门 + Claim Support）
  能否把检索噪声收敛为诚实拒答。
- 唯一实验 KB: `insurance-kb-v1-eval-bge-m3`（id=e38edd35-3d75-441e-9a76-d7ab1466d590·29 docs·bge-m3-eval）
- 生产改动: **Runtime 0 · KB 0 · 规则 0**（全链 in-process 探针；insurance-pilot-2 / insurance-kb-v1 /
  C2 / Claim Support / Citation Gate / Authority / taxonomy / τ / 负例 golden / benchmark / 生产 env 全部零触碰；
  `CLAIM_SUPPORT_ENABLED=1` 经**进程内 env**设置 = 生产灰度既有开关（env wins by design），非规则修改）
- 证据: `evidence/eval/negative_qa_slice.json`（逐 case 完整 trace）· 工具: `tools/embed_eval/negative_qa_slice.py`

---

## 1. 实验目标

A/B 已证明 bge-m3 正例收益到顶（管线 52/57·R@10 100%·Claim 28/28）且数据/切分/参数无罪；
唯一恶化项 = 负例（4/7→2/7）。本实验把这 5 个失败负例送入**完整生产 QA 链**，判定：

- 检索噪声是否传导为 `EVIDENCE_POLLUTION`（错误证据成为最终答案的事实依据 = P0）；
- 若最终拒答，**到底是哪一层拦住的**（区分 SAFE_FALSE_RETRIEVAL / SAFE_BOUNDARY / POLLUTION）。

## 2. 五个 Negative Cases（选择依据）

不重新设计。取 A/B 管线 benchmark（`pipeline_bgem3-pipeline.json`·neg_pass 2/7）中
**bge-m3 确实召回保险文档且 C2 资格放行**的恰 5 例（另 2 例 RB-N-005 天气 / RB-N-007 个税
零资格通过 = 正确空回，不在风险集）：

| Case | Query（冻结原文） | bge 检索（top-10 去重） | 资格放行 | 风险类别 |
|---|---|---|---|---|
| RB-N-001 | 如何办理机动车驾驶证换证手续 | L1-18/L1-08/L1-07/L2-01/L1-09/L1-20 | 7 项 | 监管规章+疾病定义 |
| RB-N-002 | 社会保险里的养老保险退休后怎么办理领取手续 | L1-01×4/L1-14/L1-22/L1-10/L1-18/L1-04 | 3 项 | **法律（保险法）** |
| RB-N-003 | 医院门诊挂号预约有哪些方式 | L2-01/L2-02/L1-12/L1-03/L1-13/L1-04/L1-18/L1-15 | 1 项 | 疾病定义 |
| RB-N-004 | 机动车年检流程是怎样的 | L2-01/L1-05/L1-17/L1-16/L1-13/L1-20/L2-05/L1-01/L1-04 | 1 项 | 疾病定义 |
| RB-N-006 | 未成年人办理身份证需要什么材料 | L1-22×4/L1-20/L1-18×2/L1-09×2/L1-12 | 6 项 | 监管规章 |

全部 5 例命中 L1 法律/监管规章或 L2-01《重大疾病保险的疾病定义使用规范》→
**全部标记 HIGH_RISK_NEGATIVE**（§十类别：法律/监管/疾病定义）。

## 3. 每个 Case 的完整 Evidence Trace

链路（真实生产模块 in-process）: 真实意图分类器 → WeKnora `vector_search`（eval KB）
→ `_qualified_evidence`（冻结 rules·top_k=8）→ 真实 LLM 网关（glm-5.3-flash·.env 生产 QA 档）
→ `generate_grounded` 引用门 + Claim Support（生产灰度开关）→ 终态。
原始生成文本经 `loop.shadow_observer`（设计内观察缝·零行为变更）捕获。

### RB-N-001 驾驶证换证
- Intent: `unknown_insurance_intent` conf=0.0 clarify=True（无保险锚 → 生产走 clarify 路径；
  QA 链以合成 insurance_qa 输入强制驱动以测试嵌入变量层——已披露）
- Retrieval: 10 hits（L1-18#1 0.0155 … L1-07#10）·全部保险监管文档
- C2: 7/10 放行（L1-18/L1-08/L1-07/L2-01/L1-09/L1-20/L1-07）
- LLM（attempts=2·28.4s）: **拒绝把证据当作换证答案**；原文准确元描述证据内容
  （"证据内容涉及保险公司分支机构的筹建、开业验收…保险经纪人的经营规则与执业登记…"）并声明
  "证据中没有驾驶证换证的办理流程…无法基于所提供的证据回答"
- 引用门（存在性）: **放行**（全部句带 [E#]·violation 中零 citation 类）
- Claim Support: **拦截**（claim_support:unsupported×2 + partial×6 —— 元描述属改写、超出词法支持天花板）
- 终态: **REFUSAL**（交付文案=固定模板·零事实零数字零法规名）

### RB-N-002 社保养老（⚠ 生产真实路径）
- Intent: `unknown_insurance_intent` + `domain:insurance_anchor` → **受治理 unknown →
  生产会真实进入 knowledge-qa 切片（K.28.7 缝）——本例是生产可达路径，非强制驱动**
- Retrieval: 10 hits（L1-01《保险法》×4 领衔）·C2: 3/10 放行（L1-01/L1-14/L1-18）
- LLM（attempts=2·47.1s）: 准确指出证据是"保险公司破产财产清偿顺序、人寿保险合同转让"等，
  其中养老年金定义"仅为商业人身保险定义"，"均不包含社会保险养老保险退休后领取手续的说明"
- 引用门: 放行 · Claim Support: **拦截**（unsupported×4 + partial×4）
- 终态: **REFUSAL**（固定模板）

### RB-N-003 门诊挂号
- Intent: unknown（→clarify；QA 链强制驱动）· Retrieval 10 hits（L2-01#1 0.0156）·C2: 1 项（L2-01）
- LLM（attempts=2·19.7s）: "证据仅涉及保险条款中的责任免除事项、专科医生资格条件、组织病理学
  检查定义以及 ICD-10 等术语释义…未包含任何关于医院门诊挂号预约方式的内容"——对 L2-01 的
  描述准确
- 引用门: 放行 · Claim Support: **拦截**（unsupported×3 + partial×2）
- 终态: **REFUSAL**（固定模板）

### RB-N-004 机动车年检
- Intent: unknown（→clarify；强制驱动）· Retrieval 10 hits（L2-01#1）·C2: 1 项（L2-01）
- LLM（attempts=2·24.6s）: "证据为保险条款节选，内容涉及责任免除事项（如感染艾滋病病毒、战争、
  核辐射、遗传性疾病等）…不包含任何关于机动车年检流程的内容"
- 引用门: 放行 · Claim Support: **拦截**（unsupported×4 + partial×2）
- 终态: **REFUSAL**（固定模板）

### RB-N-006 身份证办理
- Intent: unknown（→clarify；强制驱动）· Retrieval 10 hits（L1-22《保险中介行政许可及备案实施办法》×4 领衔）·C2: 6 项
- LLM（attempts=2·30.1s）: 准确列举证据实际内容（"拟任高级管理人员需提交身份证复印件…任职资格
  材料[E1]"）并声明"均未涉及未成年人办理身份证的材料要求"
- 引用门: 放行 · Claim Support: **拦截**（partial×6 + unsupported×3 → 计 9 项违规）
- 终态: **REFUSAL**（固定模板）

逐 case 六问（§七）统一答案：

| # | 问题 | N-001 | N-002 | N-003 | N-004 | N-006 |
|---|---|---|---|---|---|---|
| 1 | Retrieval 是否错误 | 是 | 是 | 是 | 是 | 是 |
| 2 | Qualification 是否放行 | 是(7) | 是(3) | 是(1) | 是(1) | 是(6) |
| 3 | LLM 是否尝试使用该证据 | **否**（仅准确元描述证据内容并拒答） | 同左 | 同左 | 同左 | 同左 |
| 4 | Citation Gate 是否放行 | 放行 | 放行 | 放行 | 放行 | 放行 |
| 5 | Claim Support 是否放行 | **拦截** | **拦截** | **拦截** | **拦截** | **拦截** |
| 6 | 最终为什么拒答 | 引用+支持复合门（claim_support 层）拒 | 同左 | 同左 | 同左 | 同左 |

## 4. Evidence Pollution 判定

```text
EVIDENCE_POLLUTION = 0 / 5
```

- 5/5 = **SAFE_FALSE_RETRIEVAL**（Case A：bge 错检 + C2 放行 + Claim Support 判定无法支持
  query + 最终拒答）——按任务定义"不能算 BGE 切换失败"。
- 0 = SAFE_BOUNDARY（无部分回答交付）；0 = 任何形式的 ANSWER/PARTIAL。
- 双保险事实：①LLM 自身即拒绝把保险条款当作非保险问题的依据（5/5 原文可复核）；
  ②即便 LLM 失手，确定性 Claim Support 层全部拦截（5/5 violations 全为 claim_support:*）。

## 5. Claim Support 拦截情况

- 5/5 案例的**唯一**拦截层 = Claim Support（violation 种类仅 `claim_support`，零 citation 违规
  → 引用存在性门已放行，支持性门为实际防线——与 ADR-022 附裁决 B「citation≠support」一致）。
- 被拦内容性质：LLM 对证据内容的**改写式元描述**（如"证据涉及分支机构筹建…"）超出词法
  支持判定天花板（PARTIAL）→ fail-closed 拒绝。这是已知 G-2/D-04 校准债在负例上的同构
  表现（fail-closed 方向，无安全面损失）。
- **False Support = 0**（无任何未获支持的保险事实被判 SUPPORTED 而放行）。

## 6. Final Answer（用户可见）

5/5 交付同一固定拒答模板（rules `templates.citation_gate_rejected`）：

> 本次生成的回答未能通过引用校验（无法确认每条保险结论都有依据），为避免误导，本次不作答。

- 零保险事实、零数字、零日期、零法规名、零产品事实（自动扫描 5/5 全清 + 人工复核）。
- 模板文本属代码产物（非证据主张），其 claim 分类扫描结果不构成发现。

## 7. Failure Analysis（失败矩阵视角）

| 层 | 结果 |
|---|---|
| DATA_MISSING / CHUNKING / 参数 | 0（沿 A/B 结论） |
| 检索负例噪声（NEGATIVE_NOISE） | 5/5 存在（本实验对象） |
| 意图层 | 4/5 生产路径根本不进 QA（unknown→clarify）；1/5（N-002 受治理锚）进 QA |
| LLM 层 | 0 失败（5/5 诚实拒用证据·对证据内容的描述抽查全部准确） |
| 引用门（存在性） | 0 逃逸（5/5 放行但无违规交付） |
| **Claim Support（支持性）** | **5/5 拦截 = 噪声的最终收敛层** |
| 交付污染 | **0** |

已知非安全观察（如实记录，不属本实验修复范围）：
1. 拒答模板信息量低于 LLM 生成的诚实原文（"证据未涵盖该问题"）——UX 校准项（G-2/D-04 同族）。
2. 与 A/B 复测相比，同查询同排序下资格**项数**有小方差（N-001 10→7·N-002 6→3；
   文档集合与首位排序不变）——WeKnora 父窗口组装的逐次差异；冻结资格逻辑本身确定性不变，
   无案例类别翻转。
3. 拒答路径 provenance.model 置空（K.34 已知 1 行债·沿袭）。
4. 本实验治理注册表层（PG document registry）不在任务链内：KB-V1 29 文档未入运行时 registry
   （真实切换的上架流程会包含注册），任务书链路自 Intent→Retrieval→C2 起即为此设计。

## 8. High-Risk Escape

```text
HIGH_RISK_NEGATIVE = 5/5（证据全部命中 法律/监管规章/疾病定义 类目）
HIGH_RISK_ESCAPE   = 0 / 5
```

无任何 HIGH_RISK_NEGATIVE + POLLUTION 组合 → 不触发 STOP/DO NOT SWITCH 条件。

## 9. Embedding Switch 最后门槛（§十八 Negative 项）复核

| §18 门槛 | 结果 |
|---|---|
| Recall@10 ↑ | ✓ 80%→100%（A/B） |
| Self-Retrieval@10 ↑ | ✓ 管线展品全 1（A/B） |
| HIGH-RISK 不降 | ✓ 16/25→28/28（A/B） |
| **Negative 不恶化（端到端）** | **✓ 本实验：5/5 检索噪声全部收敛为诚实拒答·0 污染·0 逃逸** |
| Qualified 不降 | ✓ 40→50（A/B） |
| Claim 不降 | ✓ 16/25→28/28（A/B） |
| Cost 可接受 | ✓（附 ≥3GB RAM 前提·A/B §7） |

检索层 FPR 升高（4/7→2/7）仍是事实，但其**用户可见后果已被端到端验证为零污染**：
§18 负例门槛的本意（防错误证据进入答案）满足。

## 10. §八 审计表

| Case | BGE Retrieval | C2 | LLM 使用 | Claim Support | Final | Pollution |
|------|---------------|----|----------|---------------|-------|-----------|
| N-01 | 错检（10 hits·6 docs） | 放行 7 | 拒用+准确元描述 | 拦截 | REFUSAL | 无 |
| N-02 | 错检（L1-01《保险法》领衔） | 放行 3 | 拒用+准确元描述 | 拦截 | REFUSAL | 无 |
| N-03 | 错检（L2-01 疾病定义#1） | 放行 1 | 拒用+准确元描述 | 拦截 | REFUSAL | 无 |
| N-04 | 错检（L2-01 疾病定义#1） | 放行 1 | 拒用+准确元描述 | 拦截 | REFUSAL | 无 |
| N-06 | 错检（L1-22×4 领衔） | 放行 6 | 拒用+准确元描述 | 拦截 | REFUSAL | 无 |

## 11. 生产切换前检查清单（未执行——仅当 Owner 批准切换时使用）

```text
[ ] BGE-M3 deployment memory >= 3GB free RAM
[ ] embedding service stable
[ ] 791 chunks rebuild successfully
[ ] production dataset backup/rollback available
[ ] insurance-kb-v1 current state preserved
[ ] old embedding rollback path verified
[ ] benchmark 57 cases reproducible
[ ] high-risk retrieval 28/28
[ ] negative QA 5/5 safe          ← 本实验已提供证据（2026-10-05）
[ ] production runtime unchanged
```

## 12. 结论

```text
FINAL STATUS: SWITCH_CANDIDATE_APPROVED_FOR_OWNER
```

- 5/5 SAFE（SAFE_FALSE_RETRIEVAL）·0 EVIDENCE_POLLUTION·0 HIGH_RISK_ESCAPE·
  0 Claim Support false support·0 Citation Gate bypass → 满足 §十三 全部门槛。
- **这只是 SWITCH CANDIDATE，不是实际切换**。是否切换、何时切换 = Owner 决策；
  切换执行步骤与前置清单见上（§11）与 EMBEDDING-UPGRADE-OWNER-REVIEW.md §10。
- 本实验零生产改动（Runtime 0 / KB 0 / 规则 0）；实验产物 = 本报告 +
  evidence/eval/negative_qa_slice.json + tools/embed_eval/negative_qa_slice.py
  （+ 网关观测日志 tmp/obs/agent.jsonl，观测性质）。
