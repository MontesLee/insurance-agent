# Phase 28.M5-C.2 — User-Space & HD-2 Readiness Audit 报告

Date: 2026-09-26（审计窗口 2026-09-25T16:10–16:20Z + 回归）· 性质：
**READ-ONLY AUDIT + 唯一允许的 tripwire 测试确定性修复**。业务代码
零改动（唯一 code change = 1 个测试文件的时钟固定，见 §H）。

## A. Executive Summary

1. **User-Space 不存在**（作为可分离的产品面）：当前 web UI 是
   Phase-1 内部观测台 + 27.5-27.7.6 治理面的单壳四入口应用；chat
   **能力**存在且产品路径干净（M5-C.1 实测），但没有任何
   route/flag/配置能呈现"仅消费者体验"——四入口、Developer 组件
   内嵌、demo 模式均为**无条件渲染**。→ `USER_SPACE_EXISTS = NO`，
   按 §18 **STOP（不自行实现）**；需 Owner 授权专门的 User-Space
   Consumer Surface 设计/实现阶段。
2. **HD-2 = CONFIG_ONLY**：真实 WeKnora 的代码路径完整（strict 模式
   禁 mock、启动期校验、live provider+治理链），Phase-24 基础设施
   **仍在运行**（docker: WeKnora-app :8080 存活[401=需鉴权]、
   docreader/redis/pg + agent-postgres :5433）；缺的只是生产
   runtime env 三变量接线（Owner 凭据动作）。
3. **Planning tripwire = 纯测试确定性问题**（9 问取证 + 日期固定
   后哈希逐位复现已提交基线的预验证），已按 §15 做**最小测试修复**
   （仅测试文件时钟固定）；定向 10/10，全量回归见 §J。

## B. User-Space Finding

```text
USER_SPACE_EXISTS     = NO（chat 能力存在，但无独立/可分离的 Consumer Surface）
PRODUCT_SURFACE_READY = NO
PRODUCT_SURFACE_MISSING = YES（§6 情况 B → §18 STOP，不实现）
```

判定依据（源码级，非文件名）：

- `web/src/App.tsx`：单壳四 mode（chat/review/dashboard/developer），
  `navBtn` 四入口**无条件渲染**，无鉴权/无边界/无 feature flag；
  mode 经 localStorage 持久化，默认 chat。
- `web/src/components/chat/ChatLayout.tsx:296`：右侧
  `AgentInspectorPanel` 于 **xl 视口默认无条件渲染**（非 devMode
  门控——chat 内不存在 devMode 状态，"⚙ Developer Mode"按钮是
  App-level mode 切换）。
- `web/src/components/inspector/AgentInspectorPanel.tsx`：直接复用
  **RuntimeInspector——与 Developer Mode 同一组件**（注释自述
  "one inspector, one source of truth"）。
- `web/src/components/RuntimeInspector.tsx:39-40`：
  `<Row label="run_id" value={meta.run_id}/>` / `case_id` 无条件
  渲染（M5-C.1 U2 实测 UI 可见 run_03771136/agentcase-03771136）。
- chat 头部恒有 Agent/演示 Demo 模式切换 + `⚙ Developer Mode`
  （ChatLayout.tsx:213-245）；`makeChat` 默认携带 demo caseId
  （chatState.ts:41）→ Agent 模式下仍显示
  「Portfolio Demo Mode · bm-complete-001」
  （AgentActivity.tsx:99 无条件渲染）。

## C. Surface Matrix

| Surface | 当前存在 | 用户可访问 | 是否 Product Surface | 是否允许普通用户 |
|---|---|---|---|---|
| Consumer Chat（独立消费者面） | **NO**（能力在、面不存在） | 部分（chat tab 可达但融合内部结构） | NO | 暂 NO（需新面） |
| Conversation（历史/输入/发送/回复） | YES | YES | **部分**（交付自然语言 ✓，外壳违规 ✗） | 同上 |
| Developer Mode | YES | **YES**（一键直达，无门控） | NO | NO |
| Dashboard | YES | **YES** | NO | NO |
| Run Detail（RuntimeInspector） | YES | **YES**（chat 面 xl+ 默认内嵌） | NO | NO |
| Review（审核队列/审批/工作台） | YES | **YES** | NO | NO |
| Trace（事件轨迹/原始事件名） | YES | **YES**（RuntimeInspector 内嵌 + Developer 面） | NO | NO |

「用户可访问 YES」= 无任何鉴权/路由/flag 边界（单壳恒可见）——
即 PRODUCT_VISION User/Operator/Developer 边界在 UI 层**尚未实现**。

