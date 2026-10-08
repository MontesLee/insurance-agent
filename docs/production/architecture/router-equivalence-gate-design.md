# B4 Behavior Equivalence Gate — 设计（Phase 28.B3 Step 2 · DESIGN ONLY）

Date: 2026-09-25 · 性质：**设计文档，不实施**。用途：Router authority
每阶段切换（ADR-025 §4 M1..M4）的客观等价验收工具设计。对应
phase-28-implementation-plan §5.1 硬前提（"重构前后 CLIENT_ADVISORY 产物
逐字节等价"）与 phase-28-implementation-gates ADR-021 栏（行为等价门）。

## 1. 定位与核心原则

**B4 门回答一个问题：切换权威后，同一输入是否产生了被证明等价的
行为？** 等价分两类（ADR-025 §7）：

| 类 | 适用 | 判定 |
|---|---|---|
| **E1 字节级等价** | planning 类（insurance_plan / modify_existing_plan 路径复用同一确定性执行：同 seeds 同 skills） | artifacts/evals **逐字节**一致（sha256 对比）；事件序列在归一化后一致 |
| **E2 契约级等价** | QA 类（insurance_qa / product_qa——新路径输出与 legacy **设计上不同**：grounded 引用答案 vs 自由文本） | 不比文本；比**不变量**：每轮 schema-valid AnswerContext、failure_reason∈枚举、引用闭环（cited⊆evidence、事实句带引）、幻觉结构性为零、延迟预算、以及与 legacy 的 shadow 一致性指标 |

原则：**确定性可复现**（离线 mock/scripted provider，同输入两次运行
自身必须先等价——自等价是工具可信前提）；**fail-closed**（无法采集
基线=该 case RED，不是 SKIP）；**报告即证据**（每阶段切换附 B4 报告）。

## 2. 输入：Golden Cases

输入 = golden case 清单（docs/testing/router-golden-cases.md，Step 3
交付）+ 每案固定夹具：

```
GoldenCase = {
  case_id, intent(期望), message, conversation_context?, seeds/case_ref?,
  provider_script(E1 planning: FakeLLM 逐步脚本；E2 QA: 答案模板),
  flags: {QA_SLICE, PRODUCT_QA_SLICE, PLAN_SLICE, ROUTER_AUTHORITY},
  equivalence_class: E1|E2,
  environment: {KNOWLEDGE_PROVIDER=mock, catalog=demo, 时钟注入}
}
```

采集方式：**同进程双跑**——同一 GoldenCase 以 `flags_off`（legacy 路径）
与 `flags_on`（目标权威路径）各执行一次，两侧捕获同一组观测（§3）。
（备选：先采基线快照落盘、后比对——用于跨版本；v1 用同进程双跑，
消除环境漂移。）

## 3. 对比维度（spec 六项全覆盖）

| # | 维度 | 捕获物（两侧各一份） | 比较器 |
|---|---|---|---|
| C-1 | **execution path** | 事件序列（/api/runs/{id}/events 全量） | **归一化后严格比对**：剥离 additive 新事件（intent_classified/qa_answered/未来 grounding_*、route_selected）；剥离时间戳/event_id/latency；E1 要求序列等价；E2 只要求 run 终态与消息交付等价（completed + assistant 消息存在） |
| C-2 | **agent selection** | intent_classified.data（intent/route_decision）+ shadow actual_execution + legacy agent_state.intent（annotate） | E1：路由目标=planning 行为单元且 legacy 粘滞意图映射等价；E2：route_decision.registry_lookup 且 actual_execution=insurance-qa-agent；unknown 案必须 fallback conversation-agent（绝不默认 planning） |
| C-3 | **artifacts** | artifact registry 全 dump（类型/血缘/status） | E1：**逐字节**（payload sha256 相等 + 元数据除时间戳外相等）；E2：QA 轮无 artifact（D1）——断言"零 artifact"本身（不得私自产生 artifact 类型） |
| C-4 | **evaluations** | eval 事件与结果（eval_id/规则/verdict/repair 次数） | E1：verdict 集合与 repair 计数相等；E2：QA 轮无 eval 事件（评估属工作流域）——同样断言零 |
| C-5 | **grounding result** | AnswerContext（run_dir 记录）+ qa_answered 事件 data | E2 主战场：schema 校验零错；grounded⇒refs≥1 且 cited⊆evidence_map；refused⇒failure_reason∈9 值枚举；D6 参数双缺必 catalog_missing_fact；**幻觉注入负向案**（scripted 无引/伪引答案）必被门拒（citation_gate_rejected）——证明门活着 |
| C-6 | **risk signals** | eval_failed/repair_*/needs_review/approval 触发/review-card 生成计数 | E1：集合相等（风险面不得因重构漂移）；E2：QA 轮零 approval/零 review-card（low-risk 声明的一致性验证）；任一侧出现计划外 risk 事件=RED |

## 4. 判定与输出

```
B4Verdict(per case) = PASS | RED
  RED 触发：任一适用比较器不等 / 基线无法采集 / 自等价失败（工具先自检：
  flags_off 跑两次，事件+artifacts 必须自身一致——排除环境噪声假阳）
报告：docs/production/reports/router-equivalence-b4-<stage>-<date>.md
  （per-case 矩阵 + 六维度摘要 + 首个差异点定位 + 两侧指纹哈希）
门禁：**阶段切换条件 = 适用 golden 全 PASS**（E1 案零 RED；E2 案零 RED）
```

## 5. 运行形态

- 离线（CI 可跑）：mock knowledge + FakeLLM/MockLLM 脚本 + demo catalog
  ——全部确定性，无网络。
- 入口（未来实现）：`python -m tools.b4_gate --cases docs/testing/
  router-golden-cases.md --stage M3`（模块落点实施时定；本阶段不建）。
- 与既有资产关系：复用 make_client/wait_terminal（服务器全链）、
  shadow.iter_records、AnswerContext 校验器；不新建运行时。

## 6. 明确边界（本设计不做）

- 不实施任何代码/工具（spec：设计 only）。
- 不切换任何 flag；不采集基线（Step 3 清单亦"不要执行"）。
- 不做 live 流量对比（那是 shadow/observability 域，M2/M4 观测包）。
- 不引入新事件类型（归一化器对 reserved 类型前瞻兼容即可）。

## 7. 风险与开放点

- E1 的 FakeLLM 脚本脆性：chat planning 路径长脚本对 prompt 变化敏感
  ——基线采集后 prompt 冻结（M3 前禁改 prompts.py planning 段）。
- 时间敏感字段（created_at/usage）归一化白名单需维护（新增字段默认
  忽略=可能漏比；默认比较=可能误报——取"白名单忽略+新增字段须登记"）。
- modify_existing_plan 在 ADR-024 continuation 段 BLOCKED 期间：golden
  案期望=planning 行为单元内澄清承接（非 continuation）——清单显式标注。
