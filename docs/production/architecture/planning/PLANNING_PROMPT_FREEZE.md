# Planning Prompt Freeze — M3 前置冻结记录（Phase 28.B6）

Date: 2026-09-25 · 性质：冻结记录（**M3 planning 基线采集前，本 prompt
不得变更**——E1 字节等价基线的可信性前提；变更=E1 基线重采）。

## 1. Prompt source 与指纹

- **source**：`runtime/agent/prompts.py`（chat 规划路径唯一的 system
  prompt 来源；工具描述在 `runtime/agent/schemas.py`）。
- **frozen sha256（prompts.py 全文）**：
  `193ed7da5865708ecd2dbe550d9630581a59c5299c02f8c1f4f4d1bcbaddd5bc`
- 冻结由测试钉死：`tests/runtime/test_p28b6_preflight.py::
  test_planning_prompt_frozen`（哈希不符即红）。
- 版本口径：意图条款已于 28.A-1 降级（Intent Layer 是意图权威；
  prompt 意图段=行为参考）。

## 2. Workflow stages（prompt 所服务的工作流）

8 阶段（runtime/insurance-analysis.yaml）：client-intake →
requirement-analysis → risk-analysis → coverage-gap-analysis →
solution → product-candidate-provider → product-recommendation →
report-generation（上游 client-intake/requirement_analysis 冻结于
AGENTS.md §4）。

## 3. Allowed tools（prompt 可支配的完整闭集）

DIALOGUE_TOOLS：record_client_profile / record_requirement_analysis /
record_risk_assessment；STAGE_TOOLS：coverage_gap_analysis / solution /
product_candidate_provider / recommendation / report_generation；
QA_TOOLS：knowledge_search / check_catalog_product（schemas.py:186-190
声明全集；agent 只能调用列名工具——无隐藏工具）。stage 工具内部经
`orchestrator._execute_stage` 走唯一执行脊柱（eval+bounded repair；
GATE 命中时 V0.1 自动 approve——已知债务，见 §8）。

## 4. Forbidden behavior（prompt 内规则 + 治理双层）

- **不得承担 Router Authority**（已扫描验证，banned-token 零命中）：
  无 "if user asks X → use Agent Y"、无 agent 选择/路由/分发措辞——
  prompt 只定义**如何完成 planning**，不定义**是否应被调用**（意图
  与分发=Intent Layer + Router，ADR-019/020）。
- 不得编造保险事实/不得无证据输出（prompt 硬规则在案；代码级强制
  在技能/CaseState/eval 层——见 §8 已知限制）。
- Ambiguity rule（缺信息→ask_user，不猜）；hard rules 1-7 原文在案。

## 5. Expected artifact / evidence behavior

- 产物=9 类型 contracts 契约（终产物 insurance-report，
  output_contract=contracts/insurance-report.schema.json）。
- 证据=knowledge_search→治理证据 artifact（K001-K004：空结果 fail-
  closed，绝不存伪造证据）；产品事实=check_catalog 确定性查表。
- 每阶段 deterministic eval + provenance 规则（ADR-004/005 冻结）。

## 6. Deterministic constraints（E1 可比性的基础）

同输入+同脚本下：事件链（归一化后）、artifact 载荷（时间戳/uuid 剥离
后 sha256）、eval verdict 集、risk signal 集完全可比——由 B4
normalizer（ADDITIVE_EVENT_TYPES+VOLATILE_KEYS+ISO 擦洗）保证，
**本冻结未改 comparator/normalizer**。

## 7. Known limitations（如实）

1. **planning 叙事文本无代码级引用门**（与 QA 的 ADR-022 闭环门不同
   层）：最终聊天消息中的叙述不受逐句引用校验——事实管控在技能产物/
   eval 层。M3 契约显式禁止 Planning Agent 补充事实；叙事层代码门=
   未来独立决策（Owner）。
2. chat 路径 GATE 自动 approve（V0.1，mirror demo wrapper）——M3 范围
   外，记录在案。
3. P4（active-case 修改）基线被 ADR-024 数据政策 BLOCKED 段阻塞——
   M3/28.E 解封后补采。

## 8. 变更纪律

任何 prompts.py（或 schemas.py 工具描述）变更 ⇒ 本文件哈希更新 +
E1 planning 基线重采 + git review——三者缺一即架构违规。
