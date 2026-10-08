# Phase K.30 — Model Tiering + Generation Latency Feasibility Audit

Date: 2026-09-28 · 性质：**AUDIT ONLY**（零生产变更：默认模型/路由/Agent/
Skill/Tool/prompt/schema/retry/streaming/SSE/reducer 全部未动）。

证据等级标注：[MEASURED] 真实运行 / [CODE-EVIDENCE] 代码审计 /
[ESTIMATED] 依真实数据估算 / [UNKNOWN] / [BLOCKED]。

---

## 1. Executive Summary

1. **[CODE-EVIDENCE+MEASURED] 分层已存在**：`.env` 配置
   `LLM_MODEL=glm-5.3`（强）+ `LLM_FAST_MODEL=glm-5.3-flash`（快）——
   agent 循环 step1 用强模型、step2+ 与 QA 切片用 flash（agent.py:77、
   server.py QA 传 `fast_provider or provider`）。K.30 探针实测每调用
   模型地面真值证实生效（25 条 `agent.llm_call` 记录）。
2. **[MEASURED] 「快」模型并不快在长生成上**：flash 短续步（out≈150）
   7.9s，但长生成（终答/分析，out≈550）22.0s ≈ 强模型 23.4s；且 flash
   在 step1 任务（28.2s 中位，max 56.9s）**比强模型慢 2.4×**——现行
   「step1 留强模型」规则被数据证明正确。
3. **[MEASURED] 每调用 ~4s 推理地板**：真实 D 轮 9 个 flash 调用
   output 仅 5-7 tokens 仍各花 4.1-4.3s（reasoning_effort=high）——
   单次生成速度不是瓶颈，**固定推理期+开销才是**。
4. **[MEASURED] flashx 是当前最优候选**：任务等价基准（同 prompt/工具/
   schema，仅模型不同）36/36 有效工具调用下——终答 10.1s（比现役
   flash/strong 快 ~2.2×）、续步 8.4s（≈flash）、step1 14.2s（≈strong）。
5. **[ESTIMATED] Tiering 单独的理论节省 ≈ 15-25s**（D 案例 E2E 92→
   ~67-77s），**不存在达到 K.28「P95≤10s」量级（-103.7s）的理论空间**。
   残余结构：~4s×N 次推理地板 + 10-23s 长生成 + 12-15s step1。

## 2. Scope / Non-goals

只审计：调用盘点/真实链路/K.28 对账/能力矩阵/分层分类/retry 成本/
候选基准/反事实推演。不优化任何生产行为。K.29-A streaming 未触碰、
无 regression。

## 3. LLM Call Inventory（chat 消费者路径全量）[CODE-EVIDENCE]

| # | call | 代码位置 | 模型（现行） | 语义 | 流式 | 工具调用 | 用户可见 | tokens 可测 |
|---|---|---|---|---|---|---|---|---|
| C1 | step1 理解决策 | agent.py:77 `provider` | glm-5.3 | 理解新输入→首个决策/路由 | ✓ | ✓ | reasoning 段落+终答 | ✓ |
| C2 | step2+ 续步决策 | agent.py:77 `fast_provider` | glm-5.3-flash | 工具结果后→下一工具/finish | ✓ | ✓ | 同上 | ✓ |
| C3 | QA 接地生成 | grounding/loop.py:316 gateway.generate_stream | glm-5.3-flash | 引用接地的知识回答 | ✓句级门 | ✗ | 流式已验证句 | ✓ |
| C4 | QA 门败重生成 | 同上（max_regenerations=1） | 同上 | 修引用违规 | ✓ | ✗ | 迟到 | ✓ |
| C5 | intent LLM 候选 | intent/llm_candidate.py:204 | fast 层 | 规则未中时建议意图 | ✗ | ✗ | 否 | ✓ |
| — | harness planner/executor、skills | planner.py:72 等 | glm-5.3 | **不在 chat 路径**（26B 长任务 runtime/确定性技能零 LLM） | — | — | — | — |

