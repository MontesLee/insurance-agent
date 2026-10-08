# ADR Approval Review — Phase 28.0.3 Review Board

Date: 2026-09-25 · 审阅对象：docs/adr/ADR-019..024（PROPOSED）。
评审立场：本会以"未来维护者"视角审阅（作者-评审分离原则——ADR 由
Phase 28.0.2 起草，本会独立复核）。零代码改动；**本会只裁决与提出修改
文本，不直接修改 ADR 文件**——MODIFY 项待所有者确认后落笔。

评审依据：五项标准（问题真实性/边界清晰度/一致性/可增量实施/长期稳定）
+ 逐案特别问题 + O-1。参照：PROJECT_VISION · ARCHITECTURE_PRINCIPLES ·
phase-28-implementation-plan/-gates · ADR-001..007（创始）· ADR-008..018
（生产化）· 27.7.7-28.0.1 审计链。

---

## Approval Matrix

| ADR | Decision | Reason（摘要） |
|---|---|---|
| **019 Intent Layer** | **MODIFY**（小改后可批） | 问题真实、边界清楚、影子迁移可行；**缺一条：意图分类的会话上下文输入**——"把保额改成30万"无关键词，须显式规定分类输入含近期轮次+active case 存在性（见 §019-M1）。修改后即 APPROVE |
| **020 Router Contract** | **APPROVE** | 六案中最紧：职责单一（intent→agent）、四禁+import 白名单可测试、fail-closed 兜底正确、与现状无冲突（现状无 router，纯增量） |
| **021 Agent Registry** | **APPROVE**（附形态裁定） | 单一真源+启动校验成立；v1 形态裁定=**A 配置（代码内声明）**（见特别问题）；TASK_AGENT_MAP 等价承诺保住 599 回归 |
| **022 Knowledge Grounding** | **APPROVE**（附两项裁定） | 三方边界/FAIL CLOSED/引用闭环门成立，与创始 ADR-005 同脉相承；证据必须性裁定=**YES（无条件）**；qa-answer 卡面政策列人类决策（附建议） |
| **023 Artifact Experience** | **APPROVE**（附默认格式裁定） | Text+Artifact/渲染唯一性/dev 不上主屏成立；v1 默认输出裁定=**A Markdown**（HTML v1.x、PDF=打印包装，见特别问题） |
| **024 Conversation Case Lifecycle** | **MODIFY**（两处补强后可批） | 模型正确且四能力支撑三项半；**缺：①反馈锚定条款**（反馈须绑 run+artifact 版本，修改后历史反馈才不串版本）**②与 data_policy/保留策略的对齐**（持久化会话存客户事实×真实客户数据默认 BLOCKED 的 451 门——见 §024-M1/M2）。本会判定其为六案中破坏面最大，修改+card 键控先行不变 |

**总裁决：无 REJECT。四案可直接批，两案小改后批，无方向性错误。**

---

## 逐案评审详情

### ADR-019 — 五项标准 + 特别问题

- 问题真实性 ✅：prompt 内意图不可测、LLM 自裁执行路径（漂移 P0-②），
  是真实架构问题而非偏好。
- 边界 ✅：只判"用户想要什么"、不判"怎么做"；prompts.py 降级条款解决
  双源真理；Router/Registry 零越界。
- 一致性 ✅：与 Principle 2/3、ADR-004 精神、AGENTS.md §5（规则外置可
  离线回归）一致；demo 关键词表退役路径已写明。
- 可增量 ✅：影子模式（记录不裁决）→ 分意图切权威，无 big-bang。
- 长期 ⚠️→修补：2→10 Agents 时意图集与路由表增长没问题（穷举可测），
  但**会话式指代**（"改成30万""那个方案呢"）在现文本里没有输入来源
  规定——这不是 v2 问题，是 v1 第一天就会遇到的输入（Scenario C 原文
  即无意图关键词，靠上下文才知道是 modify）。

