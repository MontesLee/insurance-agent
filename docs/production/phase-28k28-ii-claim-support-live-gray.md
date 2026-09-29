# 28.K.28-II-LIVE-GRAY · Claim Support 灰度开启 + Live 验证

Date: 2026-09-29 · **Result: K.28-II-LIVE-GRAY: BLOCKED —
LIVE_CODE_DEFECT（fail-closed 方向·零安全违规·零泄漏）** ·
缺陷修复另立阶段（K.28-II-FIX1）·本阶段零生产代码修改

## 1. Runtime Identity / 2. Gray Configuration

| 项 | 值 |
|---|---|
| :8123 | PID **15708** ·start 2026-09-29 15:48:39 ·health 200 |
| HEAD | e306118 ·claim_support.py mtime 15:19 < start（IMPL 码载入） |
| **CLAIM_SUPPORT_ENABLED** | **=1**（server 启动 env·进程内探针同值） |
| LLM Claim Judge / Intent LLM | OFF（无 authority 路径·conf_src=rule） |
| Router Authority | full（未动） ·WeKnora 401-alive ·PG :5433 ·:5273 200 |
| 行为签名 | ON=同输入拒答 / **OFF(env=0)=旧路径直投**（ON-restore 复拒）——开关双向 live 实证 |

## 3-9. Probe Matrix（进程内=真实 WeKnora+真实 rules+env1·LLM 脚本化以控制主张；API=真实全链）

| Probe | 输入形态 | 结果 | 判定 |
|---|---|---|---|
| RV4-A（C2 边界） | RV4 原文 query→真实检索 | retrieved=1（农业保险条例）→ **C2 qualified=0** | ✅ C2 seal 未动 |
| G2a/b/c citation-only ×3 | 无关主张+[E1]（确诊即赔/全家投保无等待期/偿付200%） | **refused·refs=[]·regen 反馈含 claim_support 违规**（B+C 实证） | ✅ |
| **G3 RV4-B** | 健康险法规（Qualified）×「该重疾险等待期90天[E1]」 | **REFUSED·不投递** | ✅ 核心回归 live |
| G4a/b partial ×2 | 支持头+未支持尾 | **refused·deltas=0**（未支持尾零外流；「支持头先流」形态 NOT_OBSERVED——检索 chunk 不含逐字头句） | ✅（安全）/形态未现 |
| G5a/b wrong-product ×2 | P001/P005-名 claims×法规证据 | **refused**（结果拦截 ✓；**机制唯一归因 OBSERVATION_GAP**：真实 KB 无法构数值产品事实以隔离产品门与内容覆盖——分支由离线单测证明） | ✅/缺口如实 |
| G6 contradiction | — | **NOT_OBSERVED（DATA）**：真实 KB 无可检索数字锚 chunk | 如实 |
| G6 temporal | — | **NOT_OBSERVED（by design）**：R5 在检索层已滤过期证据——支持层时间窗为纵深防御，无法经真实检索构造 | 如实 |
| G1a real-LLM | 真证据+真 glm | refused（**citation_gate_rejected·既有 G-2/引用校准问题**·与 Phase 2 无关——Phase 2 前同签名） | 既有债务 |
| SUP ×3（逐字支持对照） | 证据原文逐字句+[E1] | **refused**——暴露本阶段缺陷（§Defects） | ❌ 缺陷 |
| API ×3（真实消费链） | 三问 | 2×引用门拒+1×语料拒（既有问题）；**transcript 内部元数据泄漏=0** | ✅ 安全 |

## 10. Streaming

拒答路径 deltas=0（未支持段零外流·无「先流出后拒答」形态）；G1a 1 delta
为**段级已过门**内容（K.26 held 语义保持）；OFF 等价探针 deltas=1+直投
（旧行为复现）。T_first<T_final：进程内 t_first≈0s ≪ dur（4-60s）✓。
K.26 实现零触碰。

## 11. Consumer Safety

