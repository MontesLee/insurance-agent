# Phase 29 · Hybrid Grounded Answering — Architecture & Policy Design

Date: 2026-09-30 · Mode: **ARCHITECTURE/POLICY DESIGN ONLY**（零生产
修改·零语料/阈值/Golden 变更·全部冻结基线保持）·
**K.29-DESIGN: READY_FOR_IMPLEMENTATION**（受 §17 Owner 决策约束）

一句话原则：**LLM 不再因为 KB 缺失而完全失语；但 LLM 也不能因为
自己「知道」而获得保险事实的权威性。**

---

## 1. Problem Statement

现行 QA 切片契约=单一证据策略：`QualifiedEvidence=0 → REFUSE`。
这对 R2/R3（领域/产品事实）是正确的 fail-closed；但它把
R0/R1（通用知识/一般保险方法论）也一并拒答——真实案例
「给孩子配置重疾险前，我应该先考虑什么？」（诊断 ROOT CAUSE=A）
即此形状：Intent 正确、检索机制正常、KB 无该内容 → 整题拒答。
**问题不是 grounding 太严，而是 grounding 只有一档。**

## 2. Current Architecture Limitation（代码审计）

- `generate_grounded`（loop.py:226）：evidence 为空时 qa_agent
  直接 `insufficient_evidence` 拒答——**没有「LLM 一般知识+边界」
  的第三态**。
- AnswerContext `grounding_status` ∈ {grounded, partial_grounding,
  refused}——**无 hybrid 档**（schema additive 可扩，不动现有值）。
- Claim Support（claim_support.py）已有六类 claim taxonomy
  （C-FACT/C-USER/C-RECOMMENDATION/C-CALCULATION/C-DERIVED/
  C-UNCERTAIN）与四态判定——**已具备 claim 级分政策的基础**，
  但当前对 C-FACT 一律要求证据（正确），对其它类一律豁免
  （**缺「豁免类的输出仍需边界约束」一层**）。
- Planning 独立路径存在（intake→…→recommendation）；
  K.27-RV4-C1 已修规划延续。
- 检索层 zero-hit 可区分（governed_status=insufficient_evidence
  且 denied=0）——**「KB 没有」与「KB 有但被拒」已可分辨**。

## 3. Hybrid Grounded Answering Model

```
User → Intent（SEALED 不动）
        ↓
   Answer Policy（新·纯判定层）
        ↓ 按题面 claim 构成分配模式
   ┌──────────┬──────────┬──────────┐
 MODE-A     MODE-B      MODE-C     MODE-D
 KB_ONLY    KB+LLM      LLM_GENERAL PLANNING
（现状）   （新核心）   （新·窄）  （既有）
   └──────────┴──────────┴──────────┘
        ↓（A/B/C 共用）
 Claim Classification（claim_support 既有六类·复用）
        ↓
 Claim Support（SEALED 不动·对 DOMAIN-FACT 全权）
        ↓
 Safety/QA Gate（ggate+_full_gate 既有）
        ↓
 Final Answer（用户侧=自然语言+必要引用+必要边界声明）
```

## 4. Answer Policy（四模式·判定规则）

| 模式 | 触发 | 证据规则 | 失败行为 |
|---|---|---|---|
| **MODE-A KB_ONLY** | R2/R3 领域/产品/条款/监管/具体数字（现有 citation-gate 契约原样） | QualifiedEvidence=0→REFUSE | **现状不变**（fail-closed 保持） |
| **MODE-B KB+LLM** | R1 一般保险知识/方法论/教育 + R2 成分（混合题） | KB 命中部分走既有链；KB 缺失成分降级为 **ALLOW_WITH_BOUNDARY**（§8）；**DOMAIN-FACT 成分永不降级** | 领域事实成分 REFUSE（部分拒答=逐 claim 拒，非整题） |
| **MODE-C LLM_GENERAL** | R0 通用概念/非保险/表达写作 | 纯 LLM+边界声明；**禁具体保险事实**（输出侧仍过 claim_support：C-FACT 零证据=拦截） | 无 KB 依赖·不适用于保险事实 |
| **MODE-D PLANNING** | 个性化方案/预算/缺口（家庭+需求+风险） | 既有 Planning workflow 全链（intake→…→recommendation） | **KB 缺失≠LLM 猜方案**（Planning 的证据=工件路径·现状保持） |

