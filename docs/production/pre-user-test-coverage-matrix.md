# Pre-User-Test Production Coverage Audit（普通用户测试准入前全系统覆盖审计）

Date: 2026-09-30 · Mode: **AUDIT ONLY**（零代码/测试/语料/阈值修改；
仅阅读+既有测试确认）· 结论：**PRE-USER-TEST COVERAGE AUDIT: COMPLETE**

审计基线：HEAD 24082d5（+P2-1/FIX2 工作树已 runtime-reverified）·
电池 865+2 · web vitest 270+ 系列 · 冻结件 Intent/C1/C2/K.26/Claim
Support SEALED · Planning/LLM Judge OFF · S2 OPEN-UNSTARTED（Batch-2
物理分发进行中·Owner 线下动作）。

## Coverage Matrix（用户旅程主线）

| ID | 用户链路/模块 | 风险 | 正常路径 | 异常路径 | E2E | Runtime | 状态 | Evidence | 缺口 |
|---|---|---|---|---|---|---|---|---|---|
| UJ-1 | Chat 输入（空/超长/特殊字符/重复/连发） | P2 | PARTIAL | PARTIAL | 部分 | 部分 | **PARTIAL** | chatState.test（send/binding）；API 测试 test_agent_api 8 节；K.5/K.27 真实 15+轮 | 超长/特殊字符/连发节流**未见专项**；非法输入仅 intent invalid 探针 |
| UJ-2 | 会话/上下文（新建/恢复/8 条窗/切换/污染） | P1 | TESTED | PARTIAL | 部分 | 部分 | **PARTIAL** | C1 派生（server 上下文）12 节；E-2 投毒 chat DOM 测试；K.27-RV4 A 真实两轮 | **刷新后恢复/多 tab/浏览器端会话持久化未见专项**（内存态 V0.1 已知）；「Intent 对 Context 错」面：pending 派生已测，跨重启丢失已记录 |
| UJ-3 | Intent 分类 | P1 | SEALED | SEALED | ✓(live) | ✓ | **SEALED** | e306118·金标 224（95.9%/F1 0.949）·FIX-LIVE 18 探针 | 无（残余=SW-10/REC taxonomy debt 已裁 D2） |
| UJ-4 | C1 延续 | P1 | SEALED | SEALED | ✓(live) | ✓ | **SEALED** | C1 12/12·RV4 真实两轮一等回归·C1-LIVE | ask-vs-proceed 方差=planning UX 观察项（非 intent 层） |
| UJ-5 | Router/分发 | P1 | SEALED | TESTED | ✓ | ✓ | **SEALED** | router_cases.json+B4·E2E-02 fallback | — |
| UJ-6 | 切片缝（qa/product-qa/plan/unknown_governed） | P1 | TESTED | TESTED | ✓ | ✓(full) | **RUNTIME_VERIFIED** | B4 7/7·DP 审计·K.7/K.25-RV live | slices 模式 product_qa→fail-closed=P2-1（harness 23/23+live API；**P2-1 runtime reverify 完成**）|
| UJ-7 | Planning 工作流（8 阶段/9 工具） | P1 | TESTED | TESTED | 部分 | ✓ | **PARTIAL→E2E 较强** | test_agent_loop/planning 套件·K.25-RV live 8 阶段顺序+9/9 VALID+报告交付；M3 12 节；failure_injection F01-F13 | **用户中途修改前提→重算**、**stage 重复/跳过注入**未见专项；修改流 modify 未 end-to-end（无 active case V0.1） |
| UJ-8 | 检索（正确/错题/零结果/多文档/错版本/冲突） | P1 | TESTED | TESTED | ✓ | ✓ | **TESTED+RUNTIME 部分** | C-3/C-4/C-6 探针（真实 WeKnora）·C2 套件·E2E-04/05/14 | 检索质量本身=G-1 语料缺口（28.C-3 BLOCKED@JWT）——**数据债非测试债**；多文档冲突 conflict 分支 unit 覆盖，真实冲突语料缺 |
| UJ-9 | C2 资格 | P0 | SEALED | SEALED | ✓(live) | ✓ | **SEALED** | k27rv4c2 8/8·RV4-A live 0-qualified | — |
| UJ-10 | Claim Support（数值边界/引用/产品/版本/时间/矛盾） | P0 | SEALED+FIX | SEALED+FIX | ✓(live) | ✓ | **RUNTIME_VERIFIED** | 24082d5 seal+FIX2（65/65）+runtime-reverify F2 5/5·shadow escape 88.2%→0 | 语义非字面/否定=P2-2 词法天花板（fail-closed 方向·已裁冻结）；per-claim 持久化 P3 |
| UJ-11 | 生成/引用门/重生成/拒答 | P0 | SEALED | SEALED | ✓ | ✓ | **SEALED+RUNTIME** | k22/k26 套件·E2E-06/07·regen 不可弱化 FI-5 | — |
| UJ-12 | 流式（首 delta/段界/不安全段/尾泄/断线重连） | P0 | TESTED | TESTED | ✓ | ✓(live) | **E2E_VERIFIED** | k26 6/6·K.26 live T_first<T_final（24s≪94s）·E2E-15/16 leak=0 | **SSE 断线重连/reconnect 专项**：k26/sse 套件有 cursor 重放设计，浏览器断网场景**未见专项**；K.13 12s 心跳已测 |
| UJ-13 | Artifact/报告交付（卡片/下载/版本/失败/重复/陈旧） | P1 | TESTED | PARTIAL | ✓ | ✓ | **TESTED+RUNTIME** | E-4 下载（零契约）·E-5 终态优先级·K.25-RV 47.8-50.6KB 报告 live·S1 卫生 | **artifact 失败重试/重复 artifact/长报告渲染**未见专项；HTML/PDF=NOT_IN_CURRENT_SCOPE |
| UJ-14 | Chat 交付/重试/继续 | P1 | TESTED | PARTIAL | ✓ | ✓ | **TESTED** | K.20 流式气泡·E-7 六旅程·K.1 拒答文案 | 用户「重试同一问题」UX 面部分覆盖（run 级 API 可重发；前端重试按钮行为未见专项） |
| UJ-15 | Auth/Ownership/隔离 | P0 | TESTED | TESTED | ✓ | ✓ | **E2E+RUNTIME_VERIFIED** | 28.G 15 隔离测试·E-6 5/5·K 系列 live 探针（404/403/401 矩阵）·限流 keys 模式 | 匿名并发限流=keys 模式限定（设计）；多 tab 同 key 并发会话**未见专项** |
| UJ-16 | Governance（保留/删除级联/审计） | P1 | TESTED | TESTED | ✓ | ✓ | **TESTED** | GOV-T1..T12（11）·28.I | 治理 UI/scheduler=记录未实施（已裁） |
| UJ-17 | 失败/恢复（后端/WeKnora/PG/LLM 不可用/超时） | P1 | TESTED | TESTED | ✓ | 部分 | **TESTED（注入）+RUNTIME 部分** | failure_injection F01-F13·p25 套件·K.24 deadline 8/8·K.9/K.10 llm_unavailable 真实签名·跨进程恢复 p26c4 | **WeKnora/PG 宕机时用户面行为**：kb_unavailable 拒答 unit+live 一次（K.5 429）；PG 宕机=部署前提（strict 预检拒启动）——运行中 PG 断连**未见专项** |
| UJ-18 | 并发/幂等 | P1 | TESTED | TESTED | 部分 | ✓(chat 闸) | **TESTED+（同 chat 闸 live 实证）** | test_concurrency 4 节（同 case 并发拒/不同 case 并行/适配器隔离/provenance）·M-1 409 | **同 chat 并发消息**、**同用户多 tab 并发**、**重复提交去重**未见专项 |
| UJ-19 | 可观测/审计 | P2 | TESTED | PARTIAL | — | ✓ | **PARTIAL** | F2 llm.call 48/48·run 目录 qa-answer-context·shadow.jsonl·obs 4 choke | P3-1..4 已记录（per-claim/拒答 violations/attempt-1/legacy 环 F2）——owner 队列 |
| UJ-20 | 黑盒用户体验（14 步旅程） | P1 | TESTED | TESTED | ✓ | ✓(live) | **E2E_VERIFIED（脚本黑盒；人类黑盒=Batch-G/S2）** | E-7 六旅程（浏览器实测）·K.5 10 场景 15 轮合成·K.27 7+ 真实会话·K.21/K.18 真实流式 | **完整黑盒脚本（14 步连续单用户旅程）不存在**——现有=分段旅程+真实散点；刷新后继续对话（内存态丢失=V0.1 已知限制） |

