# K.29-C FIX-3 · Claim Support Calibration Design（ADR · 仅设计）

Date: 2026-10-02 · Status: **DESIGN ONLY — 待 Owner 裁决**
FIX-3 ≠ Implementation · FIX-3 ≠ Authority Change · FIX-3 ≠ Hybrid Enable

---

## 1. Problem Statement

**旧问题(否决)**:「如何让更多 paraphrase 通过」——这是阈值调参框架,
K.29-C 已证明其在当前判定器上结构性不安全。

**新问题(本设计采用)**:

> 如何在保持高危 claim 零逃逸的前提下,提高**语义等价** claim 的
> 接受能力。

两条硬不变量(任何方案不得违反):

- **INV-1 高危零逃逸**:数字/数量、产品/合同事实、监管断言、赔付
  承诺、建议句内数字前提——在**确定性层**拦截,任何语义层/豁免
  规则不得触碰(K.29-C:全候选高危面 0 逃逸必须保持)。
- **INV-2 fail-closed 保持**:语义层错误/超时/不可判定 → 维持现行
  拒答,永不放宽为通过。

## 2. Current Evidence

| 证据 | 来源 | 含义 |
|---|---|---|
| 134 失败 claim:E(paraphrase)=61% 主导 | K.29-C 分类学 | 收益主体在语义等价类 |
| 修复 delivery 后 grounded 仍 0/30×2 | K.29 Phase 2 | 判定层是唯一剩余阻断 |
| C2(接受 PARTIAL)=10/7 翻转·**+2 金标逃逸(N8-5 否定反转)** | K.29-C 金标重放 | 词法覆盖比例 ≠ 语义等价;阈值放宽不可行 |
| C4(ws 归一/元数据投影)=+4 假阳性逃逸 | K.29-C | 归一化制造跨词界 bigram;公式否决 |
| C3v2(护栏豁免)=0 新逃逸·2/1 翻转 | K.29-C | 唯一安全确定性杠杆·收益薄 |
| F-1:建议句数字绕过支持判定 | K.29-C 探针 | 类型豁免未实现「事实前提必须支持」(K.29 设计 §5 原文) |
| N4-3:产品身份依赖 product_id 元数据 | K.28-II 账本已知 | 既有 1 例逃逸·与本设计正交 |

## 3. Why Threshold Tuning Failed（机理层）

1. **否定盲区**:判定器 CONTRADICTED 仅覆盖数字锚冲突;证据
   「不返还保费」vs claim「可以返还保费」bigram 覆盖达标 → PARTIAL。
   覆盖率与「语义方向」正交——**任何覆盖率阈值都放行反转句**。
2. **归一化副作用**:空白剥离把「责任 等待期」粘成新 bigram——
   归一化提高召回的同时制造假阳性匹配;无边界保护的归一化不可用。
3. **覆盖 ≠ 等价**:PARTIAL(50-99% bigram 覆盖)混合了真改写、
   过度泛化(「所有」)、部分真+部分假(N3 复合句)三种语义状态——
   词法层原理上不可分。

结论:**E 类 61% 主体的解锁必须引入语义级判定**;确定性层只做
高危拦截与护栏豁免(B 类 23% 中的安全子集)。

## 4. Candidate Solutions

### Option A — 保持现状（C1）

- **安全收益**:最大(fail-closed 全覆盖;唯一已知逃逸 N4-3 与本
  线正交);零变更成本;与 Batch-2 UAT 完全兼容(拒答=安全正确)。
- **用户体验损失**:QA grounded=0/30×2 持续;保险通识/概念题
  (R0/R1)全部失语;修复 delivery 后的引用纪律改善无法转化为
  用户可见价值。
- **Hybrid 价值限制**:MODE-B 生成能力已证实(K.29-B 儿童案例
  6/6 有界生成·真违规 0),但终门把一切拦下——**Hybrid 轨道整体
  停摆于最后一米**;29-C shadow 信号持续被校准噪声污染。

### Option B — C3v2 最小安全修复（确定性·薄收益）

**允许豁免(仍需过引用存在性门)**:
- B1 证据缺失叙述:META 模式(证据未提及/未载明/资料未提供/无法
  基于…)∧ **零数字锚 ∧ NUM_RE 零命中**(提及「该产品」在
  否定性叙述内=安全)。
