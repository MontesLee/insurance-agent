# Phase 28 Implementation Gates — per ADR

Date: 2026-09-25 · 依据：docs/adr/ADR-019..024（PROPOSED）+
phase-28-implementation-plan.md（GO-conditional）。**每案三栏：实施前
置（批准+测试）/ 禁改清单 / 通过门。** 任何一栏未满足 = 该 ADR 对应
实施阶段不得开工。

通用门（全 ADR 共享，每阶段收尾必过）：
git 改动范围合规（允许路径之外零改动）· 全部回归基线绿（backend
tests/runtime 599/0 · web vitest 144 + tsc clean · knowledge 离线
50+28 · business HG 门 · agent benchmark 幻觉率 0.0 · live 套件 env
门控显式 SKIP）· 负向自检（故障注入必红、清理复绿）· /product-audit
漂移基线 diff 只收敛不增长 · 阶段文档+checkpoint 更新。

---

## ADR-019 Intent Layer（实施：28.A 影子→权威）

**Before implementation**
- 批准：本 ADR 转 APPROVED（含意图阈值与 requires_confirmation 规则、
  v1 五意图分类定案）。
- 测试先行：IntentResult schema 契约测试、规则模块离线回归框架、
  影子模式采集管道设计评审。
- 前置件：无（根 ADR）。

**Forbidden changes**
- 禁止在意图规则中写入任何工作流/工具链知识（只判"用户想要什么"，
  不判"该怎么做"）。
- 禁止 LLM 分类结果未经确定性层直接进入路由或事件流。
- 禁止修改 eval engine / orchestrator / Router / Registry（各自独立案）。
- 禁止删除 demo 关键词映射（降级为示例开关，退役在 28.B）。

**Validation gates**
- 影子一致性报告：与旧 prompt 分类的分歧率+逐条归因，达标（阈值在
  批准时定）方可切权威。
- fail-closed 注入：超域/歧义/schema 破损输入 → unknown → 澄清。
- 事件词汇双端契约（intent_classified 进后端词汇表**与** web 契约，
  缺一即红）。

## ADR-020 Router Contract（实施：28.A）

**Before implementation**
- 批准：本 ADR + ADR-019 + ADR-021（表内容依赖两者产物）。
- 测试先行：INTENT_AGENT_MAP 全表用例（含 unknown/表外/Registry 缺
  agent 三类 fail-closed）设计评审。

**Forbidden changes**
- 禁止 router 模块 import 白名单（intent schema + registry 接口）之外
  的任何模块——orchestrator/yaml/skills/knowledge/engine 一律不准。
- 禁止在路由表或路由代码中出现保险业务条件、工作流步骤、检索调用、
  推荐逻辑、置信度再评分。
- 禁止 LLM 出现在路由路径任何位置。
- 禁止"默认 planning"兜底——唯一兜底是 conversation-agent 澄清。

**Validation gates**
- import 边界测试常驻 CI（违例即红）。
- 全表穷举单测 + 三类 fail-closed 用例 100%。
- route_selected 事件审计断言（每次路由可追溯 IntentResult）。

## ADR-021 Agent Registry（实施：28.A 契约 / 28.B 收编 / 28.D 注册）

**Before implementation**
- 批准：本 ADR（字段集+启动校验+internal 语义+O-1 范围说明）。
- 测试先行：启动校验全分支用例；TASK_AGENT_MAP 派生等价设计。
- 前置件：行为等价基线采集工具先就绪（28.B 开工硬前提，gate B4）。

**Forbidden changes**
- 禁止修改 SpecialistAgentExecutor 语义、专家 system prompts、
  insurance-analysis.yaml、planner registry task 定义（收编=改发现方式
  不是改行为）。
- 禁止修改 AGENTS.md §4 冻结上游（client-intake / requirement_analysis）。
- 禁止 Registry 运行时变更（无热更新；变更=代码变更+重启+校验）。
- 禁止 chat 工具栈在 28.B 等价门前发生任何行为差异。

**Validation gates**
- 启动校验 fail-closed（缺引用/越集/未知工具→拒启）。
- harness 回归 599 零变化；行为等价门（重构前后 CLIENT_ADVISORY
  产物逐字节等价）。

