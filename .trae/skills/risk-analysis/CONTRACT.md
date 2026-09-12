# Risk Analysis — Contract (V0.1)

> 本文件是 Skill 3 `risk-analysis` 的**唯一契约真源**。
> 上游（`client-intake` / `requirement-analysis`）**不可修改**；所有不兼容在此层用 adapter 解决。
> 命名、分层、status 语义遵循仓库根 [`AGENTS.md`](../../../AGENTS.md)。

---

## 1. 定位与边界

**核心问题**：这个家庭真正暴露在哪些风险上？风险有多大？哪些值得优先处理？

| 项 | 内容 |
|---|---|
| 层 | `risk_analysis` |
| 上游 | `requirement_analysis`（需求层）、`client-intake`（事实层，经 ClientState 间接消费） |
| 下游 | `coverage-gap-analysis`（消费 `residual_risk`） |
| 产物 | `Risks`（含 severity / likelihood / residual_risk / priority） |

**明确不做**：

- ❌ 不推荐任何保险产品、险种、保额数字作为"购买建议"
- ❌ 不重新产出 `requirement`（那是 `requirement-analysis` 的活）
- ❌ 不修改上游任何文件 / Schema / 行为
- ❌ 不使用恐吓式语言、不夸大风险、不为制造需求而抬高等级

**允许**：

- ✅ "建议进一步解决该风险"
- ✅ "建议评估收入替代能力"
- ✅ "建议量化家庭长期责任金额"

---

## 2. 数据流（Canonical Client State 架构）

```text
        client-intake  (CLIENT_PROFILE.md)
              │
              │  client-state adapter（本 Skill 自建，不改上游）
              ▼
      ┌───────────────────┐
      │ Canonical Client  │   ← 唯一事实源
      │      State        │
      └─────────┬─────────┘
                │
    ┌───────────┴────────────┐
    ▼                        ▼
requirement-analysis      risk-analysis
 (已有，不改)              (本 Skill)
    │                        ▲
    ▼                        │
Requirements ────────────────┘
```

**关键点**：

1. `risk-analysis` **不自由双读两份上游 output**。它只消费：
   - `ClientState`（事实，源自 client-intake，经规范化）
   - `RequirementAnalysisOutput.requirements`（需求层结论）
2. 事实溯源统一指向 `client_state.<profile>.<field>`，`source.origin.skill` 回溯到 `client-intake`
3. 若同一字段在两处出现且数值不一致 → 判 `CONFLICT`，**保留 UNKNOWN 并列出候选值**，不自行择一

---

## 3. 契约清单

| Schema | 文件 | 用途 |
|---|---|---|
| `ClientState` | [`schemas/client-state.schema.json`](schemas/client-state.schema.json) | 规范化事实层（canonical） |
| `RiskAnalysisInput` | [`schemas/risk-analysis-input.schema.json`](schemas/risk-analysis-input.schema.json) | 引擎输入 = ClientState + Requirements |
| `Risk` | [`schemas/risk.schema.json`](schemas/risk.schema.json) | 单个风险对象（供单测 / Eval 独立引用） |
| `RiskAnalysisOutput` | [`schemas/risk-analysis-output.schema.json`](schemas/risk-analysis-output.schema.json) | 引擎输出（机器可读唯一真源） |
| `EvalResult` | [`schemas/eval-result.schema.json`](schemas/eval-result.schema.json) | 独立 Eval 结果 |

---

## 4. ClientState

```jsonc
{
  "client_state_version": "1.0",
  "source": {
    "origin_skill": "client-intake",       // const
    "origin_artifact": "CLIENT_PROFILE.md",
    "profile_path": "<abs path>",
    "adapter": "risk-analysis/scripts/build-client-state.ps1",
    "adapter_version": "1.0",
    "intake_complete": true
  },
  "family_profile":        { "<field>": FactValue, "...": "…" },
  "financial_profile":     { "<field>": FactValue },
  "responsibility_profile":{ "<field>": FactValue },
  "existing_protection":   { "<field>": FactValue },
  "health_profile":        { "<field>": FactValue },
  "employment_profile":    { "<field>": FactValue },
  "missing_from_upstream": [ { "field": "…", "profile": "…", "reason": "…" } ],
  "conflicts":             [ { "field": "…", "candidate_values": ["…"], "reason": "…" } ]
}
```

### FactValue（每个字段必带四元组）

