# 28.K.28-II-SHADOW · Claim→Evidence Support 影子验证

Date: 2026-09-29 · Baseline: e306118 · Mode: **SHADOW ONLY**（零生产
行为变更·零 authority）· Status: **READY_FOR_OWNER_DECISION**
（implementation-readiness: **READY_FOR_K.28-II-IMPL**·受 OD 裁决约束）

## 1. Executive Summary

在冻结影子语料（114 例）上验证设计假设：**确定性表面层（数字/实体
锚定+产品绑定+有效窗口+矛盾检测+类别豁免）能否在不引入 LLM authority
的前提下把 Unsupported Insurance Fact Escape 从现行 citation-
presence 门压到近零？** 实测：**能**——现行门对带引用的 unsupported
事实主张 **15/17 逃逸（88.2%）**，影子策略（句级 hold+终局拒绝）
**0/17 逃逸**；七类攻击面（citation-only/同题/错版本/时间窗/矛盾/
RV4 农业条例/stuffing）**全部 100% 捕获**。LLM 对照（30 例×2·稳定
30/30）exact 76.7% 低于确定性层 80%，且其仅有的 2 例假支持恰好落在
**错产品与时间窗**——语义层不可替代结构层的实证。残余弱点如实：
复合句定性尾巴（FS-06）、语义近邻否定式（N8 67%）、RV4-B 标签粒度。

## 2. Shadow Architecture

`runtime/grounding/shadow/`（新包·**零生产 import 反向验证**·零写盘）：
claims.py（OD-1 六类 typing+OD-2 句主原子+确定性子句拆分）·
support.py（OD-3/5/6 判定+OD-7 投递策略模拟）·llm_shadow.py（OD-11
对照器·进程内 env·fail-closed）。评测器 tools/claim_shadow_eval.py +
tmp/probe_k28iish_llm.py；证据 tmp/obs/k28iish_*.json。

## 3. Corpus（tests/golden/claim-evidence-shadow.v1.json·v1 冻结）

**114 例**：P40（真实法规/目录事实/fixture 数值/豁免类）·N62（N1
citation-only 7/N2 同题 8/N3 部分 8/N4 错产品 6/N5 错版本 5/N6 时间
窗 6/N7 矛盾 6/N8 语义近邻 6/N9 RV4 形态 4/N10 stuffing 6）·
RV4-A/B 两层回归 ·S10 流式多句。来源标注：pilot-corpus(real)/
catalog(real:P001 保费400)/fixture(TEST-DATA)。**勘误 2 处**（E1
N7-6 窗口消解→SUPPORTED；E2 N9-1/04 建议形态→N/A）留痕在案。

## 4. Claim Taxonomy 实测

typing 准确率 **94.2%**（103/109 判对；失分=建议/推导边界与
「因此建议」复合形态）。六类豁免语义全部按 OD-1 生效
（C-USER/REC/CALC/UNCERTAIN/DERIVED → NOT_APPLICABLE）。

## 5. Deterministic Baseline（§5·n=103）

- 总体 exact **83.5%**
- **C-FACT（n=88）**：TP 20·FP 5·FN 5·TN 58 →
  **Precision 0.80 / Recall 0.80**
- **False Support Rate**：判 SUPPORT 中实未支持 = **20.0%**（5/25）；
  实未支持中被判 SUPPORT = **7.94%**（5/63）
- 分类 exact：N1/N2/N5/N6/N7/N9/N10=**100%**·N4 83%·N8 67%·
  N3 50%·P 77.5%

## 6. LLM Shadow（§6·30 例×2·glm·temperature 0.1）

应答 30/30·**稳定 30/30**（同输入零漂移）·exact vs expected
**76.7%**（确定性层 80%）·llm_reason 全程在案。

## 7. Agreement Matrix（§7）

| Det \ LLM | Supported | Unsupported |
|---|---|---|
| Supported | 6 | 2（det 风险：FS-06 复合×1+定性×1） |
| Unsupported | **1（LLM 风险）** | 21 |

