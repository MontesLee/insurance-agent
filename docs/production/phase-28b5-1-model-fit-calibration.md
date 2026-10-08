# Phase 28.B5.1 — Model-Fit Calibration + Re-measure 报告

Date: 2026-09-25 · 全程遵守 Owner 边界：**ADR-25 未触碰 / Router
Authority OFF / M3 未启动**；grounding gate、fail-closed、comparator、
volatility whitelist **零改动**。

## 1. Executive Summary

- **目标**：修复 B5 观察到的两个 model-fit 问题（citation 合规 2/4；
  超时 174.6s 无界），不放宽任何安全机制。
- **修改内容**：① 两个 system prompt 从代码常量**外置**到既有规则文件
  并按 trace 实证的失败模式校准（v1→v2→v3 两轮）；② 适配器补
  **墙钟看门狗**使外置 timeout 真正可执行（60s/次 × 1 重试，总预算
  有界）。
- **结果**：citation 合规 **2/4 → 3/4**（F 修复；B 违规 4→1 残留一句；
  E 为禁推探针——拒答即正确行为）；超时 **174.6s 无界慢滴 → 全程零
  llm_unavailable、墙钟全部有界（最大 154.3s ≤ 240s 预算）**。
  B4 = **GREEN（14/14）**；backend **703/0**；web 148+2；tsc clean。

## 2. Root Cause（代码+trace 实证，见 phase-28b51-pre-audit.md）

**Citation**（live probe 原始输出落 tmp/b5/probe-pre.json）：
- F：模型使用**全角括号（E1）**而非 ASCII `[E1]`——格式失配（非证据
  缺失、非 gate 缺陷）。
