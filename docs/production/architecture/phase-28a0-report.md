# Phase 28.A-0 Report — Intent Layer Contract Foundation

Date: 2026-09-25 · 状态：COMPLETE · 只建立 schema + contract + tests；
**未连接真实 Router、未改变任何现有执行路径**（runtime/web/backend/
workflow 零触碰）。

## Product Alignment（CLAUDE.md 守门四问）

服务 Chat UI：✅（意图契约是 Chat→Intent→Router 链的地基）· Space：
User Space 能力的契约层 · 新增 Artifact=三份平台契约（非业务 artifact）：
ADR-019/020/021（均已 APPROVED）授权，feature-proposal 视角字段与
phase-28-implementation-plan §5.1 28.A 范围一致 · 漂移：收敛（把"prompt
是意图真理"的现状钉进结构上不可能的契约）。

## 交付物

| 文件 | 内容 |
|---|---|
| `schema/intent-result.schema.json` | IntentResult v1 契约：intent_id（5 意图枚举）/confidence(0..1)/confidence_source(rule\|llm\|hybrid)/context_refs{conversation_id,active_case_id,message_id 可空}/clarification_required/reason_codes(≥1)/created_at；**additionalProperties:false 结构性封禁 workflow/skill/tool/agent 等执行细节**；**if/then 强制 ADR-019 M1**：modify_existing_plan 无 active_case_id ⇔ 必须 clarification_required=true |
| `schema/router-decision.schema.json` | RouterDecision v1：intent_id（同词表）/agent_id（pattern）/decision_source（**仅 registry_lookup\|fallback\|blocked，结构上无 llm 值**）/validation_result{valid,errors,intent_result_created_at}；一致性规则：registry_lookup ⇔ validation.valid=true；valid=false ⇒ 只能 fallback/blocked |
| `schema/agent-registry.schema.json` | Agent 声明 v1（ADR-021 批准子集，8 字段）：id/name/description/supported_intents(⊆意图词表)/input_contract/output_contract/capabilities/risk_level(low\|medium\|high)；additionalProperties:false——**执行字段（workflow/tools/skills…）留待 28.A-1+ 版本化修订**；v1=configuration based，禁运行时动态注册（描述条款） |
| `tests/contract/test_intent_contracts.py` | 六项强制检查 + 4 项加固 = 10 测试（standalone 与 pytest 双跑通） |
| `docs/production/architecture/intent-contract-audit-28a0.md` | Step 1 现状审计（意图来源/task_type/执行入口/差距表） |

## 六项强制检查 → 测试映射（10/10 PASS，pytest 0.13s）

1. **unknown 安全降级** → `test_unknown_intent_is_valid_value` +
   `test_modify_intent_without_case_context_requires_clarification`
   （无 case 的 modify：clarification=false 必 INVALID、=true 才 VALID、
   有 case 的孪生样本 VALID——非空洞断言）
2. **invalid intent 拒绝** → `test_invalid_intent_enum_rejected`（含旧
   枚举值 TASK_EXECUTION 亦拒）+ `test_router_rejects_invalid_intent_too`
3. **Router 不接受未声明 Agent** →
   `test_router_decision_agent_must_be_declared_in_registry`（跨契约检查：
   decision.agent_id ∈ 注册表声明集；schema 形状合法但未声明=违约）+
   `test_registry_fixture_entries_validate`（3-Agent 声明样例本身过契约）
4. **Intent 不含 workflow** → `test_intent_result_rejects_execution_detail_keys`
   （workflow/workflow_steps 等键注入必拒）
5. **Intent 不含 tool selection** → 同上（tool/tools/tool_selection/skill/
   skills/agent_name/agent_id/stage 共 12 键全拒）+
   `test_intent_schema_declares_no_execution_properties`（属性名层面快照）
6. **Schema 向后兼容** → `test_schemas_are_versioned_draft07_and_frozen`：
   全部 draft-07 合法、$id 含 /v1、additionalProperties:false（静默加字段
   结构上不可能=漂移防线）+ `test_v1_intent_vocabulary_is_frozen_golden`
   （三处词表=冻结金清单，改动必须走版本化修订）

## Validation

- 测试：`python -m pytest tests/contract/ -q` → **10 passed**；standalone
  `python tests/contract/test_intent_contracts.py` → 10/0。
- git 范围：新增 `schema/` + `tests/contract/` + `docs/**`（审计+本报告）；
  **runtime/ web/ backend/ workflow/ 零改动**（tracked diff 中
  runtime/server.py、tests/runtime、web、bat 均为 27.7.6-D..F/27.7.7 既有
  未提交工作，非本阶段产物）。
- 红线复核：未连接真实 Router ✅ · 未改变现有执行路径 ✅ · prompt/事件/
  规则模块未动（留待 28.A-1）✅。

## 留给 28.A-1（下一阶段，待授权）

意图规则模块（外置规则+确定性分类器）· IntentResult 实例产出与
intent_classified 事件（后端词汇+web 契约双端）· 影子模式（只记录不
裁决+与旧 prompt 分类一致性报告）· prompts.py 意图条款降级 · 行为等价
基线采集（28.B 前置 B4）· HD-1 阈值影子校准。

**STOP — 等待 28.A-1 授权。**
