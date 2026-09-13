# 09 · Phase 9 Review（终审）

> 终审目标：不是"再补几个用例"，而是把**假成功**找出来——
> 文档承诺但没实现的引用、规则文件里躺着却没人读的配置、引擎里硬编码却宣称外置的常量、
> 以及看起来生效其实永远不触发的开关。

---

## 1. 审计范围与方法

| 审计项 | 方法 | 落地 |
|---|---|---|
| 悬空引用 | 扫描 md 中所有相对路径引用，逐条 `Test-Path` | 守卫 `B1` |
| 死配置 | 规则文件**顶层键** × 全部脚本文本，未被引用即死 | 守卫 `B2` |
| 硬编码常量 | 引擎内字面量枚举 / profile 列表 / 状态次序 / 关键词表 | 已改为读配置 |
| 静默 no-op | `priority_overrides` 比较方向与可达性推演 | 已改为显式开关 |
| 结构合规 | AGENTS.md §7 骨架 + SKILL.md ≤100 行 | 守卫 `A*` |
| 编码卫生 | 每个 .ps1 的 BOM 与 Parser 可解析 | 守卫 `B5` |
| 上游不可变 | 脚本中不得出现写上游的语句 | 守卫 `B6` |

---

## 2. 发现与处置

### R1 ·「假外置」：规则里躺着，引擎里硬编码（4 处，均已修）

| # | 死配置（无人消费） | 引擎硬编码 | 处置 |
|---|---|---|---|
| 1 | `risk-sufficiency.rules.json#field_profile_index` | 三个引擎各写一份 6 个 profile 的列表 | 新增 `profile_names` 作为单一真源；三引擎改读配置，**缺键即抛错**（不回退硬编码） |
| 2 | `risk-discovery.rules.json#health_abnormal_keywords` | `analysis` 引擎内 9 个健康异常词 | 词表迁入 `risk-scoring.rules.json#health_anomaly_tokens`；引擎改读配置 |
| 3 | `risk-sufficiency.rules.json#analysis_status_rules.precedence` | `analysis` 引擎内硬编码状态次序 | `analysis` 改从 shared rules 读（discovery 早已如此，两处口径统一） |
| 4 | `numeric_zero_is_absent_fields` / `status_unknown` / `high_risk_occupation_keywords` / `income_unstable_keywords` / `default_currency` / `high_risk_occupation_tokens` | ——（纯冗余） | 删除；域内 keyword 已写在 `domains.<id>.gate/amplifiers`，不在顶层重复 |

**为什么这是缺陷而不是洁癖**：配置写着、引擎不读，改配置的人会以为改生效了。
"假成功"比失败更危险——它会让人基于错误的预期做决策。

**处置原则**：缺键**抛错**，不做默认值兜底。静默回退硬编码 = 把假外置藏得更深。

### R2 · 静默 no-op 的优先级开关（已显式化）

`priority_overrides.critical_residual_high_likelihood_p0`：

- 原实现 `min_priority` 比较方向写成 `$cur -lt $mn`，而 rank 越小越紧急（P0=0），
  ⇒ `$cur -lt 0` 恒假 ⇒ **写了等于没写**
- 更麻烦的是：修正为 `-gt` 后它会覆盖 `R5_always_low`（R5 可达 `CRITICAL + HIGH`，实测 `ds-001` 的 R5-001 正是此组合）⇒ 属**产品裁决**，不能由工程私自决定

**处置**：
1. 比较方向修正为 `-gt`（`analysis` 与 `repair` 两处同步）
2. 规则文件加 `enabled` 字段，该项置 `false`，`reason` 写明冲突
3. 引擎**强制要求**每条 override 显式声明 `enabled`，缺字段即抛错（防止静默 no-op 复活）
4. 两组单测固化语义：`enabled=false` → R5 保持 P3；`enabled=true` → R5 抬到 P0

打开开关只需把 `enabled` 改成 `true`，代价与后果已写在配置里。