- B2 纯程序性建议:GUIDE 模式(建议查阅条款/如实告知/通读…)∧
  零锚 ∧ NUM_RE 零命中 ∧ HIGH_RISK 词零命中。

**永远禁止豁免(任何措辞)**:
- 含数字锚(含区间「3-5倍」·百分比·年龄·天数)的 claim;
- 产品指称(P0xx/demo-/该产品/这款/某产品)**于肯定性事实句中**;
- 监管断言(保险法/办法/令第/施行/监管要求);
- 赔付/续保承诺(保证续保/赔付/返还/承诺);
- 否定标记事实句(不返还/不属于/不赔——反转风险面·待 Option C
  语义层解决前一律拒);
- 一切 CONTRADICTED 判定。

**需新增 negative corpus(实现前置)**:否定反转族 ≥10·建议包裹
数字族 ≥10·meta 内嵌数字族 ≥8·meta 内产品族 ≥6·程序建议正例
≥10(见 §6 Benchmark v2)。

**预期**:main/flash 翻转 2/1;新逃逸 0;价值=B 类诚实叙述解锁+
防御纵深,非可用性跃迁。**默认 OFF·env 旋钮·staged**(沿
CLAIM_SUPPORT_ENABLED 惯例)。

### Option C — Semantic Judge Shadow Layer（仅设计·shadow≠authority）

```
claim
  ↓
[1] deterministic safety filter（现行 claim_support + Option B 护栏 + 高危清单）
      ├── HARD BLOCK（数字/产品/监管/赔付/建议数字前提/CONTRADICTED/否定标记）
      │     → 拒答/重生成（行为与今日逐字节一致）
      └── PARAPHRASE CANDIDATE（cited ∧ 非硬类 ∧ 词法判定≠SUPPORTED）
            ↓
[2] semantic equivalence judge（LLM·shadow）
      输入 = claim(去引用标记) + 被引用证据 chunk（仅此,防上下文渗漏）
      输出 = {entailment: ENTAILED|NOT_ENTAILED|PARTIAL,
              contradiction: bool, confidence: 0-1, reason}
      错误/超时/不可判定 → 视为「不升级」（INV-2 fail-closed）
      ↓
[3] shadow 记录（仅观测:per-claim 行持久化——补 K.28-II 已知粒度缺口）
      指标 = would-flip（安全收益）/ would-escape vs 金标负例（安全成本）
      ↓
[4]（未来·Owner 门槛）阈值冻结 + 人工抽样验证 + 才可议 authority
```

- **不变量**:shadow 输出永不改变本轮行为(拒答照旧);语义层只能
  「升级」非硬类 claim,硬类清单在确定性层先行终局。
- **判定设计要点**:单 claim 单证据 chunk 输入(防全上下文渗漏);
  输出结构化(entailment/contradiction 分离——直接检测否定反转);
  模型=qa 槽位或专用小模型(成本≈每次拒答 5-20 个候选 claim·可批)。
- **验证门槛(S1→S2 前置)**:金标负例(含 N8 反转族/新 v2 语料)
  100% 拒绝;benchmark E 类 would-flip ≥40%(否则不值得);错误率
  <5%;人工抽样 50 例一致率 ≥90%。
- **这是 E 类 61% 主体的唯一安全路径**;但它是**新能力轨道**
  (LLM judge),不是校准——须独立立项与观察窗口。

### Option D — 建议句专项防御（F-1·类型感知政策）

问题:「建议保额3-5倍」因含「建议」整句定型 C-RECOMMENDATION →
类型豁免 → **数字前提零检查**(仅引用存在性)。K.29 设计 §5 原文
「RECOMMENDATION 本体豁免·**事实前提必须支持**」未在实现落地。

设计:豁免必须**前提感知**——

```
对每条 claim(无论类型)执行数字前提扫描:
  if type ∈ {C-RECOMMENDATION, C-UNCERTAIN} ∧ 数字锚/NUM_RE 非空:
      拆分 = 数字前提(事实断言) + 建议外壳
      数字前提 → 按C-FACT 全规(引用 + SUPPORTED)
      前提不过 → 整句拒(维持 fail-closed)
  else: 现行类型路径不变
```

