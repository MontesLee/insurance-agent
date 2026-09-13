# 05 · Repair Loop（Phase 7）

> 本文是 Repair Loop 的深层规则。SKILL.md 只做索引，判定细节与动作清单以本文 + `resources/config/repair.rules.json` 为准。

---

## 1. 定位

Eval（Phase 6）判定产物是否合格；Repair Loop 判定**不合格时能否由机器可靠地修好**。

它不是一个"把 FAIL 洗成 PASS"的组件。它的职责边界是：

- 能修的：**确定性重算**能修的机械偏差；
- 不能修的：**如实上报**，说明"哪些无法可靠判断 + 需要人工确认什么"。

把修不好的东西洗成 PASS，比留着 FAIL 更危险——它让下游以为产物可信。

---

## 2. 四条红线

| # | 红线 | 为什么 |
|---|---|---|
| R1 | **只做重算，不做发明** | 修复值必须由产物已有字段按同一份规则算出。任何需要新事实的修复都是伪造。 |
| R2 | **只做降级，不做升格** | 删除虚假主张（悬空证据锚点）安全；把 `UNKNOWN` 升成 `KNOWN`、把缺失的 `amount` 补成正数，一律禁止。 |
| R3 | **立场问题不自动清洗** | 恐吓话术、产品泄露是立场越界，不是数值错误。自动删句会抹掉越界证据，必须留痕。 |
| R4 | **修完必须重评** | 修复可能引入新的不一致（如重算 residual 后 priority 失配）。不得修完即信；上限 2 轮。 |

判据一句话：**派生量算错了 → 可自动修；事实或立场有问题 → 上报。**

---

## 3. 循环算法

```
attempt = 0
eval    = Eval(analysis)

while eval.eval_status == FAIL and attempt < max_attempts:
    blocking = eval.failures            # 只含 BLOCKING
    actions  = [resolve(i) for i in blocking]   # 由 issue code + risk 状态决定 action_id
    auto     = [a for a in actions if mode(a) == AUTO]

    if auto is empty: break              # 没有任何安全修复可做
    apply(auto) -> analysis'
    if serialize(analysis') == serialize(analysis): break   # 确定性修复的不动点，再跑无意义
    attempt += 1
    log(attempt, failed_codes, action)
    analysis = analysis'
    eval = Eval(analysis)

if eval.eval_status == FAIL:
    eval.eval_status = NEEDS_REVIEW
    eval.needs_review_note = 由剩余 BLOCKING code 查 review_reason 生成
```

### 3.1 三个终止条件

1. **收敛** — `eval_status == PASS`，`repair_attempts` 记录实际轮数。
2. **无可安全修复** — 剩余 BLOCKING 全部是 REVIEW 模式，立即停止（不空转消耗 attempt）。
3. **不动点** — 应用修复后产物字节不变。确定性修复若第一轮没改变任何东西，第二轮必然同样不变，继续跑是自欺。

`max_attempts = 2` 是**上限不是配额**：不会因为"才跑了 1 轮"就硬凑第二轮。

### 3.2 NEEDS_REVIEW 的三段式说明

`needs_review_note` 必须回答三件事，缺一不可：

- **剩余 BLOCKING**：哪些检查没过（code + risk_id）
- **无法可靠判断项**：按 code 查 `review_reason`，说明为什么机检修不了
- **需人工确认**：是补事实、撤回结论，还是改判定规则——**机检不得代为选择**

---

## 4. 动作清单

完整清单外置于 `resources/config/repair.rules.json`（改动作模式不必动引擎）。

