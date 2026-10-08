# Phase 28.0.1 — Architecture Decision Gate Audit & Implementation Plan

Date: 2026-09-25 · READ-ONLY gate audit（零代码改动）。本文件是 Chat-first
Multi-Agent 迁移（28.A..G）实施前的**最终决策门**：核对产品对齐、依赖图、
ADR 完备性、实施风险，并给出经审的实施顺序与门禁。

Inputs：docs/PROJECT_VISION.md · docs/ARCHITECTURE_PRINCIPLES.md ·
docs/production/architecture/unified-chat-multi-agent-migration-280.md
（下称"迁移文档"）· docs/production/ADR-008..018（在册）· 迁移文档 §20
（ADR-019..024 提案）· 27.7.7–28.1 审计链证据。

---

## 1. Product Alignment（对齐核验）

**结论：对齐成立，四项检查三绿一黄。**

| 检查 | 判定 | 依据 |
|---|---|---|
| User entry = Chat-first | ✅ 愿景/原则与现状方向一致 | 默认入口已是 Chat+agent 模式（ChatLayout.tsx:30-32）；差距（发起入口错位/产物/回链）全部在 28.A/B/F/G 射程内，且方向是收敛非扩大 |
| Agent boundary | ✅ QA+Planning 双 Agent 边界与代码资产吻合 | QA=知识底座已生产形态（缺 AnswerContext+引用门=28.C）；Planning=现有 8 阶段图原样引用（28.D 仅注册不重写）；无第三业务 Agent 被引入（anti-goal 遵守） |
| Developer space separation | ⚠️ 方向对、现状欠账最大 | 无门禁/无 URL/dev 标记泄漏（漂移基线 P1）——28.G 承接；**注意 28.G 依赖 ADR-014 身份（design only）的最小落地或显式降级为"无认证空间切换"**，这是本 gate 新识别的依赖 |
| Knowledge grounding | ✅ 架构上从 prompt 自律升级为代码门 | Principle 5 + ADR-022 提案（AnswerContext+引用闭环）与 WeKnora/Catalog 边界（ADR-023）一致；现状 P0（证据不进上下文）正是 28.C 要修的 |

无任何既有 ADR（008-018）与迁移方向冲突；需显式对齐声明的三项：
ADR-004（引用闭环门=确定性代码，兼容）、ADR-011（QA 的 LLM 调用是否走
治理网关——见 §4 隐耦 #6）、ADR-016/008（会话持久化走向 PG，方向一致）。

## 2. Architecture Dependency Graph（真实依赖图 + 阻塞点）

规格书给出的线性链（Intent→Router→Registry→QA→Grounding→Planning 迁移）
**不是**真实依赖。实测依赖：

```
[G0] ADR 批准（019..024 成文并批准）          ← 阻塞一切实施
  │
  ▼
[28.A] Intent Layer + Router + Registry 契约        (ADR-020+021)
  │   内部序：IntentSchema/Rules ──► Registry 契约 ──► Router 查表
  │   （三者互不依赖既有运行时代码；可影子模式先行）
  │
  ├──────────────► [28.G] Space 分离（纯前端，28.A 后任意并行；
  │                  URL 结构需与空间设计一致，故不建议先于 28.A）
  ▼
[28.C] QA Agent + grounding                          (ADR-022; 023 契约面)
  │   依赖：28.A 的 IntentResult/Router/Registry 条目
  │   外部阻塞（不阻塞代码、阻塞价值）：KB 语料（现 10 份）
  │   子阻塞：Scenario D（产品事实）需 023 的目录 schema 决策
  ▼
[28.B] Unified Runtime                              (ADR-019)
  │   依赖：28.A 的 Registry 契约（收编目标）
  │   前置件：行为等价回归门必须先建成（可挂在 28.A 尾或 28.C 期）
  ▼
[28.D] Planning Agent 迁移（注册+ownership 声明）    (ADR-019)
  │
  ▼
[28.E] Conversation Continuation                    (ADR-024)
  │   依赖：28.D（planning agent 已注册）+ 会话持久化后端决策（PG）
  │
[28.F] Artifact Experience（统一渲染+导出）—— 28.B 后并行，不依赖 C/D/E
```

