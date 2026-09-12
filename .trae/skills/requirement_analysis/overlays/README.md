# requirement_analysis Domain Overlays（险种需求扩展层）

Lawgent Domain Overlay 模式在本 skill 的落地：**通用层只讲方法论，险种专有规则一律下沉到 overlay**。

## 目录约定

```
overlays/
  README.md              # 本协议
  _template/             # 新增险种的模板（不参与检查，不作为领域生效）
  life/                  # 寿险需求
  critical-illness/      # 重疾需求
  medical/               # 医疗需求
  accident/              # 意外需求
  savings/               # 储蓄/教育/养老需求
```

每个 overlay 目录必须包含：

- `overlay.yaml` —— 声明式配置（机器可读）：
  - `id` / `name` / `version` / `status(active|draft)` / `priority(整数)`
  - `triggers.goal_types` —— 与 `analysis_scope` 对齐的需求类型标识
  - `triggers.keywords` —— 触发关键词
  - `dimensions` —— 维度文档文件名（默认 `requirement-dimensions.md`）
  - `contamination_terms` —— 本险种专有术语；**这些词不得出现在通用层**（SKILL.md / references / schemas）
  - `boundary.must_not` —— 本险种边界红线
  - `analysis.*` —— 分析引擎消费的确定性规则：
    `required_fields` / `evidence_fact_refs` / `coverage_field` /
    `need_formula` / `priority_rule` / `priority_when_*`
- `requirement-dimensions.md` —— 人读的领域维度文档（必填事实、缺口口径、优先级档位、证据要求、边界红线）

## 分析引擎如何消费

`invoke-requirement-analysis-analysis.ps1` 对每个 `analysis_scope` 载入对应 overlay，
用其中的 `analysis.*` 驱动判定（必填字段是否齐备、证据引用、缺口公式、优先级档位）。
**overlay 缺失或字段缺失时回退到内置默认值**，保证行为不因配置缺口而崩坏。

## 新增一个险种

1. 复制 `_template/` 为新目录（目录名 = `overlay.yaml` 的 `id`）。
2. 填写 `overlay.yaml`，替换全部占位符（守卫 A11 会检查 `<...>`、`TODO`、`待填`、`XXX`）。
3. 编写 `requirement-dimensions.md`，保留必备小节。
4. 在 `scripts/lib/requirement-analysis-runtime.ps1` 的 scope→overlay 映射表中登记。
5. 跑 `scripts/check-skill-anatomy.ps1` 与 `scripts/run-requirement-analysis-dataset.ps1` 确认全绿。

## 边界

- overlay 只描述**需求侧**规则（`requirement_only`），严禁出现产品名、费率、投保建议。
- 通用层被领域术语污染 = 架构退化，守卫 B2 会直接判 FAIL。