## ADR-022 Knowledge Grounding（实施：28.C）

**Before implementation**
- 批准：本 ADR（含 WeKnora/Catalog/LLM 三方边界、FAIL CLOSED 规则、
  qa-answer artifact/卡面政策**批准时裁决**、目录 schema 字段增补）。
- 测试先行：引用闭环门单测框架、四故障路径答案形态设计评审。
- 前置件：019+020+021 已实施（QA Agent 可被路由）；mock provider
  全链可离线回归。

**Forbidden changes**
- 禁止修改 Provider Protocol、治理层 R1-R9、provenance、WeKnora
  transport、mock/live 选择语义。
- 禁止知识工具描述与实现再次出现不一致（描述谎言修复后冻结同步）。
- 禁止目录缺数据时以 WeKnora/LLM 补位（事实缺失=诚实缺失）。
- 禁止 prompt-only 兜底替代代码门。

**Validation gates**
- 引用闭环门 100%（cited⊆evidence、无引用关键句拒答）。
- Scenario A/D/F e2e：grounded 答 / 事实 fail-closed / 无证据拒答。
- knowledge 离线 50+28 与 business HG 不回归；幻觉率保持 0.0。
- 若裁决走治理网关：网关接线测试；否则 debt 记录进本 ADR 修订。

## ADR-023 Chat Artifact Experience（实施：28.F，28.B 后）

**Before implementation**
- 批准：本 ADR（格式矩阵+PDF=打印优先决策）。
- 测试先行：渲染器唯一性断言方案、渲染快照基线建立。
- 前置件：无 ADR 硬依赖；深链功能等 URL 路由（28.G）。

**Forbidden changes**
- 禁止新增第二套同类 human renderer（唯一性红线）。
- 禁止用户面首屏出现 artifactType/run id 等内部标识（L1 层级）。
- 禁止删除 Review Workspace / Developer Space 的 raw artifact 查看能力。
- 禁止服务端 PDF 重依赖直引（需另案批准）。

**Validation gates**
- 渲染器唯一性断言 + 渲染快照等价（四旧表面→一新表面）。
- 导出契约（Content-Type/Disposition/格式正确）。
- vitest 144 + tsc 基线绿；L1 断言通过。

## ADR-024 Conversation / Case / Run Lifecycle（实施：28.E，最后）

**Before implementation**
- 批准：本 ADR（持久化后端=PG、存储叠加策略、card 键控重构方案、
  槽位语义）。
- 测试先行：card 键控专项测试设计、并发槽位用例、血缘断言框架。
- 前置件：28.D 完成（planning agent 已注册）；**Review Card 键控重构
  必须先于首个多 run case 落地**（顺序硬门）。

**Forbidden changes**
- 禁止修改 run-dir 磁盘布局、restored-runs 只读恢复、trace 重放
  确定性（叠加不重构）。
- 禁止修改 approval 状态机（ADR-017）；复审联动只做锚定与聚合展示。
- 禁止迁移/改写旧 run 数据（新会话生效，旧数据只读保留）。
- 禁止 QA 轮占用 case 槽位（豁免规则不可移除）。

**Validation gates**
- Scenario C e2e（规划→修改→diff→history）。
- card 键控专项（多 run case 取数正确）+ restored-runs 回归 + trace
  重放确定性。
- 并发槽位测试（同 case 修改排队、QA 不阻塞）。
- 跨 run lineage 断言。

---

## 汇总：批准 → 实施映射

| 批准动作 | 解锁 |
|---|---|
| ADR-019+021+020 转 APPROVED | 28.A（Intent+Router+Registry 契约，影子模式） |
| + ADR-022 | 28.C（QA Agent + grounding） |
| + O-1 裁决（Unified Runtime 立案或确认由 plan §5 承载）+ 行为等价门就绪 | 28.B（统一运行时）→ 28.D |
| + ADR-024 | 28.E（continuation；card 键控先行） |
| ADR-023（任意时点，28.B 后实施） | 28.F（产物体验） |
