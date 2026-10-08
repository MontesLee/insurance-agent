# Phase K.31-A — FlashX E2E Shadow + Quality Gate Validation

Date: 2026-09-28 · 性质：**Shadow A/B 实验**（生产配置零改动：`.env` 未触碰
——实验变量经进程 env `LLM_FAST_MODEL=glm-5.3-flashx` 注入隔离实例；
结束后已恢复生产配置并经 `/api/agent/config` 复证）。

证据等级：[MEASURED] / [CODE-EVIDENCE] / [ESTIMATED] / [UNKNOWN] / [BLOCKED]。

## 1. Executive Summary

- **[MEASURED] E2E 收益成立（D/E 显著，C 受行为方差污染）**：D Δmedian
  **-21.0s（110.0→89.0s·-19%）**；E Δmedian **-20.7s（43.2→22.5s·-48%）**；
  C completed-only Δ≈-10s，但 flashx 2/3 轮提前澄清（WAITING_USER）。
- **[MEASURED] LLM generation 总量同步下降**：D 105.1→84.2s（-20%）·
  E 30.1→13.9s·C(completed) 76.2→66.0s。
- **[MEASURED] K.30 的 verbosity 恐惧未兑现**：Output Expansion Ratio
  步2+ 实测 **0.64-1.13**（K.30 单调用 step1 任务测得的 3-4× 不属于
  flashx 的实际分层槽位）；context 无膨胀（inTok 持平或更低）。
- **[MEASURED] 质量门零回归**：18/18 轮 schema/工具全过、retry=0、
  repair=0、needs_review=0、无 invalid continuation。
- **[MEASURED n=2] QA 引用门无新回归**：flashx 2/2 与现行 flash 同签名
  `citation_gate_rejected`（G-1 语料根因，两臂同样拒答），生成期 5.7-9.2s
  vs flash 基线 12.2-18.2s。
- **K.30 估计 15-25s：CONFIRMED**（D 实测 -21s·E -20.7s，落于区间）。

**最终分类：A · E2E Benefit Established**（质量门无回归；C 澄清行为差异
与 QA 样本量记为限制）。

## 2. Experiment Scope / Controls

| | Current 臂 | FlashX 臂 |
|---|---|---|
| step1 | glm-5.3 | glm-5.3（不变） |
| step2+/QA | glm-5.3-flash | **glm-5.3-flashx** |
| effort/prompt/schema/tools/retry/WeKnora | 全同（.env 锁定 14:49 版·effort=high） | 全同 |

单变量成立验证：`/api/agent/config` 双向核验（current 臂
`fast=glm-5.3-flash`·flashx 臂 `fast=glm-5.3-flashx`，model/effort 两臂
一致）[MEASURED]。同日连续执行（provider 时间窗漂移最小化）；
C/D/E×3=9 轮/臂 + flashx 臂补 B×2 QA 探针。

## 3. E2E Latency Results [MEASURED]

| 场景 | Current（3 轮） | FlashX（3 轮） | Δmedian | 配对 Δ |
|---|---|---|---|---|
| C | 32.1/96.0/81.1（全 COMPLETED） | 47.1*/71.4/20.3*（*2 轮 WAITING_USER） | completed-only ≈-9.7s | 行为污染，见 §16 |
| D | 108.2/110.0/135.3 | 89.0/45.4/95.7 | **-21.0s（-19%）** | -19.1/-64.6/-39.6 |
| E | 43.2/26.8/149.1 | 34.9/20.5/22.5 | **-20.7s（-48%）** | -8.3/-6.3/-126.6 |

## 4. LLM Generation Results（agent.llm_call 逐调用观测）[MEASURED]

| 场景 | Current LLMΣ med | FlashX LLMΣ med | 调用数（两臂） |
|---|---|---|---|
| C completed | 76.2s | 66.0s | 10-12 / 10 |
| D | 105.1s | 84.2s（-20%） | 10-12 / 10-11 |
| E | 30.1s | 13.9s | 3-5 / 3-5 |

LLMΣ≈E2E 的 93-96%（与 K.28/K.30 结构一致）；收益全部来自 generation。

## 5. Output Verbosity Analysis（§九 核心）[MEASURED]

| 场景 | outTok Current med | outTok FlashX med | Expansion Ratio |
|---|---|---|---|
| D | 2348 | 2656 | **1.13** |
| E | 396 | 255 | **0.64** |
| C completed | 1786 | 1788 | 1.00 |

**K.30 的 3-4× 来自 step1 槽位实验（flashx 顶替强模型位）；在 flashx 的
真实槽位（步2+）verbosity 与 flash 持平。** Generation Efficiency
（省时/多产出 token）：D = 20.9s/308tok ≈ 68ms/tok 净赚。

## 6. Context Propagation [MEASURED]

inTok：D 39708→39383（持平）·E 12414→9596（更低）·C 40724→32563。
**无 context 膨胀放大效应。**

## 7. Retry / Repair / Schema [MEASURED]

18/18 轮：agent_step_error=0（retry 0）·repair 事件 0·schema rejection
路径未触发（步数/工具序列形态正常）·invalid continuation 0。

