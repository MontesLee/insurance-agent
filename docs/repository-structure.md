# Repository Structure

> 本文档描述仓库的目录契约。结构不变量由 `tests/structure/test_structure_integrity.py` 守护。
> 重构依据：`docs/dev-notes/repository-structure-audit.md`。

## 目录职责

| 目录 | 职责 |
|---|---|
| `.trae/skills/` | Specialist Skills — 每个目录一个独立 Skill（SKILL.md / scripts / evals / schemas / resources）。`client-intake` 与 `requirement_analysis` 为冻结 Skill（历史命名例外 + 回归基线），禁止修改内容与目录名。 |
| `runtime/` | Agent Runtime — orchestrator / tasks / artifact_registry / eval_engine / repair / checkpoint / trace / observability / state + 声明式工作流 `insurance-analysis.yaml` + 外置规则 `resources/config/`。 |
| `domain/` | Insurance Domain Pack — `domain/insurance/`（pack.yaml / playbook / references / overlays），中心化险种分类、证据类型与来源等级，是 RAG 的权威语料生产方（`build_domain_engine.py` → `seed_rag.py`）。 |
| `adapters/` | Cross-layer transformations — legacy → canonical 信封适配器，吸收上游数据结构与 canonical 契约的差异（稳定边界，不移动）。 |
| `contracts/` | Canonical Artifact Contracts — 9 份 artifact schema（draft-07）与生成器 `build_contracts.py` 同目录。禁止 Schema 语义漂移。 |
| `knowledge/` | RAG + Evidence — `knowledge/rag/`（models / store / engine，纯 stdlib + sqlite3）与 `knowledge/evidence/`（request / provider / loop / attribute_grounding）。两层职责边界不合并、不扁平化。 |
| `catalog/` | Product Catalog — `product-catalog.v0.1.json`（版本化），产品候选与推荐的唯一产品事实源。 |
| `tests/` | Test Programs — 契约测试（contracts/）、工作流单测（workflow/）、变异测试、Evidence 不变量、结构完整性测试（structure/）。 |
| `test-cases/` | Test Scenarios — E2E 场景数据集（case JSON + manifest）与就地 runner（见 `test-cases/README.md`）。 |
| `evals/` | System-level Evaluation — `agent-benchmark/`（Benchmark manifest / baseline / Golden Cases）。与 Skill-level `.trae/skills/*/evals/` 的区别见 `evals/README.md`。 |
| `docs/` | Architecture / ADR / Documentation — `architecture/`（活架构文档）、`adr/`（决策记录）、`dev-notes/`（开发过程记录）、`archive/`（历史归档）。 |
| `client-intake-data/` | 运行时客户数据（CLI 采集输出），不入库（.gitignore）。 |
| `scripts/` | 辅助脚本（数据集 runner：`run_evidence_dataset.py` 等）。 |
| `demo.py` | Demo CLI 入口（Demo A / B / C）。 |

## Architecture → Directory Mapping

| Architecture | Directory |
|---|---|
| Orchestrator | `runtime/orchestrator` |
| CaseState | `runtime/state` |
| Artifact | `runtime/artifact_registry` |
| Eval | `runtime/eval_engine` |
| Repair | `runtime/repair` |
| Checkpoint | `runtime/checkpoint` |
| Trace | `runtime/trace` |
| Evidence | `knowledge/evidence` |
| RAG | `knowledge/rag` |
| Product Catalog | `catalog` |
| Skills | `.trae/skills` |
| Contracts | `contracts` |

## 关键约定

- **两层 Eval**：`.trae/skills/*/evals/` 是 Skill-level Eval（单元语义）；顶层 `evals/` 是 System-level Benchmark / Golden（系统行为）。两层命名有意一致以示同源纪律，见 `evals/README.md`。
- **tests vs test-cases**：`tests/` 是测试程序（代码），`test-cases/` 是测试场景与数据。E2E runner 与 scenario 同居是既定工程选择，见 `test-cases/README.md`。
- **冻结 / 稳定边界**：`client-intake`、`requirement_analysis`（AGENTS.md §4 上游不可变）、`adapters/`、`contracts/`、`catalog/product-catalog.v0.1.json`、`client-intake-data/` 路径为稳定边界，非必要不动。
- **结构守护**：`python tests/structure/test_structure_integrity.py`，任何破坏目录契约的改动都会 fail。