C5 在 pilot 关闭（`INSURANCE_AGENT_INTENT_LLM` 未设→intent 实测 0-16ms
纯规则）[MEASURED]。

**一次 D 型规划轮实际 LLM generation：10-12 次**（1×C1 + 8-10×C2，
其中 1-2 次为长生成「分析/终答」类）[MEASURED：K.30 探针 D=11 次、
C=10、E=4]。

## 4. Real Runtime Call Chain（K.30 探针，现行配置）[MEASURED]

```text
D（run_f028cd68·E2E 91.7s·LLM 合计 86.6s=94.5%）:
#1  glm-5.3      step1  11.6s in=2302  out=334  →agent_decide
#2  glm-5.3-flash step2  21.4s in=2535  out=784  →record_requirement+risk（长生成）
#3  flash        2.5s   out=7   →coverage_gap_analysis
#4  flash        4.1s   out=7   →coverage_gap
#5  flash        10.7s  out=446 →record_risk
#6-#10 flash     1.1-4.3s out=5-7 →solution/product/recommend/report（地板型）
#11 flash        18.5s  out=594 →agent_decide finish（长生成·终答）
E（run_a535bbb8·37.0s）: 仅 4 次调用（6.4+8.2+5.8+7.8s）——步数本身方差大
```

## 5. K.28 Latency Reconciliation（D 案例预算，现行配置）[MEASURED]

```text
E2E 91.7s ≈ intent 0.0 + LLM 86.6（94.5%）
          + knowledge_search 4.3（4.7%·嵌套于工具）
          + 工具序列化/收尾 ≈ 0.8
LLM 86.6s = step1 11.6 + 长生成 2×(21.4+18.5)=39.9 + 地板型 8×~4=34.9
```

**配置变更必须记录**：`.env` mtime 2026-09-28 14:49（K.28 基准 13:0x
之后、K.29 之前）——`LLM_REASONING_EFFORT` 由默认 low 改 high（config.py
注释自证"28.K.30 did exactly that"）。故 K.28 与 K.29 不可直接混同：
每步跨度 K.28 med 4.9s → K.29 med 5.6s、reasoning delta 数 37-69 →
334-1911 [MEASURED]；config.py 自测：low 6.1-16.3s/步 vs high
11.8-30.4s/步。**effort 是与模型分层正交且量级相当的延迟杠杆**。

## 6. Per-call 分布（18 个历史规划轮 step 跨度池）[MEASURED]

| 集 | step1 | step2+ | retry(agent_step_error) |
|---|---|---|---|
| K.28（9 轮） | med 10.5s / max 22.1 | med 4.9s / p90 20.5 / max 32.9 | **0** |
| K.29（9 轮） | med 12.8s / max 27.2 | med 5.6s / p90 21.4 / max 59.6 | **0** |

## 7. Model Capability Matrix [CODE-EVIDENCE]

