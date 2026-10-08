# Phase 28.B4 Pre-Audit — B4 门实现 + Golden 框架 + M2 灰度观测（开工前置）

Date: 2026-09-25 · 性质：MANDATORY 只读审计（先于一切代码）。任务边界：
**不切权威**（Router 保持非权威；ADR-025 保持 PROPOSED）。

## 1. ADR-025 边界核验

ADR-025（PROPOSED）§Implementation boundary 列明 M0 准备段包含"B4 门
实现"与开关/观测建设——本任务=该段实施，**不进入 M3/M4**（planning
切片/全量权威）。PROPOSED 状态下实施准备性基础设施与既定先例一致
（ADR-019..024 批准前 28.A-0 已建 schema 契约）。红线复核：不改 ADR
文件、不改其 Status。

## 2. 当前 Router authority 状态（实证）

- insurance_qa → QA Agent（flag 默认 ON，D4 裁决例外）；product_qa →
  Product QA Agent（flag 默认 OFF）；plan/modify/unknown → legacy chat
  agent。shadow 全量记录；Router 查表仅切片生效。**本任务不翻转任何
  flag 默认值。**

## 3. 既有 feature flags

`INSURANCE_AGENT_QA_SLICE`（ON）/ `INSURANCE_AGENT_PRODUCT_QA_SLICE`
（OFF）/ `INSURANCE_AGENT_INTENT_LLM`（OFF）/
`INSURANCE_AGENT_INTENT_SHADOW_DIR`。**M2 灰度旗复用 PRODUCT_QA_SLICE**
（spec 例名 GRAY 仅示意——单一真源，不建第二开关）；本任务增补的是
**观测记录**（slice_decision：选中路径/未触发原因/错误），非新开关。

## 4. 既有 golden/test 基础设施

- 语料：runtime/intent/report.py CORPUS（22 条，分类期望已验证）。
- 服务器全链测试模式：tests/runtime/_common.make_client +
  wait_terminal + FakeLLMProvider 脚本（含 planning 全链脚本资产，
  test_agent_api.test_full_agent_chain）。
- QA/Product QA 契约测试（C-1/C-2，21 用例）内含五类场景模式。
- docs/testing/router-golden-cases.md：25 案设计清单（PENDING_CAPTURE）。
- **缺口**：无可执行 golden 框架、无对比器/归一化器、无等价报告——
  即本任务 Phase 1/2 的建设面。

## 5. Artifact lifecycle 影响

B4 门**只读**：经 GET /api/runs/{id}/artifacts 读取 + run_dir 读取
qa-answer-context.json；不写 artifact registry、不新增 artifact 类型
（E2 断言 QA 轮零 artifact——D1 延续）。**零改动**。

## 6. Evaluation 影响

B4 门读取 eval 事件做集合比较；不改 eval engine/规则/门语义
（ADR-004 冻结）。runtime/evaluation/router_equivalence/ 为**新建测试
基础设施包**（对比工具，永不进生产执行路径——仅 tests/CLI import），
与顶层 evaluation/（eval 引擎，ADR-004 域）无代码耦合、不修改之。
**零改动**。

## 7. Approval / Review Card 生命周期影响

QA 轮零 approval/零 card（C-1 已验证）；B4 E2 把"零 approval/零 card"
作为断言（安全面不漂移）。不触碰 approval 状态机（ADR-017）与 card
生成器。**零改动**。

## STOP 条件核验

| 条件 | 触发？ |
|---|---|
| 需改 orchestrator | 否（零 import/零改动；B4 经服务器 API 驱动） |
| 需改 workflow engine | 否 |
| 需改 artifact contracts | 否（只读消费） |
| 需改 approval 状态机 | 否 |
| 需建第二运行时 | 否（router_equivalence=对比库；执行仍走唯一 server 路径；双跑=同进程两次真实服务器实例） |

**判定：GO。** 实施计划：P1 runtime/evaluation/router_equivalence/
（models/normalizer/comparator/runner/report）→ P2 schema/router-golden-
case.schema.json + tests/golden/router_cases.json（14 可执行案）+
docs/testing 清单增补 → P3 灰度观测（shadow slice_decision + 切片错误
 annotate + 隔离测试）→ P4 等价报告生成 → P5 全量验证。
