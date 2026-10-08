# Phase 28.A-2 Report — Intent Layer Completion & QA Agent Preparation

Date: 2026-09-25 · 状态：COMPLETE · 生产执行路径**未变**（shadow 只记录
不裁决；`actual_execution` 恒 `existing-agent`；orchestrator/workflow/
skills/eval/approval/artifact 零改动；Router 权威保持禁用）。

## 1. Completed work（对应 spec Step 1-5）

- **Step 1 Pre-audit**（`phase-28a2-pre-audit.md`）：现状/缺口/风险/计划
  盘点，判定 GO，代码前置零改动。
- **Step 2.1 Context-aware classification**（ADR-019 规则 7）：意图输入
  message+会话上下文+active case 全量支持（M1 fail-closed 双保险保持）；
  **新增确定性上下文信号**——示指型产品引用（那款/这款/这个产品/那款/
  P0xx）可从会话上下文继承保险域锚点（`context:anchor_inherited`）；
  评价式措辞**永不继承**（会话中段"今天天气怎么样"仍 unknown）；
  外置开关 `context.anchor_inheritance`。
- **Step 2.2 LLM Candidate Adapter**（`runtime/intent/llm_candidate.py`）：
  provider 对象**注入**（LLMProvider 协议，模块永不 import provider）；
  env 门控 `INSURANCE_AGENT_INTENT_LLM=1` **默认关**；线程看门狗超时
  （规则文件 `llm_candidate.timeout_seconds`=4.0，env 可覆盖）；输出契约
  闭合 `{intent, confidence, explanation?, evidence?}`——**agent/workflow/
  decision_source/tool/skill/action 键一律拒收**（→`llm:invalid_proposal`
  →unknown）；超时/不可用 → raise（→`llm:candidate_error`→rule 路径）；
  规则快路径永不咨询 LLM；确定性 resolver + schema 终检永远裁决
  （HD-1 floor 引用外置规则，provisional）。
- **Step 2.3 Confidence calibration**（`report.py --shadow`）：消费
  shadow.jsonl 产出校准报告——source×confidence 交叉表（rule/llm/
  hybrid）、resolver 结果分布、unknown/clarification 比例、latency
  p50/p95/max、disagreement 类型计数、annotate 覆盖率；**不硬编码阈值**
  （floor 只引用规则文件并标注 provisional）。
- **Step 3 Shadow router improvement**（`shadow.py`）：记录新增
  `latency_ms`（classify+route 墙钟）、`resolver`（从 IntentResult 字段
  确定性派生六值——**冻结 schema 零改动**）、`reason_codes`（规则 id，
  纯元数据）、轮末 annotate 后 `mismatch_type`（空=一致；
  `intent_difference`/`confidence_difference`/`missing_context`；
  legacy 缺失=不可比不计入分母）。隐私纪律不变：sha1+len+24 字头；
  LLM explanation **绝不入记录/事件**。
- **Step 4 Testing**：`test_p28a2_intent.py` 17 测试（五项强制用例全落
  点）+ 全量回归。
- **Step 5 28.C readiness**（`phase-28c-readiness.md`）：CONDITIONALLY
  READY——代码缝明确（AnswerContext/引用闭环门/描述谎言修正），3 项人工
  决策 + HD-2 未决；**未实施 QA Agent，未触碰 WeKnora**。