**阻塞依赖清单（Blocking）**：

| # | 阻塞点 | 阻塞谁 | 解法 |
|---|---|---|---|
| B1 | ADR-019..024 仅为提案（无独立文件、无 alternatives/边界，见 §3） | 全部 | 批准前先成文（docs-only，可授权后即做） |
| B2 | KB 语料覆盖（10 份监管文本） | 28.C 的**用户价值**（非代码） | 运营并行投入；代码先行、灰度开答 |
| B3 | 目录 schema+数据双缺（等待期/免责/健康告知） | 28.C 的 Scenario D、真实产品推荐 | 023 分两步：schema 决策先行，数据工程并行 |
| B4 | 行为等价回归门不存在 | 28.B/28.D 开工 | 在 28.A 尾声交付（chat CLIENT_ADVISORY 路径产物逐字节对比基线） |
| B5 | 会话持久化后端未决（现内存） | 28.E | ADR-024 内决策（候选 PG，对齐 ADR-008/016） |
| B6 | ADR-014 身份 design-only | 28.G 的"门禁"语义 | 28.G 先做无认证空间切换 + who-am-I 最小端点（或显式记为降级） |

## 3. ADR Completeness（019~024 完备性审计）

**在册 ADR 状态**（实测）：008/009/011/012/013/014/015/016/018 APPROVED
（多为 design-only 后分期实现）；010 DEFER；**017 APPROVED 已实现**
（27.5, commit 7985680）；011 已实现**但未接线**（agent 路径绕行，
迁移文档 R6/27.9 G-279-10——ADR 与实现的漂移样本，019..024 引以为鉴）。

**提案 ADR 完备性矩阵**（对照五要素：problem/decision/alternatives/
consequences/implementation boundary）：

| ADR | problem | decision | alternatives | consequences | impl boundary | 判定 |
|---|---|---|---|---|---|---|
| 019 统一运行时 | ✅（迁移文档 §2/§11） | ✅ §11 | ⚠️ 隐含（未列大爆炸重写/双写桥接/门面收编的取舍） | ✅ §11+§17 | ⚠️ 散落（"不重写 orchestrator"有，模块边界无） | **不成文** |
| 020 意图层+路由 | ✅ §4 | ✅ §4/§6 | ⚠️（纯规则/纯 LLM/混合的取舍未列） | ✅ | ⚠️（未声明 prompts.py 意图条款的退役边界） | **不成文** |
| 021 Registry | ✅ §5 | ✅ §5.2 | ⚠️（代码声明 vs DB vs 配置文件未列） | ✅ | ⚠️（与 TASK_AGENT_MAP/harness 的兼容边界未写） | **不成文** |
| 022 grounding | ✅ §7 | ✅ §7.2 | ⚠️（仅 prompt 约束 / 仅事后 eval / 代码门+注入 未列） | ✅ | ⚠️（工具描述修正、事件词汇增量未列） | **不成文** |
| 023 WeKnora/Catalog | ✅ §9 | ✅ §9.2 | ⚠️（catalog 作 Provider vs 独立工具 未列） | ✅ | ⚠️（schema 变更与 demo 数据兼容未列） | **不成文** |
| 024 血缘/Continuation | ✅ §13 | ✅ §13.2 | ⚠️（新建 PG 会话存储 vs 复用 harness project vs 内存+磁盘 未列） | ✅ | ⚠️（review-card 按 run-dir 键控的破坏性变更未列，见 §4 隐耦 #4） | **不成文** |

**Gate 判定：六案方向均成立、素材充分，但按本项目 ADR 标准（对照
008-018 文件结构）全部不成文。** 成文要求：每案补齐 alternatives（至少
两案被否理由）与 implementation boundary（改哪些模块、不碰哪些冻结域、
兼容承诺），并加 Status: PROPOSED → APPROVED 流转。**成文是 docs-only
工作，建议作为实施第一步（28.A 的第 0 项交付）。**

## 4. Implementation Risk（隐耦 / 迁移 / 回归）