```jsonc
{
  "value": 1500000,                 // UNKNOWN 时为 null
  "status": "KNOWN",                // KNOWN|UNKNOWN|ESTIMATED|ASSUMED|INFERRED
  "source": {
    "layer": "client_state",
    "origin": { "skill": "client-intake", "field": "mortgage_balance" }
  },
  "confidence": 0.9,                // 0.0–1.0
  "note": "可选；ESTIMATED/ASSUMED/INFERRED 必填（说明依据）"
}
```

**硬规则**：`ESTIMATED` / `ASSUMED` / `INFERRED` 的 `note` **必填**，否则 Eval 判 `UNKNOWN_INTEGRITY` FAIL。

### 字段词表（沿用 requirement-analysis 规范词汇，保证跨 Skill 一致）

| profile | 字段 |
|---|---|
| `family_profile` | `age`、`gender`、`city`、`marital_status`、`spouse_employment`、`spouse_income`、`children_count`、`children_info`、`dependents` |
| `financial_profile` | `household_income`、`annual_income`、`household_expense`、`assets`、`cash_flow`、`premium_budget` |
| `responsibility_profile` | `mortgage_balance`、`liabilities`、`children_education`、`elderly_support`、`family_responsibility` |
| `existing_protection` | `social_insurance_status`、`existing_life_coverage`、`existing_critical_illness_coverage`、`existing_medical_coverage`、`existing_accident_coverage`、`employer_benefits` |
| `health_profile` | `customer_health`、`health_history` |
| `employment_profile` | `occupation`、`employment_type`、`income_stability` |

> 未在词表中的上游字段：原样保留到最接近的 profile（防止信息丢失），并在 `note` 标注 `unmapped_original_field=<原名>`。

---

## 5. RiskAnalysisInput

```jsonc
{
  "input_version": "1.0",
  "client_state":  { …ClientState… },
  "requirements":  [ { "requirement_id": "REQ-001", "requirement_type": "life",
                       "summary": "…", "priority": "P1_HIGH", "boundary": "requirement_only" } ],
  "upstream": {
    "client_intake":         { "provided": true, "intake_complete": true, "profile_path": "…" },
    "requirement_analysis":  { "provided": true, "analysis_status": "PRELIMINARY",
                               "analysis_scope": ["life","critical_illness","accident"],
                               "output_path": "…",
                               "unknowns":     [ { "field": "…", "reason": "…" } ],
                               "assumptions":  [ { "field": "…", "assumption": "…", "reason": "…" } ] }
  },
  "analysis_scope": ["R1","R2","R3","R4","R5"],
  "provenance_index": [
    { "client_state_field": "financial_profile.annual_income",
      "origin_skill": "client-intake", "origin_field": "annual_income", "status": "KNOWN" }
  ]
}
```

**降级规则**：

- `upstream.requirement_analysis.provided = false` → `requirements = []`，并在输出 `missing_from_upstream[]` 记录 `MISSING_FROM_UPSTREAM: requirement_analysis`
- `upstream.client_intake.provided = false` → 整个 ClientState 全字段 `UNKNOWN`，`analysis_status` 强制 `NEED_MORE_INFORMATION`
- `provenance_index` 是 ClientState `source` 的扁平索引，供 Eval 2（Evidence Grounding）O(1) 校验

---

## 6. Risk（单个风险对象）

结构严格对齐需求文档 §8，并补上可机检字段：

```jsonc
{
  "risk_id": "R2-001",
  "risk_category": "R2",                 // R1..R5
  "risk_name": "Critical Illness Risk",

  "status": "KNOWN",                     // KNOWN|UNKNOWN|ESTIMATED|ASSUMED|INFERRED

  "trigger": { "event": "家庭主要收入者确诊重大疾病并长期无法工作" },
  "exposure": { "why_exposed": "家庭收入高度依赖夫妻双方工资，且存在持续刚性支出" },

  "potential_impact": {
    "financial": "…", "lifestyle": "…", "family_responsibility": "…"
  },
  "impact_estimate": {
    "amount": 1500000,
    "range": { "low": 1000000, "high": 2200000 },
    "confidence": 0.6                    // 0.0–1.0
  },

  "existing_resources": {                // 每一项都是 FactValue 或 null
    "cash": null, "investments": null, "income": {…},
    "employer_benefits": {…}, "social_security": {…},
    "existing_insurance": {…}, "family_support": null
  },
  "existing_protection": "…",

  "coverage_assessment": {
    "protected_amount":   500000,
    "unprotected_amount": 1000000,
    "confidence": 0.5
  },

  "residual_risk": "HIGH",               // LOW|MEDIUM|HIGH|CRITICAL|UNKNOWN
  "severity":   "HIGH",                  // LOW|MEDIUM|HIGH|CRITICAL
  "likelihood": "MEDIUM",                // LOW|MEDIUM|HIGH|UNKNOWN
  "priority":   "P1",                    // P0|P1|P2|P3

  "reasoning": "…",                      // Evidence → Reasoning 链
  "conclusion": "…",                     // 结论，不得超出 evidence 支撑范围
  "reasoning_evidence_refs": ["E001","E002","REQ-001"],   // ≥1，可机检

  "evidence":  [ { …EvidenceEntry… } ],
  "assumptions": [ { "field": "…", "assumption": "…", "reason": "…" } ],
  "unknowns":    [ { "field": "…", "reason": "…" } ],
  "next_information_needed": [ { "field": "…", "question": "…", "why_needed": "…" } ]
}
```