| action_id | 触发 code | 模式 | 动作 | 依据 |
|---|---|---|---|---|
| `CLAMP_NOT_IDENTIFIED_BANDS` | `LOGICAL_INCONSISTENCY` | AUTO | `risk_exists=false` → 强制 `severity=LOW` / `residual=LOW` / `priority=P3` | CONTRACT §7 置低档约定 |
| `RECOMPUTE_RESIDUAL` | `LOGICAL_INCONSISTENCY` | AUTO | 重算 `residual = band(0.6·sev_rank + 0.4·lik_rank)` | 与 analysis 引擎同式同阈值 |
| `RECOMPUTE_PRIORITY` | `PRIORITY_INCONSISTENT` | AUTO | 重算 `priority_matrix[sev][lik]` + `priority_overrides` | 与 analysis 引擎逐字一致 |
| `DROP_DANGLING_REFS` | `UNSUPPORTED_CONCLUSION` | AUTO（条件） | 删掉 `evidence[]` 中不存在的 `E###` 锚点；**仅当删后仍有 ≥1 个锚点** | 删除虚假溯源主张＝降级 |
| `ESCALATE_UNSUPPORTED` | `UNSUPPORTED_CONCLUSION` | REVIEW | 无 evidence / 锚点删空 | 补 evidence＝补事实；撤回结论＝改主张 |
| `ESCALATE_MISSING_RISK` | `MISSING_RISK` | REVIEW | 域缺失或结构缺失 | 引擎已确定性，缺域＝事实不足 |
| `ESCALATE_UNKNOWN_AS_KNOWN` | `UNKNOWN_AS_KNOWN` | REVIEW | UNKNOWN 当 KNOWN 用 | 主张越界，非计算错误 |
| `ESCALATE_SALES_BIAS` | `SALES_BIAS` | REVIEW | 恐吓/夸大话术 | 立场问题，删句＝掩盖 |
| `ESCALATE_PRODUCT_LEAK` | `PRODUCT_RECOMMENDATION_LEAK` | REVIEW | 风险写成产品需求 | 违反分层职责，须留痕 |
| `ESCALATE_INVALID_OUTPUT` | `INVALID_OUTPUT` | REVIEW | 结构不合规 | 引擎缺陷或篡改 |

### 4.1 为什么 `UNKNOWN_AS_KNOWN` 不自动降级 status

表面看"把 `status=KNOWN` 降成 `UNKNOWN`"符合 R2（只降级）。但它修不干净：Eval 对同一情形有**两条** BLOCKING——

1. `status=KNOWN` 但全部 evidence 为 UNKNOWN/UNVERIFIED
2. `impact_estimate > 0` 但无 KNOWN/ESTIMATED 类证据支撑

降级 status 只消掉第 1 条，第 2 条仍 BLOCKING。结果是一个**半修复产物**：主张撤了一半，金额还在。这比原样上报更难解释。故整体 REVIEW。

---

## 5. 与相邻 Phase 的接口

- **输入**：`RiskAnalysisOutput`（待修产物）+ 可选 `Discovery` 产物（使 `completeness` 的域覆盖子检查可比）
- **调用**：Repair 内部调用 Phase 6 的 `invoke-risk-analysis-eval.ps1`，**不复制判定逻辑**
- **输出**：
  - 修复后的 `RiskAnalysisOutput`（`-RepairedOutputJsonPath`）
  - 最终 `EvalResult`（`-EvalOutputJsonPath`），含 `repair_required` / `repair_attempts` / `repair_log` / `needs_review_note`
- **下游（Phase 8 Dataset）**：可统计"各类 code 的收敛率"，用于判断哪些判定式过严

---

## 6. 常见误用

| 误用 | 后果 | 正确做法 |
|---|---|---|
| 把 `amount=0` 自动补成估算值 | 伪造量化基础 | 保持 0 + 进 `next_information_needed` |
| 自动删除含产品名的整句 | 立场未改、证据被抹 | REVIEW 留痕 |
| 修复后不重评直接 PASS | 可能引入新不一致 | 必须重跑 Eval |
| 为凑满 2 轮而空转 | 日志失真、掩盖不动点 | 无变化即停 |
| 用修复掩盖引擎缺陷 | 缺陷被反复"修"掉 | `INVALID_OUTPUT` 一律回引擎 |