**LLM 仅有的假支持 = N4-3（错产品）+ N6-1（时间窗）**——恰为结构层
强项；Det 风险 2 例为复合定性尾巴（语义层理论强项但 LLM 也未抓住）。
Partial/Contradiction/Temporal 单列：矛盾检测 det 6/6（LLM 落
UNSUPPORTED 不辨冲突）；时间窗 det 6/6（LLM 0/2 捕获）。

## 8. False Support Analysis（§8·5 例逐条：N3-3/N3-6/N3-7/N3-8/N4-3）

**[LEDGER-AUDIT 2026-09-29 更正（Case A 笔误）]**：初版误引中间运行
的「FS-02×1」——终版数据无 FS-02；FS 集=**5 例**，与 FP=5 /
P=0.80 / FSR=20% 完全自洽。终版逐条：
- **FS-06 ×4**（N3-3/N3-6/N3-7/N3-8）：复合句定性尾巴——数值子句
  已证≠尾巴已证（子句拆分已收窄但尾巴句语义覆盖仍弱）
- **FS-04 ×1**（N4-3）：产品名≠id 无解析——生产有 find_product_in
  可复用
无 FS-01（citation-only 0 逃逸）/FS-02/FS-03/FS-05（时间窗 0 逃逸）/
FS-07..FS-10。

## 9. Unsupported Escape Analysis（§9·核心安全结果）

带引用+C2 后证据的 at-risk 集 17 例：**现行 citation-presence 门
逃逸 15/17（88.2%）→ 影子策略逃逸 0/17（-100%）**。影子策略逐例：
unsupported 事实句 hold→regen 模拟（静态二 pass）→终局 refused——
含 15×[E1] stuffing 形态与 RV4 农业条例形态全部拦截。

## 10. RV4 Two-Layer Regression（§3）

- **RV4-A（C2 层）PASS**：真实 `_qualified_evidence` 对 RV4 原文
  query×农业条例 → **0 qualified**（C2 seal 不受影子影响·实证）。
- **RV4-B（Phase 2 层）核心证明成立**：健康险法规（对 重疾/医疗 族
  query **通过 C2**）×「该重疾险的等待期为90天」→ 影子判定
  UNSUPPORTED（证据只言参数由合同约定）→ hold。标签与语料期望
  PARTIAL 有粒度差（**policy-equivalent**：两者都不投递）——
  **Qualified ≠ Supportive 被确定性层捕获**。

## 11. Claim-Type Breakdown（§9/§13）

C-FACT P/R 0.80/0.80（上表）·C-USER/C-RECOMMENDATION/C-CALCULATION/
C-DERIVED/C-UNCERTAIN 豁免 exact=100%（语料内无泄漏案例；typing
层面 94.2%）。Planning（C-DERIVED）与 Recommendation 不要求外部
引用（OD-9 ✓）；其内嵌事实前提（S8「全行业最低价」形态）按 C-FACT
拦截 ✓。

## 12. Contradiction

det **6/6**（跨证据同标签异值→CONTRADICTED·OD-5 fail-closed 不裁
优先级）；流式 S6（答案内 90 vs 180）双句均 CONTRADICTED（优于语料
逐句期望）。LLM 不辨冲突（落 UNSUPPORTED）——结构层独有。

## 13. Temporal

det **6/6**（窗口外证据→不可用→UNSUPPORTED；N5 版本案例经窗口
建模 5/5）；复用 effective_from/to 字段（OD-6 ✓·无第二套治理）。
LLM 0/2 捕获（N4-3/N6-1 之一即时间窗）。

## 14. Streaming S1 vs S3（§10·离线模拟·SSE 未动）

