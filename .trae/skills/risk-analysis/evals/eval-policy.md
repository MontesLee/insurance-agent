# Eval Policy — 风险分析 7 项机检

> 本文档定义 `risk-analysis` Skill 的 **独立 Eval**（Phase 6）检查口径。
> 引擎见 [`scripts/invoke-risk-analysis-eval.ps1`](../scripts/invoke-risk-analysis-eval.ps1)，词典见 [`resources/config/anti-sales.rules.json`](../resources/config/anti-sales.rules.json)。
> 所有检查均为**确定性机检**，不调用 LLM。

---

## 1. 总纪律

- 只有**可机检**断言才能判 `PASS`。
- `MANUAL`（自然语言断言）/ `NOT_EXECUTED`（未执行）**不计通过**。
- `eval_status = FAIL` → 进入 Repair（≤2 次）→ 复评；仍失败 → `NEEDS_REVIEW`，并输出"哪些无法可靠判断 / 需要人工确认什么"。
- 单项 `checkResult.status`：`PASS`（无 BLOCKING 问题）/ `FAIL`（存在 BLOCKING 问题）/ `MANUAL` / `NOT_EXECUTED`。
- 单项的 `score`：无 BLOCKING 时为 `1.0`，每条 WARNING 按 `0.05` 递减（下限 `0.0`）；存在 BLOCKING 时按问题数递减（下限 `0.0`）。
- `eval_status` 汇总：任一 check `FAIL` → `FAIL`；否则 `PASS`。

---

## 2. 七项检查

| # | 检查 | 失败 code | 性质 |
|---|---|---|---|
| 1 | `completeness` | `MISSING_RISK` / `INVALID_OUTPUT` | 结构完整性 |
| 2 | `evidence_grounding` | `UNSUPPORTED_CONCLUSION` | 证据可溯源 |
| 3 | `reasoning_consistency` | `LOGICAL_INCONSISTENCY` | 逻辑自洽 |
| 4 | `separation` | `PRODUCT_RECOMMENDATION_LEAK` | 风险 ≠ 产品需求 |
| 5 | `unknown_integrity` | `UNKNOWN_AS_KNOWN` | 不把未知当已知 |
| 6 | `priority_consistency` | `PRIORITY_INCONSISTENT` | 优先级与档位一致 |
| 7 | `anti_sales` | `SALES_BIAS` | 无恐吓/夸大/销售 bias |

---

## 3. 各检查确定性口径

### 3.1 completeness（#1）
输入：单个 `RiskAnalysisOutput`（可选附 Discovery 产物）。
- **应发现域覆盖**（CONTRACT §8 本义）：当提供 `-DiscoveryJsonPath` 时，取 Discovery 候选中
  `discovery_status ∈ {IDENTIFIED, NOT_IDENTIFIED}` 的风险域集合，逐个比对 `risks[]`；缺失记 `MISSING_RISK`(BLOCKING)。
  - `UNDETERMINED` 候选**不在**期望集合内（Phase 4 决策：不提升为 Risk 对象）。
  - **坑**：候选的 `status` 是 FactValue 溯源状态（`KNOWN`/`ESTIMATED`/…），三态结论在 **`discovery_status`**，读错字段会让该子检查静默失效。
  - 未提供 Discovery 产物时该子检查不执行（Note 中明示），只做下面的结构完整性校验。
- 每个 `risk` 必须含：`risk_category ∈ {R1..R5}`、`risk_exists`(bool)、`severity`/`likelihood`/`residual_risk`/`priority`(合法枚举)、`impact_estimate`(对象)。
- `risk_exists = true` 的 risk 必须有 `impact_estimate` 对象：缺失 → `MISSING_RISK`(BLOCKING)。
- `risk_exists = true` 且 `impact_estimate.amount ≤ 0` → `MISSING_RISK`(**WARNING**，非 BLOCKING)。
  理由：CONTRACT §7 允许"部分分析"——收入/负债等量化基础缺失时金额为 0 是诚实的中间态，
  应进 `next_information_needed` 而不是判死。
