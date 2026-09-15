# 保险 Agent V2 — Phase 6：report-generation 输入扩展至 Canonical Artifact 集

> 本文件记录 **Phase 6** 的产出与验证结论。
> 上游：`docs/architecture/contract-layer.md`（Phase 1–5）、`docs/architecture/evidence-provider.md`（Phase 4）、
> `docs/architecture/product-recommendation-v2.md`（Phase 5）。
> 审计基线 `docs/dev-notes/architecture-v2-audit.md` 未修改。

---

## 1. 目标

`report-generation`（Skill 8）从「消费 5 路 legacy 输出」升级为
「消费 Canonical Artifact 集 + legacy 别名」：

| 交付 | 含义 |
|---|---|
| collect | 接收 7 路 Canonical Artifact |
| normalize | `upstream_results_adapter` 归一化（含 envelope 解包、别名解析） |
| render | 章节渲染（新增策略块 + 证据附录） |
| validate | 六维校验 + 冲突呈现 |

**硬边界（不变）**：Report Generation **不拥有**任何 Artifact 的业务判断权。
它只做 `collect / normalize / render / validate`——不重算缺口等级、不重评风险、不重排策略、
不重选产品、不自行测算保额、不裁决上游冲突。

---

## 2. 输入契约（7 路 Canonical + legacy 别名）

`schemas/report-input.schema.json`：

| Canonical key | legacy 别名 | 必填 | 说明 |
|---|---|---|---|
| `client_profile` | — | ✅ | CanonicalClientState（画像/财务/责任/已有保障/健康） |
| `requirement_analysis` | — | ✅ | RequirementAnalysis |
| `risk_analysis` | — | ✅ | RiskAssessment |
| `coverage_gap_analysis` | — | — | CoverageGapAnalysis，**04 章节的 Canonical 唯一来源** |
| `solution_plan` | — | — | SolutionPlan，**06A 解决策略来源** |
| `knowledge_evidence` | `knowledge_search` | — | KnowledgeEvidence，**附录 A 证据来源** |
| `product_recommendation` | `recommendation` | — | ProductRecommendation，06B 推荐方向来源 |

**别名规则**：canonical key 优先；只给 legacy key 时使用它，并记入
`normalize_input(...)["aliases"]`，使报告可以说明数据实际以哪个名字到达。
**Envelope 规则**：经 `adapters/` 产出的 Artifact 带 `{artifact_type, skill, payload, ...}`，
消费方在有 `payload` 时解包——同一段代码同时兼容 canonical 与 raw Skill output。

---

## 3. 章节映射

| 章节 | 来源 | 规则 |
|---|---|---|
| 01–03 客户画像 / 财务 / 风险暴露 | `client_profile` + `risk_analysis` | 照搬，缺失→「待确认」 |
| **04 保障缺口** | `coverage_gap_analysis`（canonical-first） | 有 canonical → 逐条照搬（含 `gap_level`），`derivation="canonical"`；无 → 回退 risk/requirement 推导，`derivation="derived"` + 警告 |
| 05 需求优先级 | `requirement_analysis` | 照搬 |
| **06A 解决策略** | `solution_plan` | 逐条照搬 objective / coverage_direction / priority / constraints / trade_offs / rejected_directions |
| 06B 推荐方向 | `product_recommendation` | 照搬 candidate_id / fit / reason_codes |
| 07–08 信息缺口 / 下一步 | `requirement_analysis` + `risk_analysis` | 汇总裁决（不新增判断） |
| **附录 A 证据来源** | `knowledge_evidence` | 逐条列示 evidence_id / content / source / relevance / confidence / conflict |

### 3.1 04 章节的 canonical-first（关键设计）

```
CoverageGapAnalysis 存在?
 ├── 是 → 04 逐条照搬 canonical gaps；derivation="canonical"；风险推导条目被抑制
 └── 否 → 04 由 risk_analysis / requirement_analysis 推导；derivation="derived"
          + 警告 GAP_SOURCE_DERIVED_NOT_CANONICAL
```

两条路径**永不可混淆**：结构化输出带 `coverage_gap_derivation`，渲染稿带不同的小注
（`gap_canonical_note` / `gap_derived_note`，均在 `report.rules.json` 外置）。
若 canonical 存在而风险层另有 HIGH 残余风险，报告**不自行合并**——canonical 是判断层，
报告没有资格把两套结论拼起来。

### 3.2 跨 Artifact 冲突呈现（不裁决）

`v2_gap_vs_risk_conflict` 用例：CoverageGapAnalysis 把 `life` 判为 NONE（无覆盖），
但 risk_analysis 的 `R4-001` 记载已有 200 万保障。报告**检测到该不一致并原样呈现**，
不择一、不改写任何一侧。冲突是信息，不是错误。

---

## 4. 诚实性约束

| 约束 | 实现 |
|---|---|
| 金额不重算 | 上游 `unprotected_amount` 为数值（如 `500000`）时**原样字符串化**——刻意不换算成「万元」，因为换算即计算，即出错的机会 |
| 策略不转述 | `coverage_direction` / `trade_offs` 等逐字照搬；转述就是让一条策略悄悄变成另一条策略 |
| 缺上游不臆造 | 缺失章节 → 规则化说明文案（`missing_solution_note` / `missing_evidence_note`…），绝不生成「看起来合理」的内容 |
| 不可裁决不裁决 | 上游冲突 → 显式列出，交人工确认 |
| 幻觉扫描 | 渲染稿中的金额与具体产品名与上游交叉比对（既有 `hallucination_guard` 用例） |

