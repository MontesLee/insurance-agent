# Phase 28.D — Planning Slice Implementation Contract（M3 契约，只定义不实现）

Date: 2026-09-25 · 前置：ADR-025 APPROVED（28.B6 记录）+ 本 preflight
全绿。**M3 开工仍需独立授权**（NEXT GATE）。参照已验证切片模式
（insurance_qa D4 / product_qa 灰度）。

## 1. Input

```text
IntentResult（schema/intent-result.schema.json 校验通过；
intent_id ∈ {insurance_plan, modify_existing_plan}；
clarification_required=true → 澄清承接，不进规划）
+ Conversation context（≤8 轮；chat 历史既有机制）
+ Active case context（**ADR-024 continuation 段 BLOCKED 期间恒缺**→
  modify_existing_plan 必澄清（M1）；解封后注入 case 上下文）
```

## 2. Output

规划结果=既有 9 类产物链（终产物 insurance-report，
contracts/insurance-report.schema.json）+ run_completed 事件流 +
run_dir 审计——**零新产物类型、零契约变更**。聊天交付=既有
chats.add_assistant_message 机制。

## 3. Authority 链（不可移位）

```text
Intent Layer（意图真理）→ Router（查表 insurance-planning-agent）
→ Registry（身份）→ Planning 行为单元（8 阶段图引用）
→ 既有执行脊柱 orchestrator._execute_stage（零改动）
```

行为单元=registry 条目 insurance-planning-agent 的运行时实现
（server 切片分派，同 QA 模式；路由表**不变**）。

## 4. Feature flag / rollback（沿既有体系）

- `INSURANCE_AGENT_PLAN_SLICE`（默认 **OFF**；灰度→演练→开启三步走，
  复用 M2 验证过的流程）。
- `INSURANCE_AGENT_ROUTER_AUTHORITY` 保持 OFF（M4 前不动；分段值
  slices→no-plan→full 由 ADR-025 §5 定义）。
- 回滚=flag OFF+重启（M2 已验证模式）；候选异常→**legacy fallback +
  slice_error 标注**（QA 切片已验证的 fail-safe 模式，28.B4 测试在案）。
- 观测：slice_decision（selected path/reason/latency）+ 事件词汇
  **零新增**。

## 5. E1 等价门（M3 验收硬门）

Legacy（flag OFF）vs 候选（flag ON）在 planning golden corpus
（tests/golden/，P1-P10 映射）上，经 B4 既有 comparator/normalizer
（**禁改**）比较九维：执行路径 / 选中 Agent / 事件链 / artifact
schema / 稳定字段哈希（时间戳·uuid·遥测剥离——normalizer 白名单）
/ eval verdict 集 / risk signal 集 / grounding 结果 / 安全结果。
基线=tests/golden/planning-baseline.json（28.B6 已采并钉死）。

## 6. Forbidden（Planning Agent 永不）

- 重新分类意图 / 自行路由到其他 Agent / 绕过 Router；
- 编造保险事实 / 绕过证据门（目录/治理证据唯一来源）；
- 修改治理文件 / ADR / 冻结原则；
- 调用隐藏执行运行时（一切经既有脊柱）；
- 修改 orchestrator / artifact 契约 / approval / 事件词汇；
- 叙事文本补充无证据事实（prompt 冻结禁令；代码级叙事门=未来独立
  Owner 决策，见 PLANNING_PROMPT_FREEZE §7.1）。

## 7. Failure 处理矩阵（全部 fail-closed 到既有机制）

| 故障 | 处理 |
|---|---|
| timeout（生成/脊柱） | 既有 LLM 网关看门狗预算（240s 界）→ llm_unavailable 语义 → 用户面诚实话术；轮不悬死 |
| provider failure | 网关错误族规范化→重试策略（可重试限一次）→失败→legacy fallback（切片模式）或轮失败 run_failed |
| grounding failure（KB 不可用/证据不足） | KnowledgeService fail-closed（K001-K004）→ 技能层既有处理（空证据不伪造）；规划继续/明示缺口——**不补位** |
| validation failure（产物不过契约/eval） | 既有 eval+bounded repair→NEEDS_REVIEW 停轮（人工升级路径）；候选切片下同行为（E1 断言） |
| artifact failure（注册/写失败） | 既有脊柱异常路径→run_failed；无半产物交付 |
| 切片自身异常 | except 捕获→legacy fallback+slice_error 标注（28.B4 已验模式） |

## 8. 验收（M3 Definition of Done）

planning golden corpus E1 全 PASS（基线哈希一致）· 全量回归零退化
（backend/web/tsc）· B4 GREEN · 回滚演练 ON→OFF→ON 通过 · flag 默认
OFF 交付 · 治理一致性复审 PASS · `/product-audit` 漂移只收敛。