确定性层语料上 **S1≡S3**（主张粒度=句/子句，两策略仅投递时机异——
逃逸/拒绝结果逐例相同）。S1 逐句判定 10 例答案：7/10 逐句全对
（含 2 例 anaphora「它的免赔额」句局判 UNSUPPORTED=S1 已知盲点·
fail-closed 方向）；hold 计数=答案级拒绝 8/10（负例答案）。
**结论材料**：S1 无确定性层代价且保 K.26 T_first；语义层若引入只能
S3/离线（设计 §11 预判成立）。

## 15. Safety（§11）

shadow 包零生产 import（grep 反向验证）·零文件写（仅评测器写
tmp/obs）·零 EventBus/DB/Runtime 触碰·Consumer 不可见（无任何
生产路径引用）·无 ID/prompt/tool/CoT/evidence 内件外泄面（不进
生产流）。

## 16. Regression（§12）

Intent 套件+C1 12 节+C2 8 节+K.26 6 节 targeted **26/26** ✓；
全电池 **865 passed + 2 skipped** ✓（427s·零新失败）。
K.28-I/C1/C2/K.26 全 unchanged；RV4 已入影子语料（N9+RV4-A/B）。

## 17. Observed Metrics（§13·不设阈值·OD-12）

| 指标 | 观测值 |
|---|---|
| Claim Support Precision / Recall (C-FACT) | 0.80 / 0.80 |
| False Support Rate | 20.0%（of judged-S）/ 7.94%（of actual-unsup） |
| **Unsupported Insurance Fact Escape** | 现行门 88.2% → 影子 **0%**（at-risk 17） |
| Partial Support Accuracy (N3) | 50%（4/8） |
| Contradiction Detection | 6/6（LLM 0/6） |
| Temporal Validity Detection | 6/6（LLM 0/2 样本） |
| Citation-Support Consistency | citation-only 类 7/7 拦截（N1 100%） |
| Typing | 94.2% |
| LLM agreement / exact / stability | 76.7% / 76.7% / 30/30 |

## 18. Risks

- FS-06 复合定性尾巴与 N8 否定式=确定性层天花板（词法盲区）；
  LLM 对照也未能补（两 det 风险例 LLM 亦未捕获）
- 语料 fixture 占比高（数值事实多为 TEST-DATA）——真实流量分布
  待 shadow 上线后校准
- typing 边界（建议/推导）5.8% 失分会在生产转化为豁免误用（方向：
  多豁免=少拦截，保守但漏防）
- S1 anaphora 盲点（句局 fail-closed·可接受）

## 19. Owner Decisions（沿设计 OD + shadow 新增）

OD-4 判定法路线（**建议更新：D-hybrid 实证成立——A 层独立即获
escape 0%，LLM 语义层不具替代性仅可作 shadow 增强**）·OD-7 策略
（B+C 模拟即本 shadow 所用）·OD-8 流式（S1 无代价材料齐）·
OD-12 阈值（观测分布如上·建议 escape=0 为不变量、FSR 目标待真实
流量）·新增：OD-14 LLM 对照是否常驻 shadow；OD-15 FS-06/N8 词法
天花板是否接受为 V1 边界（vs 语义层立项）。

## 20. Implementation Recommendation（§16 八问）

①确定性层可行 ✓（80/80 P/R·攻击面全捕获）②false support 显著降
（逃逸 88.2%→0%）③escape 降 ✓ ④**LLM 非必要**（低于 det 且漏结构
类；仅 shadow 增强）⑤S1 值得（零代价·保 T_first）⑥分类差异化策略
必要 ✓（豁免语义已验）⑦C2 可完全不动 ✓（RV4-A 实证）⑧最小面=
segmenter 相邻挂接+rules 块+additive schema（设计 §19）。
→ **READY_FOR_K.28-II-IMPL**（待 Owner OD 裁决后启动）。

---

```
K.28-II-SHADOW: READY_FOR_OWNER_DECISION

Production authority: OFF
LLM authority: OFF
Intent: SEALED
C1: SEALED
C2: SEALED
K.26: SEALED

STOP.
```
