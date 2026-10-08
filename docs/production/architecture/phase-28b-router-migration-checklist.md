# Phase 28.B Router Migration Checklist — 权威切换运行手册

Date: 2026-09-25 · 性质：准备产物（**未切换任何权威**）。用途：Router
authority 从"切片灰度"走向"唯一生产入口"（Message→Intent→Router→Agent）
的逐项核对清单。五域：shadow accuracy / regression / rollback /
feature flag / observability。每项标注状态（✅ 就绪 / ⬜ 待办 /
🔒 需授权或人工决策）。

切换前置总门（来自 phase-28b-readiness-audit.md）：ADR-025 立案 ·
B4 行为等价门 · planning 目标行为（28.D）· 本清单全绿。

---

## 1. Shadow Accuracy（影子一致性）

| # | 项 | 状态 | 说明 / 验收 |
|---|---|---|---|
| S-1 | 语料基线 | ✅ | 22/22 v1-correct，100% legacy 映射一致（离线） |
| S-2 | live shadow 积累 | ⬜ | 需服务器重启（新代码）+ 真实流量；现 shadow.jsonl 样本薄 |
| S-3 | annotate 覆盖率 | ⬜ | 既有 live 记录 legacy_intent 全 None（agent_state.intent 捕获不全）——修复捕获或按意图抽样人核 |
| S-4 | 一致性指标口径 | ✅ | report.py --shadow：分源置信分布/resolver/latency/mismatch（intent_difference/confidence_difference/missing_context） |
| S-5 | 切换阈值 | 🔒 | HD-1 floor（0.75 provisional）与"新旧分歧率达标线"需所有者按 live 数据裁定（建议：可比样本 ≥N=200 且 intent_difference ≤2%、无 P0 归因） |
| S-6 | QA 切片实跑对照 | ⬜ | insurance_qa 已权威（D4）：以 qa_answered/AnswerContext 审计代替 shadow 对照；product_qa 灰度开后同样 |

## 2. Regression（回归门）

| # | 项 | 状态 | 说明 / 验收 |
|---|---|---|---|
| R-1 | 全量 backend battery | ✅ | 681/0（28.B prep 后；零回归纪律持续） |
| R-2 | web vitest + tsc | ✅ | 148 passed +2 skipped · tsc clean（契约同步后） |
| R-3 | 语料回归 | ✅ | 22/22 漂移防护常驻（C-2 测试内） |
| R-4 | B4 行为等价门 | ⬜ | **未建**：chat CLIENT_ADVISORY 路径重构前后产物逐字节 diff 工具（28.B 开工硬前提） |
| R-5 | 幻觉率 0.0 | ✅ | 引用闭环门结构性保障（幻觉引用/无引用事实句必拒；场景 E 用例常驻） |
| R-6 | knowledge 离线 50+28 · business HG 门 | ⬜ | 每切换窗口重跑（既有套件，未动） |
| R-7 | /product-audit 漂移基线 diff | ⬜ | 切换前后各跑一次，只收敛不增长 |
| R-8 | restored-runs / trace 重放 | ⬜ | 28.B 前回归（plan 切片牵动 run 生命周期时必须） |

## 3. Rollback（回滚）

| # | 项 | 状态 | 说明 / 验收 |
|---|---|---|---|
| B-1 | 切片级开关 | ✅ | `INSURANCE_AGENT_QA_SLICE`（默认 ON）/ `INSURANCE_AGENT_PRODUCT_QA_SLICE`（默认 OFF）——置 0 即回退既有 agent 路径，**单 env 重启即回滚**，无数据迁移 |
| B-2 | plan 类切片开关 | ⬜ | 28.D 实施时同款（INSURANCE_AGENT_PLAN_SLICE，默认 OFF） |
| B-3 | 意图层回滚 | ✅ | LLM candidate 独立开关（INSURANCE_AGENT_INTENT_LLM 默认 OFF）；规则文件版本化（git） |
| B-4 | 回滚演练 | ⬜ | 预演：QA 切片 ON→OFF→ON，验证 run 完成、chat 交付、shadow actual_execution 三态如实 |
| B-5 | 回滚决策线 | 🔒 | 建议拒答率或一致性劣化阈值触发（observability §5 联动）；需运营拍板 |
| B-6 | 不可回滚面 | ✅ 无 | AnswerContext/shadow 记录为增量审计，无破坏性写 |

