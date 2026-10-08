# K.34 Stage 1 Rollout Readiness

## Status

**STAGE1_READY_WITH_OBSERVATIONS**（核心 routing/reliability/rollback 全过；
观察项=QA 拒答路径的 model 归因空缺[预存]、G-1 拒答基线、C 早澄清产品
决策——均非阻断）。

## Environment

- Production default（静态实测·未被污染）：Step1=glm-5.3 ·
  Step2+=glm-5.3-flash · QA=glm-5.3-flash（qa 回落 fast）
- Canary（进程 env·`.env` mtime 14:49 全程未变）：
  `LLM_FAST_MODEL=glm-5.3-flashx + LLM_QA_MODEL=glm-5.3-flash`
  （/api/agent/config 实测 model=glm-5.3 fast=flashx qa=flash）
- Canary 进程已终止；生产配置后端已恢复并复证。

## QA Scenario

- 场景：K.28/K.31-A 既有 QA 场景 B（百万医疗险免赔额/续保条款——历史上
  5+ 次稳定路由 QA 切片）
- run_id：`run_7c192aa77f7346e5` · 终态 completed/**QA_REFUSED**
  （citation_gate_rejected·G-1 语料根因·两臂同签名基线）
- E2E 35.5s（首内容 14.9s 流式到达）

## Routing Evidence

- **Step1**：G1 本轮 QA 直答路径无 agent 环 → 本轮 NOT EXERCISED；
  K.33 同配置 3/3 实测 glm-5.3 [REUSED]
- **Step2+**：同上——K.33 同配置 23/23 调用=glm-5.3-flashx 零泄漏
  [REUSED]；本轮未经过规划链
- **QA**：QA 切片真实执行（qa_answered 在案·attempts=2·两次
  provider OK）。模型归因三重证据：①进程配置 qa=flash（live 实测）
  ②构造路径唯一确定（K.32-C seam·契约测试 T1-T4）③**执行级时延签名
  15.9s/14.7s = flash 波段**（K.28 flash 基线 12.2-18.2s；K.31-A
  flashx-on-QA 同问题探针 5.7-9.2s——若泄漏到 flashx 必然落入该波段，
  实测明确排除）→ **G3 VERIFIED（无 QA→flashx 泄漏）**
- **Isolation（G4）**：同 canary 配置下 K.33（step2+=flashx 23/23）+
  本轮（QA=flash 签名）——两个 execution class 实际使用不同模型 ✓

## Reliability

agent_step_error=0 · schema 拒绝 0 · invalid continuation 0 · repair 0 ·
needs_review 0 · terminal failure 0。QA_REFUSED=已知 G-1 基线
（分类③ QA/citation gate existing issue，非 FlashX 回归——K.28 flash
臂与 K.31-A flashx 臂同签名）。

## Grounding / Citation

EXERCISED：grounding=refused · failure=citation_gate_rejected ·
attempts=2（首试+门败重生成，均在 flash 波段）。单次记录，不建统计结论。

## Latency

OBSERVATION ONLY：E2E 35.5s · QA 两次生成 15.9s/14.7s · 首内容 14.9s。
不更新 K.31-A 性能结论。

## Rollback

**VERIFIED**：移除 LLM_FAST_MODEL 覆盖且 LLM_QA_MODEL 未设 → resolver
实测 step1=glm-5.3 · step2+=flash · QA=flash；`.env` 未触碰；生产进程
已恢复复证。

## Observations

1. QA 拒答路径 provenance.model 硬编码空串（`gctx.refused(... model:"")`
   ·28.C-1 起预存）——执行级模型归因依赖时延签名旁证；建议后续 1 行
   填充（K.32-B 已列可选项，本阶段禁改）。
2. G-1 语料缺失使 QA 场景以拒答收尾——Stage 1 观测中 QA 侧只能验证
   "拒答一致性"，无法验证"接地带引文的通过路径"。
3. C 早澄清行为差异：Product decision required 维持（K.31-A/K.33）。

## Recommendation for Next Engineering Step

进入 Stage 1 受控发布：pilot 实例以进程 env 常驻
`LLM_FAST_MODEL=glm-5.3-flashx + LLM_QA_MODEL=glm-5.3-flash`，
probe-alpha 合成流量 + 真实用户小样本观察 1-3 天；观测清单=agent.llm_call
（model/duration/status）+ K.32 §7 回滚阈值；同时补齐 QA provenance
model 字段（1 行）以便 QA 侧直接归因。