- 与 Option B 正交且互补(B 管 B 类豁免·D 堵类型豁免漏洞);
  两者可打包为同一 FIX-3 实施阶段。
- 属 SEALED claim_support 变更(classify/check 路径)→ 需解封授权。
- negative corpus:建议+数字族 ≥10(Q3 family 4)·正例(前提有据
  的建议句)≥6。

### 组合建议（描述·不选择）

- **最小包** = B + D(纯确定性·0 新逃逸·翻转 2/1+纵深闭合)
- **完整包** = B + D + C-shadow(E 类主体的安全解锁路径;shadow
  零 authority·可长期观察)
- A = 不立项(维持现状)

## 5. Security Analysis

| 威胁 | Option B | Option C | Option D |
|---|---|---|---|
| 否定反转(N8-5 型) | 拒(否定标记入禁豁免清单) | shadow 判 contradiction→不升级;authority 前提=金标 100% 拒 | 不涉及 |
| 建议句数字(F-1) | 部分(护栏挡 GUIDE 类) | 硬类清单先拒 | **根治**(前提拆分全规) |
| 跨词界归一假阳性(C4 型) | 不引入归一化 | 不涉及 | 不涉及 |
| 引用滥用(N1/N10 stuffing) | 引用存在性门不动 | judge 只看被引 chunk | 同左 |
| 产品身份(N4-3 型) | 不变(既有已知 1 例) | 硬类→确定性拒 | 不变 |
| 语义层被绕过(对抗措辞) | N/A | INV-1 硬类终局在确定性层;judge 只能升非硬类;judge 失败=不升级 | N/A |
| 上下文渗漏 | N/A | 单 chunk 输入约束 | N/A |

**R3/R4 面**:三方案均保持 0 产品/数字逃逸(benchmark 重放证据+
硬类清单前置);Hybrid 的 R4 保护仍依赖 OD-H3(正交·不变)。

## 6. Benchmark Plan（v2·schema 见
tests/golden/k29c_fix3_taxonomy.v2.json）

六族(最低配额):paraphrase 正例 ≥20 / 否定反转 ≥10 / 通用建议 ≥10 /
建议+数字 ≥10 / 矛盾断言 ≥10 / 法规产品 ≥15。来源三分:金标派生
(带原 case 锚定)/ benchmark 派生(A-fixed/B 臂真实生成·标注)/
对抗手写。冻结程序沿 intent-golden 惯例(首评→受审修正→冻结→
回归锁)。**本任务只交付 schema,不生成语料。**

## 7. Rollout Strategy（若 Owner 批准实施）

```
FIX-3-IMPL(B+D) → 金标 v2 冻结 → 回归(OD-12 式三层 Gate:A 硬安全/
 B 质量/C 运营) → env 默认 OFF → S0 离线重放(本文 K.29-C 工具复用)
 → S1 in-process 灰度(沿 CLAIM_SUPPORT_ENABLED 先例) → S2 Owner 复验
(C-shadow 若同批:S1' 影子并行记录·零行为变化·观察窗口 Owner 定)
```

## 8. Rollback Strategy

- B/D:env 旋钮置 OFF → 行为逐字节回 C1(沿 FIX1/FIX2 回滚先例);
  逐条款可独立回滚(豁免清单/前提扫描分旗)。
- C:shadow 本身零行为 → 移除=停记录;若未来进入 authority(另行
  ADR+门槛),回滚=关旗+回归证明等价。
- 语料/工具新增文件独立,不触碰任何现有 Golden。

---

## OWNER DECISION REQUIRED（最多三项）

1. **FIX-3 立项范围**:A 不立项 / 最小包(B+D·解封 claim_support 需
   授权) / 完整包(B+D+C shadow 新轨道)——三选一。
2. **C-shadow 资源与观察窗**(仅当选完整包):judge 模型槽位与成本
   预算;S1' 影子观察窗口时长;would-flip/would-escape 阈值由 Owner
   沿 OD-12 模式冻结。
3. **Benchmark v2 冻结程序**:六族配额(§6)与来源配比审定;是否
   需要第二评审人(沿 intent-corpus v1.1 二审惯例)。

**STOP——不实施·不解封·不启 shadow·不动任何生产文件。**
