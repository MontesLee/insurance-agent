# Phase 28.B5 Pre-Audit — M2 Product QA 灰度启用 + 回滚演练（开工前置）

Date: 2026-09-25 · 性质：只读审计（先于一切操作）。本阶段=**运营动作**
（真实服务器灰度 + 观察 + 回滚演练），预期**零代码改动**；若发现需改
orchestrator/workflow/artifact contract/approval/ADR/Router Authority
即 STOP——审计结论：**均不需要**（见 §8）。

## 1. PRODUCT_QA_SLICE flag 现行为（代码实证）

`runtime/product_qa_agent/agent.py::product_qa_slice_enabled`：
`INSURANCE_AGENT_PRODUCT_QA_SLICE`，**默认 OFF**；读取发生在每轮
`_agent_worker`（os.environ 动态读）——**env+重启即生效/回滚**，无
持久状态。切片条件四联：flag ∧ intent=product_qa ∧ 无待澄清 ∧
registry_lookup→insurance-qa-agent（server.py 切片段）。

## 2. slice_decision telemetry（28.B4 已建）

每轮 shadow 记录携带 `{slice, fired, reason}`，reason 词汇：
`flag_off` / `fired` / `clarification_required` / `not_registry_lookup`
——五语义中四者由此覆盖；`slice_error` 为切片异常时的 annotate 字段
（回退 legacy 且记录）。落盘 tmp/intent-shadow/shadow.jsonl。

## 3. slice_error fallback（28.B4 已建，测试在案）

切片执行异常 → except 捕获 → shadow annotate `slice_error` → 落回
既有 agent 路径（轮永不死）；测试 `test_gray_slice_error_annotates_
and_falls_back` 常驻（688 基线内）。

## 4. rollback 路径

**flag=0 + 重启**即回滚（无数据迁移/破坏性写；AnswerContext 与
shadow 记录为增量审计，回滚后只增不减）。演练=本阶段 Step 4 核心：
同组 product_qa 消息在 ON/OFF 两态各跑一遍，对比 selected slice/
result/events/context state；再验证 insurance_qa、insurance_plan、
unknown 回滚后无异常。

## 5-7. 隔离性（product_qa vs 其他 intent）

代码+测试双重在案：切片条件按 intent 精确匹配（product_qa 才进
product 行为）；`test_gray_flag_on_fires_only_product_qa` 断言
insurance_qa→knowledge-qa 切片不受影响、insurance_plan→legacy
（slice_decision=None）；B4 golden GC-PL-G02/GC-MD-G01/GC-UN-G01
（双 flag 开）E2 断言 plan/unknown 不进任何切片。unknown 的路由
兜底=conversation-agent（comparator 安全断言）。

## 8. STOP 条件核验

| 需求 | 判定 |
|---|---|
| 改 orchestrator/workflow/artifact contract/approval | 否——纯运营 + 观测 |
| 改 ADR-025 / 切 Router Authority / 进 28.D | 否——flag 仅为切片灰度（ADR-025 §5 既有开关语义），权威面不变 |
| 改 B4 comparator / volatility whitelist | 否——本阶段不触碰 B4 代码 |

**判定：GO。**

## 9. 灰度环境说明（如实）

- 灰度实例：本机独立进程（127.0.0.1:8106，demo 模式 loopback 免钥），
  不触碰用户既有 :8000 进程。
- LLM：**live glm**（.env 配置；密钥永不打印）；knowledge：进程环境
  无 weknora 变量 → **mock 治理组合**（fixtures KB，治理+引用全量）。
  组合如实记录于观察报告——不冒充生产 WeKnora 流量。
- 真实用户流量：无——报告将按 spec 明示 **INSUFFICIENT LIVE SAMPLE**
  （灰度样本=本次 smoke/drill 注入流量，非真实用户）。