### EvidenceEntry

```jsonc
{
  "evidence_id": "E001",
  "fact": "家庭年收入约 120 万",
  "source": {
    "layer": "client_state",             // client_state | requirement_analysis | unknown
    "field": "financial_profile.household_income",
    "origin": { "skill": "client-intake", "field": "household_income" },
    "status": "ESTIMATED"
  }
}
```

不可溯源时**必须**：

```jsonc
{ "layer": "unknown", "field": "unknown", "origin": { "skill": "unknown", "field": "unknown" }, "status": "UNVERIFIED" }
```

**禁止**把不可溯源的证据伪装成 `KNOWN`。

### Risk / Requirement 分离（Eval 4）

`risk_id` 使用 `R<域>-<序号>`；`reasoning_evidence_refs` 允许同时引用 `E###`（事实）与 `REQ-###`（需求），
但 **Risk 对象自身不得新增 `requirement` 字段**，也不得出现"应购买 / 应配置 + 险种名"的措辞。

---

## 7. RiskAnalysisOutput

```jsonc
{
  "output_version": "1.0",
  "layer": "risk_analysis",              // const
  "upstream": "requirement_analysis",    // const
  "analysis_status": "PRELIMINARY",      // FORMAL|PRELIMINARY|NEED_MORE_INFORMATION|CONFLICTING_INFORMATION|NEEDS_REVIEW|FAILED
  "overall_confidence": 0.72,

  "sufficiency": {
    "sufficiency_status": "PARTIAL",     // SUFFICIENT|PARTIAL|INSUFFICIENT|CONFLICTING
    "method": "risk_dependency_graph_v1",
    "domain_results": [ { "risk_category": "R2", "score": 0.75, "status": "SUFFICIENT",
                          "blocking_fields": ["…"], "conflict_fields": ["…"] } ],
    "blocking_fields": ["…"],
    "conflict_fields": ["…"]
  },

  "family_risk_overview": "…",
  "risks":        [ { …Risk… } ],
  "risk_matrix":  [ { "risk_id": "R2-001", "risk_category": "R2",
                      "severity": "HIGH", "likelihood": "MEDIUM",
                      "residual_risk": "HIGH", "priority": "P1" } ],
  "top_priorities": [ { "risk_id": "R2-001", "priority": "P1", "reason": "…" } ],

  "unknowns":    [ { "field": "…", "reason": "…" } ],
  "assumptions": [ { "field": "…", "assumption": "…", "reason": "…" } ],

  "next_information_needed": [
    { "question_id": "Q001", "question": "…", "why_needed": "…",
      "affects_risks": ["R3","R4"], "priority": "HIGH",
      "expected_information_value": 0.82 }
  ],

  "missing_from_upstream": [ { "source": "requirement_analysis", "field": "…", "reason": "…" } ],

  "guardrails": {
    "product_recommendation_included": false,   // const
    "sales_language_detected": false,           // const
    "layer_note": "本分析只到风险层，不涉及任何保险产品推荐。"
  },

  "eval": { …EvalResult… }
}
```

**状态判定**（确定性，非 LLM 判断）：

| 条件 | `analysis_status` |
|---|---|
| 全部 5 个域 `SUFFICIENT` 且无 conflict | `FORMAL` |
| 至少一个域 `PARTIAL`，无域 `INSUFFICIENT` | `PRELIMINARY` |
| 任一域 `INSUFFICIENT` | `NEED_MORE_INFORMATION` |
| 存在未解决 conflict | `CONFLICTING_INFORMATION` |
| Eval 连续 2 次修复仍 FAIL | `NEEDS_REVIEW` |
| 引擎异常 | `FAILED` |

### 允许"部分分析"