- B：模型**摘要式转述、事实句零 [E#] 标注** + 违规桥接"按品类推测
  约为30天"。
- 二轮后残余（probe-post + 违规机器记录）：**结尾免责句**（"应以合同
  **条款**为准"——条款∈事实词表→被判事实句）与长枚举（E 案 19+ 句
  中 4 句漏引）。

**Timeout**（代码链路）：
```
rules timeout_s=30 → gateway（未被执行）→ 适配器【忽略 request.timeout_s】
→ provider httpx 60s 为 per-READ（慢滴流可远超）→ max_retries=1 → 无总上限
E 案 174.6s = 2 次 × ~87s 慢滴尝试（算术吻合）
```
非"单次 provider latency"单一原因；三因叠加（预算未执行+per-read 语义+
无总界）。耗尽后 fail-closed 拒答**本来正确**（B5 已证）。

## 3. Changes（逐文件）

| file | change | reason | risk |
|---|---|---|---|
| config/qa-grounding-rules.yaml | prompt 外置（v3）+ timeout_s 30→60 + 注释 | 格式契约/逐句引用/禁推测桥接/禁无引用免责句/限 6 句；60s 容纳实证 ~50s 合法慢成功 | 低：prompt 只影响模型输出形状；gate 不变。60s×2×2=240s 有界上限 |
| config/product-qa-rules.yaml | prompt 外置（v3） | 同上 + 目录锚点/品类归属/禁售边界强化 | 低，同上 |
| runtime/qa_agent/agent.py + __init__ | SYSTEM_PROMPT 常量 → `system_prompt(rules)` 从规则装载（保留 fallback） | AGENTS.md §5 外置纪律；后续校准零代码 | 低：仅装载方式；无消费者破坏（grep 验证仅内部使用） |
| runtime/product_qa_agent/agent.py + __init__ | 同上 | 同上 | 低 |
| runtime/grounding/loop.py | `_GatewayProviderAdapter.generate` 增墙钟看门狗（线程 join(request.timeout_s)，超时抛 llm TimeoutError[retryable]） | 让外置 timeout 真正可执行；gateway 既有重试策略自然接管；同 llm_candidate 既有模式 | 低-中：超时线程为 daemon（后台自然结束，已注释）；mock 即时返回零影响（B4/全量已证） |
| tests/runtime/test_p28b51_calibration.py | 新增 15 测试（§6） | 回归+安全钉 | — |

**未触碰**（git 复核）：gate.py/comparator/normalizer、router.py、
agent_registry.py、orchestrator、events.py、server.py（本阶段零改动）、
knowledge/、contracts/、ADR、web。

## 4. Citation Before / After（同场景/同模型/同夹具，独立真实服务器）

```text
compliant: before = 2/4   after = 3/4     （分母=到达生成的 QA 轮：A,B,D,F）
E（禁推探针）不计入合规分母——其拒答是期望安全行为
```

Failure taxonomy（机器可读 gate_violations + 原始输出）：

| 轮次 | B | F | E |
|---|---|---|---|
| B5（before） | 4×fact_sentence:no_citation（摘要式零引用+推测桥接） | 5×（**全角括号（E1）**） | llm_unavailable（超时，未达 gate） |
| v2 后 | 1×（idx3 残留） | 1×（**免责句"应以…条款为准"**） | 4×（长枚举漏引；已能达 gate） |
| v3 后（final） | 1×（idx4 残留单句） | **0（grounded）** | 5×（建议型长答仍倾向漏引——**拒答=安全正确**） |

残余归因：B=单句漏引（模型方差）；E=价值判断问句下模型仍写建议性
长段落——门拒之（无推荐泄漏交付）。

## 5. Timeout Before / After

```text
before: E 案 llm_unavailable @ 174.6s（无界慢滴，2×~87s）
after : 全部 8 场景零 llm_unavailable；最大墙钟 154.3s（E，2 轮生成）
        budget = 60s/provider尝试 × 2(gateway retry) × 2(闭环门再生成)
               = 240s 有界上限；观测全部 ≤ 154.3s
attempts: 生成轮 1–2 次（再生成上限=1）；gateway 重试=1（可重试错误）
timeout rate(live): 0/8 场景（before 1/8）
fallback: 耗尽→llm_unavailable 模板拒答（fail-closed，单测 8 案覆盖）
```

## 6. Safety Verification

- **gate 未放宽**：citation.pattern/fact_markers(≥38)/max_regenerations=1
  原样（单测钉死）；全角括号/漏引/伪引/unsupported 仍全拒（15 测试）。
- **fail-closed 保持**：超时→llm_unavailable 拒答；AnswerContext 拒答
  零 evidence_refs 零 evidence_map（无幻觉 ctx）；grounding loop 无
  artifact 路径（结构断言）——零伪造 artifact。
- **推荐泄漏**：E 两轮均被门拒，**零交付**；未增加。
- prompt 变更只作用于模型输出形状，合规≠放宽（两个方向均有测试钉）。

## 7. B4 Result

**PASS — 14/14 cases, 0 RED**（v3 规则下重跑；
docs/production/reports/router-equivalence-report.md 已更新；comparator/
normalizer 零改动——E1 平凡等价标注保持诚实）。

## 8. B5 Re-measurement

**INSUFFICIENT LIVE SAMPLE** — 全部为受控 smoke 注入流量（独立实例
8106、live glm-5.3/fast、mock 治理知识组合；无真实用户）。结论口径：
*Model-fit signal observed under controlled smoke traffic; insufficient
live sample for production-behavior conclusion.*（不声称 production
validation。）

## 9. Architecture / Governance

```text
ADR-025:        unchanged / PROPOSED
Router Authority: OFF
M3 Planning:    NOT STARTED
红线复核:        orchestrator/workflow/artifact contract/approval/
                WeKnora/event vocabulary/router ownership 零改动
```

## 10. Recommendation（事实性，不代 Owner 决策）

- 两项 model-fit 问题已 measurable 改善（citation 3/4 且残余为方差级
  单句；timeout 有界零发生）且安全机制全保持：**Ready for Owner
  consideration of ADR-025 and subsequent M3 gate**。
- 若 Owner 希望 citation 再提升：候选=生成温度/模型档位实验、或将
  免责句式纳入 fact-marker 豁免清单（**那是 gate 语义变更，须 Owner
  显式批准，本阶段未做**）。