- `risk_matrix[]` 必须覆盖 `risks[]` 中每个 `risk_id`；缺失记 `MISSING_RISK`。
- 重复 `risk_id` 记 `INVALID_OUTPUT`(WARNING)。
- 若 `analysis_scope` 存在，risk 的 `risk_category` 必须 ⊆ scope；越界记 `INVALID_OUTPUT`(WARNING)。
- 任何 `risk_exists=true` 缺上述必填字段 → `MISSING_RISK`(BLOCKING)。

### 3.2 evidence_grounding（#2）
- 每个 risk 的 `reasoning_evidence_refs` 至少含 1 个能解析到 `evidence[].evidence_id` 的 `E###` 锚点；解析失败记 `UNSUPPORTED_CONCLUSION`(BLOCKING)。
- `REQ-###` 为跨阶段引用（需求层），本检查不强制解析，但不计入"已支撑"。
- 每个 risk 至少含 1 条 `evidence` 条目，否则 `UNSUPPORTED_CONCLUSION`(BLOCKING)。

### 3.3 reasoning_consistency（#3）
- **仅对 `risk_exists = true` 生效**：逐字复算 analysis 引擎公式
  `score = 0.6·severity_rank + 0.4·likelihood_rank`，再按 `residual_thresholds` 分档，
  与 `residual_risk` 不符 → `LOGICAL_INCONSISTENCY`(BLOCKING)。
  高 `likelihood` 可把 `residual` 抬到高于 `severity`（如 HIGH+HIGH→CRITICAL），这**合法**；
  旧版"residual 不得高于 severity"与"必须落在 [min,max] 区间"两版判定均已废弃。
- `risk_exists = false` 时**不做公式复算**：引擎按契约强制 `severity=LOW`/`residual_risk=LOW`/`priority=P3`
  （置低档），但 `likelihood` 保留域 base 值，公式在此不适用。此时只校验下面的 LOW/LOW/P3 约束。
- `risk_exists = false` 必须同时满足 `severity=LOW` `residual_risk=LOW` `priority=P3`（Phase 5 约定）；否则 `LOGICAL_INCONSISTENCY`(BLOCKING)。
- `risk_exists = true` 但无 `impact_estimate` → 已在 #1 覆盖。

### 3.4 separation（#4）
- risk 对象本体**不得**出现 `requirement` 字段（schema 已禁，仍做防御）。
- 扫描 risk 全部文本字段（reasoning / conclusion / trigger / exposure / existing_protection / potential_impact.*）:
  - 同时命中 `product_names` 与 `sales_verbs`（且 `product_leak_requires_verb=true`）→ `PRODUCT_RECOMMENDATION_LEAK`(BLOCKING)。
  - 即：仅出现产品名不判漏（中性提及允许）；出现"应配置/推荐购买+某险"才判。

### 3.5 unknown_integrity（#5）
- risk `status = KNOWN` 但其全部 `evidence[].source.status` 均 ∈ {`UNKNOWN`,`UNVERIFIED`}（无一 KNOWN/ESTIMATED/ASSUMED/INFERRED）→ `UNKNOWN_AS_KNOWN`(BLOCKING)。
- `impact_estimate.amount > 0` 但 risk 全部 evidence 均为 UNKNOWN/UNVERIFIED → `UNKNOWN_AS_KNOWN`(BLOCKING)（量化了却无依据）。
- `existing_resources` 中任一 FactValue 的 `status ∈ {ESTIMATED,ASSUMED,INFERRED}` 但 `note` 为空 → `UNKNOWN_AS_KNOWN`(WARNING)（schema 已要求 note，此处兜底告警）。
- **不查 `evidence` 的 note**：`EvidenceEntry` schema 无 `note` 字段（`additionalProperties:false`），`ESTIMATED` 事实的 `note` 在 `client_state` 源 FactValue，由上游 adapter / 契约校验负责；Eval 侧不重复判。

