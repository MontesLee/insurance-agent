# 28.K.28-II-IMPL · Claim→Evidence Support 生产实现

Date: 2026-09-29 · Baseline: e306118 + K.28-II-SHADOW（账本审计
PASS_WITH_REPORT_CORRECTION）· **K.28-II-IMPL: PASS**（DoD 18/18）

## 1. Scope（实际改动）

| 文件 | 性质 |
|---|---|
| `runtime/grounding/claim_support.py` | **新**·确定性支持层（生产 authority） |
| `runtime/grounding/loop.py` | 最小挂接：`_full_gate` 帮助函数+两处调用替换（段门 ：272·终门 ：332）——`ggate.check` 语义原样保留，support 仅收紧 |
| `config/qa-grounding-rules.yaml` | `claim_support:` 块（**默认 OFF**·slices 灰度惯例） |
| `schema/claim-evidence-support.schema.json` | **新**·additive 契约（draft-07·仓库风格） |
| `tests/runtime/test_k28ii_claim_support.py` | **新**·43 检查（standalone 约定） |
| `runtime/grounding/shadow/__init__.py` 注记 | 文档级（shadow 工具保持冻结） |

**零触碰**：intent/router/C1/C2 资格语义（`_qualified_evidence` 原样）/
WeKnora/agent workflow/K.26 provider 契约/SSE/EventBus/前端/schema 既有
契约。product_qa **共享 generate_grounded**（agent.py:37）→ 切片开启时
自动获得同一门（§14 无需另改）。

## 2. Architecture

```
C2(资格·SEALED) → QualifiedEvidence → generate_grounded
  → 段级/终级 _full_gate = citation closure(原 gate) ∧ claim_support
    → SUPPORTED → emit/grounded
    → PARTIAL/UNSUPPORTED/CONTRADICTED → hold → regen(违规入反馈·B+C)
      → 终局仍败 → citation_gate_rejected(既有拒答路径·零新文案)
```

## 3. Claim Taxonomy（§4·shadow 冻结六类）

C-FACT（必须支持）/C-USER/C-RECOMMENDATION/C-CALCULATION/C-DERIVED
（=planning DERIVED）/C-UNCERTAIN（豁免； typing 94.2%）。UNCERTAIN
不升级为断言事实——豁免由类型系统保证。

## 4. Support Semantics（§5-6/§8）

句主原子（`ggate.split_sentences`·与 K.26 分隔符同族）+确定性子句
拆分；**引用标记先剥离**（`[E1]` 数字永不入锚——IMPL 中实测捕获并
修复的生产 bug）；产品名内嵌数字剔除（最长名优先）。判定：
数字/实体锚 DIRECT·定性 bigram 覆盖（保守：overlap 永不=SUPPORTED）·
**产品身份**（claim 解析 `find_product_in`（FS-04 修复）↔ evidence
doc 经 catalog `evidence_refs` 双向 stem 容错匹配·product_id 路由）·
**时间窗**（anchor 自带 effective_from/to·复用 R5 字段零新治理）·
**矛盾**（新增 claim↔evidence 数值冲突检测 + 跨证据同标签异值·
OD-5 检测即 fail-closed 不裁优先级）。四态=任务 §6 命名
（SUPPORTED/PARTIAL/UNSUPPORTED/CONTRADICTED；语料映射
PARTIALLY_SUPPORTED 在评测器侧归一）。

## 5. Production Authority（§7）

**仅确定性层**。LLM Judge 无 production 路径（shadow 对照器保留为
评测工具）。Citation≠Support 成为真实门：i2/i3 证明带引用的不支持句
被 hold→regen→refuse。

## 6. Streaming（§12·K.26 契约保持）

挂接在既有 segmenter 的段门（同一判定点）：`T_first<T_final` 不受
影响（确定性判定 ~ms 级）；未过门的段进 `pending`（既有 held 机制）
——i2 实证未支持句零外流、已支持句照常流式；i4 实证生成期 delta≥2。
provider 流契约/SSE/前端零触碰。

## 7. RV4 双回归（§15）

- **RV4-A**：C2 层——电池含 test_k27rv4c2（8 节）全绿，农业条例
  仍 0 qualified（C2 seal 不动）。
- **RV4-B**（i3·Golden）：Qualified 健康险法规×「该重疾险等待期90天
  [E1]」→ **refused**（UNSUPPORTED·不投递）——Qualified≠Supportive
  进入生产回归。

