> 🌐 **Language:** 🇺🇸 [English](ADR-002-orchestrator-over-pipeline.md) · 🇨🇳 中文

# ADR-002 · Orchestrator instead of hard-coded pipeline

## Context
有了 8 个 Skill 后，需要一个东西决定「下一步跑谁、能不能跑、跑完对不对、错了怎么办」。
最直接的做法是在某个脚本里顺序写 9 行调用。

## Decision
建一个**不含任何保险业务判断**的 Orchestrator（`runtime/orchestrator.py`），
其行为由**声明式**的 `runtime/insurance-analysis.yaml` 驱动（stage 顺序 / 生产消费 / executor / gate 全部外置）。

## Alternatives
- 硬编码顺序调用：新增/调序要改代码，且顺序逻辑散落。
- 通用工作流引擎（Airflow / Temporal 级）：本阶段过重，违反「不引入复杂基础设施」。
- 让 Skill 自己找下一个 Skill：等于把编排逻辑分散到 8 处。

## Why
编排是**跨领域**关注点，与保险无关，因此必须与业务 Skill 解耦。
声明式 YAML 使「链路长什么样」可被**阅读**（而非从代码推断），也让测试可以直接断言「执行顺序 == 声明顺序」（自评 SE-2）。

## Trade-offs
- YAML 与代码之间可能出现两处真源（例如 `index` 字段）——用「列表顺序即 index，不手写」消除。
- 声明式表达力有限，复杂条件分支（如按 case 类型走不同链）需额外机制；当前用 gate + repair 覆盖。
- 调试需要同时看 YAML 与 Python，入门门槛略高。
