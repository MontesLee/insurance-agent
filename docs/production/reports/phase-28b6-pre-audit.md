# Phase 28.B6 Pre-Audit — ADR-025 批准记录 + M3 Planning Preflight（只读）

Date: 2026-09-25 · 性质：只读审计（本文件先于一切改动）。依据：治理链
（FROZEN vision/principles + ADR-019..025 + decision-freeze + CLAUDE.md）、
近期证据（B5 灰度/B5.1 校准/B4 门）、Planning 实现代码。

## 1. 治理与证据核对（读毕）

- ADR-019..024 APPROVED/APPROVED_WITH_CONSTRAINTS（docs/adr/，非
  spec 所写 docs/production/architecture/adr/ ——实际路径以仓库为准）；
  ADR-025 PROPOSED（待本阶段记录 Owner 批准）；decision-freeze +
  CLAUDE.md 约束在案。
- B5.1 后状态：B4 GREEN 14/14；backend 703/0；web 148+2；tsc clean；
  citation 3/4（残余=方差级）；timeout 有界零发生；gate 未动。
- 一致性风险：无（见 §4 与终报告 §3）。

## 2. Planning 真实调用链（代码实证，非文件名推测）

```
Chat（POST /api/chats/{id}/messages → create_agent_run → _agent_worker）
  → Intent Layer（insurance_plan / modify_existing_plan[→澄清]）
  → 【Router 查表：insurance-planning-agent——但无切片，actual=
    existing-agent】→ LEGACY run_agent_turn（LLM 工具自选）
  → agent_decide.call_tool：
      record_client_profile / record_requirement_analysis /
      record_risk_assessment   → adapters（.trae/skills 三上游）直写
                                CaseState + artifact registry
      coverage_gap_analysis / solution / product_candidate_provider /
      recommendation / report_generation
                             → tools.py:_run(stage) →
                               orchestrator._execute_stage(state, wf,
                               stage)  ←与 /api/runs 管线同一执行脊柱
                               （skills→artifact registry→eval engine→
                               bounded repair；GATE 命中时 V0.1 自动
                               approve——demo wrapper 同款，如实记录）
      knowledge_search         → KnowledgeService（治理证据→artifact）
      check_catalog_product    → 目录确定性查表
  → 终态：run_completed（产物 9 类 + eval verdicts + 事件流）
Pipeline 演示路径（/api/runs）：orchestrator.run() 全 8 阶段直跑（不动）
Harness 4 专家世界：demos/benchmark/approval-resume only（不在迁移面）
```

**关键事实**：chat 规划与管线规划**已共用同一执行脊柱**
（`orchestrator._execute_stage`）——M3 的 router→planning 行为单元是
"换入口不换脊柱"，E1 字节等价因此可期。

## 3. Planning 组件清单（实证）

- **入口**：仅 legacy chat 路径（无切片；registry 条目
  insurance-planning-agent 已声明 supported_intents=[insurance_plan,
  modify_existing_plan]、risk_level=high、output_contract=
  contracts/insurance-report.schema.json——身份就绪，行为单元未建）。
- **workflow**：runtime/insurance-analysis.yaml 8 阶段（client-intake→
  requirement-analysis→risk-analysis→coverage-gap-analysis→solution→
  product-candidate-provider→product-recommendation→report-generation）。
- **skills**：8 阶段各一（+knowledge-search 证据技能）；上游冻结
  AGENTS.md §4：client-intake / requirement_analysis 禁改。
- **tools（chat 侧）**：DIALOGUE_TOOLS 3 + STAGE_TOOLS 5 +
  QA_TOOLS 2（schemas.py:186-190）；无隐藏工具（tool 表=声明全集，
  agent 只能调用列名工具）。
- **artifacts**：9 类型（contracts/*.schema.json 全量契约）。
- **evaluation**：每阶段 deterministic eval + bounded repair（eval
  engine + evals/ 规则：业务 HG 门/结构/provenance——ADR-004 冻结）。
- **events**：stage_*/tool_*/artifact_created/eval_*/run_*（词汇=
  canonical EVENT_TYPES，契约双端测试在案）。

## 4. 治理一致性预检（详细矩阵见终报告 §3）

- Intent=Intent Layer ✓（prompt 已降级 A-1；LLM candidate 仅提案）；
  Router=查表 ✓（decision_source 无 llm）；Registry=身份唯一源 ✓
  （config 声明+启动校验）；Agent=工作流所有权 ✓；执行脊柱唯一 ✓。
- 禁项扫描：prompts.py 无 agent-selection/routing 措辞（banned-token
  扫描零命中，哈希 193ed7da…将入冻结文档）；前端 mapPromptToCase 仅
  demo 模式选演示 case（agent 模式后端分类——ChatLayout.tsx:30-32
  默认 agent）；demo 映射不作生产权威 ✓；无 agent 私联（生产路径）。
- 已知债务（记录非阻断）：chat 路径 GATE 自动 approve（V0.1 语义）；
  planning 叙事文本无代码级引用门（与 QA 的 ADR-022 门不同层——
  事实经技能/CaseState/eval 管控；M3 契约将显式禁止 Agent 层补充事实）。

## 5. STOP 边界核验

本阶段全部交付物（批准记录/审计/冻结/基线/契约/测试/文档）均在允许
清单内；无需任何禁项改动。**判定：GO。**