模式判定输入=IntentResult+claim 预分类（复用 classify_claim 的
确定性标记，不新增 taxonomy）+检索命中形状。**单题可混合**
（如儿童重疾题=主体 MODE-B：方法论成分 ALLOW_WITH_BOUNDARY +
领域事实成分 REQUIRE_KB）。

## 5. Claim Source Policy（与 claim_support 六类核对后定稿）

| Claim Type | LLM | KB | User | Planning | Support 要求 |
|---|---|---|---|---|---|
| DOMAIN-FACT（=C-FACT 保险域子集） | ❌ | ✅ | ❌ | ❌ | **必须**（SEALED 链全权） |
| GENERAL-KNOWLEDGE（=C-FACT 非域子集/教育类） | ✅ | 可选 | ❌ | ❌ | 不要求外部证据；**要求边界声明** |
| USER（=C-USER） | ❌ | ❌ | ✅ | ❌ | 沿 ADR-022-B 裁定3 豁免 |
| RECOMMENDATION（=C-RECOMMENDATION） | ✅（框架） | 可选 | ✅ | ✅ | 本体豁免·**事实前提必须支持**（现状） |
| CALCULATION（=C-CALCULATION） | ❌ | 输入可溯源 | ✅ | ✅ | 可复算（现状） |
| DERIVED（=C-DERIVED·Planning） | ❌ | 可引用 | ✅ | ✅ | 推导链可解释（现状） |
| UNCERTAIN（=C-UNCERTAIN） | 受限 | 受限 | 受限 | 受限 | 不得伪装确定（现状） |

**关键新增仅一行**：GENERAL-KNOWLEDGE 的「允许+边界声明」——其余
全部沿用 D-08/24082d5 冻结语义。

## 6. Risk Classes

```
R0 General（非保险/表达）           → MODE-C
R1 Insurance General（方法论/教育）  → MODE-B
R2 Insurance Domain Fact（监管/惯例）→ MODE-A 成分（在 B 中 REQUIRE_KB）
R3 Product/Contract Fact（条款/数字）→ MODE-A（绝不降级）
R4 Personalized Recommendation      → MODE-D
```
映射是**claim 级**而非题级（一题多 claim 多级）——claim_support
的句级原子化已提供执行粒度。

## 7. 责任边界

- **LLM=能力**：语言综合、框架组织、教育解释、边界自declared。
- **KB=领域权威**：R2/R3 事实唯一权威（Citation≠Support 链全权）。
- **Planning=个性化推理**：用户上下文→方案（工件证据路径）。
- **Grounding/Claim Support=高风险守门**：对 DOMAIN-FACT 现状
  无损；新增=对 LLM 输出的 **C-FACT 保险域成分同样过门**
  （claim_support 已这样做——MODE-B/C 不绕过 `_full_gate`）。

## 8. 五级 LLM 无证据话语权

```
ALLOW              ：R0 通用概念（重疾险是什么=概念定义亦属此与 R1 交界）
ALLOW_WITH_BOUNDARY：R1 方法论/教育——回答+边界声明（「具体产品责任/
                    等待期/疾病定义需以具体产品资料为准」类·边界文案
                    固定模板·Owner 审定）；禁：具体产品事实/监管结论/
                    赔付承诺/具体数字结论
REQUIRE_KB         ：R2/R3（任何数字、等待期、免责、疾病定义、条款、
                    监管规定、产品责任）
REQUIRE_PLANNING   ：R4（个性化数字/方案）
REFUSE             ：高风险且不可安全泛化（现状 MODE-A 失败路径）
```

## 9. Citation ≠ Support（保持）

