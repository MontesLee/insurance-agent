# Usage Guide — risk-analysis 调用模板

> 全部引擎为**确定性 PowerShell 5.1**，零 LLM 依赖。Windows 上先执行
> `Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force`（仅当前进程）。

---

## 1. 最小链路（推荐）

```powershell
$skill = 'D:\Workspace\insurance-agent\.trae\skills\risk-analysis'
$s = Join-Path $skill 'scripts'

# 1) 充分性
& "$s\invoke-risk-analysis-sufficiency.ps1" -InputJsonPath  <RiskAnalysisInput.json> `
                                            -OutputJsonPath <tmp>\suff.json
# 2) 风险发现
& "$s\invoke-risk-analysis-discovery.ps1"   -InputJsonPath  <RiskAnalysisInput.json> `
                                            -OutputJsonPath <tmp>\disc.json `
                                            -SufficiencyJsonPath <tmp>\suff.json
# 3) 量化分析
& "$s\invoke-risk-analysis-analysis.ps1"    -InputJsonPath  <RiskAnalysisInput.json> `
                                            -OutputJsonPath <tmp>\ana.json `
                                            -DiscoveryJsonPath   <tmp>\disc.json `
                                            -SufficiencyJsonPath <tmp>\suff.json
```

产物 `ana.json` 为阶段产物（含 `stage` / `stage_version` / `risk_analysis` / `risks[]`）。

---

## 2. 质量闸门（Eval + Repair）

```powershell
# 4) Eval（7 项机检）
& "$s\invoke-risk-analysis-eval.ps1" -AnalysisJsonPath <tmp>\ana.json `
                                     -DiscoveryJsonPath <tmp>\disc.json `
                                     -OutputJsonPath   <tmp>\eval.json

# 5) Repair（仅当 Eval FAIL；≤2 轮，仍失败 → NEEDS_REVIEW）
& "$s\invoke-risk-analysis-repair.ps1" -AnalysisJsonPath       <tmp>\ana.json `
                                       -DiscoveryJsonPath      <tmp>\disc.json `
                                       -EvalOutputJsonPath     <tmp>\eval.json `
                                       -RepairedOutputJsonPath <tmp>\ana_repaired.json
```

`-DiscoveryJsonPath` 对 Eval 是**可选但强烈建议**：缺了它，`completeness` 的"应发现域覆盖"子检查不执行并在 Note 中明示。

---

## 3. 端到端数据集

```powershell
& "$s\run-risk-analysis-dataset.ps1"          # 输出 tmp/dataset_result.json + tmp/dataset_report.md
& "$s\test-risk-analysis-dataset.ps1"         # 基线 + 3 个反橡皮图章探针
```

退出码非 0 即失败。

---

## 4. 参数速查

| 脚本 | 必需参数 | 可选 |
|---|---|---|
| `invoke-risk-analysis-sufficiency.ps1` | `-InputJsonPath` `-OutputJsonPath` | `-RulesPath` |
| `invoke-risk-analysis-discovery.ps1` | `-InputJsonPath` `-OutputJsonPath` | `-SufficiencyJsonPath` `-RulesPath` |
| `invoke-risk-analysis-analysis.ps1` | `-InputJsonPath` `-OutputJsonPath` `-DiscoveryJsonPath` | `-SufficiencyJsonPath` `-RulesPath` `-SharedRulesPath` |
| `invoke-risk-analysis-eval.ps1` | `-AnalysisJsonPath` `-OutputJsonPath` | `-DiscoveryJsonPath` `-AntiSalesRulesPath` `-ScoringRulesPath` `-EvalSchemaPath` `-PatchOutput` |
| `invoke-risk-analysis-repair.ps1` | `-AnalysisJsonPath` `-RepairedOutputJsonPath` | `-DiscoveryJsonPath` `-EvalOutputJsonPath` `-RepairRulesPath` `-ScoringRulesPath` `-AntiSalesRulesPath` `-EvalSchemaPath` |
| `run-risk-analysis-dataset.ps1` | —— | `-ManifestPath` `-OutputJsonPath` `-ReportPath` `-DiscoveryRulesPath` `-ScoringRulesPath` `-AntiSalesRulesPath` |

`RulesPath` 系列存在的意义是**让规则可被注入篡改以做负向测试**——规则真外置，不是装饰。

---

## 5. 输入怎么来

**v1 的输入契约是 `RiskAnalysisInput`（契约 §5）**，由调用方直接提供 JSON：

```
ClientState（事实） + RequirementAnalysisOutput.requirements（需求） → RiskAnalysisInput
```

- 现成样例：`evals/cases/dataset/ds-*.input.json`（由 `scripts/gen-dataset-cases.py` 可复现生成）
- `build-client-state.ps1` / `build-risk-input.ps1` 两个 adapter **未实现**（⏳）；
  它们是"从 `CLIENT_PROFILE.md` 直接开工"的工程化入口，不影响 v1 可交付性——
  手工或由上游管线组装出 `RiskAnalysisInput` 即可跑通全链路。

---

## 6. 回归

```powershell
$tests = @('sufficiency','discovery','analysis','eval','repair','dataset')
foreach ($t in $tests) { & "$s\test-risk-analysis-$t.ps1"; if ($LASTEXITCODE -ne 0) { "FAILED: $t" } }

& "$s\check-skill-anatomy.ps1"                 # 架构守卫（骨架 / 命名 / 悬空引用 / 死配置）
python "$s\verify-contract.py"                 # 契约校验（§1–§10）
```

---

## 7. 常见坑

| 现象 | 原因 |
|---|---|
| 脚本静默不执行 | 未先设 `Set-ExecutionPolicy Bypass -Scope Process` |
| 中文变乱码 / `param(` 解析报错 | `.ps1` 丢了 UTF-8 BOM（用 `scripts/fix_ps1_bom.py <file>` 补回） |
| `Join-Path` 报 ParameterBindingException | PS 5.1 只支持两个参数，需嵌套 |
| 改了规则文件但结论没变 | 该键是死配置（未被消费）→ 跑 `check-skill-anatomy.ps1` 的死键检查 |
| 引擎抛 "缺 xxx：不得回退硬编码" | 注入的规则副本缺该键；属**故意的硬失败**，不要加兜底默认值 |