**特别问题 1：意图识别应为 A LLM only / B Rule only / C Hybrid？**
**推荐 C（Hybrid，即 ADR 现方案）**：规则优先（确定性、可穷举测试、
离线回归），LLM 仅长尾提案（advisory），确定性层终裁。理由：A（LLM
only）使第一跳非确定——路由输入不可回归测试，违背 ADR-004 同精神且
置信度不可复现；B（Rule only）对保险口语长尾召回不足，兜底全落
unknown→澄清会造成澄清疲劳（用户体验塌方）；C 以 <10% 的复杂度换取
长尾覆盖，且 LLM 失效时退化为 B（安全降级而非故障）。

**特别问题 2：意图真理存于何处？**
**答：schema（契约）+ 外置规则文件（逻辑）+ runtime 事件（记录），
不存于 prompt。** 精确地说：意图分类的**词表**由 IntentResult schema
定义（代码契约，评审期可 diff）；**判定逻辑**在 resources/config 规则
文件（可离线回归）；**每次裁决**落 `intent_classified` 事件（审计真身）。
prompt 自 ADR 生效日起降级为展示辅助，不再持有真理。

**§019-M1 修改文本（提案）**——Decision 增补：
"意图分类输入 = 当前消息 + 会话上下文（最近 N 轮摘要 + active case
存在性标志）。确定性规则可引用上下文信号（如 active_case_present 且
命中修改动词 ⇒ modify_existing_plan 候选）；LLM 提案同样获得该上下文。
上下文不可得（新会话/重启后）时，修改类意图不可成立，降级为澄清。"

### ADR-020 — 验证确认

- **Router 只做 intent→agent**：✅ 确认。INTENT_AGENT_MAP 查表是唯一
  行为；输出 agent_id + route_selected 事件。
- **Router 不能访问 WeKnora / 产品目录 / 选择 workflow**：✅ 三项确认。
  机制有三层：契约明文（四禁+置信度再评分禁+LLM 永禁）；import 白名单
  （router 只准 import intent schema + registry 接口——WeKnora/Catalog/
  orchestrator/yaml 物理不可达）；常驻 CI 的 import 边界测试（违例红）。
  product_qa 与 insurance_qa 同落 QA Agent、目录优先还是知识优先由
  Agent 内工作流决定——这正是"Agent owns workflow"的正确体现，非路由
  职责泄漏。
- 长期：表规模随 Agent 数线性增长，穷举测试成本 O(agents×intents)，
  10 Agent 完全可承受。**APPROVE 无保留。**

### ADR-021 — 特别问题

**Registry 应为 A 配置 / B 运行时服务 / C 数据库？**
**推荐 v1 = A（配置：代码内声明 + 启动 fail-closed 校验）**，即 ADR
现方案。理由：B（运行时服务）引入热更新与状态——Agent 身份在运行中
可变=配置漂移入口，且与"启动校验拒启"的强保证矛盾；C（数据库）把
契约变数据，多环境一致性难审，仅为远期多租户托管预留。演化路径：若
Agent 增至 10+ 或按部署差异化，可转**受同样启动校验约束的配置文件**
（YAML）；DB 仅在多租户 SaaS 化时重议。

- 一致性 ✅：TASK_AGENT_MAP 派生等价承诺保住 harness 599 回归；O-1
  范围说明诚实（不越权裁决运行时统一）。
- 长期 ✅：通信矩阵 O(n²) 在 n=10 可接受；internal 标志让专家层无疼
  保留。**APPROVE（附形态裁定记录）。**

### ADR-022 — 裁决与定义

**最终裁决：保险事实必须有证据？——**YES（无条件）。保险条款、产品
参数、监管规定等一切事实断言，必须溯源到治理证据（WeKnora ACTIVE
版本）或目录记录（版本钉死）；LLM 参数记忆**永远不构成证据**。本会
确认这与创始 ADR-005（evidence-provenance）一脉相承——005 为工件立
此规，022 把它延伸到对话答案。

**证据缺失行为定义**（fail-closed，统一模板语义）：

