# K.29-C FIX-3 · B+D Offline Simulator — 设计方案（不实现）

Date: 2026-10-02 · Mode: **DESIGN ONLY**（工具尚未编写·不改生产）

---

## 1. 目标

在**零生产改动**下,用既有 K.29-C 重放机制量化四个臂的收益与安全,
为 Owner Decision v2（Decision 1）提供证据:

```
Arm-0 Baseline C1     （现行规则·对照）
Arm-B Candidate B     （C3v2 护栏豁免·白名单+永禁清单）
Arm-D Candidate D     （建议句前提防御·F-1 闭合）
Arm-BD B+D 组合       （两旗独立·联合上界）
```

## 2. 输入数据（全部既有·不新造）

| 数据集 | 用途 | 已在 |
|---|---|---|
| K.28-II 金标 104 单 claim + 10 流式 | **安全面**(攻击族 N1-N10) | tests/golden/claim-evidence-shadow.v1.json |
| k29c 分类学 134 失败 claim(A-fixed 80 记录派生) | **收益面**(拒答翻转) | tests/golden/k29c_claim_taxonomy.json |
| K.29-C 探针 7 例 | B/D 行为锁 | tests/golden/k29c_claim_taxonomy.json(c3_c4_probes) |
| B 臂生成答案 51 条(存储 600 字符) | D 的真实暴露扫描(REC+数字形态) | tmp/obs/k29b/B_{main,flash}_all.jsonl |
| (可选·若 Owner 授权)v2 语料冻结后 | 六族硬门验收 | tests/golden/k29c_fix3_benchmark_v2_plan.json 生成物 |

## 3. 模拟器结构（扩展现有 tools/k29c_calibration_study.py 模式）

### 3.1 候选实现（离线 policy 函数·不 import 生产修改)

```
clause_accept_B(clause):     # = 现 C3v2:护栏正则 ∧ 零锚 ∧ NUM_RE 零
                             #   ∧(GUIDE 类)HIGH_RISK 零命中 → 豁免
                             # 否则 verdict==SUPPORTED
clause_accept_D(clause):     # 新增:若 claim_type ∈{REC,UNCERTAIN}
                             #   ∧ numeric_anchors(bare) 非空
                             #   → 以 C-FACT 语义重判(需证据全文)
                             #   否则现行类型路径
clause_accept_BD:           B ∨ D
```

D 的重判需要 claim 全文+证据:金标面天然可用;benchmark 面对
taxonomy 的 48 字符截断文本——**处理**:重判只用数字锚+证据
(锚提取不受截断影响·定性 bigram 受影响时按保守=不翻计入,
披露截断影响率)。

### 3.2 双面重放

**安全面(金标 104·clause-aware·与冻结 shadow 评估器同约定)**:
逐 case 逐子句判四臂 → escape=接受∧期望∈{UNSUPPORTED,
CONTRADICTED};分族计数(N1-N10);对照 Arm-0 基线得**新逃逸**。

**收益面(134 失败 claim 按记录聚合)**:记录翻转=该记录全部失败
子句过臂∧无 no_citation 违规;新过 claim 风险画像(数字/产品/
监管计数+type 分布)。

**暴露面(B 臂答案扫描·D 专项)**:REC/UNCERTAIN∧NUM_RE 子句计数
(K.29-C 实测=0·复跑确认+若>0 逐条列样)。

**探针锁**:7 探针四臂行为表(B 需 3/4 过·D 需 F-1 两针 REJECT)。

## 4. 输出指标（任务规定全项）

### Safety（硬门·任一>0 即 Arm 出局）

| 指标 | 定义 | 数据源 |
|---|---|---|
| new escape count | Arm vs Arm-0 在金标攻击面的新增接受 | 金标重放 |
| R3/R4 escape count | benchmark R3/R4 记录新翻转中含高危新过 claim | 收益面 |
| numeric escape count | 新过/新接受中含数字锚的 claim | 双面 |
| contradiction escape count | 期望=CONTRADICTED 被接受 | 金标(N7/F2 族) |

### Utility（收益·如实上界声明）

| 指标 | 定义 |
|---|---|
| grounded flip count | citation-gate 拒→模拟过(终 attempt 上界) |
| refusal reduction | 翻转/46(main+flash 合并与分槽双报) |
| paraphrase acceptance | E 类(82 条)被各臂接受的比例 |

### 附带报告

- false refusal 变化(金标 P 族:Arm-B/D 预期=0 变化·如实验证)
- per-family 逃逸矩阵;截断影响率(benchmark 面 D 重判保守计数占比)
- N4-3 基线逃逸(预期四臂同值=1·不归因候选)

## 5. 预期结果（先验·待实测覆盖）

基于 K.29-C 已有 C3v2 数据:B≈2/1 翻转·0 新逃逸;D≈0 翻转
(F-1 暴露 0)+B 臂答案扫描预期 0;BD≈B。若实测显著偏离(
如 D 在金标面引入任何新逃逸)→ 停止并升级 Owner(设计缺陷信号)。

## 6. 实现约束

- 新文件 tools/k29c_fix3_simulation.py(约 ~250 行·复用
  calibration_study 的 judge/正则);**不修改**该既有工具。
- 全部离线;不触 WeKnora/LLM(金标自带证据);可在分钟级完成。
- 产出 tmp/obs/k29c_fix3_simulation.json(逐 case 审计轨迹+
  四臂指标),供 Owner Decision v2 引用。

## 7. 与 OD-12 的关系

本模拟=S0 离线重放层(OD-12 状态机的证据预备);它**不触发**任何
Gate——Gate 判定发生在 FIX-3-IMPL(若授权)的金标+回归阶段。