### R3 · 文档空洞（3 份 references + 1 份 usage-guide）

`SKILL.md` 引用了但从未创建的：`01-provenance.md`、`05-questioning.md`、`06-output-schema.md`；
`AGENTS.md` §7 要求的 `resources/usage-guide.md` 也缺失。全部补齐，内容取自**已实现**的引擎与规则，不编造。

- `06-output-schema.md` 明确标注：Markdown 渲染器**未内置**，本文档是渲染契约（避免"文档承诺了实现"）

### R4 · 悬空引用与幽灵文件

- `CONTRACT.md` §10 指向旧文件名 `risk-taxonomy.md`（实际文件是带编号的 `03-risk-taxonomy.md`）→ 已修正
- 根目录存在 0 字节的 `nul`（Windows 重定向产生的幽灵文件）→ 已删除
- `build-client-state.ps1` / `build-risk-input.ps1` 仍未实现 → 在文档中**显式标 ⏳** 并说明 v1 不依赖
  （守卫规则：不存在的引用必须标 ⏳，否则判 FAIL——不允许"悄悄引用一个不存在的文件"）

### R5 · 遗留污染

规则文件的 `.bak` 备份、开发期的临时探针脚本等运行残留 → 已删除并在守卫中固化 `B4`。

---

## 3. 新增资产

| 资产 | 作用 |
|---|---|
| `scripts/check-skill-anatomy.ps1` | 架构守卫：A 骨架 12 项 + B 纪律 7 项；输出 `tmp/anatomy_result.json` |
| `scripts/test-risk-analysis-anatomy.ps1` | 守卫的**反橡皮图章自检**：基线 PASS + 5 种污染必须 FAIL |
| `references/01-provenance.md` / `05-questioning.md` / `06-output-schema.md` / `09-review.md` | 补齐文档空洞 |
| `resources/usage-guide.md` | 调用模板、参数速查、常见坑 |

守卫的 5 个探针（每个都必须让守卫掉分）：

1. 删 `evals/eval-policy.md` → `A8`
2. 注入未被消费的规则键 → `B2`
3. 去掉 override 的 `enabled` → `B3`
4. 剥掉 .ps1 的 BOM → `B5`
5. 文档引用不存在的文件且未标 ⏳ → `B1`

---

## 4. 残余风险（交给下一阶段 / 产品裁决）

| # | 风险 | 建议 |
|---|---|---|
| 1 | `critical_residual_high_likelihood_p0` 仍禁用 | 由产品决定是否允许"R5 致命+高概率"压过 `R5_always_low`；改 `enabled` 即可 |
| 2 | 健康异常词表两版不一致 | 引擎实际用 9 词；规则里曾有一份 13 词的更全列表（已删）。建议产品确认后合并到 `health_anomaly_tokens` |
| 3 | `build-client-state.ps1` / `build-risk-input.ps1` 未实现 | 有真实 `CLIENT_PROFILE.md` 时再建，v1 用 `RiskAnalysisInput` 直供 |
| 4 | Markdown 渲染器未实现 | 契约已定（`06-output-schema.md`），需要对外出报告时再实现 |
| 5 | 全 UNKNOWN 用例 R4 判 `UNDETERMINED` | 属**正确保守逻辑**（any_of 组要求全体成员确定不存在才能下消极结论）；要消极结论需显式填 `family_responsibility` |

---

## 5. 验收快照

| 项 | 结果 |
|---|---|
| 单元测试 | sufficiency 8/8 · discovery 13/13 · **analysis 15/15** · eval 16/16 · repair 11/11 · dataset 5/5 · **anatomy 6/6** |
| 架构守卫 | 19 项全 PASS（`tmp/anatomy_result.json`） |
| 契约校验 | `verify-contract.py` §1–§10 零错误，退出码 0 |
| 上游零改动 | `client-intake` / `requirement_analysis` 本会话零写入 |
