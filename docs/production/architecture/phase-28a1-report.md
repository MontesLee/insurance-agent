# Phase 28.A-1 Report — Intent Layer Runtime Integration & Shadow Router

Date: 2026-09-25 · 状态：COMPLETE · 生产执行路径未切换（shadow 只记录
不裁决）；orchestrator/workflow/skills/eval/approval 零改动。

## 0. 开工前置检查（spec 要求）

1. **Repository architecture scan**：复读 runtime/events.py（事件契约）、
   server.py 的 RunManager.__init__/create_agent_run/_agent_worker（接线点）、
   agent/prompts.py（降级对象）、agent/chats.py（会话上下文）。
2. **ADR compliance check**：ADR-019（M1 已批准）/020/021 全部约束映射
   到实现（见 §2 影响分析）；无 ADR-004/017/018 触碰。
3. **Existing intent implementation audit**：28.A-0 的
   intent-contract-audit-28a0.md（意图真理仅在 prompt；无 router；
   planner task_type≠用户意图）。

未出现 STOP 条件（无需改 orchestrator 核心/workflow/artifact lifecycle/
新增 runtime——intent 层是库模块+旁路记录，不是执行引擎）。

## 1. Changed files

**新增**：
- `config/intent-rules.yaml` — 外置规则（version:1；词表/markers
  insurance_anchors+product_specific+product_evaluative+definition/
  intents signals+support_signals 两级/thresholds HD-1=0.75）
- `config/agent-registry.json` — 3 Agent 声明（qa/planning/conversation）
- `runtime/intent/__init__.py` / `classifier.py` — 确定性优先分类器
  （规则快路径→LLM candidate（可选、仅提案）→确定性 resolver→schema
  终检 fail-closed→unknown）
- `runtime/intent/shadow.py` — shadow 记录器（JSONL；message 只存
  sha1+长度+24 字头，全文绝不入事件/记录）
- `runtime/intent/report.py` — 语料 runner + 统计报告
- `tests/runtime/test_p28a1_intent.py` — 20 测试

**修改**：
- `runtime/events.py` — EVENT_TYPES 增 `intent_classified`（唯一改动；
  事件契约/管道不变）
- `runtime/server.py` — 三处增量：RunManager.__init__ 加载 registry
  （fail-closed 启动校验）；_agent_worker run_started 后 shadow 块
  （classify+route+intent_classified 事件+shadow 记录，fail-quiet 包裹
  ——shadow 故障绝不破坏业务轮）；run 完成后 annotate legacy_intent
- `runtime/agent/prompts.py` — 意图条款降级（见 §6 前后对照）
- `runtime/router.py`（新文件，属修改清单内的"新增模块"）——确定性
  Router（lookup/validate/dispatch；输出过 router schema 自检）

## 2. Architecture impact analysis

- **不新增平行 runtime**：runtime/intent/ 是被现有 server 路径消费的
  库模块；shadow JSONL 是本地诊断文件（tmp/），不是第二 run store、
  不进事件管道。
- **ADR-019**：IntentResult 真理=schema+rules+runtime event ✓；prompt
  降级为辅助 ✓；M1 双保险（代码 clarify=not has_case + schema if/then）✓；
  LLM 仅 candidate（candidate 异常/越词表→fail-closed unknown）✓；高风险
  LLM 提案低于 0.75 → clarification ✓。
- **ADR-020**：Router 纯查表（表从 registry 派生）；decision_source 无
  llm 值（schema 结构排除+测试）；import 边界（router.py 只 import
  jsonschema，测试扫描 import 行）✓；invalid IntentResult → 路由为
  unknown 兜底（原始错误保留在 validation_result.errors，bogus 值不泄入
  契约文档）✓。
- **ADR-021**：config 声明+启动 fail-closed 校验（schema 违例/越词表/
  意图重复声明/缺 unknown 兜底 Agent 均拒启）✓；无任何注册/变更 API
  （禁动态注册的结构性实现）✓。
- **既有系统**：orchestrator/eval/repair/approval/review-card/
  SSE 契约/restored-runs 零触碰；demo 关键词映射未动（28.B 退役）。

## 3. Intent flow diagram（as-built）

