# K.29-C · Semantic Judge Shadow Layer — 设计（仅设计·不实现）

Date: 2026-10-02 · Status: **DESIGN ONLY — 不实现·不开启·不挂接**

---

## 0. 绝对边界（先于一切设计)

| 不变项 | 语义 |
|---|---|
| **不影响用户答案** | shadow 输出只写观测记录;本轮门结果/拒答文案/流式行为逐字节不变 |
| **不改变 gate** | ggate(引用存在性)与 claim_support 判定语义零触碰 |
| **不改变 authority** | 确定性层保持唯一裁决;shadow 无 gate 权限(无代码路径能把 shadow 输出送进 merge_verdict) |

shadow ≠ authority,全程成立;任何 authority 授予=未来独立 ADR+
OD-12 式门槛+Owner 批准,不在本设计范围。

## 1. 管线位置

```
[现行链不变]
claim → deterministic safety filter(claim_support+INV-1 硬类清单)
        ├─ HARD BLOCK(数字/产品/监管/赔付/REC数字前提/CONTRADICTED/
        │              否定标记) → 拒(行为与今日逐字节一致)
        └─ 非 HARD ∧ cited ∧ 词法判定≠SUPPORTED
              ↓ (仅此分支旁路观测·不拦截不改写)
          [C-shadow: 语义等价判定]
          输入 = claim(去[E#]) + 被引用证据 chunk(单 chunk·防上下文渗漏)
          输出 = 结构化语义决定(§2) → 观测记录(§4)
```

Phase 形态:S0 离线重放(工具)→ S1' in-process 影子(loop.py 观测缝
=届时另行授权)→ S2 Owner 阈值裁决。**本文件只覆盖 S0/S1' 设计。**

## 2. Candidate Semantic Decision（三值词汇·任务规定)

| 决定 | 语义 | 对本轮行为的影响 |
|---|---|---|
| `ALLOW_UPGRADE` | judge 判定 claim 被该证据 chunk 严格蕴含(entail)·无矛盾·置信 ≥ 阈值 | **零**(仅记录「若升级会翻转」) |
| `KEEP_BASELINE` | 判定不蕴含/部分蕴含/证据不足 | **零**(维持基线拒) |
| `UNCERTAIN` | 判定置信 < 阈值或输出不自洽(如 entailment=no 但 contradiction=yes) | **零**(按 KEEP_BASELINE 记账) |

**错误规约(任务规定)**:任何错误——LLM 异常/超时/输出不可解析/
超成本预算/证据 chunk 缺失——**⇒ `KEEP_BASELINE`**。shadow 无失败
面:最坏情况=没有观测记录的价值,从无行为风险(INV-2)。

## 3. Judge 设计规格

- **输入**:system(判定协议+输出 schema)+ user(claim 文本 +
  单条证据 chunk 文本)。**不含**其他证据/对话上下文/问题原文
  (防上下文渗漏与「整体看起来对」偏置)。
- **输出(JSON schema)**:
```json
{"entailment": "yes|no|partial",
 "contradiction": true|false,
 "contradiction_reason": "...",
 "confidence": 0.0-1.0,
 "unsupported_elements": ["..."]}
```
- **映射**:entailment=yes ∧ contradiction=false ∧ confidence≥τ →
  ALLOW_UPGRADE;entailment∈{no,partial} ∧ contradiction=false →
  KEEP_BASELINE;contradiction=true → KEEP_BASELINE
  + 反转观测标记(供 F2 族质量度量);其余/解析失败 → UNCERTAIN
  (记账=KEEP_BASELINE)。
- **模型/成本**:qa 槽位或专用小模型;每候选 claim 一次调用
  (每拒答答案 ≤5-20 次·可批);S1' 影子按 run 限预算(超=停记录
  该 run 剩余候选·全部记 UNCERTAIN)。
- **失败注入预期**(S1' 验收):LLM 断供窗口内 shadow 零行为影响
  逐字节成立(对照 run 快照)。

## 4. 观测记录（S1' 粒度·补 K.28-II 已知缺口)

per-run per-claim 持久化(`claim_id, run_id, claim_text, cited_label,
verdict_deterministic, semantic_decision, confidence, latency,
error?`)——现有生产「per-claim 行不持久化」是 K.28-II 已记录的
粒度限制;影子记录独立文件,不进 AnswerContext(用户面零新增
暴露·沿 E-2/K.1 边界)。

## 5. 指标与验收门槛（S1'→S2 前置·阈值由 Owner 冻结)

| 指标 | 定义 | 初拟门槛(待 Owner) |
|---|---|---|
| would-escape | 金标负例(含 F2 反转/F4 陷阱/F5/F6 冲突)判 ALLOW_UPGRADE | **0(硬门)** |
| would-flip | E 类(F1)判 ALLOW_UPGRADE 比例 | ≥40%(低于此=不值得开 S2) |
| 判定稳定 | 同输入 3 次重复决策一致率 | ≥90% |
| 反转检出 | contradiction=true 在 F2 族召回 | ≥90%(影子质量度量) |
| 人工一致 | 50 例抽样人工复核同意率 | ≥90% |
| 行为不变性 | S1' 前后 run 快照(答案/事件/时延形态) | 逐字节等价(除影子记录) |

## 6. 安全论证（为何 shadow 不能造成逃逸)

1. 无代码路径:merge_verdict/_full_gate 不读影子输出(S1' 审计点:
   grep 证明 loop/gate 无 shadow import)。
2. 硬类前置:数字/产品/监管/赔付/REC 数字前提在确定性层终局,
   影子根本不接收这些 claim(候选过滤在先)。
3. 失败单向:一切异常坍缩为 KEEP_BASELINE(fail-closed)。
4. 成本单向:预算耗尽=停记录,不改变任何门结果。
5. 记录面独立:观测文件不经消费者边界(无用户可见面)。

## 7. 未来 authority 路径（仅占位·非本设计承诺)

若 S1' 全绿且 Owner 冻结阈值 → S2 裁决「是否授予升级权」→ 若授予:
env 旗(默认 OFF)·只升非硬类·升级也仅把 PARTIAL→SUPPORTED(不
绕引用门)·OD-12 Gate A/B/C 全过·回滚=关旗逐字节回基线。任何一步
不满足 → 维持 shadow 观测形态,无期限。