## D. Product Path（Agent 模式全链，M5-C.1 实测 + 本阶段源码复核）

```text
User → Composer → POST /api/chats/{id}/messages（文本原样）
  → :8000 _agent_worker → intent（rule，后端）→ Router(authority=full)
  → registry → qa/product/planning agent → 既有执行脊柱 → grounding
  → 交付（chat 消息 + SSE 事件流）
```

- **无前端关键词路由（Agent 模式）**：`mapPromptToCase`
  （chatState.ts:22）仅被 `Composer.tsx:39` 的 **Demo 分支**使用；
  agent 分支原样 `postChatMessage`（ChatLayout.tsx:124-131）。
- **无直接 Agent 选择**；**无第二 Runtime**。
- ⚠️ 但 §8 禁止模式以**用户可选模式**存在：`演示 Demo` 模式 =
  前端关键词映射（mapPromptToCase）+ `POST /api/runs`（legacy demo
  runtime 直跑，绕过 chat/intent）。该模式对普通用户可见可选——
  属 User-Space 违规清单（M5-B §19 已列为 cleanup 候选）。

## E. Internal-ID Exposure（用户可见，源码+实测）

| 项 | 证据 |
|---|---|
| run_id / case_id | RuntimeInspector.tsx:39-40 无条件 Row；U2 实测可见 |
| 原始事件名（run_started/qa_answered…） | RuntimeInspector Trace 列表；M5-C.1 U1/U2 快照实测 |
| bm-* demo case id | Composer 演示下拉 + AgentActivity.tsx:99 标签（Agent 模式亦显示） |
| approval_id / eval_id / trace_id | review 面（审核队列卡片）与 Developer 面可见；chat 面未见 |
| internal agent 名（insurance-planning-agent） | **chat 面未观察到**（进度为自然语言状态 + 事件名）；Developer/review 面存在内部标识 |
| 阶段进度文案 | AgentActivity 中文自然语言（客户建档/需求分析…）✓ 符合期望形态 |

## F. QA_REFUSED Exposure

分类（§10 五类归属）：**backend status（run_completed.result_status
=QA_REFUSED + qa_answered.grounding_status=refused）+ frontend
fallback/template 缺陷（第 5 类）**。

- 正确面：拒答文案=run_completed.message（诚实自然语言），UI 实测
  完整呈现（M5-C.1 U1）。
- 违规面：`ChatLayout.tsx:71-93 finalizeAgent` 对**任何 completed
  终态**（含 QA_REFUSED，其 run_completed status=completed）硬编码
  `artifactTitle="客户保险需求分析报告"` + `chatState.ts:210` 罐头
  话术「分析完成。我整理了一份《客户保险需求分析报告》…」+ 8 阶段
  空清单 → **虚构报告卡片**（服务端零 artifact）。
- 判定：**User-Space contract violation（记录，未修改**——修复属
  UI 产品工作，超出本阶段 wiring 范畴）。

## G. WeKnora HD-2

```text
HD-2 = CONFIG_ONLY
```

证据链：

1. **代码完整**：`knowledge/service.py`——`INSURANCE_AGENT_
   KNOWLEDGE_PROVIDER`（默认 mock；未知值报错）；**strict 模式禁
   mock（HG-24-03）且 weknora 配置为启动期硬要求（RV-P2-01，URL/
   API_KEY/KB_ID 缺一即 fail-closed）**；`knowledge/provider/
   weknora.py` live provider（Phase 18/24：HTTP transport、PG
   registry 投影、chunk 内容再锚定）。
2. **基础设施在位**：docker 实测 `WeKnora-app`（127.0.0.1:8080，
   HTTP 401=服务存活需鉴权）、WeKnora-docreader/redis/postgres、
   `agent-postgres`（127.0.0.1:5433）全部运行中（Phase-24 部署）。
3. **语料/治理链在案**：phase14-p2-weknora-poc、phase18-integration、
   PHASE_24_INDEPENDENT_REVIEW、KNOWLEDGE_GOVERNANCE.md、
   OPERATIONS_RUNBOOK.md（含 embedding-model KB stall、KB-scoped
   key、tenant header 运维要点）。
4. **缺口的全部内容 = 生产 env 未接线**：`.env` 无
   `INSURANCE_AGENT_WEKNORA_{URL,API_KEY,KNOWLEDGE_BASE_ID}`；当前
   实例 runtime_mode=demo（非 strict）→ mock 合法运行。
5. 文档缺口（次要）：`.env.example` **不含 WEKNORA 模板段**（建议
   Owner 授权后补——本阶段不改）。

