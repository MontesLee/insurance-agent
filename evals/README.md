# Evals — 两层评估体系

仓库存在两层 Eval，目录名相同但层级不同：

| 层 | 位置 | 回答的问题 | 内容 |
|---|---|---|---|
| **Skill-level Eval** | `.trae/skills/<skill-id>/evals/` | 这个 Skill 自身的行为对吗？ | 各 Skill 的 eval-policy、cases 数据集、fixtures、回归脚本（Skill 目录内自包含） |
| **System-level Eval** | `evals/`（本目录） | 整个 Agent 端到端表现如何？ | `agent-benchmark/`：Benchmark 数据集（manifest / baseline）、Golden Cases、结果报告 |

## 区别

- Skill-level Eval 验证**单元语义**：某 Skill 的输出契约、边界（如反产品泄漏）、规则表行为，由该 Skill 的 SKILL.md §Eval 驱动。
- System-level Eval 验证**系统行为**：多 Skill 编排后的整体质量、安全硬门（Safety Hard Gates）、Golden 回归，不关心单个 Skill 内部实现。
- 两层命名统一为 `evals/` 是有意的：同一套 Eval 纪律（可机检断言才 PASS、FAIL→Repair→重跑、负向自检）在两层同样适用（见 AGENTS.md §6）。

运行入口见 [docs/development/testing.zh-CN.md](../docs/development/testing.zh-CN.md)（`evals/agent-benchmark/run_agent_benchmark.py` / `run_golden_cases.py`）。