缺失一个字段**不得**停止整个 Skill。例：缺资产 → 医疗 / 重疾 / 死亡责任风险仍照常分析，
只把这些风险的 `impact_estimate.confidence` 与 `coverage_assessment.confidence` 下调，并把资产列入 `next_information_needed`。

### 风险存在 ≠ 现在处理

```jsonc
{ "risk_exists": true, "materiality": "MEDIUM", "residual_risk": "LOW", "priority": "P3" }
```

是**合法结果**。优先级不得由风险名称决定（"医疗风险"不天然是 P0）。

---

## 8. EvalResult

7 项检查（6 + Anti-Sales），全部机检：

| # | 检查 | 失败 code |
|---|---|---|
| 1 | `completeness` — 是否遗漏应发现的风险域 | `MISSING_RISK` |
| 2 | `evidence_grounding` — 每个结论是否有可溯源 evidence | `UNSUPPORTED_CONCLUSION` |
| 3 | `reasoning_consistency` — Evidence→Reasoning→Conclusion 是否自洽 | `LOGICAL_INCONSISTENCY` |
| 4 | `separation` — 是否把风险直接变成保险产品需求 | `PRODUCT_RECOMMENDATION_LEAK` |
| 5 | `unknown_integrity` — 是否把 UNKNOWN 当 KNOWN 用 | `UNKNOWN_AS_KNOWN` |
| 6 | `priority_consistency` — P0/P1 是否真有足够 severity/likelihood/residual/时间敏感性 | `PRIORITY_INCONSISTENT` |
| 7 | `anti_sales` — 恐吓语言 / 夸大 / 为卖而抬级 / 产品名入结论 | `SALES_BIAS` |

```jsonc
{
  "eval_status": "PASS",                // PASS|FAIL|NEEDS_REVIEW
  "checks": {
    "completeness":          { "status": "PASS", "score": 1.0, "issues": [] },
    "evidence_grounding":    { "status": "PASS", "score": 1.0, "issues": [] },
    "reasoning_consistency": { "status": "PASS", "score": 1.0, "issues": [] },
    "separation":            { "status": "PASS", "score": 1.0, "issues": [] },
    "unknown_integrity":     { "status": "PASS", "score": 1.0, "issues": [] },
    "priority_consistency":  { "status": "PASS", "score": 1.0, "issues": [] },
    "anti_sales":            { "status": "PASS", "score": 1.0, "issues": [] }
  },
  "failures": [],
  "repair_required": false,
  "repair_attempts": 0,
  "max_repair_attempts": 2
}
```

Issue 结构：`{ "code": "…", "severity": "BLOCKING|WARNING", "risk_id": null, "message": "…", "evidence": "…" }`

**纪律**（沿用既有 Skill）：

- 只有可机检断言判 PASS；自然语言断言记 `MANUAL`，**不计通过**
- 未执行的检查记 `NOT_EXECUTED`，**不计通过**
- `eval_status = FAIL` → Repair → 重跑，最多 2 次 → 仍失败则 `NEEDS_REVIEW` 并输出"哪些无法可靠判断 + 需要人工确认什么"

---

## 9. Adapter Contract

```
输入 A：client-intake  CLIENT_PROFILE.md  ──► build-client-state.ps1 ──► ClientState
输入 B：requirement-analysis output JSON  ──► extract requirements/unknowns/assumptions
                                    │
                                    ▼
                            RiskAnalysisInput
```

| 规则 | 说明 |
|---|---|
| 只读上游 | adapter 对上游文件**只读**，绝不写回 |
| 未知字段 | 不丢弃，保留到最接近的 profile + `note: unmapped_original_field=<原名>` |
| 缺失字段 | 按词表补 `UNKNOWN` 槽位，并记 `missing_from_upstream[]` |
| 冲突字段 | 判定 `CONFLICT`，`status=UNKNOWN`，候选值进 `conflicts[]`，**不自行择一** |
| ❓ 记号 | client-intake 的 `❓` / 空值 → `UNKNOWN` |
| 模糊词 | "约 / 大概 / 左右 / 估计" → `ESTIMATED`（必带 `note`） |
| 派生字段 | `family_responsibility`、`liabilities` 等由引擎派生 → `status=INFERRED` + `note` 写明推导依据 |
| 版本 | `adapter_version` 写入 ClientState，便于回归比对 |

---

## 10. 风险分类 R1–R5（V1.0）

放 `references/risk-taxonomy.md`，**不使用 overlay**。
分类是**风险域**，不是产品分类：医疗风险 ≠ 百万医疗险，重疾风险 ≠ 重疾险，死亡风险 ≠ 定寿。