| 能力 | C1 step1 | C2 续步 | C3/C4 QA 接地 | 依据 |
|---|---|---|---|---|
| 复杂推理 | **高**（开放输入理解/路由） | 中（状态延续） | 中（仅综合） | prompts.py 语义 |
| 工具调用 | ✓必需 | ✓必需 | ✗ | schemas 工具协议 |
| JSON/schema 遵从 | ✓ | ✓ | ✓（引用门校验） | gate/validate_arguments |
| 长文生成 | 偶发 | 终答步必需 | ✓ | message ≤1200 clip |
| 中文多语 | ✓ | ✓ | ✓ | 消费者中文面 |
| 流式 | ✓ | ✓ | ✓句级门 | K.26/K.29-A |
| grounding | ✗ | ✗ | **✓刚性**（拒答优先） | ADR-022 |
| 确定性格式 | 中 | 中 | **高**（[E#]引用） | citation gate |

## 8. Tiering Candidate Classification

**A · Potentially Tierable（已分层或可再降）**
- C2 短续步（地板型 out≈6）：**已是 flash**；候选 flashx（continue
  8.4s≈flash 7.9s，36/36 有效）——收益不在速度而在长生成步。
- C5 intent 候选：已 fast 层（当前关闭）。

**B · Conditional（需 E2E 质量验证后可换）**
- C2 长生成步（分析 21.4s/终答 18.5s）：**flashx 终答 10.1s[MEASURED]
  ——但 flashx step1 输出 1204 tokens（verbosity 3-4×），决策风格差异
  未经 E2E 验证**；质量门：工具名/参数全过、无明文泄漏[MEASURED 单调用级]。
- C3/C4 QA 接地：flash 现役 22.0s/次×2；flashx 未在接地+引用门下测过
  → **[BLOCKED] 待专项基准**（引用纪律是刚性门）。

**C · Strong Model Required / Not Yet Tierable**
- C1 step1：**flash 实测更慢（28.2 vs 11.8s）且开放输入理解能力敏感**
  ——维持强模型 [MEASURED]。

## 9. Retry Cost Analysis [MEASURED]

- agent 循环 retry（LLM_RETRY=2）：18 个 C/D/E 轮 **0 次触发**
  （agent_step_error=0）；首 delta 15-19s 的 3 轮为 provider 慢响应非
  retry。gateway RetryLimit 退避在 C/D/E 未触发。
- **真实「重试类」成本在 QA 路径**：引用门败→**完整重生成**（同模型同
  prompt）：K.28 B 轮 3/3 都付了 2 次生成（首试 12.2-18.2s+重生成
  9.3-13.4s=26.8-30.4s）且最终仍拒答——**门控重生成是 QA 路径 ~45% 的
  LLM 成本**。规划路径无此机制（评估失败→needs_review 终止）。

## 10. Candidate Model Benchmark（SHADOW·任务等价）[MEASURED]

方法：`tools/perf/model_bench.py`——真实 SYSTEM_PROMPT+真实 D 问题+全部
11 工具规格+真实 AgentState 上下文；三任务（step1/continue/final）×4
模型×3 次；仅模型名不同（effort=high 同参）；流式接口直连 provider。

| 模型 | step1 med | continue med | final med | 有效性 |
|---|---|---|---|---|
| glm-5.3（S·现行 step1） | 11.8s | 14.7s | 23.4s（max 51.3） | 9/9 |
| glm-5.3-flash（F·现行步2+） | **28.2s**（max 56.9） | **7.9s** | 22.0s | 9/9 |
| **glm-5.3-flashx** | 14.2s | 8.4s | **10.1s** | 9/9 |
| glm-5-turbo | 16.1s | 13.2s | 16.4s | 9/9 |

36/36：工具名全部在册、参数全部可解析、final 无明文-only。**质量警示**：
flashx step1 输出中位 1204 tokens（strong 252/flash 789）——verbosity
与决策风格差异 [MEASURED]，E2E 影响未验证。

## 11. Counterfactual Scenarios（D 案例·E2E 92s 基线）

| 场景 | 变更 | 估算 E2E | 节省 | 依据等级 |
|---|---|---|---|---|
| A 保守 | 仅长生成 2 步换 flashx | ~72s | ~20s | [ESTIMATED]（final 10.1 vs 18.5-21.4 实测差平移） |
| B 中等 | 步2+ 全换 flashx（step1 留 strong） | ~67-72s | ~20-25s | [ESTIMATED]（continue 持平、长生成 -10~-12s/步） |
| C 激进 | 全换 flashx | ~69-74s | ~18-23s（step1 反慢 2.4s 抵消） | [ESTIMATED] |

**未计入的风险**：flashx verbosity 3-4× → 上下文膨胀→后续步变慢/质量门
通过率变化；QA 接地未测；E2E 反事实未运行（成本与授权原因）。

## 12. K.28 Q7 Re-evaluation

```text
Model Tiering alone 理论贡献：≈ 15-25s（D P95 113.7→~89-99s）[ESTIMATED]
Streaming（K.29-A）：感知延迟已解，wall-clock 贡献 0
WeKnora 4.3s/次：正交轨道，最多 ~4-8s
Retry：规划路径 0 成本；QA 门控重生成 ~14s（B 类路径）
编排/并行：步序本身方差（E=4 步 vs D=11 步）提示行为收敛空间 > 模型空间
```

**结论：Model Tiering 单独 NOT ESTABLISHED 达 -103.7s 量级。** 10s 目标
需要范式级变化（步数收敛/并行/缓存/预算内小模型整链），非本审计范围。

## 13. Quality / Regression Risk

flashx 单调用级质量门全过[MEASURED]，但：①verbosity 差异未做 E2E 验证
②QA 接地+引用门未测③step1 反慢。**任何切换决策需先跑 C/D/E E2E
counterfactual（shadow 双跑对比质量门通过率/步数/产物数）**。

## 14. Recommended Experiment Candidates（仅列·不实施）

1. **E2E shadow 双跑**：C/D/E ×3 on flashx（步2+）vs 现役——对比
   质量门/步数/产物/E2E（预计 ~20s 节省验证）。
2. **QA 接地 flashx 专项**：generate_grounded + 引用门下 flash vs
   flashx（拒答率/门败重生成次数）。
3. **effort×模型 矩阵**：low/high × flash/flashx（config.py 自测提示
   low 省 ~5s/步；与分层正交可叠加）。
4. **步数收敛审计**：E 轮 4 步完成 vs D 轮 11 步——行为方差本身的
   E2E 优化空间可能大于模型空间。

## 15. Open Questions

- flash 的 step1 反常慢（28.2s）机制未知[UNKNOWN]（疑与高 effort 下
  flash 推理上限有关）。
- glm-5.3-flashx 的计费/限流档位[UNKNOWN]。
- 4s 推理地板的 provider 侧构成（排队/首 token 网络）[UNKNOWN]。

## 16. Evidence / Commands / Tests

- 探针：`tmp/obs/k30/probe_k30.log` + obs `agent.llm_call` ×25
- 基准：`tools/perf/model_bench.py` → `tmp/obs/k30/model_bench.json`（36/36）
- 历史：`tmp/obs/perf-bench-k28/`、`tmp/obs/perf-bench/`（K.29）、
  `tmp/obs/run-profiles/`（30 run 时间线）
- 新 instrumentation：`agent.llm_call` obs 记录（agent.py·纯观察·
  测试 8/8）+ 测试密闭化（obs 不再污染真实 jsonl）
- 回归：backend 852+2（见 §18 最终确认）·web 未改（319+2 现状）·
  tsc 未改无需重跑 · **生产默认行为未变**（.env 未动）

## 17. STOP Decision

**K.30 COMPLETE — STOP。** 不进入 K.30-B/不切模型/不改 prompt/不动
WeKnora/不实现 tier router。等 Owner 审阅裁决。

---

## 18. §二十五 8 问直答

**Q1** 规划轮实际 LLM generation：**10-12 次**（D=11·C=10·E=4
[MEASURED]；构成=1 step1 + 8-10 续步，其中 1-2 次长生成）。
**Q2** 模型：step1=glm-5.3；step2+/QA=glm-5.3-flash（现行分层已生效
[MEASURED]）。
**Q3** 消耗最多 wall-clock 的调用：**两个长生成步**（需求+风险分析
~21s、终答 ~18.5s）+ step1（11.6s）[MEASURED]。
**Q4** 代码能力要求下可分层：C2 全部（长生成步→flashx 候选；短续步已
flash）；C5（已 fast/关闭）。
**Q5** 暂不能 Tier：C1 step1（能力敏感+flash 实测反慢）；C3/C4 QA 接地
（引用门刚性·flashx 未验证 [BLOCKED]）。
**Q6** 只做 Tiering 理论最大节省：**≈15-25s**（D E2E 92→67-77s
[ESTIMATED]）。
**Q7** 单靠 Tiering 达 -103.7s 量级：**NOT ESTABLISHED**（无理论空间；
残余=4s×N 推理地板+长生成+step1）。
**Q8** 最值得的下一实验：**①E2E shadow 双跑 flashx（步2+）验证 ~20s
节省与质量门；②QA 接地 flashx 引用门专项；③effort×模型矩阵**。