```
状态: insufficient_evidence | catalog_fact_missing | retrieval_error
行为: 1) 不生成事实性回答（不部分编造、不"据我所知"）
      2) 明示缺口，统一语义模板（实现期文案治理，语义如下）:
         "根据当前知识库/产品目录，无法核实【X】。我无法在没有依据的
          情况下回答这个问题。" + 知识缺口记录（进事件/工件，供语料运营）
      3) 可选后续（仅当真实动作存在）：澄清问题 / 转人工标记 /
         告知该数据在目录中暂缺（Scenario D 语义）
```

- 一致性 ✅：四故障路径全部映射既有机制（Provider 错误族/4 态 status/
  冲突检测/R2-R2b）；治理层零改动。
- 可增量 ✅：mock 全链先行、live env 门控、目录 schema 决策与数据工程
  分离（数据不阻塞代码、阻塞真实价值）。
- 长期 ✅：多知识源=Provider 协议既有设计；引用闭环门与源数量无关。
- 遗留人类决策：qa-answer 是否产 Review Card（本会建议：**v1 不产卡**
  ——卡机面向规划产物，逐问产卡会淹没审核员；改为 qa-answer 工件落档
  +离线 grounding eval 抽检；待所有者确认）。

### ADR-023 — 裁定与定义

**默认输出 v1/future 推荐**：**v1 = A Markdown only**（chat 内渲染 +
`?format=md` 导出，零新依赖、rendered_report 现成）；**v1.x = HTML**
（确定性模板，字节可回归，服务导出与打印的基座）；**PDF = 浏览器打印
HTML/Markdown 视图**（打印样式+打印按钮，不发文件）；**服务端 PDF =
future**（仅当出现真实"离线交付"需求信号再议，重依赖另案）。理由：
v1 蔑视零风险路径；HTML 是打印与排版的正确基座；PDF 的本质需求是
"带得走"，打印即满足，服务端生成是优化不是能力。

**用户工件 vs 开发者工件定义**：

| | 用户工件（User Space） | 开发者工件（Developer Space） |
|---|---|---|
| 本体 | **同一存储工件**（信封+payload+provenance） | 同左 |
| 投影 | human-readable 渲染（报告章节/方案摘要/证据引用），业务标题标识（"家庭保障方案报告"） | raw JSON 信封 + 注册表元数据（ART-id/血缘/fingerprint）+ 事件/trace |
| 禁止 | 内部 id 作主内容、payload 直出、枚举原文 | —（无限制，永久审计居所） |
| 渲染器 | 每类型恰一个（唯一性红线） | 一个 raw viewer |

### ADR-024 — 最重要的案子

**模型核验：Conversation→Case→Run 支撑四能力？**

| 能力 | 支撑 | 依据 |
|---|---|---|
| continuation | ✅ | conversation 绑定 active case；同 case 新 run；QA 轮不建 case 不占槽 |
| modify existing plan | ✅ | modify 意图（019+M1 上下文条款后成立）→ human-input artifact（provenance+FACT_CONFLICT）→ RERUN_FROM_UPSTREAM 子图重导出 → 报告 diff → 高影响走 replan/HITL |
| human review | ✅ | card 键控 case 感知重构（先行硬门）+ 审批锚定 run/case 不动（ADR-017）；升级语义随 27.7.8/27.8 方向 |
| feedback learning | ⚠️ **半支撑——缺锚定条款** | 模型隐含支持（run 级血缘可定位版本），但未规定反馈绑定粒度；修改功能上线后，"这个方案不行"的反馈若不钉 run+artifact 版本，会串版本污染金标集（ADR-018 反馈=证据原则要求证据可定位） |

**识别的缺失与修改提案**：

**§024-M1 反馈锚定条款（提案）**——Decision 增补：
"反馈（ADR-018 域）锚定粒度 = conversation_id + case_id + run_id +
所评 artifact 版本（ART-id）。case 历史使纵向反馈（对第 N 版方案的
修正意见）可与前序版本 diff 关联；金标集抽取按 run+版本去重。反馈
永不直接改动 case 状态（证据非控制）。"