---

## 5. 渲染缺陷修复（本阶段发现）

**现象**：策略块的 `约束 / 取舍 / 未采用方向` 直接渲染成 Python dict 字面量：

```
- 约束：{'constraint': '从零建立', 'value': '当前无对应保障...', 'source': 'GAP-R1-001'}
- 取舍：{'axis': '保障范围', 'option_a': '仅社保目录内', 'option_b': '...', ...}
```

原因：`'; '.join(str(c) for c in s['constraints'])` 对 dict 取 `str()` 得到 Python repr。

**修复**：按契约声明的字段做**字段感知渲染**（纯格式化，不引入任何新语义）：

```
- 约束：从零建立：当前无对应保障，需完整建立该方向保障（来源 GAP-R1-001）；…
- 取舍：在「保障范围」上，权衡「仅社保目录内」与「含目录外与免赔额以上」，选择「含目录外与免赔额以上」；理由：…
- 未采用方向：仅依赖社保（理由：社保目录外与起付线以上部分无法覆盖大额支出敞口）
```

- 新增 `_fmt_constraint` / `_fmt_tradeoff` / `_fmt_rejected`，`_kv_text` 作为未知键的兜底
  （**永不再 `str(dict)`**——那会把 Python repr 泄漏进客户报告）。
- 顺带修正 `匹配度` 一栏：`fit` 现取 fit-label 词表（`insufficient_evidence`）而非状态枚举，
  状态仍完整保留在原因句中，避免把「证据状态」当「匹配等级」呈现。
- 新增外置 `fit_names`（`report.rules.json`），使 fit token 在中文报告中正确呈现。

---

## 6. 本阶段改动的文件

| 文件 | 变更 |
|---|---|
| `schemas/report-input.schema.json` | 扩展为 7 路 canonical key + legacy 别名 |
| `schemas/report-output.schema.json` | 新增 `solution_strategies` / `evidence_summary`；`coverage_gaps` 放宽并加 `gap_id` / `gap_level` |
| `scripts/upstream_results_adapter.py` | 新增 `adapt_coverage_gap_analysis` / `adapt_solution_plan` / `adapt_knowledge_evidence` / `adapt_recommendation` + 别名解析 + envelope 解包 |
| `scripts/report_generation_engine.py` | 04 canonical-first；新增 06A 策略块与附录 A 证据表；跨 Artifact 冲突检测；金额原样字符串化；渲染格式化修复 |
| `resources/config/report.rules.json` | 新增 `solution_type_names` / `gap_level_names` / `fit_names` / 各章节说明文案 |
| `SKILL.md` / `CONTRACT.md` | 输入/输出/边界描述同步到 V2 |
| `evals/cases/v2-dataset-manifest.json`（新） | 6 个 V2 用例（fixtures 由真实引擎产出） |
| `scripts/run_report_v2_dataset.py`（新） | V2 数据集 runner |
| `scripts/test_report_v2.py`（新） | 10 项架构不变量 |

**新增**，未改写既有评估语义。legacy 数据集（8 例）与 legacy 单测（含 2 项负向自检）全部保持通过。

---

## 7. 验证结论

| 套件 | 结果 |
|---|---|
| report-generation **LEGACY** 数据集 | **ALL GREEN**（8/8） |
| report-generation **LEGACY** 单测 | **ALL GREEN**（含 2 项负向自检） |
| report-generation **V2** 数据集 | **ALL GREEN**（6/6） |
| report-generation **V2** 架构不变量 | **ALL GREEN**（10/10） |
| 契约测试 | **9/9** |
| 负向探针（防橡皮图章） | **5/5 LIVE** |

V2 用例：`v2_full_chain`、`v2_canonical_gap_suppresses_derivation`、
`v2_derived_fallback_warning`、`v2_solution_without_product`、`v2_evidence_conflict`、
`v2_gap_vs_risk_conflict`。

负向探针（探针说明「护栏真的会响」）：

```
PROBE1 canonical_suppression_live: LIVE (canonical n=1 -> derived n=3)
PROBE2 domain_mapping_externalized: LIVE (base=['R1'] tampered=['R5'])
PROBE3 strategy_verbatim_copy: LIVE
PROBE4 derived_warning_branch_live: LIVE
PROBE5 conflict_detector_conditional: LIVE (with_link=1 without_link=0)
```

其中 PROBE1 是「单一真源」的双向证明：只给 canonical 时只有 1 条缺口来源；
抽掉 canonical 后同一次分析出现 3 条 risk 推导条目——说明抑制逻辑是真实生效的，
不是恒真的橡皮图章。

---

## 8. 如何运行

```bash
# legacy 回归（8 例）
python .trae/skills/report-generation/scripts/run_report_dataset.py
python .trae/skills/report-generation/scripts/test-report-generation.py

# V2 数据集（6 例）
python .trae/skills/report-generation/scripts/run_report_v2_dataset.py

# V2 架构不变量（10 项）
python .trae/skills/report-generation/scripts/test_report_v2.py

# 契约测试
python tests/contracts/run_contract_tests.py
```

---

## 9. 下一步（Phase 7，待人工确认）

1. **case-state（`state/`）+ orchestrator（`workflow/insurance-analysis.yaml`）+ E2E** —— 把 8 个 Skill
   串成可一键运行、带状态与人工复核闸门的完整链路。
2. （V2.1，按用户评审暂缓）抽取 `domain/insurance` Domain Pack。

**本阶段结束后已 STOP，未自动进入 Phase 7。**
