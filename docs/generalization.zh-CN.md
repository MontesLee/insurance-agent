# 泛化审计 —— 保险是领域适配器，不是运行时本身

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](generalization.md)

由 `tests/runtime/test_generalization.py` 结构性验证：下表"通用"列的
每个模块在代码层面无领域词（扫描命中的只有注释/文档字符串，以及
`harness.py` 内为 Phase 3 兼容而保持冻结、已记录的遗留 `TASK_DEFS`
映射）。

## 通用运行时（无领域、可直接复用）

```text
Generic Runtime
├── Planner 引擎           runtime/planner/{planner,validator,schemas}.py
│     （WHAT：不可信 LLM 输出 → 可信已校验图；重试 ≤ 2、fail-closed ——
│      对"存在哪些任务类型"一无所知）
├── Harness + 调度器       runtime/harness/harness.py
│     （WHEN/控制：任务生命周期、BSP 并行轮次、worker 隔离、scheduler
│      独占提交、恢复）
├── 审批网关               runtime/approval/（HITL：fail-closed 状态机、
│     确定性策略、actor 白名单）
├── 控制面                 runtime/control/（HOTL：确定性 monitor、风险
│     级别、介入策略、可审计幂等命令）
├── 消息总线协议           runtime/agents/message_bus.py（只做协调 ——
│     传输是通用的；通信策略表是 agents 注册表内的领域配置）
├── 状态机                 runtime/state/（CaseState、守卫、存储）
├── Checkpoint/恢复        runtime/checkpoint.py
├── Artifact 血缘          runtime/artifact_registry.py
├── Eval 引擎机制          runtime/eval_engine.py（检查族完全由
│     resources/config/eval.rules.json 驱动 —— 规则文件是领域配置，
│     引擎是通用的）
├── 重规划                 不可变图修订、diff、预算、no-change 守卫
│     （在 harness 内）
└── 可观测性               runtime/events.py、event_bus.py、trace.py
```

## 领域层（保险 —— 第一个适配器）

```text
Domain Layer
├── 保险 Skills            .trae/skills/*（9 个自包含 skill，带契约与 eval）
├── 保险契约               contracts/*.schema.json
├── 保险目录               catalog/product-catalog.v0.1.json（is_demo、
│                         版本化、生效日期）
├── 保险知识               knowledge/（RAG 引擎 + Evidence Provider、
│                         本地演示语料）
├── 保险工作流             runtime/insurance-analysis.yaml
├── 任务目录（配置）       runtime/planner/registry.py —— 受信的 WHAT
│                         清单；换领域就换它
├── Agent 目录（配置）     runtime/agents/registry.py —— 专家、工具范围、
│                         通信策略
├── 工具面                 runtime/agent/tools.py
└── Eval 规则（配置）      runtime/resources/config/eval.rules.json
```

## "更换领域"意味着什么

把保险换成别的领域（理赔、贷款咨询、医疗分诊……）= 替换领域层：
任务注册表、agent 注册表、workflow YAML、skills、contracts、catalog、
knowledge、eval 规则。通用运行时 —— 调度器、重规划、审批、控制面、
checkpoint、血缘、消息协议 —— 原封不动。Phase 11 的思想实验测试在
合成的非保险项目形态上实例化 monitor/policy 来证明这一点。

已知并保持冻结的耦合（已记录、不重构 —— Phase 11 不改运行时）：
`harness.py` 内的遗留 `TASK_DEFS`/`TASK_CHAIN` 兜底映射（仅当项目不
带任务图创建时使用），以及按声明路径驱动保险流水线 stage 的
`orchestrator.py`。


## 已演示而非仅声明：软件工程领域适配器（Phase 12）

`demos/demo_generalization.py` 在**同一套** Planner / Harness / 调度器 /
Eval / Artifact 栈上运行软件工程工作流（需求 → 风险 → 方案 → 实现
计划 → 测试计划）—— 没有复制或 fork 任何运行时模块。适配器只有约 40
行声明式代码：任务目录（WHAT）、agent 定义（WHO）、workflow 定义、
eval 规则、领域执行器（HOW）。

该运行验证：同一个图校验器、同一个有界并行调度器、同一个 Harness
所有的 eval（5/5 PASS）、同一个带血缘校验的 artifact 注册表、同一套
checkpoint 与运行摘要 —— `COMPLETED`。

### 泛化摩擦点（已记录，未修复）

1. **CaseState schema 词表** —— `stages/*/executor` 被限制为保险时代的
   取值（python/provided/service），`produces` 限单字符串。适配器只能
   遵从（SE 适配器把 stage 标为 python）；未来放宽 schema 即可消除。
2. **harness.py 内的遗留 `TASK_DEFS` 映射** —— Phase 3 兜底，保持冻结；
   任何从任务图创建的 project 都不会走到它。
3. **orchestrator.py 按声明路径驱动保险 stage** —— 仅参考模式使用；
   agent 模式的 project 不会触碰。
