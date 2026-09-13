# 08 · Dataset（Phase 8 端到端数据集）

> 单测证明"每个零件对"，数据集证明"整条链对"。
> 本文只描述数据集的设计与纪律，具体期望值一律写在 `evals/cases/dataset-manifest.json`。

---

## 1. 它解决什么问题

Phase 3–7 的单测都是**单点注入**：给引擎一份现成的产物，断言某一项检查的行为。
这带来一个盲区——引擎之间的**接缝**没人验证。典型接缝缺陷：

- 充分性判定 `FORMAL`，传到发现阶段被无端降成 `PRELIMINARY`（契约 §7 被违反）
- 上游缺失在两个地方各登记一次，`missing_from_upstream` 出现重复条目
- 客户原话是整句时（"父母有退休金，无需固定赡养"）否定词识别失效，消极事实被读成积极事实

数据集用**真实家庭原型**跑完整链路，专门照这些接缝打。

---

## 2. 链路

```text
input.json → sufficiency → discovery → analysis → (mutation) → eval → repair
                                                                   ↓
                                             EvalResult（唯一裁判）→ 五维评分
```

**评分不另起炉灶**：五维全部由 `EvalResult.checks` 换算，Eval 引擎是唯一裁判。

| 维度 | 取自 | 聚合 |
|---|---|---|
| `completeness` | `completeness` | 直取 |
| `evidence_grounding` | `evidence_grounding` | 直取 |
| `reasoning_consistency` | `reasoning_consistency` + `priority_consistency` | avg |
| `unknown_integrity` | `unknown_integrity` | 直取 |
| `product_boundary` | `separation` + `anti_sales` | **min** |

`product_boundary` 取 `min` 而非平均：销售语言与产品泄漏任一发生即视为边界失守，
平均会让"一边满分一边零分"看起来还有 50 分。

---

## 3. 用例三类

| 类别 | 数量 | 作用 |
|---|---|---|
| `positive` | 7 | 真实家庭原型，断言状态 / 三态 / 风险存在性 / 优先级 / 覆盖完整 |
| `degraded` | 3 | 全 UNKNOWN、取值冲突、上游缺失——断言**不伪造**、**不择一**、**不阻塞** |
| `mutation` | 5 | 在正确产物上注入单点错误，断言被 Eval 抓出且 Repair 处置得当 |

### degraded 类为什么重要

"诚实地说不知道"是最容易被误伤的行为：全 UNKNOWN 的用例如果引擎为了凑产出而编造风险，
7 项 Eval 仍可能全绿。所以这类用例的期望是 `risks=0` + `NEED_MORE_INFORMATION`，
并额外挂 `fabricated_certainty` 禁止行为（有金额就必须有可溯源证据）。

### mutation 类的双重收益

既是对 Eval 的负向测试（变异必须被抓出），也是对 Repair 红线的正向测试：

| 变异 | 首轮失败码 | Repair 处置 | 期望终态 |
|---|---|---|---|
| 删除应发现的风险 | `MISSING_RISK` | REVIEW（禁止补造） | `NEEDS_REVIEW` / 0 轮 |
| 优先级抬高 | `PRIORITY_INCONSISTENT` | AUTO `RECOMPUTE_PRIORITY` | `PASS` / 1 轮 |
| 恐吓话术 | `SALES_BIAS` | REVIEW（禁止清洗立场） | `NEEDS_REVIEW` / 0 轮 |
| 把未知当已知 | `UNKNOWN_AS_KNOWN` | REVIEW（避免半修复） | `NEEDS_REVIEW` / 0 轮 |
| 悬空证据锚点 | `UNSUPPORTED_CONCLUSION` | AUTO `DROP_DANGLING_REFS` | `PASS` / 1 轮 |

---

## 4. 期望值的写法纪律

**先按契约推理写期望，再跑；出错先归因，不照抄实际输出。**

归因只有两种结论：

1. **引擎错** → 改引擎，并把该场景补一条单测（Phase 8 实测：3 处，见 §6）
2. **期望错** → 改期望，并在 manifest 的 `why` 字段写明为什么原来的推理不对

第 2 种同样有价值——它记录了"我们以为该这样，实际规则是这样"的口径。

另外一条硬纪律：**反向断言**。变异用例除目标检查 FAIL 外，其余检查必须 PASS；
探针用例篡改规则后数据集**必须**掉分，否则说明期望值是照抄引擎输出的假通过。

---

## 5. 反橡皮图章探针

`test-risk-analysis-dataset.ps1` 在基线之外跑 3 个探针，注入被篡改的规则副本
（写进 `tmp/`，绝不改动 `resources/config/`）：

| 探针 | 篡改 | 数据集必须 |
|---|---|---|
| 子串否定词表 | `negative_substrings = []` | 失败（整句否定用例翻转） |
| 优先级矩阵 | `priority_matrix.CRITICAL.HIGH = 'P3'` | 失败（优先级期望失配） |
| 恐吓词典 | `panic_tokens = []` | 失败（恐吓话术漏检） |

探针结束后**必须重跑一次基线**：探针会覆盖 `tmp/ds_<id>_*.json`，
不恢复会让 `verify-contract.py §10` 读着被污染的规则产物做判断。

---

## 6. Phase 8 实测发现的缺陷（均已修 + 补回归）

| # | 缺陷 | 影响 | 修复 |
|---|---|---|---|
| D1 | 中文整句否定（"无需固定赡养" / "不承担赡养"）不被识别 | R4 误判成立并给出 240 万金额 | `risk-discovery.rules.json` 新增 `negative_substrings`，`Test-RdNegative` 增加子串匹配 |
| D2 | `missing_from_upstream` 同一缺失登记两次 | 下游重复追问 | 充分性引擎按 `source+field` 去重 |
| D3 | 发现阶段把"无未决、无冲突"硬编码成 `PRELIMINARY` | 信息完整的用例永远拿不到 `FORMAL`，违反契约 §7 | 基线改取充分性结论，发现阶段只能加严不能放宽 |

D1 已补单测 `case-embedded-negation.json` + "清空 `negative_substrings` 结论必须改变"的负向用例。

---

## 7. 复现

```powershell
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process -Force
cd .trae\skills\risk-analysis\scripts

# 1) 生成 / 重生成用例输入（可复现，覆盖写）
python gen-dataset-cases.py

# 2) 跑数据集（产物：tmp/dataset_result.json + tmp/dataset_report.md）
.\run-risk-analysis-dataset.ps1

# 3) 数据集回归 + 反橡皮图章探针
.\test-risk-analysis-dataset.ps1

# 4) 契约校验（§10 校验数据集产物）
python verify-contract.py
```

改 .ps1 后用 `python fix_ps1_bom.py <file>` 补回 UTF-8 BOM（PS 5.1 按 GBK 解析无 BOM 的中文）。

---

## 8. 新增用例的步骤

1. `scripts/gen-dataset-cases.py` 的 `CASES` 里加一条紧凑规格（未声明字段自动补 UNKNOWN 槽位 + `missing_from_upstream`）
2. `evals/cases/dataset-manifest.json` 加一条，写清 `expect` 与 **`why`**（为什么期望是这个值）
3. 跑数据集；失败先按 §4 归因
4. 若该场景暴露了引擎缺陷，补一条**单点**单测（不要靠数据集兜底回归）