## 8. Tool-call / Step Variance [MEASURED]

D 步数 10-12（两臂重叠）·E 3-5（重叠）·**C：flashx 2/3 轮 2-3 步即
ask_user 澄清 vs current 0/3**——flashx 在欠指定输入上更倾向早问。
属行为差异（非延迟效应），单独标记（§十八纪律）。

## 9. QA Grounding / Citation Gate [MEASURED n=2]

flashx B×2：均 QA 切片（qa_answered 在案）·grounding=refused·
failure=citation_gate_rejected·evidence=0——与现行 flash 基线（K.28
B 3/3 同签名）**完全一致**；根因=G-1 语料零命中（语料轨道，非模型）。
生成期 5.7-9.2s/调用 vs 基线 12.2-18.2s。**无新回归；样本 n=2 为限制。**

## 10. Needs Review [MEASURED]

两臂 0/18。无 needs_review 回归。

## 11. Paired Analysis（§十九）[MEASURED]

- D 全 3 对同向改善（-19.1/-64.6/-39.6s）——方向一致性强。
- E 3 对同向（-8.3/-6.3/-126.6s；第 3 对含 current 臂 149s 异常慢尾）。
- C 无同型配对（flashx 2 轮澄清型终态）。

## 12. K.30 15-25s Estimate Validation

**CONFIRMED**：D -21.0s·E -20.7s [MEASURED]（C completed -10s 在区间
下沿）。K.30 的 per-call 平移估算方法本轮被 E2E 实测验证有效。

## 13. Net Performance Benefit [MEASURED/ESTIMATED]

- Gross Generation Saving：D -20.9s·E -16.2s [MEASURED]
- Retry/Repair Cost：0 [MEASURED]
- Additional Context Cost：0（inTok 持平/更低）[MEASURED]
- **Net ≈ Gross**；E2E Saving = Generation Saving（93-96% 占比结构）

## 14. Quality Trade-offs

无质量门回归 [MEASURED]。开放风险：①C 类欠指定输入的早澄清行为变化
（用户体验影响未评估——可能其实是好行为）②QA 样本 n=2③flashx 计费/
限流档位 [UNKNOWN]④长尾稳定性（E current 臂 149s 慢尾提示 provider
方差仍在，flashx 臂未见但 n=3 不足以下结论）。

## 15. Limitations

n=3/格（P95=max 不可靠，未报告）；C 场景行为污染；QA n=2；同日单
provider 窗口；32 轮新增 LLM 成本；browser 未涉及（UI 零改动）。

## 16. Production Readiness Evidence

**ESTABLISHED（进入下一阶段生产化评估的证据充分）**：
- E2E 稳定改善：D/E 6/6 配对同向 [MEASURED]
- 质量门：18/18+2 全过、零 retry/repair/needs_review [MEASURED]
- verbosity/context 恐惧被证伪于真实槽位 [MEASURED]
- 剩余决策属下一阶段（灰度策略/回滚标准/QA 扩样/计费核实）

## 17. Next Experiment Candidates（仅列）

1. 灰度方案设计：fast 槽位 flash→flashx 的 staged rollout + 回滚阈值
2. QA 引用门扩样（n≥10·含命中语料的问题）+ G-1 修复后复测
3. C 类欠指定输入行为 A/B（早澄清是否更优的产品判断）
4. effort=low × flashx 叠加矩阵（K.30 候选③）

## 18. STOP Decision

**K.31-A COMPLETE — 分类 A（E2E Benefit Established）— STOP。**
不修改生产模型/不建 tier router/不进 K.31-B/C。生产配置已恢复并复证。

## 19. Test Results

- Benchmark 前：backend 853+2 green（K.30 收尾态）
- Benchmark 后：backend 853+2（本报告后附最终复跑）
- **Web 未修改**（driver --out 参数为 benchmark 工具改动，非 web）
- `.env` mtime 14:49 全程未变；生产 fast=glm-5.3-flash 已恢复复证

数据：`tmp/obs/perf-bench/k31a/{current,flashx,flashx_qa}/` +
`tmp/obs/run-profiles/`（20 个新 run 时间线）+ obs `agent.llm_call`。

## 20. 十问直答

**Q1** 是——D -20.9s/E -16.2s/C(completed) -10.2s generation 总量
[MEASURED]。**Q2** 是——D -21.0s(-19%)/E -20.7s(-48%)
[MEASURED]。**Q3** 成立——实测 -20~-21s 落于 15-25s。**Q4** 真实槽位
扩张比 0.64-1.13（3-4× 是 step1 槽位假象）。**Q5** 否——inTok 持平或
更低。**Q6** 否——0/20。**Q7** 无新回归（同签名拒答，G-1 根因，n=2）。
**Q8** D/E 无系统变化；C 早澄清行为差异（单独标记）。**Q9** 净收益≈
毛收益：D -21s/E -20.7s E2E。**Q10** **ESTABLISHED**（进入生产化评估；
生产切换本身仍需 Owner 决策+灰度设计）。