## Critical Coverage Gaps（按风险）

### P0（安全/错误交付面）——**无未 mitigated 项**

核心安全链（Intent→C2→Claim Support→Gate→Streaming→Hygiene）全
SEALED/RUNTIME_VERIFIED；DP 审计 P1-P6 结构性否定。**当前 P0 缺口
=0**。条件性项：UJ-12 SSE 断线重连的真实浏览器断网场景（k26 cursor
重放有设计+单测，缺浏览器级演练）——降 P2（重连后走 durable 事件
重放，k22 I9 已锁）。

### P1（核心链路）

1. **G-01 会话持久化**（UJ-2/20）：状态更新 2026-09-30（P1 闭合
   验证）——同进程刷新=完全恢复（TESTED·live）；后端重启丢失=
   **KNOWN_V0_1_LIMITATION**（ADR-024 债·Owner 决策项沿袭）。见
   pre-user-test-p1-coverage-closure.md。
2. **G-02 Planning 改前提重算**（UJ-7）：状态更新 2026-09-30——
   **RUNTIME_VERIFIED**（live：改收入/房贷→全流程重算·8 stages·
   旧值残留 0·后续方案全部基于新值）。见 closure 报告。
3. **G-03 同 chat 并发**（UJ-18）：状态更新 2026-09-30——**TESTED**
   （live：一 chat 一 turn 闸·第二消息 409 busy 显式拒绝·终态后
   retry 200·无丢失/串扰）。见 closure 报告。
