# Phase 28.A-2 Pre-Audit — Intent Layer 完成度盘点（开工前置）

Date: 2026-09-25 · 性质：READ-ONLY 盘点（本文件本身是 Step 1 交付物，
写入前零代码改动）。依据：28.A-2 spec + PRODUCT_VISION /
ARCHITECTURE_PRINCIPLES（FROZEN v1.0）+ ADR-019/020/021/022（均已
APPROVED）+ phase-28-implementation-plan §5 + phase-28-implementation-gates。

## 1. Current state（as-built，28.A-0 + 28.A-1 实证复读）

| 组件 | 现状 | 证据 |
|---|---|---|
| 契约 | 3 个 closed draft-07 schema（intent-result / router-decision / agent-registry）+ 10 契约测试 | schema/ · tests/contract/ |
| classifier | 确定性七步流水（specific-product → evaluative → modify → plan → qa → LLM candidate（仅注入 callable）→ unknown），schema 终检 fail-closed | runtime/intent/classifier.py |
| router | 纯查表 lookup/validate/dispatch；import 边界测试常驻 | runtime/router.py |
| registry | config 声明 + fail-closed 启动校验；无 mutation API | runtime/agent_registry.py · config/agent-registry.json |
| shadow | JSONL 记录（sha1+len+24 字头，全文绝不入记录）+ 轮末 annotate legacy_intent/action | runtime/intent/shadow.py |
| report | 仅语料 runner（22 条 CORPUS）；不消费 live shadow.jsonl；无校准统计 | runtime/intent/report.py |
| server 接线 | run_started 后 fail-quiet shadow 块（classify+route+intent_classified 事件+record），rules-only（未传 LLM candidate）；轮末 annotate | runtime/server.py:538-569, 620-629 |
| 事件 | intent_classified 已进后端词汇表；**web 契约未同步**（A-1 已知限制 #4） | runtime/events.py:67 |
| 测试 | A-1 20 测试；全量 629 passed / 0 failed | tests/runtime/test_p28a1_intent.py |
| live 数据 | shadow.jsonl 已有 8 条真实轮记录（服务器已重启过；legacy_intent 全 None=annotate 覆盖不全，本身是校准数据点） | tmp/intent-shadow/shadow.jsonl |

## 2. Missing pieces（映射 spec Step 2-5）

| # | 缺口 | 归属 |
|---|---|---|
| M1 | 上下文已作为**输入**支持（M1 fail-closed 已双保险），但未作为**分类信号**——确定性规则只看当前消息（除 active_case_id） | Step 2.1 |
| M2 | LLM candidate 只有 callable 参数位，无 provider 适配（超时/输出形状校验/禁键拒绝/不可用降级） | Step 2.2 |
| M3 | 无置信度校准度量：live shadow 无消费入口；无 rule/llm/hybrid 分源分布、clarification ratio、latency、mismatch 统计 | Step 2.3 |
| M4 | shadow 记录缺 classification latency、resolver 结果（哪一分支裁决）、disagreement 类型标注 | Step 3 |
| M5 | server shadow 块未接 candidate 开关、未测延迟 | Step 2/3 接线 |
| M6 | A-2 五项强制测试用例不存在 | Step 4 |
| M7 | 28.C 前置就绪评估文档不存在 | Step 5 |
| D1 | intent_classified 的 web 事件契约同步在 A-1 被缓（ADR-019 验证门"双端同步"未闭合）；web/** 不在本阶段允许路径内 | Automatic Decision Handling |

## 3. Risks（本阶段新增风险 + 缓解）

- **R1 改动范围**：spec 允许清单（runtime/intent/*、router.py、tests、docs）字面不含
  runtime/server.py 与 config/intent-rules.yaml，但 Step 2.1（规则外置）与
  Step 3（live 可观测）必须触达两文件。缓解：server.py 只在**既有 fail-quiet
  shadow 块内**做最小增量（同 28.A-1 已授权模式，执行路径零增量）；rules
  yaml 是规则文件的内容演进（其存在目的）；最终报告 git review 节显式列出
  并说明。
- **R2 分类漂移**：新增上下文规则不得改变 context=None 行为。缓解：规则经
  外置开关（context.anchor_inheritance）+ 语料回归重跑必须 22/22 不变。
- **R3 LLM 进 shadow 增加业务轮延迟**：candidate 调用发生在 fail-quiet 块内。
  缓解：**默认关**（INSURANCE_AGENT_INTENT_LLM=1 才启用）+ 线程看门狗硬超时
  （默认 4s，env 可调）+ 失败即走 rule 路径；启用时优先 fast tier。
- **R4 schema 冻结**：IntentResult additionalProperties:false——resolver/latency
  等新观测量**只进 shadow 记录与事件 data**，绝不进 IntentResult；从既有字段
  确定性派生（confidence_source+reason_codes+clarification_required），零
  schema 改动。
- **R5 mismatch 语义**：legacy 侧无置信度可比。缓解：确定性类型定义——
  intent_difference（映射后意图不同/不可映射）/ missing_context（shadow 因
  active_case 缺失澄清）/ confidence_difference（同意图且 source=llm 低于
  外置 floor）；legacy 缺失=不可比，不计入分母。
- **R6 隐私**：LLM explanation 可能回显用户文本。缓解：explanation **绝不**
  进入 shadow 记录或事件（沿 hash-only 纪律）。
- **R7 回归**：report.py 重构保持公共函数签名兼容；A-1 的 20 测试不改不红；
  全量基线 629 只增不减。

## 4. Implementation plan（顺序）

```
A config/intent-rules.yaml + classifier.py —— 指示范词锚点继承（窄口径：
   仅 product_specific 示指/产品号，evaluative 不继承——会话中段
   "今天天气怎么样" 仍必须 unknown）
B runtime/intent/llm_candidate.py —— provider 适配（LLMProvider 协议复用、
   线程超时、严格输出形状 {intent,confidence,explanation?,evidence?}、
   禁键 agent/workflow/decision_source 拒收、env 门控默认关）
C runtime/intent/shadow.py —— latency_ms + resolver 派生 + mismatch_type
   （annotate 时计算并落盘）
D runtime/intent/report.py —— --shadow 消费模式 + 校准统计（分源置信分布/
   unknown/clarification/resolver/latency/mismatch；不硬编码阈值，floor 只
   引用外置规则文件并标注 provisional）
E runtime/server.py —— shadow 块最小增量：延迟计时、env 门控 candidate
   （fast tier 优先）、record 传 latency
F tests/runtime/test_p28a2_intent.py —— 五项强制用例 + 上下文/超时/禁键/
   mismatch/校准用例
G 全量回归 + 语料回归重跑（22/22 不变证明）+ 校准报告生成
H 28.C readiness + decisions 记录（D1）+ phase-28a2-report.md
I 记账（checkpoint/current-task/decisions/memory）
```

**判定：GO** —— 无 STOP 条件；无需触碰禁改面（orchestrator/workflow/
skills/eval/approval/artifact 全程零改动；Router 权威保持禁用，
actual_execution 恒 existing-agent）。
