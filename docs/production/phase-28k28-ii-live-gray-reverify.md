# 28.K.28-II-LIVE-GRAY-REVERIFY · FIX1 后灰度纯复验

Date: 2026-09-29（16:4x-17:1x）· Mode: **REVERIFY ONLY**（生产逻辑
修改=0）· **K.28-II-LIVE-GRAY-REVERIFY: PASS**

## 1. FIX1 已修复的问题（背景·不重测代码）

qualitative 单侧归一化缺陷（跨标点 bigram → 逐字引用 PARTIAL 误拒）
——由 K.28-II-FIX1 以共享 `_cjk_norm()` 双侧对称化修复（改动=
claim_support.py 单点+5 回归；本阶段零改动）。

## 2. 本次重新验证的数据

### §二 环境

| 项 | 值 |
|---|---|
| Runtime | :8123 **PID 25928**（=FIX1 启动进程·未重启）·start 16:07:43·health 200 |
| Commit | e306118（FIX1 为工作树·claim_support.py mtime 16:05:27 < start=已载入·sha `c28957d8`） |
| **CLAIM_SUPPORT_ENABLED** | **=1**（launch env） |
| LLM Claim Judge | **OFF**（无 authority 路径） |
| Planning Claim Support | **NOT ENABLED**（无接入） |
| WeKnora/PG | 401-alive / :5433 |

### §三 ON/OFF 双向签名（复用既有 signature）

ON=同输入拒答（G2a）→ **OFF(env=0)=旧路径直投**（grounded refs=[E1]
deltas=1）→ ON 复拒。双向 ✓·无 500·无内部 metadata·streaming 契约
无变化。

### §四 L1-L6 矩阵（真实 WeKnora+真实 rules+env1·新证据
`k28ii_reverify_matrix.json`）

| 场景 | 结果 | 判定 |
|---|---|---|
| L1/L2 支持型+FIX1 场景 | **grounded refs=[E1]+流式**（见 §3·False Refusal 专项） | ✅ |
| L3 RV4-B | **REFUSED·不投递**（FIX1 未放行） | ✅ |
| L4 PARTIAL ×2 | refused·**unsupported tail delta=0** | ✅ |
| L5 Wrong Product ×2 | refused | ✅ |
| L6 Citation-only ×3 | refused+regen 反馈含 claim_support 违规 | ✅ |
| RV4-A（C2 边界） | 检索=农业条例→**C2 0 qualified**（seal 不动） | ✅ |

### §六 False Refusal 专项（`k28ii_reverify_fr.json`）

FIX1-01 列举标点逐字 ×5（三句×3 轮）→ 全 **grounded**（t_first
0.0-0.097s）·FIX1-03「（2026版）等待期90天」数字腿（真实 chunk 无
数字→fixture 数值项附加·如实注记）→ **grounded**。
**FIX1 False Refusal = 0/6** ✓。**真实缺失对照**（全家投保）→ 仍
refused ✓（对称化未放宽）。G1a 真 LLM 仍 citation-gate 拒（既有
G-2/D-04·非本线·如实保留）。

### §五 Shadow Safety（`k28ii_reverify_metrics.json`）

FP=**5**（≤ baseline 5 ✓）·**Unsupported Escape=0**（cited 集·✓）·
P/R 0.80/0.80 不变·FSR 20%/7.94% 不变。九类攻击面 by_class 与
FIX1 后基线逐类一致。

## 3. 安全边界

消费者边界综合扫描（reverify 全部 delta/transcript/answer + API
transcripts）：run_id/claim_id/support_state/evidence_refs/
support_reason/support_type/internal score/router internals/
qualification internals/debug 字段 → **零命中**。

## 4. Streaming 行为

支持路径：T_first（0.0-0.097s）< T_final ✓·delta_count=1/答案·
final answer 完整（grounded refs=[E1]）。拒答路径：**delta_count=0**
（RV4-B/partial/wrong-product/citation-only 全零·无「先流出后拒答」）。
K.26 实现零触碰。

## 5. Frozen Component Regression（§九·净环境）

Intent（含 C1 12 节）+C2（k27rv4c2 8 节）+K.26（k22 6 节）+
FIX1 套件（48 检查）targeted **26 收集项全过**；全电池
**865 passed + 2 skipped**（386s·与基线完全一致·数字无变化）。
（过程注记：一次 targeted 运行因 hd2 env 泄漏触发 strict 预检
ENCRYPTION_REQUIRED——净环境复跑全绿·环境性非行为性。）

## 6. Remaining Gaps（沿 FIX1/Live-Gray·未变）

G6 contradiction/temporal NOT_OBSERVED（DATA/R5-by-design）·G5 机制
唯一归因 OBSERVATION_GAP·真实 LLM 支持通过率受既有引用校准
（G-2/D-04）+G-1 语料约束（非 Claim Support 线）。

## 7. Scope Audit（§十）

本阶段生产逻辑修改=**0**：tracked-modified 41（=基线）；全部生产
文件 mtime 早于本阶段起点（claim_support.py 16:05=FIX1·其余
intent/gate/loop/rules/语料全部更早）——Intent/C1/C2/K.26/Router/
Planning/LLM Judge/Shadow corpus/OD-12 零触碰。

## 8. Owner Decision 前置条件

**满足**：FIX1 修复 live 持续有效（0 误拒）·安全三零（escape/
false-support 不增/consumer 泄漏 0）·流式契约保持·冻结组件零
回归·开关双向·RV4-B/PARTIAL/wrong-product/citation-only 全拦截。
→ **Claim Support: READY_FOR_OWNER_DECISION**（OD-12 阈值/扩大灰度/
Planning 轨道由 Owner 裁决）。

---

```
K.28-II-LIVE-GRAY-REVERIFY: PASS
Claim Support: READY_FOR_OWNER_DECISION
```