4. **G-04 黑盒全旅程**（UJ-20）：状态更新 2026-09-30——
   **E2E_VERIFIED**（SCRIPTED_PROBE 黑盒 14/14 步 live：零泄漏·
   零卡死·上下文保持·改题重算·诚实拒答 3 步）。真实人类黑盒=
   Batch-G/S2。新观察 OBS-1（P2 路由语义）/OBS-2（P3 重复文案）
   见 closure 报告。

### P2（体验/运营）

0. **G-06/07/08 已闭合（2026-09-30 Final Gap Test）**：Network/SSE
   （中断/重连/刷新/retry 四路 E2E_VERIFIED·cursor 协议行为级）·
   PG Failure（fail-closed+隔离 E2E_VERIFIED·启动期依赖=部署特性）·
   Artifact（live 9-artifact+注入 28/28+长报告证据）——P0/P1=0。
   残余 P2：前端断线 UX 提示（UAT 观察）·运行中 PG 无进程内告警。
5. G-05 超长/特殊字符/连发输入专项（UJ-1）——限流有（keys 模式），
   输入形态边界未专项。
6. ~~G-06 浏览器断网/SSE 重连~~（2026-09-30 E2E_VERIFIED·见
   pre-uat-final-gap-test.md·残余=前端断线 UX 提示）。
7. ~~G-07 artifact 失败/重复/长报告~~（2026-09-30 E2E_VERIFIED·证据引用）。
8. ~~G-08 运行中 PG 断连~~（2026-09-30：启动期依赖=部署特性记录+
   fail-closed/隔离已证）。
9. G-09 检索质量语料债=G-1（28.C-3 BLOCKED@JWT——数据非测试）。

