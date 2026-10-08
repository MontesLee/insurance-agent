# K.27-RV4-C1 · Planning Continuation Minimal Fix

Date: 2026-09-28 · IMPLEMENTATION（仅 P1-A·依 RV4-B 设计·零 P1-B 改动）。

## 1. Root Cause（RV4-A 复用）

classifier 规则链无规划延续语义：plan 规则强制动作词、qa 产品名词即中
conf=1.0 → 补充答案被劫持到 knowledge-qa；`active_case_id` 调用点写死
（ADR-024 阻塞）。

## 2. Implementation

- `config/intent-rules.yaml`：`context.plan_continuation` 配置块
  （enabled/reason_code/ack_reason_code/ack_max_len 外置）。
- `runtime/intent/classifier.py`：`classify(..., pending_clarification:
  bool = False)` 新参 + **规则 4.5**（位于 plan 规则后·qa 规则前）：
  pending ∧ 无新意图信号 → `insurance_plan` conf=1.0·reason=
  `plan:continuation`+`context:pending_clarification`；ack-only
  （≤6 字）→ clarify=True fail-closed（复用既有 clarification 机制）。
- `runtime/server.py`：classify 调用前从**既有状态**派生信号（同 chat
  上一 run `result_status==WAITING_USER` ∧ 其 intent_classified 事件
  intent==insurance_plan；bus events_for 查询·fail-quiet·零新建存储/
  零 case 生命周期/零 active_case 引入）。
- `tests/runtime/test_agent_intent.py`：+3 sections（正/负/歧义矩阵+
  RV4 真实两轮+无信号回归锚）。

## 3. Continuation Rule

```text
pending_clarification=True（server 派生）
∧ 当前消息无新意图信号（无 定义词/产品评价词/产品特指/问号·吗呢/
  modify 动词——裸产品名词【不是】切换信号=RV4 答案的本质特征）
→ insurance_plan · conf 1.0 · rule · plan:continuation
```

## 4. Topic Switch Boundary（切换必胜）

`百万医疗险和重疾险有什么区别？/什么是等待期？/医疗险能买吗？/
P001值得买吗？/帮我重新规划…` → 正常落既有链（qa/product_qa/plan 规
则 4）——**QA 规则本体零改动**。歧义（好的/是的/嗯）→ plan+clarify
（fail-closed，legacy 环 ask_user）。

## 5. Test Matrix（§9 全实现）

Positive 5（含多问补充/产品名词/QA signals 混载/多轮）✓
Negative 6（新 QA 问/定义/比较/评价/明确切换/无 pending 普通消息）✓
Ambiguous 3（极短/好的/是的）✓ + **RV4 真实两轮一等回归**（T1 plan/
T2+pending=plan continuation·reason 验证·**NOT qa**）+ 无信号全等锚
（排除 created_at）✓

## 6. Regression Results

- `test_agent_intent.py` **12 passed**（9 既有+3 新）
- intent/router-gate/QA/planning 相关 7 套件 **112 passed**
- 完整后端电池 `tests/runtime tests/contract` **857 passed + 2 skipped**
  （23 分钟·长跑授权内）
- Web：本阶段零 web 改动（未跑·不适用）；TypeScript：同

## 7. Security Results

`pending_clarification` 为进程内布尔——不进任何事件/消息/SSE 载荷；
新增 reason_codes（`plan:continuation`/`context:pending_clarification`
/`…:ambiguous_ack`）与既有 rule: 码同类（非内部 ID·无 run_/chat_/
artifact_/agent_ 泄漏）。九零维持 ✓。

## 8. Real Case Result（静态+运行路径）

RV4 T1→`insurance_plan`（rule:plan 保障/家庭/孩子）；T2+pending→
`insurance_plan`（plan:continuation）→ Router registry_lookup→
`insurance-planning-agent`（authority full→plan 切片）——**不再进
knowledge-qa/农业保险条例路径** [classify 实测]。T2 无信号→旧行为
`insurance_qa`（回归锚确认无意外行为变化）。

## 9. Files Changed（本阶段净改动）

`runtime/intent/classifier.py`（+~40 行·未跟踪文件）
`runtime/server.py`（+~28 行）·`config/intent-rules.yaml`（+12 行·
未跟踪）·`tests/runtime/test_agent_intent.py`（+~80 行）

## 10. Diff Scope Audit

其余 modified 文件（runtime/agent/*·web/*·knowledge/* 等）=K.26-K.32
既有未提交跨度（各阶段已自证），本阶段零触碰；**未改**：qa_agent/
grounding/llm/router.py/agent_registry/planning/tools.py/WeKnora/
Catalog/web/SSE/streaming/authority/schema——P1-B 未动 ✓。

## 11. LIVE Verification Status

**LIVE_VERIFICATION_PENDING**——当前 :8123 进程为旧代码（且最近一次
被内存回收后未重启）。需 Owner 授权 restart 后以 RV4 原两轮消息实测
（预期 T2→planning workflow·产物交付）。

## 12. Known Limitations

①信号仅覆盖 insurance_plan 的 WAITING_USER（modify/product_qa 的
pending 未覆盖——按设计不扩大）②进程内派生：后端重启丢 chat/run
内存态→同会话跨重启的延续信号丢失（V0.1 in-memory 已知限制·ADR-024
线解决）③ack-only 走 legacy 环 ask_user（非 planning 切片——fail
closed 但体验可后续优化）④仅静态+classify 级验证，真实 E2E 待
restart。

## 13. Next Step

Owner：①授权 restart + RV4 真实回归（浏览器两轮复测）②批准 ADR-019
附裁决文案 ③排期 RV4-C2（P1-B 证据资格下限·阈值决策）。
