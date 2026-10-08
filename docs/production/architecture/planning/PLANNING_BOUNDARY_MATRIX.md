# Planning Boundary Matrix — 职责归属矩阵（Phase 28.B6 / M3 preflight）

Date: 2026-09-25 · 依据：FROZEN principles + ADR-019..025 + 代码实证
（phase-28b6-pre-audit.md §2-4）。

| Responsibility | Owner | 代码/文档锚点 |
|---|---|---|
| Intent recognition | **Intent Layer**（schema+外置规则+runtime 事件） | runtime/intent/ · ADR-019；prompt 意图段已降级 |
| Agent dispatch | **Router**（纯查表；LLM 永不参与） | runtime/router.py · ADR-020；decision_source 无 llm |
| Agent identity | **Registry**（config 声明+启动校验；禁动态注册） | runtime/agent_registry.py + config/agent-registry.json · ADR-021 |
| Planning process | **Planning Agent**（未来行为单元；现在=legacy chat agent 承载） | registry: insurance-planning-agent（身份就绪，行为=M3） |
| Planning workflow | **Planning Agent 拥有 8 阶段图**（引用不复制） | runtime/insurance-analysis.yaml · ADR-021 v1 条目 |
| Product facts | **Catalog / WeKnora**（目录确定性查表；治理证据） | runtime/catalog_governance.py · knowledge/ · ADR-022 |
| Evidence grounding | **Existing grounding spine**（KnowledgeService K001-K004） | knowledge/service.py（不改） |
| Execution | **Existing execution spine**（orchestrator._execute_stage——chat 与管线共用） | runtime/orchestrator.py（M3 零改动） |
| Artifact generation | **Existing artifact spine**（artifact registry+contracts） | runtime/artifact_registry.py + contracts/（零改动） |
| Evaluation | **Existing evaluation spine**（eval engine+规则；ADR-004 唯一门） | runtime/eval_engine.py（零改动） |
| Human escalation | **Review / Approval**（ADR-017 状态机冻结；chat 侧 V0.1 auto-approve 为已记录债务） | runtime/approval/ · evaluation/human-review/ |
| UI rendering | **Chat / existing UI layer**（demo 关键词映射仅 demo 模式选 case，非生产权威） | web/src/components/chat/ |

## Ownership overlap 检查（逐项）

- **Intent**：唯一源=Intent Layer。chat prompt 意图段=行为参考（已降级，
  A-1）；LLM candidate=提案；demo 映射=demo-only。**无重叠**。
- **Dispatch**：唯一源=Router。prompt 无路由措辞（banned-token 扫描零
  命中，冻结哈希钉死）；QA/Product-QA 切片=Router 查表后的行为单元
  分派（路由表不变）；无 agent 私联（生产路径）。**无重叠**。
- **Identity**：唯一源=Registry（启动 fail-closed；无 mutation API）。
- **Workflow**：planning 图归 Planning Agent 所有；Router 零工作流
  知识（ADR-020 NO 清单）。chat 工具→_execute_stage=脊柱调用非旁路。
- **Execution/Artifact/Eval**：chat 与管线已共用唯一脊柱（§2 调用链）；
  M3=换入口不换脊柱。**无第二运行时**。
- **Facts/Evidence**：目录/WeKnora 双源边界（ADR-022）；QA 切片有代码
  级引用门；planning 叙事层为已记录缺口（freeze §7.1，M3 契约禁止+
  未来 Owner 决策）——**唯一已知灰区，已显式登记非隐匿**。

**结论：无未登记的 ownership overlap。**