## 4. Feature Flag（开关治理）

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| F-1 | 开关清单集中化 | ⬜ | 现散于各模块常量：QA_SLICE / PRODUCT_QA_SLICE / INTENT_LLM / INTENT_SHADOW_DIR /（未来 PLAN_SLICE、AUTHORITY 总开关）——建议 28.B 开工时集中成一页 env 文档（docs/production/operations/） |
| F-2 | 总权威开关 | ⬜ | 28.B 定义 `INSURANCE_AGENT_ROUTER_AUTHORITY`（分段：qa→product→plan→full），每段独立灰度 |
| F-3 | 默认值纪律 | ✅ | 新切片一律默认 OFF；D4 的 QA 切片是唯一裁决例外（已 live） |
| F-4 | 开关与 shadow 记录联动 | ✅ | actual_execution 如实三态（insurance-qa-agent / existing-agent）——审计不因开关漂移 |
| F-5 | demo 关键词映射退役 | ⬜ | chatState.ts mapPromptToCase 仍在（demo 模式）；退役=28.B 内容，双路径测试覆盖直至完成 |

## 5. Observability（可观测）

| # | 项 | 状态 | 说明 |
|---|---|---|---|
| O-1 | 意图遥测 | ✅ | intent_classified（含 shadow 标志/route_decision/latency_ms）+ shadow.jsonl（resolver/mismatch/latency） |
| O-2 | grounding 遥测 | ✅ | qa_answered（grounding_status/failure_reason/evidence_refs/retrieval/generation/slice）+ run_dir/qa-answer-context.json 全量审计 |
| O-3 | 校准报告 | ✅ | `python -m runtime.intent.report --shadow`（分源置信/resolver/latency/mismatch/覆盖率） |
| O-4 | 前端可见性 | ✅ | 契约已同步（本阶段 Step 1/2：union=schema+reserved，双端守护测试）；**呈现**=AgentActivity v2（设计就绪，待授权实施） |
| O-5 | grounding 相位事件 | 🔒 | grounding_started/completed 已 reserved（schema+前端契约）；**后端发射**需 runtime 授权（与 28.B 同批建议） |
| O-6 | route_selected 独立事件 | 🔒 | 现内嵌 intent_classified.data.route_decision；权威切换后建议独立发射（ADR-020 审计事件设计） |
| O-7 | 告警线 | ⬜ | 拒答率（kb_unavailable/insufficient/citation_gate_rejected 分型）、latency p95、mismatch 率——建议接入 runtime/obs 指标 + 阈值告警（切换前定线） |
| O-8 | 切换日观测包 | ⬜ | 切换窗口内每小时：校准报告 + qa_answered 分布 + shadow mismatch 归因快照（人工复核材料） |

---

## 切换序列建议（勾选顺序）

```
⬜ P-1 ADR-025 立案（O-1 Unified Runtime）            🔒 人工
⬜ P-2 B4 行为等价门建设 + 基线采集                    开发
⬜ P-3 grounding_started/completed 后端发射（reserved 毕业）🔒 runtime 授权
⬜ P-4 product_qa 切片灰度（flag ON）+ S-2/S-3 数据积累  运营
⬜ P-5 HD-1/一致性阈值裁定（S-5）                       🔒 人工
⬜ P-6 28.D planning 切片（含 B-2 开关 + R-8 回归）      开发
⬜ P-7 AgentActivity v2 实施（O-4 呈现层）              开发
⬜ P-8 demo 映射退役 + 全量权威 flag（F-2）分段切换      开发+运营
⬜ P-9 切换日观测包（O-8）+ 24h 双轨                    运营
```

**STOP 边界重申**：本清单为准备产物；任何 ADR 修改、权威切换、
orchestrator/artifact lifecycle/approval 改动均需显式授权。