### 4.1 Hidden coupling（本 gate 新识别，迁移文档未全覆盖）

1. **意图双源真理**：迁移期 prompts.py 的意图条款（:12-41）与 Intent
   Layer 并存 → 分类分歧无处裁决。边界必须在 ADR-020 写死：28.A 起
   prompt 意图条款降级为"展示辅助"，权威分类唯一来自 Intent Layer。
2. **工具描述谎言**：knowledge_search 工具描述承诺返回 chunk（schemas.py:
   163-165）而实现不返回——28.C 引入 AnswerContext 时若不同步修正描述，
   LLM 行为将按旧描述漂移。
3. **事件词汇静默吞并**：runReducer TRANSITIONS 表外事件被设计性忽略
   ——新增 intent_classified/route_selected 若只加后端不加 web 契约，
   UI 静默不显示（不报错），漂移无告警。28.A 必须双端同步+契约测试。
4. **Review Card 键控假设**：card 生成器按 run 目录 glob `*`/case_state
   "one case per run dir"（review_card_generator.py:63-75）——28.E 的
   "一 case 多 run"直接破坏该假设，card 可能取错 run 的 state。ADR-024
   必须把 card 键控重构列为显式边界（case 级 card 或 run-dir 布局保留）。
5. **RunManager 槽位语义**：`_active[case_id]` 一 case 一活动 run +
   `case_already_running` 409——continuation run（同 case 并发追问）与
   该语义冲突；28.E 需重定义槽位（case 级排队或意图级豁免 QA 轮）。
6. **ADR-011 网关绕行**：QA Agent 的 LLM 调用若继续走 model.py 直连，
   等于在新增路径上复制既有治理债。决策项（进 ADR-022 边界）：28.C 的
   LLM 调用经治理网关（接线 011，偿债）或显式记债走现路径——**推荐前者**，
   因为这是唯一的新增 LLM 调用点，顺带偿清 R6。
7. **AGENTS.md 冻结域**：§4 上游不可变（client-intake / requirement-
   analysis 禁改）——28.B 收编时严禁"顺手优化"上游 skill；§5 确定性
   优先同样约束 Intent 规则模块（规则外置可回归）。
8. **eval 词汇联动**：qa-answer 若成为 artifact 类型，eval.rules.json /
   review-card risk-rules / contracts 白名单三处联动；且 card"零底层
   检查的维度报 FAIL"诚实规则会让 QA run 的卡面全红——QA 是否产卡是
   bootstrap 报告开放问题 #4，必须在 28.C 开工前定案。

### 4.2 Migration risks

- **28.B 行为等价**：chat CLIENT_ADVISORY 工具链重构前后产物必须逐字节
  等价（同 seeds 对比）——等价门（B4）不存在前不得开工。
- **28.E 数据布局**：store.py "one case == one directory" 布局变更牵动
  restored-runs 只读恢复、trace 重放、card 键控三处下游——ADR-024 需
  逐处列出兼容承诺（建议：run-dir 布局保留、case 级注册表为增量叠加，
  不迁移旧数据，新会话生效）。
- **双模并存**：demo 关键词映射在 28.A 后仍存在（降级为示例开关）——
  回归测试须覆盖两条路径直到 28.B 退役旧意图路径。

### 4.3 Regression risks（基线硬门）

backend tests/runtime 599/0 · web vitest 144 + tsc clean · knowledge 离线
50+28 · business HG 门 · agent benchmark（幻觉率 0.0）· live 套件 env
门控显式 SKIP · e2e core-analysis 清单不动 · restored-runs 恢复路径回归
（重启只读恢复 + trace 重放确定性）。**每阶段收尾必须全绿并跑
`/product-audit` 与漂移基线 diff（只收敛不增长）。**

---

## 5. Final Recommendation（实施计划）

### 5.1 Approved implementation order（自 ADR 成文批准起生效）