Hybrid 全链不改变：`[E1]` 存在≠支持——每个 C-FACT 仍过
claim_support 四态；**MODE-B 的 LLM 成分不携带 [E#]**（无证据
引用=可识别为 general 段——引用集与支持集一致性检查保持）。

## 10. 用户可见回答模型

内部（additive·不动现有 schema 值）：AnswerContext 扩
`answer_mode`（A/B/C/D）+ claims[]（claim_support 既有输出结构）。
用户侧：自然语言+必要引用+**必要边界声明**（固定文案）；不可见：
claim 类型/run_id/agent/支持态/路由内部（沿 E-2/K.1/K.27-S1 既有
边界·零新增暴露面）。

## 11. Failure Policies（六场景）

| 场景 | 行为 |
|---|---|
| 1 KB 足证 | MODE-A/B 现状 grounded（不变） |
| 2 KB 部分覆盖 | 混合：KB 段引用+general 段边界声明（新=MODE-B 核心） |
| 3 KB 全无 | R1 成分→LLM+边界；R2/R3 成分→**逐 claim 拒**（部分拒答文案=Owner 审定模板） |
| 4 LLM↔KB 冲突 | KB authoritative——claim_support/CONTRADICTED 拦截（现状）+regen（现状） |
| 5 LLM 生成不可验证保险事实 | `_full_gate` UNSUPPORTED→hold/regen/refuse（SEALED 现状·零绕过） |
| 6 实为 Planning | MODE-D→Planning workflow（Intent/C1 既有路由；**QA fallback 禁**——policy 判定层兜底到 D） |

## 12. 十案例映射（题级预期·不改 Golden）

| # | Case | Intent（现行/预期） | Mode | LLM? | KB? | Planning? | Claim Support | 失败行为 |
|---|---|---|---|---|---|---|---|---|
| 1 | 给孩子配置重疾险前考虑什么 | qa（=封金） | **B** | ✅框架 | 可选 | ❌ | 域事实成分必须 | general+边界（vs 现状全拒） |
| 2 | 重疾保额通常建议多少 | qa（OBS-1 修复后） | **B** | ✅方法论（如「通常3-5倍收入」**属数字结论→R2 REQUIRE_KB**） | 数字部分必须 | ❌ | 必须 | 框架可答+具体倍数拒 |
| 3 | 什么是重疾险 | qa | B/C 交界（纯概念→C 或 B 无 KB 段） | ✅ | 可选 | ❌ | 域事实成分必须 | 概念可答 |
| 4 | 等待期是什么意思 | qa | B/C（概念定义） | ✅ | 可选 | ❌ | 同上 | 可答 |
| 5 | XX产品等待期是多少 | product_qa | **A** | ❌ | **必须** | ❌ | 必须 | 0 证据→REFUSE（现状） |
| 6 | XX疾病是否赔 | product_qa | **A** | ❌ | 必须 | ❌ | 必须 | REFUSE |
| 7 | 我家5岁孩子买多少重疾险 | qa（现行）·**张力**（语义=个性化→D） | **D** | ❌直答 | 工件 | **必须** | 工件链 | Planning intake（**OWNER_DECISION：现行 qa 落点=03/07/10 同族张力**） |
| 8 | 100万预算怎么配置家庭保险 | plan（现行✓） | D | ❌直答 | 工件 | 必须 | 工件链 | Planning |
| 9 | 儿童重疾险和医疗险区别 | qa | **B** | ✅概念对比 | 命中则引用 | ❌ | 域事实必须 | KB 有则 grounded·无则 general+边界 |
| 10 | 给孩子买保险越早越好？ | qa（有必要吗类） | **B** | ✅权衡框架 | 可选 | ❌ | 域事实必须 | general+边界 |

**发现 taxonomy 张力（不修）**：case 7 现行落 qa（量词问句族=
既有 GOLD_UNCERTAIN/OWNER_DECISION 沿袭）——Hybrid Answer Policy
判定层可在 **不改 Intent** 的前提下将其 policy-route 到 MODE-D
（题级 policy 重于 intent 家族的落地=设计选项 O-B2，交 Owner）。

## 13. 位置选择（三案比较·依代码事实）

- **Option A**（现状+尾部 Claim Support）：无政策层——整题单档，
  不能解决本问题。**否**。
- **Option B**（Intent→Answer Policy→检索/LLM→分类→支持→生成）：
  政策前置可在检索前分派 MODE-D（case 7）——但 policy 判定需要
  检索命中形状（KB 有无）才能定 A/B/C……前置与信息不足矛盾。
  **部分采纳**：MODE-D 分派前置（Intent 后即可判），A/B/C 分派
  后置。
- **Option C**（检索→资格→**Answer Policy**→LLM 综合→Claim
  Support→终门）：政策层在证据形状已知后裁决——与
  `_qualified_evidence` 输出零-hit/有-hit 信号天然对接；
  MODE-D 前置小缝（Intent 后）+A/B/C 后置主缝。**选定：C 为主干
  （生成前·gate 前不可绕）+B 的 D 前置分派**。实现面=qa_agent
  组装层新增 policy 判定（~1 模块+rules 块）+generate_grounded
  增 MODE-B/C 合成路径——**不动 SEALED 组件语义**（claim_support/
  ggate/loop 主链复用；K.26 流式经既有 emit 通道）。

## 14. Evaluation Framework（Phase 29-B benchmark）

A 有用性（原拒答题可答率）·B grounding 正确性（KB-backed claim
真支持率）·**C 未支持事实逃逸（核心·数字/等待期/赔付/疾病定义/
产品责任/监管结论六类专项）**·D KB 冲突服从·E Planning 边界
（个性化不降级 QA）·F 拒答质量（部分拒答 vs 整题）·G 幻觉专项
（数字陷阱题集）。基线对照=现状 MODE-A 行为（冻结语料
intent-arbitration/claim-evidence 复用+新 hybrid 语料 v1）。

## 15. Migration（六阶段·灰度惯例）

```
29-A 设计（本文件） → 29-B 离线 benchmark（policy 判定器+
混合语料·零生产） → 29-C Shadow（MODE-B/C 生成影子·不投递） →
29-D Claim 级验证（影子输出过 _full_gate 全链离线） →
29-E 受控灰度（env HYBRID_ANSWER_ENABLED·默认 OFF·沿
CLAIM_SUPPORT_ENABLED 惯例） → 29-F Production Authority（Owner）
```
**LLM shadow ≠ LLM authority** 全程成立。

## 16. Rollback

`HYBRID_ANSWER_ENABLED=0`（默认）→ 行为逐字节=现行 MODE-A 单档
（沿 claim_support 的 env 旋钮先例）；policy 模块纯旁路。

## 17. Open Questions / Owner Decisions

1. **OD-H1 边界声明文案**（ALLOW_WITH_BOUNDARY 固定模板）审定。
2. **OD-H2 部分拒答呈现**（逐 claim 拒 vs 整题拒的 UX 文案）。
3. **OD-H3 case-7 形态**（量词个性化问句 policy-route 到 MODE-D
   是否随 Hybrid 一并启用——与既有 03/07/10 裁决合并处理）。
4. **OD-H4 MODE-C 范围**（纯 R0 是否首期纳入——建议首期仅 B）。
5. **OD-H5 与 28.C-3 的关系**（KB 语料解封仍独立推进——Hybrid
   不替代语料债）。
6. OD-H6 hybrid 语料 v1 规模/来源审定。
7. OD-H7 29-F 阈值（沿 OD-12 模式：观测分布→Owner 定）。

## 18. Recommended 29 Implementation Sequence

29-B（benchmark 判定器+语料）→29-C（shadow 生成）→29-D（离线
claim 验证）→29-E（灰度·默认 OFF）——每阶段独立可回滚、可审计；
29-F 等观测分布+Owner 阈值。

---

```
K.29-DESIGN: READY_FOR_IMPLEMENTATION
（全部冻结基线保持·零生产修改·实现受 §17 Owner 决策约束）
```