```
User Message (chat)
  ↓  _agent_worker (server.py, run_started 之后)
recent context (≤8 轮) + chat_id            [active_case 恒 None：ADR-024 blocked]
  ↓
rule classifier (config/intent-rules.yaml)
  ├─ 命中 → IntentResult(source=rule, conf=1.0)         快路径，LLM 不参与
  ├─ 未命中 → LLM candidate（可选注入；本阶段未接 provider）
  │     └─ 提案 → deterministic resolver（词表校验/HD-1 阈值/fail-closed）
  └─ 仍无 → unknown_insurance_intent (clarification_required=true)
  ↓ schema 终检（失败→unknown 兜底重建）
IntentResult ──→ intent_classified 事件（EventBus，data.shadow=true）
  ↓
shadow router: route(IntentResult, registry) → RouterDecision
  ├─ registry_lookup（表命中→声明 Agent）
  └─ fallback（unknown/需澄清/校验失败/未声明 → conversation-agent）
  ↓ shadow.jsonl 记录（+轮结束 annotate legacy_intent）
【实际执行完全不变：仍走既有 chat agent（actual_execution=existing-agent）】
```

## 4. Shadow mode design

- **只记录不裁决**：classify+route 的全部产物进事件与 JSONL；Agent 调度、
  工具选择、workflow 一概不动（`actual_execution` 恒 `existing-agent`）。
- **fail-quiet**：整块 try/except——shadow 层任何故障只打 stderr，业务轮
  照常（shadow 不能成为新的故障源）。
- **一致性度量**：每轮结束把旧 prompt 分类的 sticky 意图
  （agent_state.intent）annotate 进记录 → 后续真实流量可计算
  新旧分类一致率（切换 28.B 权威前的影子验收指标）。
- **隐私**：记录含 sha1+长度+24 字头；全文不入事件（events 元数据原则）。

## 5. Test results

- **新增**：`tests/runtime/test_p28a1_intent.py` 20/20（六项强制用例
  全覆盖：规划请求/知识问题/产品问题（含 P001 特指 vs 定义式）/无上下文
  修改→clarification/LLM 形状决策必拒+router import 边界/随机文本→unknown；
  另含 LLM candidate 四态（采纳/高风险阈值/快路径不咨询/异常降级）、
  registry 三类篡改拒启、事件词汇、shadow 记录+annotate）。
- **契约兼容**：tests/contract 10/10 继续全绿。
- **全量回归**：`pytest tests/runtime tests/contract` → **629 passed, 0
  failed（348s）**（基线 599 + 新 20 + 契约 10）。
- **接线冒烟**：`runtime.server` 导入 OK；RunManager 启动加载 registry
  （五意图→三 Agent 映射正确）；样例消息分类正确。
  （注：127.0.0.1:8000 在跑的进程仍是旧代码——重启后 shadow 开始积累
  真实流量。）

## 6. Prompt 降级（前后对照）

- **改前**（runtime/agent/prompts.py:9-12）："Your FIRST job on every
  user message is to classify their intent, then act accordingly." +
  标题 "## Intent classification (always include `intent` in agent_decide)"
  ——prompt 是意图真理来源。
- **改后**："The RUNTIME Intent Layer (schema + rules + events, ADR-019)
  classifies every user message BEFORE you run — that classification is
  the intent authority." + 标题 "## Intent guidance (behavioral
  reference — NOT the intent source)"；agent_decide 意图上报保留但标注
  为 shadow 对照过渡用途、不得与 runtime 分类矛盾。
- **未动**：五类意图的行为规则、Ambiguity rule、Hard rules 1-7、
  Key boundary——全部原文保留（行为等价；退役留给 28.B）。

## 7. Known limitations

1. LLM candidate 已实现但未接 provider（规则快路径覆盖当前语料 100%；
   provider 适配留 28.A-2——届时 source=llm/hybrid 才会在生产出现）。
2. 会话上下文已传入但未作为分类信号（v1 规则仅看当前消息；指代消解
   依赖 active_case，而 case 持久化被 ADR-024 约束 BLOCKED——故
   modify 恒 clarification，这是设计正确性而非缺陷）。
3. shadow 真实流量自服务器重启后开始积累；本报告为语料基线
   （docs/production/reports/intent-shadow-report-2026-09-25.md：
   22 请求，22/22 与 v1 期望一致，19/19=100% 与 legacy 映射一致，
   unknown 14%）。
4. web 事件契约未加 intent_classified（按 spec"用于未来 UI 展示"；
   前端 timeline 对未知类型设计性忽略——加类型时需双端同步）。
5. 规则文件为中文关键词集——多语种/口语长尾覆盖依赖 LLM candidate
   （HD-1 校准后启用）。

**STOP — 生产执行路径未切换；等待 28.A-2/切换授权。**