### P3

UJ-19 P3-1..4 观测债（已列 owner 队列）·HTML/PDF NOT_IN_SCOPE·
治理 UI·scheduler。

## Recommended Test Batches

| Batch | 目标/覆盖缺口 | 类型 | 前置 | 需 runtime? | 允许真实 pilot? | Pass/Block |
|---|---|---|---|---|---|---|
| **A — P0 Safety 复验** | 已覆盖项的发布前快照复跑（非重测）：电池+web+四密封套件+E2E22 | 既有套件 | 无 | 否（离线） | 否 | 全绿=Pass |
| **B — Core E2E** | G-03 同 chat 并发探针（1 次）+G-04 黑盒 14 步旅程（脚本化浏览器） | 探针+浏览器 E2E | runtime :8123 | 是 | 合成用户可·真实用户否 | 无状态覆盖/无泄漏=Pass |
| **C — Knowledge/ProductQA** | G-09 依赖 28.C-3 解封（JWT）；未解封前=检索拒答一致性抽测（已有 C-3 探针复用） | 探针 | 28.C-3 Owner | 是 | 否 | 28.C-3 解封前=数据受限如实 |
| **D — Failure/Recovery** | G-06 断网重连浏览器演练+G-08 PG 断连探针（1 次·恢复后复绿） | 注入 | runtime+docker | 是 | 否 | 恢复后全绿=Pass；不可恢复=Block |
| **E — Concurrency/Idempotency** | G-03+同用户双 tab+重复提交去重 | API 探针 | runtime | 是 | 合成可 | 无重复 run/artifact/无串扰=Pass |
| **F — Artifact/UI** | G-07 失败重试/重复/50KB+ 长报告渲染 | 前端+API | runtime | 是 | 合成可 | 无重复卡/无内部件=Pass |
| **G — Black-box UAT** | 3-5 名普通用户×14 步旅程引导（对照 Batch-B 脚本）；**即 S2 Batch-2 的一部分** | 人工引导 | Owner 分发 key | 是 | **是（=S2 窗口）** | OD-12 Gate A 零失败 |

## Ordinary User Test Readiness Conditions

依既有冻结政策提取（**不自创阈值**）：

- **硬门槛（已满足）**：OD-12 Gate A 当前零失败（escape/FP 增量/
  leakage/流式/RV4-B/冻结回归全零）·D-08 SEALED·runtime reverify
  PASS·四密封件零回归·电池 865+2。
- **准入形式**：本仓既定=受控试点（pilot key 受邀制）——普通用户
  测试**即 S2 Expanded Gray 的真实用户面**（OD-12：S1→S2 需 Owner
  显式批准+traffic+window——**Batch-2 分发进行中即为该批准的执行**）。
- **UAT 规模/时长阈值**：仓库无独立 UAT 阈值 → **UNDEFINED — OWNER
  DECISION REQUIRED**（S2=48h 窗口是唯一既定观测期；普通用户「正式
  测试」规模/通过标准未另定义）。
- **建议（非门槛）**：~~G-03 并发 UNKNOWN~~ 已闭合（2026-09-30
  TESTED）；Batch-B/E 相应项改为回归性复验。

## OWNER DECISION REQUIRED（现存）

1. G-01 会话持久化（ADR-024 线）——影响刷新继续旅程。
2. G-03 同 chat 并发行为确认（可先探针后裁）。
3. UAT 阈值（规模/标准）UNDEFINED。
4. 28.C-3 KB 语料解封（JWT env）——检索质量主杠杆。
5. P3 观测债四项（per-claim/拒答 violations/attempt-1/legacy F2）。
6. Planning Claim Support 独立轨道立项。
7. S2→S3（窗口期满后）·Batch-3·D-08 span 续封（P2-1+FIX2+DP+审计
   +本矩阵入封）。

---

```
PRE-USER-TEST COVERAGE AUDIT: COMPLETE
（零修改·零分发·零 S2 启动·production state 不变）
```