- **Automatic Decision Handling**：1 条决策记录——`intent_classified`
  web 事件契约同步（web/** 超本阶段允许路径）→
  `docs/production/decisions/2026-09-25-28a2-web-event-contract-sync.md`
  标记 **BLOCKED_FOR_IMPLEMENTATION**（28.B/G 解锁）。

## 2. Files changed（28.A-2 增量；树中其余 diff 为 27.7.6-D..F..28.A-1 存量）

**新增**：`runtime/intent/llm_candidate.py` · `tests/runtime/
test_p28a2_intent.py` · `docs/production/reports/{phase-28a2-pre-audit,
intent-shadow-report-28a2,intent-calibration-report-28a2,
phase-28c-readiness,phase-28a2-report}.md` · `docs/production/decisions/
2026-09-25-28a2-web-event-contract-sync.md`

**修改**：`runtime/intent/classifier.py`（上下文锚点继承 + candidate
None/raise 契约）· `runtime/intent/shadow.py`（latency/resolver/mismatch
+ LEGACY_TO_INTENT 移驻）· `runtime/intent/report.py`（--shadow 校准模式）
· `runtime/intent/__init__.py`（docstring：llm_candidate 不在此导出）
· `config/intent-rules.yaml`（context + llm_candidate 两节，规则内容
演进）· `runtime/server.py`（**仅 shadow 块**：计时 + env 门控 candidate
（fast tier 优先）+ record 传 latency——同 28.A-1 fail-quiet 模式）

**零触碰**：runtime/router.py、runtime/agent_registry.py、orchestrator、
workflow、skills、eval engine、approval、artifact lifecycle、web/**、
schema/**（IntentResult 冻结契约未动一字）。

### git diff review（spec Required Final Validation #1）

- 允许面内：runtime/intent/* · tests · docs ✅（router.py 本阶段无需改）
- **两处超出字面允许清单的最小触达**（spec 目标所必需，显式报备）：
  `runtime/server.py` shadow 块（Step 3 live 可观测的唯一接线点；增量
  改动同 28.A-1 已授权模式，执行路径零增量）与 `config/intent-rules.yaml`
  （规则外置文件的内容演进——其存在目的）。均已在 pre-audit R1 预判并
  在此复核说明。
- 禁改面：orchestrator rewrite / workflow / skill / approval —— **零改动**
  （git status 复核：上述文件不在本阶段 diff）。

## 3. Architecture impact

- **One Runtime**：无新执行核/存储/注册表；shadow JSONL 仍是本地诊断
  文件。LLM candidate 是库模块适配器，不构成第二运行时。
- **Intent ≠ Prompt**：候选 prompt 仅生成提案；真理仍= schema+rules+
  runtime event；禁键拒收使 "LLM 决定 agent/workflow" 结构性不可能。
- **Router is Deterministic**：router.py 未动；candidate 永远不产生
  RouterDecision（decision_source 无 llm 值，契约+测试不变）。
- **ADR-019**：规则 1（propose-only）/2（不经确定性层不得进事件流——
  事件里的 intent_classified data 全部来自 resolver 产物）/3（fail-
  closed）/4（HD-1）/7（上下文信号+M1）/8（prompt 非权威）全对齐。
- **ADR-020/021**：未触碰；registry/router 契约测试原样通过。
- **字节级兼容**：context=None 时分类行为与 28.A-1 完全一致（语料回归
  22/22 同分布）；env 开关默认关 ⇒ 生产 shadow 块与 A-1 行为一致仅增
  latency 元数据。

## 4. Tests

- **Before**：629 passed / 0 failed（28.A-1 基线，348s）
- **After**：**646 passed / 0 failed（352.7s）**（629 + 新 17；
  `pytest tests/runtime tests/contract`）
- 新套件五项强制用例：①有效候选→resolver 接受/拒绝（高风险低置信→
  澄清）②LLM 输出 agent/workflow/decision_source→形状拒收→unknown
  ③LLM 不可用→rule 路径继续（快路径不受影响）④modify 无 active case→
  clarification（有会话上下文也 fail-closed）⑤legacy/shadow 分歧→仅记录
  （mismatch_type 落盘，actual_execution 不变，registry 纯度断言）。
- 另覆盖：上下文继承三态（继承/无上下文/开关关）、评价式不继承、超时
  降级、候选形状 11 种拒绝、resolver 六值派生、mismatch 词表、校准报告
  （含空记录）、llm_candidate import 边界。
- 语料回归：22/22 与 28.A-1 基线逐条一致（零漂移，
  `intent-shadow-report-28a2.md`）。
- A-1 套件 20/20 原样通过（未修改）。

## 5. Generated reports

- `intent-shadow-report-28a2.md` — 语料回归（22/22，分布同基线）
- `intent-calibration-report-28a2.md` — live 8 条（28.A-2 前旧格式，
  缺 latency/resolver 字段被如实报为缺失，不编造）；新版记录自服务器
  重启后自动携带全字段

## 6. Known limitations

1. **LLM candidate 未在 live 启用**（默认关）——重启服务器并设
   `INSURANCE_AGENT_INTENT_LLM=1` 后才开始积累 llm/hybrid 源真实数据，
   HD-1 校准依赖该数据。
2. live shadow.jsonl 现有 8 条均为旧格式；且 legacy_intent 全 None——
   annotate 覆盖率（agent_state.intent 捕获率）本身是切换 28.B 前需
   观察的缺口。
3. `intent_classified` web 契约未同步（决策记录 BLOCKED）——28.B 权威
   切换前必须闭合。
4. 上下文信号 v1.1 只覆盖示指型引用；自由指代（"它怎么样"）仍走
   unknown→澄清（正确但保守）。
5. 规则词表为中文；多语种/长尾依赖校准后的 LLM candidate。
6. mismatch 的 confidence_difference 仅在 legacy 可比且 source=llm 时
   可判（legacy 无置信度，属结构性限制）。

## 7. Next recommended phase

- **28.C（推荐先决）**：三项人工决策（qa-answer 产物/卡面政策、QA LLM
  走 ADR-011 网关或记债、目录 schema 字段）+ HD-2 KB 数据集——就绪评估
  见 `phase-28c-readiness.md`（CONDITIONALLY READY）。
- **28.B**：需先 ADR-025（O-1）+ 行为等价门 B4 + live shadow 一致性
  达标 + web 契约同步闭合。
- **或按兵不动**：重启服务器（新代码）+ 开启 `INSURANCE_AGENT_INTENT_
  LLM=1` 积累真实 shadow 数据供 HD-1 校准。

**STOP — 生产执行路径未切换；Router 权威保持禁用；等待下一阶段授权。**
