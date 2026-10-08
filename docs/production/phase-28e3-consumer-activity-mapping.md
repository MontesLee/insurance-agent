# Phase 28.E-3 — Consumer Activity Mapping & Semantic Presentation 报告

Date: 2026-09-26 · 范围：**web/** only（activity.ts 扩展 + AgentActivity
DTO 渲染 + 消费者文案修复）。runtime/schema/config/契约零触碰。

## 1. Status

```text
E-3 STATUS: PASS
```

## 2. Objective

在现有 `activity.ts` 之上建立 **Consumer Activity Semantic DTO**
（确定性 allowlist 折叠），使 AgentActivity 从"解释 Runtime 事件/
stageOrder 模板"变为"渲染 DTO"；同时修复既有文案中的内部术语泄漏。
**不建第二套映射系统**（同一文件导出 activityLabel + consumerActivities）。

## 3. Pre-Audit（E-2 后事实）

数据流：SSE → runReducer(RunUiState) → AgentActivity（E-2 后仍读
stageOrder 模板 + events）· activityLabel 单行映射已存在但含内部
措辞（「检索保险知识库」「模型调用异常」「分析结束（{status}）」、
zhTool/stageZh 未知值**原样回显**）· 无 DTO · 无 dedup（单行模式无需）。
事件词汇表核对：intent_classified/qa_answered 在册；grounding_*
为 **reserved**（后端尚未发射）。**关键事实：QA 轮事件链仅 4 个
事件**（run_started/intent_classified/qa_answered/run_completed）——
检索发生在 Agent 内部，无独立事件。

## 4. Semantic Mapping（内部 → 消费者语义 → 可见性）

| Internal | Consumer | 可见性 |
|---|---|---|
| run_started | 正在理解你的问题（understand:running） | 显示 |
| intent_classified | 已理解你的问题 + 正在为你分析（work:running——路由完成=开始作答的事实） | 显示 |
| qa_answered | 已完成分析（work:completed） | 显示 |
| agent_step_started / agent_decision(finish·final) | work running / 已完成分析 | 显示 |
| agent_decision(ask_user) | 需要你补充一些信息（clarify:waiting） | 显示 |
| tool_started/completed/failed（knowledge_search、check_catalog_product，kebab/snake 双拼写） | 正在核对相关资料/已核对/未完成（materials·catalog） | 显示（仅白名单工具；QA 轮无此事件→**不虚构**） |
| grounding_started/completed（reserved） | 正在核实相关信息/已完成信息核实（verify） | contract-first 映射；真实事件到达才点亮 |
| stage_started/completed/failed（8 个已知 stage） | 正在/已+动词短语（如 已了解家庭基本情况）；未启动 stage **不出现** | 显示（仅已知 stage；未知→隐藏） |
| artifact_created@report-generation | 分析报告已生成（report:completed） | 显示（Completion≠Artifact 维持） |
| run_completed(completed/failed/needs_review) / run_failed | work 终态闭合（已完成分析/分析未完成） | §17 终态语义（waiting 不伪闭合） |
| eval_*/checkpoint_*/repair_*/其余全部 | —（eval 汇总行独立保留"质量校验 X/Y"） | 隐藏 |

单行 activityLabel 同步修复：「正在检索保险知识库」→「正在核对
相关资料」；「模型调用异常」→「处理出现波动，正在重试」（隐藏模型
概念）；「分析结束（{status}）」→ 状态映射文案（需要你补充信息/
需要进一步核实/这次没有完成）；未知事件→null（原为 null ✓ 维持）；
zhTool 未知→「处理你的请求」（原样名→通用）。**useRunStream
humanError（消费者路径）**：「无法连接 runtime server。/Runtime server
error {code}/Run 不存在」→消费者文案（内部 useRunMeta 保留内部措辞，
仅 Developer 面使用）。

## 5. Dedup

upsert-by-key 语义去重：同一语义 key 只出现一行，状态在位更新——
3×tool_started → 1 个「正在核对相关资料」（T9）。天然覆盖
SSE 重连/重复投递/重放（折叠对序列幂等）。

## 6. Unknown Handling（fail closed）

未知事件→跳过（activityLabel→null）；未知 stage→knownStageZh
null→跳过（**不再原样回显**）；未知 tool→不在 TOOL_ACTIVITY→跳过；
无文案的 (key,status) 组合→不渲染。DOM 属性仅语义值
（data-activity-item/data-status），内部 key/stage id 不入属性。

## 7. Leakage Audit

```text
internal ID = 0 · raw event = 0 · raw stage = 0 · agent ID = 0
tool/skill = 0 · router/registry = 0 · provider/model = 0
reason code = 0 · 思维链 = 0 · 伪进度/伪完成/伪产物 = 0
```
（T4/T5/T6 投毒 + DOM 级断言 + U5 live 快照佐证。）

## 8. Tests（精确数字）

```text
activity tests（映射+DTO 套件）: 25/25（src/state/activity.test.ts）
AgentActivity DTO 渲染:           6/6
DOM 泄漏（含 §26 扩展禁词）:      2/2（consumerDom）
consumerView（E-2 回归）:        12/12
SSE/reducer 路径（T13 等价）:    reducer 驱动构建 state（上述内含）+ live U5
E-2 回归（fake card/ID/refused）: 全部通过（175→189 逐项绿）
backend: 729/729 · web: 189 passed + 2 skipped · tsc: PASS
architecture invariants: 22/22（§45 清单）
```

## 9. Files Changed

```text
M web/src/state/activity.ts（DTO 折叠+文案修复+knownStageZh 守卫）
M web/src/state/activity.test.ts（重写扩展）
M web/src/components/chat/AgentActivity.tsx（纯 DTO 渲染重写）
M web/src/components/chat/AgentActivity.test.tsx（重写）
M web/src/components/chat/consumerDom.test.tsx（§26 禁词+EventSource stub）
M web/src/hooks/useRunStream.ts（humanError 消费者化）
```

## 10. Forbidden Scope Verification

```text
Runtime/Router/Intent/Grounding/Event Contract/Artifact Contract
= UNCHANGED（git 实证；backend 729/729 复证）
Auth/WeKnora/REAL_USER/Authority = UNCHANGED / NOT CONNECTED /
NOT ENABLED / UNCHANGED
第二套 Activity Mapping = 0（同一 activity.ts 双导出）
```

## 11. Deferred Items

E-4 Artifact Delivery（导出/深链）· E-5 Terminal UX（终态完整文案/
布局；waiting 轮 work 不伪闭合的呈现）· E-6 Consumer Auth ·
E-7 Consumer E2E · **词汇表缺口（Owner 可选）**：QA 轮无检索/核实
独立事件（reserved grounding_* 未发射）——「正在核对相关资料/
核实信息」里程碑在 QA 轮诚实缺席；若产品要求展示，需 Owner 授权
后端发射（STOP-10 纪律，未自行发明）。

## 12. Final Gate

```text
E-3 STATUS: PASS
```
