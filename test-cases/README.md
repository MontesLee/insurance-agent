# test-cases — E2E 测试场景

本目录存放**测试场景与数据**，与 `tests/`（测试程序）分工：

| 目录 | 内容 |
|---|---|
| `tests/` | 测试程序（契约测试 / 工作流单测 / 变异测试 / Evidence 不变量 / 结构完整性） |
| `test-cases/` | E2E 场景数据集 + runner（本目录） |

## 场景

| Scenario | 覆盖 |
|---|---|
| `e2e/core-analysis/` | Step 1 核心分析链（profile → requirement → risk） |
| `e2e/full-agent/` | 全链路 8 Skill 编排（71 检查，含 repair / checkpoint / trace / guardrails） |
| `e2e/product-recommendation/` | Step 2 产品推荐链（evidence → candidate → recommendation → report） |

## 约定

- **runner 与 scenario 同居**：每个 scenario 目录自带 `run_<scenario>_e2e.py`。runner 与数据集强耦合（seed、mutate、断言都针对同一 manifest），就地放置避免跨目录脆弱引用——这是有意的工程选择，不迁移到 `tests/`。
- case 文件命名 `case-NNN-<slug>.json`；每个目录的 `manifest.json` 声明用例清单。
- 运行产物只写 `tmp/`，不污染场景目录。