| ID | 名称 | 说明 |
|---|---|---|
| R1 | Medical Risk | 疾病/受伤导致的医疗支出风险 |
| R2 | Critical Illness Risk | 重大疾病导致的收入中断 + 康复支出风险 |
| R3 | Accident / Disability Risk | 意外伤残 / 失能导致的长期收入能力损失 |
| R4 | Death / Family Responsibility Risk | 家庭主要收入者身故导致的长期责任无法履行 |
| R5 | Long-term Financial / Savings Risk | 养老 / 教育 / 长期财务目标无法达成的风险 |

扩展点：taxonomy 带 `version`，未来新增 R6/R7/R8 走版本号升级 + regression 检查影响面，**不提前建 overlay**。

---

## 11. 已决 / 未决

### 已决

| 议题 | 结论 | Phase |
|---|---|---|
| 各风险域依赖图最小字段集 | `resources/config/risk-sufficiency.rules.json` | 3 |
| EIV 计算规则 | `raw = tier × blocking × spread × status_factor + conflict_bonus`，`÷4.0` 归一 | 3 |
| R1–R5 分类落点 | `references/03-risk-taxonomy.md`（非 overlay，带 `taxonomy_version`） | 4 |
| 风险是否成立的判定 | 三态 `IDENTIFIED / NOT_IDENTIFIED / UNDETERMINED`，禁止二值化 | 4 |
| `UNDETERMINED` 候选的归宿 | **不提升为最终 `Risk` 对象**（无事实可引，补证据即伪造）；进 `unknowns` + `next_information_needed` | 4 |
| 确定量化引擎 | `risk_scoring_v1`：primary_income → gross_impact（按域公式）→ protected（coverage_map）→ unprotected → severity（档位 + 资产吸收降档）→ likelihood（base + 指示条件）→ residual（severity×0.6 + likelihood×0.4）→ priority（矩阵 + overrides）；**所有阈值外置** `resources/config/risk-scoring.rules.json` | 5 |
| `NOT_IDENTIFIED` 进 `risks[]` | 置低档 severity=LOW / residual=LOW / priority 封顶 P3，以支持复合 Eval（4/5/6）校验，但证明"不成立" | 5 |
| `existing_resources` FactValue | 每条必须带 schema 合规 `source`（`layer`/`field`/`origin`/`status` 四件套），溯源回 `client_state`；`note` 允许 `null` | 5 |
| Anti-Sales 词典内容 | 外置 `resources/config/anti-sales.rules.json`（panic / exaggeration / sales_verbs / product_names 四类 + 开关）；判定细则见 `evals/eval-policy.md` | 6 |
| Eval 7 项判定的具体不变量 | 见 `evals/eval-policy.md` §3（每项列出机检规则 + BLOCKING/WARNING 分级） | 6 |
| `completeness` "应发现域"口径 | 需以 Discovery 产物为参照（`-DiscoveryJsonPath`）；取 `discovery_status ∈ {IDENTIFIED,NOT_IDENTIFIED}` 的域集合比对 `risks[]`，`UNDETERMINED` 不在期望集内。未提供 Discovery 时该子检查不执行并在 Note 中明示 | 6 |
| `reasoning_consistency` residual 公式 | 仅对 `risk_exists=true` 复算 `0.6·sev_rank + 0.4·lik_rank` 分档；`risk_exists=false` 时引擎按契约置低档（LOW/LOW/P3）且 `likelihood` 保留域 base，公式不适用，只校验 LOW/LOW/P3 | 6 |
| `completeness` 对 `amount ≤ 0` 的处置 | 记 `MISSING_RISK`(**WARNING** 而非 BLOCKING)：CONTRACT §7 允许部分分析，量化基础缺失时金额 0 是诚实中间态，应进 `next_information_needed` | 6 |
| `EvalResult.failures` 语义 | **只含 BLOCKING issue**。曾误设为全量 issues，导致 `eval_status=PASS` 而 `failures` 非空，会误导 Repair 逻辑 | 6 |

### 未决（待后续 Phase）

- Repair Loop 的修复动作清单（哪些 FAIL 可自动修复、哪些必须 `NEEDS_REVIEW`） → Phase 7
- `priority_overrides` 的 `critical_residual_high_likelihood_p0` 当前为实效 no-op（`min_priority` 比较方向为 `$cur -lt $mn`，rank≥0 永不触发）；若需"致命+高发生概率→P0"，须改 `-lt`→`-gt` 并显式豁免 R5（否则会覆盖 `R5_always_low`）→ 待架构确认