**§024-M2 data_policy/保留策略对齐（提案）**——Context/Consequences
增补："持久化会话将含客户事实；与 runtime/agent/data_policy.py（真实
客户数据默认 BLOCKED，server 451 门）的对齐为实施前置：会话持久化
仅在数据政策允许的存储边界内落客户事实，否则落脱敏/摘要形态。会话
保留期限与删除策略（retention）属治理决策，实施前须所有者裁定。"

其余核验：长期稳定性 ✅（会话持久化正是本模型；10 Agents 无关性；
case 级槽位防并发践踏）；破坏面确认（card 键控/RunManager 槽位/store
叠加三处下游，均已在边界条款+门内）；审批状态机零触碰。

---

## O-1 Unified Runtime — 裁决建议

**建议：A——设立 ADR-025，但授权时点后移至 28.B 开工前（不现在写）。**

理由：运行时统一改变模块所有权（runtime/agent 降级为会话前端、专家层
收编为 registry 内部策略）——这是全计划中风险最高的架构变更，按
CLAUDE.md"改变架构的决策进 ADR"的标准，它不该只活在 phase plan §5 里
（对照：008-018 为更小的变更都立了案）；保持 B（implementation
detail）会造成"最高风险决策无 ADR"的治理缺口。但**现在写会过早**：
其最终形态依赖 28.A/28.C 的落地发现（会话前端与被路由 Agent 的实际
交互面）。故：ADR-025 为 28.B 的硬前置（phase-28-implementation-gates
已有 O-1 解锁行），内容骨架现在可定（canonical=orchestrator 脊柱/
吸收式迁移/行为等价门），正式成文在 28.A 完成后。

---

## Required Human Decisions（仅所有者可裁）

| # | 决策 | 本会建议 |
|---|---|---|
| HD-1 | ADR-019 高风险意图置信度阈值（insurance_plan/modify 的 LLM 提案下限） | 0.75 起步，影子期用分歧数据校准 |
| HD-2 | ADR-022 qa-answer 是否产 Review Card | **v1 不产卡**（工件落档+离线 grounding eval 抽检） |
| HD-3 | ADR-023 v1 默认输出确认 | **Markdown**（HTML v1.x；PDF=打印；服务端 PDF future） |
| HD-4 | O-1：是否设 ADR-025 | **设**；28.B 开工前成文（骨架见上） |
| HD-5 | ADR-024 会话数据保留期限/删除策略 + 与 data_policy 451 门的存储边界 | 实施前裁定（§024-M2 前置） |
| HD-6 | 目录数据工程的所有权与来源（阻塞 022 的 product_qa 真实价值） | 运营/商务侧立项，工程侧只保 fail-closed |
| HD-7 | KB 语料覆盖目标与投入（阻塞 022 的 QA 价值） | 优先条款/FAQ 域，配合 28.C 灰度 |
| HD-8 | 019-M1 / 024-M1 / 024-M2 三处修改文本确认后落笔 | 按本会提案文本 |

## Implementation Unlock（批准后解锁表）

| 批准动作 | Allowed | 仍 Blocked |
|---|---|---|
| 019（含 M1）+ 021 + 020 批准 | **28.A**（Intent+Router+Registry 契约，影子模式+等价基线采集） | 其后全部 |
| + 022 批准（HD-2 裁定） | **28.C**（QA Agent+grounding） | — |
| + HD-4 裁决且 ADR-025 成文批准 + 行为等价门就绪 | **28.B** → **28.D** | — |
| + 024 批准（含 M1/M2，HD-5 裁定）且 28.D 完成 | **28.E**（card 键控先行） | — |
| 023 批准（HD-3 裁定；任意时点） | **28.F**（28.B 后实施） | — |
| HD-6/HD-7 | 不阻塞代码，阻塞 022 的真实价值交付 | — |

---

## 结论

六案无方向性错误；四案直接可批，019/024 各需一处/两处小改（提案文本
在案）；七项人类决策列出（均附建议）；O-1 建议立案延后成文。批准+
修改确认后，28.A 即可解锁。

**STOP — 本会未修改任何 ADR 文件与代码；修改提案文本待所有者确认。**