```
第 0 步  ADR-019..024 成文（docs-only，五要素齐备，Status 流转）
第 1 步  28.A Intent Layer + Router + Registry 契约（影子模式上线）
第 2 步  28.C Insurance QA Agent + grounding（首个被路由 Agent）
         └ 并行：KB 语料运营、目录 schema 决策（023 第一步）
第 3 步  28.B Unified Agent Runtime（行为等价门先行）
第 4 步  28.D Planning Agent 迁移（注册+ownership）
第 5 步  28.E Conversation Continuation（含 card 键控重构）
并行道  28.F Artifact Experience（28.B 后任意点插入）
        28.G Space 分离（28.A 后任意点；身份门禁按 B6 降级方案）
```

顺序依据：§2 依赖图 + 风险递增排序（A/C 不动规划脊柱；B/D 是结构变更；
E 依赖最重且破坏性布局变更放最后）。**首实施阶段 = 28.A**，交付物：
intent schema+确定性规则模块（外置规则、可离线回归，合 AGENTS.md §5）、
IntentResult 校验（fail-closed→unknown）、Router 查表、Registry v1
（3 Agent 条目+启动校验）、intent/route 事件（后端词汇+web 契约双端）、
prompts.py 意图条款降级、**影子模式**（Intent Layer 只记录不裁决，与
旧 prompt 分类并行比对，产出一致性报告）+ 行为等价基线采集（B4）。

### 5.2 Forbidden changes（全周期红线）

- 重写 Orchestrator / 改 8 阶段图结构 / 改 9 skills 上游（AGENTS.md §4 冻结）
- 动 eval 唯一门语义（ADR-004）· 动审批状态机（ADR-017）· 反馈变控制信号（ADR-018）
- LLM 进 Router / LLM 绕过 Intent Layer 直定执行路径
- 新建平行执行核、平行产物存储、平行运行注册表、平行检索协议
- 无证据保险事实输出（任何新 LLM 路径必须过引用闭环门）
- 删除 demo 模式 / harness / 4 专家 / Review Card / 既有测试资产
- WeKnora 集成改动越出 AnswerContext 缝（检索/治理/再锚定不动）

### 5.3 Validation gates（逐阶段门禁）

| 阶段 | 专属门 | 通用门（每阶段） |
|---|---|---|
| 第 0 步 | 六 ADR 五要素齐备+Status 流转+alternatives 有否案理由 | git 范围合规（允许路径外零改动） |
| 28.A | 影子一致性报告（Intent vs 旧 prompt 分歧率与归因）；规则模块离线回归 100% | 全部回归基线绿（§4.3）+ 负向自检（fail-closed 注入必红）+ /product-audit 基线 diff 收敛 + 阶段文档/检查点更新 |
| 28.C | 引用闭环门 100%（cited⊆evidence、无证据必拒答）；四故障路径 e2e（A/D/F 场景）；拒答文案合规 | 同上 |
| 28.B | **行为等价门：重构前后 CLIENT_ADVISORY 产物逐字节等价**；7 存储零新增 | 同上 |
| 28.D | Scenario B 经 Router 全链 e2e；harness 回归（599 含 P8/P9 套件）不动 | 同上 |
| 28.E | Scenario C e2e；card 键控重构专项测试；restored-runs 回归；continuation 血缘断言（跨 run lineage 可查） | 同上 |
| 28.F/G | 渲染器唯一性断言；空间门禁/URL 回归；L1-L4 层级断言 | 同上 |

### 5.4 Gate verdict

**GO（有条件）**——条件：①第 0 步 ADR 成文（含 alternatives+边界）并获
批准后方可动代码；②B2/B3 外部阻塞由运营并行，不塞进工程阶段；③28.A
影子模式与 B4 等价门先行的风险顺序不得颠倒。产品对齐成立、依赖清晰、
风险已识别且全部有门禁承接。

---

## STOP

本 gate audit 完成：产品对齐核验 ✅ · 真实依赖图+6 阻塞点 ✅ · ADR 完备性
矩阵（六案均"方向成立、不成文"）✅ · 隐耦 8 项/迁移/回归风险 ✅ · 实施
计划（顺序/首阶段/红线/门禁）✅。零代码改动。等待：ADR 成文授权或直接
授权第 0 步。