### 3.6 priority_consistency（#6）
- `priority ∈ {P0,P1}` 且 `residual_risk ∈ {LOW,MEDIUM}` → `PRIORITY_INCONSISTENT`(BLOCKING)（高优先级须有高剩余风险）。
- `priority = P0` 且 `residual_risk ≠ CRITICAL` → `PRIORITY_INCONSISTENT`(WARNING)（P0 理想为 CRITICAL）。
- `priority = P3` 且 `residual_risk = CRITICAL` → `PRIORITY_INCONSISTENT`(WARNING)（封顶与残险矛盾，需人工确认是否 override 合理）。

### 3.7 anti_sales（#7）
- 扫描全部 risk 文本字段：命中 `panic_tokens` 中任一 → `SALES_BIAS`(BLOCKING)（恐吓/制造焦虑）。
- 命中 `exaggeration_tokens` 中任一 → `SALES_BIAS`(WARNING)（夸大绝对化）。
- 产品泄露由 #4 负责，#7 不重复判（避免双计）。
- 任一条 `SALES_BIAS`(BLOCKING) → `anti_sales` FAIL，并诚实回填 `guardrails.sales_language_detected = true`。

---

## 4. Anti-Sales 词典（外置）

见 [`resources/config/anti-sales.rules.json`](../resources/config/anti-sales.rules.json)。四类词条：

- `panic_tokens` — 恐吓/焦虑话术（BLOCKING）
- `exaggeration_tokens` — 绝对化/夸大表述（WARNING）
- `sales_verbs` — 推荐/购买类动词（与 `product_names` 共现才判漏）
- `product_names` — 保险产品名（中性提及不判，配合 `sales_verbs` 才判 `PRODUCT_RECOMMENDATION_LEAK`）

规则开关：`panic_is_blocking` / `exaggeration_is_warning` / `product_leak_requires_verb` / `case_insensitive_match`。

---

## 5. 用例分类（见 `evals/cases/manifest.json`）

- **正向**：端到端 `discovery → analysis` 真实产物（`evals/fixtures/unit/analysis/*`），期望 `eval_status = PASS`（7 项全 PASS）。
- **负向（对抗）**：由真实 dual-income 分析产物（`tmp/smoke_ana.json`）经
  `tmp/gen_negative_fixtures.py` 单点变异生成（`evals/fixtures/unit/eval/*`），分别触发：
  - `eval-neg-sales.json` → `anti_sales` FAIL（conclusion 追加 panic token）
  - `eval-neg-product-leak.json` → `separation` FAIL（产品名 + 销售动词）
  - `eval-neg-unknown-as-known.json` → `unknown_integrity` FAIL（status=KNOWN 但全 evidence UNKNOWN）
  - `eval-neg-priority.json` → `priority_consistency` FAIL（LOW/LOW/LOW 却标 P1）
  - `eval-neg-missing-risk.json` → `completeness` FAIL（risk_exists=true 但删掉 `impact_estimate` 对象）
  - `eval-neg-unsupported.json` → `evidence_grounding` FAIL（`reasoning_evidence_refs` 指向 E999 悬空）
  - `eval-neg-missing-domain.json` → `completeness` FAIL（删掉 R4 整个风险对象；
    需配套 side-car `eval-neg-missing-domain.discovery.json` 才能启用"应发现域覆盖"子检查）

**反向断言**：每个负例除断言目标检查 FAIL 外，还断言其余 6 项必须 PASS——
证明变异只打中一处，避免"一个坏 fixture 触发一片检查"的假通过。

**坑**：`amount ≤ 0` 是 WARNING 不是 BLOCKING，不能用来做 completeness 负例
（CONTRACT §7 允许部分分析，金额 0 是诚实中间态）。要触发 BLOCKING 必须删整个 `impact_estimate` 对象。

---

## 6. 与上游 / 下游边界

- Eval **只读** `RiskAnalysisOutput`，不修改上游。
- Eval 失败 → Repair Loop（Phase 7）处理，本 Phase 只判不修。
- `guardrails` 由 analysis 引擎写入常量；Eval 独立复核并可诚实翻转 `sales_language_detected` / `product_recommendation_included`。