## 8. Negative 覆盖（§16）

citation-only（t6/i2）·same-topic（N2 8/8）·wrong product（t3 双路
由+N4）·wrong version（t4/N5 5/5）·temporal（t4/N6 6/6）·
contradiction（t5 双向+N7 6/6）·RV4-A/B·stuffing（t6）·partial
（t6 复合=门级不通过+子句态记录）。「一引证支持前半不支持后半」=
复合句→PARTIAL 族（t6·shadow N3）。

## 9. Metrics（§20·冻结语料过生产模块·vs shadow 基线）

| 指标 | Shadow | 生产模块 |
|---|---|---|
| C-FACT P/R | 0.80/0.80（TP20 FP5 FN5 TN58） | **相同** |
| FSR（judged/unsup） | 20%/7.94% | **相同** |
| **Cited-unsupported escape** | 0/17 | **0/15**（C-FACT cited 集） |
| Typing | 94.2% | 94.2% |
| Contradiction | 6/6 | 6/6 + **新增 claim↔ev 检测**（N1-7 保费 200vs400、N3-5 70vs60 由 UNSUPPORTED/PARTIAL 上调为 CONTRADICTED——语义更准·同 fail-closed 族） |
| Partial accuracy (N3) | 4/8 | 3/8（N3-5 上调 CONTRADICTED 所致·policy-equivalent） |

阈值不设（OD-12·Owner）。

## 10. Regression（§19）

专项 **43/43**；全电池 **865 passed + 2 skipped 零回归**（Intent/C1/
C2/K.26/Consumer Auth/Ownership/Governance 全含）；RV4-A（C2 套件）
绿。实施中一版曾因默认 ON 使 21 例既有桩答案测试红→按 slices 灰度
惯例改**默认 OFF**（见 §Rollback）后全绿——该教训记入（行为变更门
必须 staged）。

## 11. Rollback（§18）

`claim_support.enabled=false`（默认·已如此发布）或 env
`CLAIM_SUPPORT_ENABLED=0`（env 优先）→ `_full_gate` 退化为
`ggate.check` 单独 → **逐字节等价旧路径**（i5 测试锁定；t7 双向+
发布默认断言）。**上线=Owner 显式开启**（env=1 或 rules=true）。

## 12. Security（§17）

claim_id/evidence_refs/support_reason/内部元数据只存在于判定结构与
内部 provenance；投递文本经既有 `sanitize_consumer_text`（未动）；
i2 证明未支持内容零外流；无 tool/agent/run/artifact ID/CoT/reasoning
外泄面（新增代码不产生消费者可见输出）。

## 13. Known Limitations / Future V2 Debt

- **Planning**（§13）：V1 边界——planning 交付无证据集，支持门不
  适用（模块已备 planning 类型语义）；planning 接入=证据携带交付
  改造后的后续 Owner 阶段。Product QA 经共享 loop 自动覆盖（切片
  现默认 OFF）。
- 词法天花板沿 shadow（FS-06 复合定性尾/N8 否定式）——LLM 对照已证
  明不可简单替代（漏产品/时间结构类），语义 V2 另立项。
- 拒答路径 generation 契约不落 gate_violations（K.34 既有）——
  B+C 反馈经请求体验证（i2）。
- 语料 fixture 占比高；真实流量校准待灰度。

## 14. DoD（§22·18/18）

1✓ 路径接通（loop 双门）2✓ C2 原语义 3✓ Citation≠Support 真门
4✓ RV4-A C2 拦 5✓ RV4-B 支持层拦 6✓ Partial 7✓ Wrong product
8✓ Wrong version 9✓ Temporal 10✓ Contradiction 11✓ 未支持不外流
12✓ K.26 契约 13✓ 消费者零内部元数据 14✓ 无 LLM authority
15✓ 回归全绿 16✓ 回滚可验证 17✓ 测试对应 18✓ 范围合规。

---

```
K.28-II-IMPL: PASS

Intent: SEALED · C1: SEALED · C2: SEALED · K.26: SEALED
Claim Support: IMPLEMENTED (deterministic authority; shipped OFF —
staged rollout, Owner enables via CLAIM_SUPPORT_ENABLED=1 / rules)
LLM Intent: OFF · LLM Claim Judge Authority: OFF
Router Authority: UNCHANGED
```
