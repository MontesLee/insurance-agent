# Phase 28.B Readiness Audit — Router Authority 切换距离评估（只读）

Date: 2026-09-25 · 性质：READ-ONLY（零代码；spec Step 5）。目标：量化
当前距离「Message → Intent → Router → Agent 成为唯一生产入口」还差什么。

## 0. 当前权威面（as-built 实证）

| 意图 | 生产执行 | 依据 |
|---|---|---|
| insurance_qa | **QA Agent（真实路由）** | 28.C-1 D4 切片，默认 ON |
| product_qa | Product QA Agent（flag 默认 OFF；OFF 时走既有 agent） | 28.C-2 |
| insurance_plan / modify_existing_plan / unknown | 既有 chat agent（shadow 记录） | 未切换 |

即：Router 权威已按 ADR-020 迁移策略落在**首个切片**，但"唯一入口"要求
全部意图可路由——目前 3/5 意图的路由目标行为尚不存在或未切换。

## 1. Web event contract（阻塞，P0）

- `web/src/types/runtime.ts` EventType union **不含** intent_classified /
  qa_answered（grep 零命中）——后端词汇与前端契约**双端不同步**（ADR-019
  验证门"缺一即红"；28.0.1 隐耦 #3）。现状无害（reducer/switch 对未知
  类型设计性忽略），但切权威后 UI 对意图/grounding 事件**永久盲视**。
- 决策记录 docs/production/decisions/2026-09-25-28a2-web-event-contract-
  sync.md 已 BLOCKED_FOR_IMPLEMENTATION（web/** 不在既阶段允许路径）。
  **解锁动作小**（union + activity case + 双端契约测试），需一次含 web/**
  的授权。
- 附带产品决策（非阻塞）：User Space 是否展示 grounding 状态徽标
  （Product Vision 允许 evidence-grounded 输出；建议 L1 文案级"已引用
  N 条资料"，详情折入 L4）——需所有者定调后随同步一起做。

## 2. SSE 事件链（无阻塞）

qa_answered/intent_classified 经既有 EventBus→SSE 管道原样流动
（GET /api/runs/{id}/events 与 stream 均携带；无新管道、无契约破坏）。
唯一缺口即 §1 的前端类型面。

## 3. AgentActivity UI（低阻塞，随 §1）

web/src/components/chat/AgentActivity.tsx + web/src/state/activity.ts
按 event_type switch 渲染动态流——新事件类型需要 case 分支才会显示。
建议：intent/grounding 事件入 L4 开发者层级（默认折叠），避免 User
Space 噪声（Principle: 内部遥测不作用户内容）。

## 4. Conversation lifecycle（阻塞 28.E 级，非 28.B 硬门）

- 现状：每 chat 轮 = 新 agentcase（server.py create_agent_run）；
  QA 轮完全绕过 CaseState（切片 early-return）——对 QA 正确。
- planning 意图切权威前必须解决：continuation（modify）与 case 槽位
  语义（RunManager `_active[case_id]` 一 case 一 run；28.0.1 隐耦 #5）
  ——属 28.E（ADR-024 APPROVED_WITH_CONSTRAINTS，数据政策 BLOCKED 段
  未决：retention/access/deletion）。
- **顺序硬门**：Review Card run-dir 键控重构必须先于首个多 run case
  （ADR-024 边界原文）。

## 5. Artifact delivery（部分就绪）

- chat 内 ArtifactCard 已一等公民（"查看报告"打开 runtime 自有产物，
  不重渲染）——规划意图产物交付面存在。
- QA 答案非 artifact（D1 裁决）——文本+AnswerContext 审计记录，无交付
  缺口。
- 统一渲染/导出（Markdown/HTML/PDF）= 28.F（ADR-023），不阻塞权威切换，
  阻塞体验完整度。

## 6. Regression gate（B4，阻塞，P0）

- **行为等价门不存在**：28.B 开工硬前提（phase-28-implementation-
  plan §5.1：CLIENT_ADVISORY 路径重构前后产物**逐字节等价**基线采集
  工具）。28.A 尾声承诺未兑现——需补建（挂 harness demo 流程，同
  seeds 双跑 diff）。
- live shadow 一致性数据薄：shadow.jsonl 现存记录少且 legacy_intent
  annotate 覆盖不全（既有 live 记录全 None）——切换验收指标（新旧
  分歧率+归因）尚无可计算样本；HD-1 floor 仍为 provisional。
- 全量回归基线绿（今晚 after：见 phase-28c2-report §tests）；
  幻觉率 0.0 由引用闭环门结构性保障（场景 E 用例）。

## 7. 其他硬前置

- **ADR-025（O-1 Unified Runtime 立案）**：28.0.3 评审裁定"28.B 前必
  须成文"——未立案。
- **Planning Agent 路由目标行为不存在**（28.D）：insurance_plan/
  modify 路由目标=insurance-planning-agent（registry 已声明），但其
  切片行为（8 阶段图 ownership + chat 工具栈收编）未实施——唯一入口
  切换前必须就位或显式分段（先 QA 类权威、后全量）。
- **demo 关键词映射退役**：web/src/state/chatState.ts 前端 5 路映射
  仍在（降级示例开关；退役=28.B 内容）——需同步测试覆盖两条路径直至
  退役完成。

## 8. 判定与建议顺序

**28.B：NOT READY（5 硬阻塞 + 2 顺序依赖）**

| # | 阻塞 | 量级 |
|---|---|---|
| B-1 | web event contract 同步（+产品定调 grounding 展示层级） | 小（一次授权） |
| B-2 | B4 行为等价门建设 | 中 |
| B-3 | ADR-025 立案（O-1） | 文档 |
| B-4 | live shadow 一致性样本积累 + HD-1 校准（需服务器重启跑切片流量） | 运营时间 |
| B-5 | Planning Agent 目标行为（28.D）或显式分段切换决策 | 大 |
| — | 顺序依赖：28.E card 键控先行（多 run case 前）；ADR-024 数据政策三段定义 | 中 |

**建议推进序**：① web 同步（小授权，即解盲视）→ ② B4 等价门 →
③ ADR-025 → ④ 切片流量积累+校准（product_qa flag 灰度开）→ ⑤ 28.D
planning 切片 → ⑥ 28.B 全量权威（分段：先 plan 类、后退役 chat 工具
自选与 demo 映射）。每步过 phase-28-implementation-gates 对应栏。

（本审计零代码；未实施 Router authority——遵守 spec 禁令。）