3 条真实 transcript 扫描（claim_id/evidence_refs/support_reason/
support_type/UNSUPPORTED/CONTRADICTED/QualifiedEvidence/[E#]/tool/
agent/run/artifact）→ **泄漏 0** ✅。消费者仅见自然语言结果/标准拒答。

## 12. C2 Boundary

RV4-A live：检索=农业条例 1 条→**C2 0 qualified**——Claim Support 未
接管也未改变 C2 结果 ✅（C2 seal 保持）。

## 13. OFF Equivalence

env=0 → G2a 同输入 **grounded refs=[E1]**（旧路径直投 stuffing=预期
旧行为）→ env=1 恢复 → 复拒。开关双向+等价性 live 实证 ✅。

## 14. Metrics（观测值）

- Unsupported Block Rate：**7/7**（G2×3+G3+G4×2+API 无一外流）
- **Unsupported Insurance Fact Escape = 0** ✅（硬性安全线）
- **Consumer Internal Metadata Leakage = 0** ✅
- **Unsupported segment leaked before final refusal = 0** ✅
- Supported Pass Rate：**0/6**（G1a 1+SUP 3+API 2 可归因样本）——被
  本缺陷+既有引用校准双重阻断（见下）
- False Refusal（逐字支持误拒）：**3/3 SUP**（缺陷直接证据）
- Wrong-product blocked 2/2 ·Contradiction/Temporal=NOT_OBSERVED
- T_first：~0s（即时首 delta）·delta_count 拒答 0 / OFF 1

## 15-16. Defects / Gaps（§17 分类）

### LIVE_CODE_DEFECT（阻断 PASS 的唯一新问题）

**qualitative 支持判定单侧归一化**：claim 侧以 `[^一-龥]` 归一化产生
跨标点 bigram（如「（五）自营」→`五自`），而证据侧以**原始文本**做
成员检查——归一化不对称 → 逐字引用含列举标点时 27/28 bigram →
PARTIAL → 误拒（**fail-closed 方向·无任何不安全外流**）。离线语料
未覆盖「列举标点逐字引用」形态故 IMPL 测试未触发。
**修复规格（K.28-II-FIX1·1 行语义）**：证据 corpus_text 同规则归一化
后再做成员检查；回归用例=本 live 缺陷样本（（五）…访问链接[E1]）+
SUP ×3 复测；随后重跑本灰度矩阵。**本阶段按 §1 硬规则未现场修。**

### 既有（非本阶段引入）

- 真实 LLM 支持通过仍受**既有引用校准**（G-2/D-04 线）与 G-1 语料
  缺口约束（Phase 2 前同签名拒答——非回归）。
- G6 contradiction/temporal NOT_OBSERVED（DATA/by-design，如上）。
- G5 机制唯一归因 OBSERVATION_GAP（结果拦截已证）。

## 17. §18 IMPL 修复回归检查

数字污染锚点（G2b「无等待期[E1]」正确拒——未误判）✓·set 无序名剥
（G5b demo-名）✓·product_id 管道+doc/refs stem（G5a）✓——四修复
在 Runtime 无回归。

## 18. Rollout Recommendation

1. **先 K.28-II-FIX1**（1 行语义修复+回归）→ 重跑本灰度矩阵（预期
   SUP→grounded·Supported Pass 恢复）。
2. 支持通过率的真实上限另受引用校准/G-1 约束（D-04/28.C 线）——
   Owner 决定是否并行推进。
3. 灰度期间安全结论可先采信：**escape/leakage/流式泄漏三零**在缺陷
   存在的情况下依然成立（缺陷仅致误拒）。

---

```
K.28-II-LIVE-GRAY: BLOCKED — LIVE_CODE_DEFECT
（fail-closed 方向；Unsupported Escape=0；Consumer Leakage=0；
Streaming Leakage=0；C2/RV4-A seal 不变；OFF 等价 live 实证）

Intent: SEALED · C1: SEALED · C2: SEALED · K.26: SEALED
Claim Support: IMPLEMENTED · Gray=ON（:8123 env=1·保持运行）
LLM Intent/Judge: OFF · Router: UNCHANGED · Planning CS: NOT ENABLED

Next: K.28-II-FIX1（Owner 授权后）
```
