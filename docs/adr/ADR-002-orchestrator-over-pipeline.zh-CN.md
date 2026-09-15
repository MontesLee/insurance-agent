> 🌐 **Language:** 🇺🇸 [English](ADR-002-orchestrator-over-pipeline.md) · 🇨🇳 中文

<a id="adr-002-orchestrator-instead-of-hard-coded-pipeline"></a>
# ADR-002 · 用编排器取代硬编码流水线

<a id="context"></a>
## 背景

在已部署 8 个 Skill 的前提下，必须有某个角色来决定“谁先运行、能否运行、结果是否正确、以及失败时应如何处理”。最直接的做法：在一个脚本里写 9 次顺序调用。

<a id="decision"></a>
## 决策

构建一个 Orchestrator（编排器）（**`runtime/orchestrator.py`**），其内部**不包含任何保险业务判断**，由声明式（**declarative**）的 `runtime/insurance-analysis.yaml` 驱动（阶段顺序 / 生产-消费 / 执行器 / 门禁全部外置）。

<a id="alternatives"></a>
## 备选方案

- 硬编码顺序调用：增删或重排阶段都要改代码；排序逻辑散落各处。
- 通用工作流引擎（Airflow / Temporal 一类）：现阶段过于笨重；违反“不引入复杂基础设施”原则。
- 让 Skill 自行寻找下一个 Skill：把编排逻辑散落到 8 个地方。

<a id="why"></a>
## 理由

编排是一项**跨领域**关注点，与保险无关，因此必须与业务 Skill 解耦。声明式 YAML 让“链路长什么样”变得**可读**（而非从代码中推断），并让测试能够直接断言“执行顺序 == 声明顺序”（自评估 SE-2）。

<a id="trade-offs"></a>
## 取舍

- YAML 与代码可能变成两个事实来源（例如 `index` 字段）——通过“列表顺序即索引；绝不手写”消除。
- 声明式表达力有限；复杂的分支条件（按案例类型走不同链路）需要额外机制——目前由门禁 + 修复覆盖。
- 调试需要同时阅读 YAML 与 Python；上手成本略高。
