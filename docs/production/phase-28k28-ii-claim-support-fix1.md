# 28.K.28-II-FIX1 · Qualitative 归一化对称修复

Date: 2026-09-29 · **K.28-II-FIX1: PASS**（DoD §13 十五项全过）·
改动=claim_support.py 单点+5 项回归

## 1. Root Cause

qualitative 支持判定**单侧归一化**：claim 侧 `[^一-鿿]` 剥离产生跨
标点 bigram（`（五）自营`→`五自`），证据侧以原始 corpus_text 做成员
检查——「五自」于原始文本不存在（`）`阻隔）→ 逐字引用 27/28 bigram
→ PARTIAL → 误拒（Live-Gray SUP 3/3 复现）。离线语料 fixture 无
列举标点形态故未触发。性质=**False Refusal（fail-closed 方向）**，
非安全逃逸（Live-Gray 已证 escape/leakage 三零）。

## 2. Minimal Fix（§2-3/§6）

- 提取共享 `_cjk_norm()`（同一 `[^一-鿿]` 规则），claim 侧与证据
  `corpus_text` **双侧同函数**归一化后再做 bigram 成员判定。
- **零语义/阈值变更**：SUPPORTED/PARTIAL/UNSUPPORTED/CONTRADICTED
  定义、overlap 阈值、数字/实体锚定、产品身份、时间窗、矛盾检测、
  taxonomy、LLM OFF——全部原样。无任何模糊匹配/降阈/删检查。

## 3. Regression（§5·test_k28ii_claim_support.py 新 5 检查）

- **FIX1-01** 列举标点逐字引用（live 缺陷原样本「（五）自营网络
  平台…访问链接[E1]」× 含标点证据）→ **SUPPORTED**（原 PARTIAL）✓
- **FIX1-02** 冒号/顿号/分号形态一致通过 ✓ + **对照**：真实缺失
  内容仍拒（对称化未引入放宽）✓
- **FIX1-03** 「（2026版）等待期为90天」锚点无年份污染
  （=[("等待期","90","天")]）+ 数字路径 SUPPORTED 不变 ✓
- 套件 **48/48 ALL GREEN**（原 43+新 5）。

## 4. Metrics Before / After（§8）

| 指标 | 修复前 | 修复后 | 安全条件 |
|---|---|---|---|
| False Refusal（逐字支持误拒·live SUP） | **3/3** | **0/3**（全 grounded+流式） | ↓ 目标达成 |
| False Support（冻结语料 FP） | 5 | **5（不变）** | 未增加 ✓ |
| Unsupported Escape（cited 集） | 0 | **0（不变）** | 未增加 ✓ |
| Support P/R（语料） | 0.80/0.80 | 0.80/0.80 | 不变 ✓ |
| 语料 exact | 81.55% | 81.55%（fixture 无标点形态·零 delta 如实） | — |

## 5. FIX1 Live（§9-10·Runtime 重启载新码）

- Runtime：**PID 25928**·16:07:43·claim_support.py mtime 16:05<start
  （FIX1 码载入）·`CLAIM_SUPPORT_ENABLED=1`·health 200。
- **L1/L2**：SUP×3（真实 WeKnora 证据+逐字引用）→ **grounded
  refs=[E1]+流式 delta**（t_first 0.001-0.092s ≪ 终局）——修复前
  同输入 3/3 误拒 → 现 0/3。
- **L3 RV4-B**：Qualified 健康险法规×「等待期90天」→ **仍 REFUSED** ✓
- **L4 partial**×2：仍拒·deltas=0（未支持尾零外流）✓
- **L5 wrong-product**×2：仍拒 ✓
- **L6 citation-only**×3：仍拒+regen 反馈含 claim_support 违规 ✓
- RV4-A：检索=农业条例→**C2 0 qualified**（seal 不动）✓
- 开关签名：OFF=旧路径直投→ON 复拒（双向）✓
- G1a 真 LLM：仍 citation-gate 拒（**既有引用校准·非本修复范围·
  与 Phase 2 前同签名**——如实保留）。

## 6. Streaming（§11）

支持路径 T_first（0.001-0.092s）< 终局 ✓·deltas=1/答案；拒答路径
deltas=0（零「先流出后拒答」）✓·K.26 实现零触碰。

## 7. Security（§12）

in-process 全部 delta/transcript + SUP 答案扫描：claim_id/
evidence_refs/support_reason/support_type/UNSUPPORTED/CONTRADICTED/
tool/agent/run/ART → **零命中**。修复仅动内部成员判定，无新消费者
可见面。

## 8. Scope Audit（§1）

改动仅：`runtime/grounding/claim_support.py`（+共享归一化函数·
证据侧一行应用）+ `tests/runtime/test_k28ii_claim_support.py`
（+1 节 5 检查）。Intent/C1/C2/Router/K.26/WeKnora/taxonomy/
semantics/ProductQA workflow/Planning/LLM/Streaming/UI/EventBus/
Artifact——零触碰。

## 9. Offline Regression（§7）

FIX1 专项 48/48 ·K.28-II 全套（同文件）·**865 passed + 2 skipped**
全电池零失败。Shadow 防线复核：citation-only/wrong-product/
wrong-version/temporal/contradiction/partial/RV4-B/stuffing 类
（by_class）逐项与修复前一致——**无防线下降**。

## 10. Rollback

单文件还原即回缺陷态（缺陷态=fail-closed 误拒·无安全面变化）；
灰度开关仍为 env/rules 双通道（未动）。

## 11. Remaining Observation Gaps（沿 Live-Gray·未变）

G6 contradiction/temporal NOT_OBSERVED（DATA/R5-by-design）·G5 机制
唯一归因 OBSERVATION_GAP（结果拦截已证）·真实 LLM 支持通过率仍受
既有引用校准（G-2/D-04）与 G-1 语料约束。

---

```
K.28-II-FIX1: PASS

Claim Support: IMPLEMENTED
Gray: READY_FOR_REVERIFICATION（:8123 已载 FIX1 码灰度运行）
Intent: SEALED · C1: SEALED · C2: SEALED · K.26: SEALED
LLM Claim Judge: OFF · Planning: NOT ENABLED
```