激活前置（均为 Owner 动作，非代码）：① 三变量值（凭据）② 目标 KB
选择 + 语料时效复核 ③ 生产实例 strict-mode 决策（strict 下 mock 被
禁，接线即生效）④ 接线后按 OPERATIONS_RUNBOOK 验证检索/治理闭环。

## H. Planning Tripwire（728/729 → 修复）

§14 九问完整回答：

1. **test**：`tests/runtime/test_p28b6_preflight.py::
   test_planning_baseline_matches_committed`（GC-PL-G01）。
2. **fixture**：`tests/golden/planning-baseline.json` →
   `artifact_hashes[3]`（knowledge-evidence artifact）。
3. **日期**：evidence 条目 `governance.as_of`——已提交基线=
   2026-09-25（采集日）；失败运行=2026-09-26。
4. **跨午夜机制**：M5-C.1 battery 23:58:19（本地 09-25）启动、
   00:0x（本地 09-26）执行到 tripwire；B6→M5-C 全部历史 battery
   均在本地 09-25 内 → 首次暴露。本地=UTC+8，本地日期在 08:00Z
   翻日 → 此后所有跨 08:00Z 的 battery 都会失败（非偶发）。
5. **是否 datetime.now()**：否——`time.strftime("%Y-%m-%d")`
   （knowledge/service.py:332，as_of 接缝，模块文档明示"system
   date AT THIS SEAM ONLY"）。
6. **是否本地时区**：是（time.strftime 无 gmtime → 本地日期）。
7. **基线是否依赖日期**：是，且仅此一处——其余指纹全部日期稳定
   （ISO 时间戳被 runner 归一化为 TS；其余 artifact 哈希/事件链/
   eval/risk 全等）。全仓 `"%Y-%m-%d"` 唯一使用点即该接缝。
8. **是否只影响 test determinism**：是——as_of 取系统日期是
   **生产设计行为**（治理窗口语义），失败仅因测试拿"当日"与
   "采集日"比对。
9. **是否影响 production behavior**：否（预验证：将接缝固定回
   2026-09-25 后，fresh 哈希**逐位复现**已提交基线
   `3f75b2783e7f4570…`，其余字段全等）。

**修复（§15 授权的最小确定性修复，仅测试文件）**：
`test_planning_baseline_matches_committed` 增加 monkeypatch——
`time.strftime` 仅对 `"%Y-%m-%d"` 格式返回基线采集日 `2026-09-25`
（其余格式委托真实实现；测试结束自动还原）。生产 as_of 语义、
基线内容、golden 契约、被测代码**零改动**。定向 10/10 PASS。

## I. Changes

```text
Code Changes（业务）:    NO
Architecture Changes:   NO
Contract Changes:       NO
Test-harness change:    YES — tests/runtime/test_p28b6_preflight.py
                         （tripwire 时钟固定，§H；唯一改动——该文件
                         属 B6 起未提交 span，tracked-diff 集不变）
Docs:                   本报告
```

§21 git 审计：tracked-modified 集与 M5-C/M5-C.1 完全一致（既有
9 项，均非本阶段产物）；本阶段唯一实质改动=上述测试文件（allowed
"test fixture / test harness"）+ docs 报告 + tmp 取证（ignored）。
禁改区（runtime/router/agent/grounding/schema/ADR/权威默认等）
**零触碰**。

## J. Regression

```text
backend: PASS — 729/729（本地 09-26 跨日运行——修复经日期滚动验证）
web:     PASS — 148 passed + 2 skipped
tsc:     PASS — clean
B4:      PASS — 套件定向 23/23 之一（7 tests / 17 golden cases；battery 内亦绿）
M4:      PASS — 9/9
M3:      PASS — 7/7
```

（定向：test_p28b4_gate + test_p28m4_staging + test_p28d_m3_slice =
23 passed；tripwire 套件 test_p28b6_preflight 定向 10/10。）

## K. Recommendation（事实性 next gate，不含 Permanent Full 判断）

1. **User-Space Consumer Surface**：需要 Owner 授权专门的
   设计/实现阶段（新面或对现壳做空间隔离 + QA 终态模板修复 +
   demo 模式移出用户视野）——本轮 audit 的 STOP 项。
2. **HD-2 激活**：Owner 提供三 env 值 + KB 选择 + strict 决策；
   接线后重跑 M5-C.1（其 BLOCKED 前置即此）。
3. 回归绿后，M5-C.1 的其余 Owner 决策项（citation 缓解 / M5
   Cleanup / Permanent Full Authority）保持原样排队。
