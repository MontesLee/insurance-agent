# requirement_analysis Skill 重构报告（Lawgent 方法论）

> 重构方式：参考 skill-hardening（Lawgent）方法论，将 skill 从「单体假 skill」改造为
> 「manifest + references + schemas + resources + overlays + evals + scripts（确定性校验/真 Eval）」的契约级结构。
> 日期：2026-09-12（含 Domain Overlay 扩展层补建 + 措辞层外部化 + 遗留清理）

## 1. 重构目标

- 将散落在项目根 `02-requirement-analysis/` 与 `scripts/lib/` 的业务规则、配置、用例、测试脚本
  **收拢进 skill 目录**，形成自包含、可独立交付的 skill。
- 用「binding 契约 + 确定性校验 + 真 Eval + 负向测试守卫」替代 Prompt 级软约束。
- 补建 **Domain Overlay（险种需求扩展层）**，把五大险种的专有规则从硬编码下沉为声明式配置。
- 将险种**结论措辞**一并下沉到 overlay，消除通用脚本中最后的领域硬编码。
- 最终确认 requirement_analysis skill 达到 **生产就绪（production-ready）** 状态。

## 2. 重构前 → 重构后结构

| 维度 | 重构前 | 重构后 |
|------|--------|--------|
| 入口 | `SKILL.md`（86 行，部分承载业务） | `SKILL.md`（94 行 manifest：Scope/Workflow/Knowledge Routing/Domain Overlays/Output Contract） |
| 业务规则 | `02-requirement-analysis/CONTRACT.md` 等 8 份 md（~400 行） | `references/01~07` 七份分层文档 |
| **险种扩展层** | 无（五大险种规则硬编码在 PowerShell） | **`overlays/` 五个领域 overlay + `_template`** |
| **险种措辞层** | `$RaDomainTexts` 硬编码在分析脚本内 | **各 overlay 的 `texts:` 小节**（代码仅保留回退默认值） |
| 配置 | `02-requirement-analysis/config/*.json` | `resources/config/*.rules.json` |
| Schema 契约 | `02-requirement-analysis/schemas/*.json` | `schemas/input\|output\|eval-output.schema.json` |
| 评估纪律 | `EVAL.md`（自然语言为主） | `evals/eval-policy.md`（合并 Lawgent 评估纪律） |
| 数据集 | `02-requirement-analysis/tests/dataset/*.json` | `evals/cases/requirement-analysis.dataset.json`（18 case） |
| 单元夹具 | `02-requirement-analysis/tests/*` | `evals/fixtures/unit/{analysis,questioning,sufficiency,schema}/` |
| 脚本 | `scripts/*.ps1` + `scripts/lib/` | `scripts/`（invoke×5 + test×6 + run-dataset + **resolve-overlays** + **anatomy guard** + update-context） |
| 架构守卫 | 无 | `scripts/check-skill-anatomy.ps1`（A1–A21 + B1/B2 + C1，共 **76 项**，可负向击破） |

## 3. 关键改动清单

1. **SKILL.md 重写为 manifest**（94 行 ≤100），含 Knowledge Routing 表与 Domain Overlays 节。
2. **references/ 七份**：boundary / information-model / status-enums / information-sufficiency / questioning / analysis / repair-loop。
3. **schemas/ 三件套**搬入 skill 内 `schemas/`。
4. **resources/config/** 两份规则（information-sufficiency、question-generation）搬入 skill 内。
5. **evals/**：eval-policy.md、cases 数据集（18 case）、fixtures 单元夹具（profile_path 已改为 `client-intake-data/clients/`）。
6. **scripts/**：13 个 ps1 全部迁入 skill；路径自包含。
7. **架构守卫 check-skill-anatomy.ps1**：结构校验 + B1 旧路径守卫 + B2 领域污染守卫。
8. **$PSScriptRoot 健壮性修复**：在 WorkBuddy PowerShell 工具下以 `powershell -File` 调用时 `$PSScriptRoot` 为空，
   已在全部 `-File` 入口脚本顶部统一加入兜底，消除潜在崩溃点。
9. **Domain Overlay 扩展层**：
   - `overlays/{life,critical-illness,medical,accident,savings}/overlay.yaml`：声明
     必填事实 / 证据引用 / 缺口公式 / 优先级档位 / 污染术语 / 边界红线。
   - `overlays/{...}/requirement-dimensions.md`：人读的领域维度文档（A 必填 / B 缺口口径 / C 优先级档位 / D 边界红线）。
   - `overlays/_template/`：新增险种模板；`overlays/README.md`：扩展协议。
   - `scripts/resolve-overlays.ps1`：确定性解析本次激活哪些险种（scope / keyword 匹配）。
   - 分析引擎 `invoke-requirement-analysis-analysis.ps1` 改为**由 overlay 驱动**：
     五个 `Build-XAnalysis` 硬编码函数合并为单一的 `Build-DomainAnalysis`。
10. **措辞层外部化（本轮完成）**：
    - 各 overlay 新增 `texts:` 小节（`risk` / `impact` / `gap` / `reasoning`，medical 另含 `impact_unknown`），
      值统一用双引号包裹，使文本内可安全包含冒号。
    - YAML 解析器（`Parse-RaOverlayYaml` 与守卫侧 `Parse-OvYamlGuard`）**同步支持带引号的值**，
      两处保持同构，避免语义漂移。
    - `Get-RaDomainSpec` 新增 `Texts` 字段；引擎优先取 overlay 措辞，缺失时回退内置表
      （保证不因配置缺口崩坏）。
    - 守卫新增 **A21**：`active` 险种必须自带 `risk/impact/gap/reasoning`，且不得残留占位符，
      从契约上杜绝"措辞被硬编码回通用脚本"的架构退化。

## 4. 验证结果（全部可执行、可复现）

| 验证项 | 命令 | 结果 |
|--------|------|------|
| 架构守卫 | `scripts/check-skill-anatomy.ps1` | **PASS=76 FAIL=0**（A1–A21 + B1/B2 + C1 全绿） |
| 数据集回归（真 Eval） | `scripts/run-requirement-analysis-dataset.ps1` | **18/18 通过，100%**；五维均分 Completeness 94.44 / Evidence 96.94 / Sufficiency 100 / Logic 100 / ProductBoundary 97.78 |
| 单元测试×6 | test-{analysis,questioning,sufficiency,schema,eval,repair-loop} | **6/6 全 PASS** |
| Schema 契约测试 | test-requirement-analysis-schema.ps1 | valid 通过；invalid **预期 FAIL 且如期 FAIL**（真契约校验） |
| Overlay 解析器 | `resolve-overlays.ps1 -List / -Scope` | 5 个 overlay 正确识别，scope 命中精确 |

**零回归（两轮）**：
- overlay 化后：18/18，五维均分与改造前**逐项一致**（94.44 / 96.94 / 100 / 100 / 97.78）。
- 措辞外部化后：18/18，五维均分仍**逐项一致**。
两轮外部化均未改变任何分析行为。

## 5. 负向测试（守卫与 overlay 均非橡皮图章，Lawgent Step 10）

1. **架构守卫 B1（旧路径）**：向 `references/01-boundary.md` 注入旧路径 → B1 立即 FAIL（EXIT=1）；清理后复绿（EXIT=0）。
2. **Overlay 规则权威性**：向 `overlays/life/overlay.yaml` 的 `required_fields` 注入不存在的字段
   `__probe_nonexistent__` → life 需求结论**立即消失**（证明引擎真的读 overlay）；清理后恢复。
3. **Overlay 措辞权威性（本轮新增）**：把 life 的 `texts.risk` 改为含 `<<PROBE_MARKER>>` 的文本 →
   输出 `risk_exposure` **立即随之改变**；恢复原文后输出还原。证明措辞层同样真驱动引擎。
4. **守卫 A21（本轮新增）**：删除 life 的 `texts.risk` 行 → A21 立即 FAIL（EXIT=1，PASS=75 FAIL=1）；
   恢复后回到 PASS=76 FAIL=0。证明新增检查项可被击破，非装饰。
5. **数据集内置负向用例**：E 类（UNSUPPORTED_CONCLUSION）、F 类（MISSING_RISK）、
   G 类（PRODUCT_RECOMMENDATION_LEAK）均正确判 `eval=FAIL` 并产出对应 issue 类型。
6. **Schema 负向用例**：invalid 输入/输出如期被拒。

## 6. 清理动作（全部可逆）

- 旧目录 `02-requirement-analysis/`（8 份 md + config/schemas/tests）已整体移出项目树，
  归档至 `tmp/archive-ra-old-20260912/`（可还原）。
- 项目根 `scripts/*.bak*`（5 份历史回滚副本）已归档至 `tmp/archive-ra-bak-20260912/`；
  项目根 `scripts/` 现仅保留活跃的 `run-regression.ps1`（已确认其不引用任何被归档文件）。
- 两个 DEBUG-ONLY 诊断脚本 `.trae/internal/diag-ra-*.ps1` 的 dataset 路径已重定向至新自包含位置。
- 改造前的核心引擎已备份：`tmp/invoke-requirement-analysis-analysis.ps1.bak-pre-overlay`。

## 7. 生产就绪判定

- [x] manifest 结构合规（SKILL.md 94 行 ≤100、frontmatter、Routing 表、Domain Overlays 节）
- [x] references / schemas / evals / scripts 资产完整无缺失
- [x] **Domain Overlay 扩展层落地**（5 险种 + 模板 + 协议 + 解析器），引擎由 overlay 驱动并经验证
- [x] **措辞层外部化完成**，通用脚本不再持有险种专有措辞
- [x] **领域污染守卫 B2**：通用层（SKILL.md/references/schemas）无任何险种专有术语泄漏
- [x] 架构守卫 **76/76** 通过，且 A21/B1 均经负向测试证伪
- [x] 数据集真 Eval 18/18 通过，两轮外部化均零回归
- [x] 6 个单元测试脚本全绿，含预期失败的契约负向用例
- [x] 路径自包含，不再依赖已废弃的旧目录
- [x] 修复 `$PSScriptRoot` 空值缺陷，脚本在任意 `-File` 调用方式下健壮

**判定：可投入生产环境（production-ready）。**

## 8. 已知取舍与后续建议

### 8.1 已完成的取舍（设计决策，非缺陷）

- **B1 旧路径守卫显式排除 `REFACTOR_REPORT.md`**：该文档是迁移历史记录，需引用旧目录名，非路径依赖；
  同时排除守卫自身脚本（避免自匹配误报）。业务内容（references / 用例 / 夹具）仍在扫描范围内。
- **overlay 缺失时回退内置默认值**：规则与措辞均如此。这是刻意的健壮性设计——
  配置缺口不应导致引擎崩溃，同时 A21 等守卫会在 CI 侧把缺口判红。

### 8.2 本轮已关闭的遗留项

- ~~措辞（risk/impact/gap/reasoning）硬编码在 `$RaDomainTexts`~~ → **已下沉至各 overlay 的 `texts:` 小节**，
  并新增 A21 守卫锁定；代码内仅保留回退默认值。
- ~~项目根 `scripts/*.bak-f*` 可择机清理~~ → **已归档**至 `tmp/archive-ra-bak-20260912/`（可逆）。

### 8.3 仍待决策（范围外，未自动执行）

- **client-intake 侧仍引用 `01-client-intake`**：共 22 个文件
  （`evals/eval-policy.md` 1 处、`evals/clients/*/snapshots/round-*.json` 20 处、`examples/C009-.../CLIENT_PROFILE.md` 1 处）。
  属**另一个 skill**，且其中 20 处是 client-intake 的**回归基线快照**——直接改写有破坏其回归基线的风险，
  需与 client-intake 的守卫/基线一并评估。
  **2026-09-12 已确认：暂不处理**，维持现状；报告在此留痕，待后续需要时再评估。
