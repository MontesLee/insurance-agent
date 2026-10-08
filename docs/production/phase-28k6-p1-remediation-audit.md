# Phase 28.K.6 — P1 Remediation Audit（S-1 证据门绕过 · S-2 规划交付阻断）

Date: 2026-09-26 深夜 · 性质：**AUDIT + REMEDIATION PLAN ONLY**（零
tracked 代码改动·零测试改动·零 commit·未触碰任何服务进程——全部证据
取自 k5-ledger/运行中实例的只读端点/盘上 trace/代码与配置实读）。

## 1. Executive Summary

- **S-1 根因（代码级闭环）**：证据/引用闭包治理实现于**切片层**
  （knowledge-qa/product-qa slice 的 run_qa_turn/run_product_qa_turn
  内），而切片仅对 4 个已知 intent_id 触发（server.py:600-625）；
  `unknown_insurance_intent` 不匹配任何切片 → 落入**通用 agent 环**
  （run_agent_turn，:765-823）→ 其 finish 路径（agent.py:97-100）将
  LLM 自由文本**原样交付，无任何证据闭包**。治理边界=切片，而非
  答案边界——凡"非切片 intent"的轮次（unknown/追问漂移）共用此
  未治理出口。修复不需新架构：把既有闭包纪律延伸到该出口（方案
  A）或在路由缝把保险域 unknown 交给既有受治理问答管线（方案 B）。
- **S-2 根因（trace 实锤，4/4 同签名）**：product-candidate 阶段的
  SOLUTION_VALIDATION 证据请求以**固定模板串**检索（domain 模板+
  purpose 后缀，如「百万医疗险 保障范围 免赔额 社保目录外 适用性
  策略验证」）→ 在治理试点语料上**确定性 0 命中** → 存入的
  knowledge-evidence 证据列表为空 → eval `required_non_empty`+
  provenance 检查 FAIL（EVIDENCE_EVAL_FAIL）→ repair 重跑同一查询
  同样空 ×3 → 预算耗尽 → needs_review。**质量门行为完全正确
  （fail-closed）；阻断是知识覆盖/查询模板失配**，非契约冲突、
  非门过严误拒、非候选质量问题。
- **判定**：S-1=治理覆盖缺口（修复在既有架构内，两案可选，需
  Owner 选型）；S-2=正确 fail-closed + 数据/配置层阻断（三个处置
  杠杆均需 Owner 决策，其中"空证据不致命化"属质量门 scope 变更）。
- **Batch-1 建议：HOLD**（至少待 S-1 裁决；S-2 姿态需明确——当前
  真人规划旅程将 100% 进入 needs_review）。

## 2. S-1 Evidence-Gate Bypass（事实）

K.5 S06 t1：`unknown_insurance_intent` → 交付"医疗→意外→重疾→寿险
优先级建议"；attached knowledge-evidence=真实 A 级监管条款（健康保险
管理办法 cn-cbirc-order-2019-3 核保/告知条款），与建议内容不对应；
无引用门参与；result_status=COMPLETED。（ledger S06 全文+产物 payload
在案。）S05/S09t2/t3 同寄存器。

## 3. S-1 Actual Runtime Call Chain（重建，全部实测/实读）

```text
message「是不是该买点保险」
→ intent：规则分类器 → IntentResult{intent_id=unknown_insurance_intent}
   （四个切片条件全部要求 intent_id ∈ {insurance_qa, product_qa,
     insurance_plan, modify_existing_plan}——server.py:600-625
     _qa_slice/_pq_slice/_plan_slice 均 False）
→ router：registry_lookup 无 unknown 映射（route_decision 无 agent）
→ 切片分发：无切片接管（shadow 记 actual_execution="existing-agent"，
   server.py:666-675）
→ 通用 agent 环：run_agent_turn（server.py:765-823）
   · LLM（glm）自判内部意图 GENERAL_GUIDANCE → call_tool
   · 工具 knowledge_search → KnowledgeService 治理检索 → 存
     knowledge-evidence artifact（真实证据，工具层治理存在）
   · LLM 续写 → finish：无工具调用的纯文本=终答
→ 证据/引用闭包：【无】——闭包门位于切片内部
   （run_qa_turn/run_product_qa_turn：evidence→LLM→closure gate→
   AnswerContext，server.py:680-695 注释即写明）；通用环 finish
   （agent.py:97-100）直接采纳 LLM 文本
→ 终态 COMPLETED，消息原样交付消费者
```

概念分层定位：intent 分类=正确（insurance 域未知）；路由=正确
（无映射）；知识检索=已治理（工具经 KnowledgeService）；**证据
grounding/引用闭包=缺失（仅切片内有）**；答案生成=自由（LLM 将
检索结果当参考而非约束）。

## 4. S-1 Root Cause

> 证据治理的实现位置=切片层（按已知 intent 触发），而 ADR-022 的
> 原则（Insurance Fact Requires Evidence）是**答案边界**性质。
> 任何"非切片 intent"轮次共享同一个未治理出口。这不是某条 intent
> 的 bug，是一个**类别出口**未纳入治理。

§A.5 同类潜在绕过面（枚举）：①unknown_insurance_intent 全部轮次
（S05/S06/S09t2t3 已实证）；②会话中途追问轮 intent 漂移为 unknown
（S09 模式）；③clarification_required 轮（切片跳过——澄清本身是
提问非事实，低风险，记录）；④planning agent 环的 finish 文本
（intake 复述/总结——其报告产物另有 eval 门，但对话文本无闭包）。
主暴露面=①②。

## 5. S-1 Minimal Remediation Options（不实施，选型交 Owner）

```text
方案 A（答案边界闭包·结构性）：把既有闭包纪律延伸到通用环 finish
  ——保险域对话的 finish 文本须经与 knowledge-qa 同源的引用闭包
  校验（复用 B5.1 校准套件锁定的 validator 机制），主张未闭合于
  本轮检索证据 → fail-closed 降级为诚实拒答/范围声明。触点=
  run_agent_turn finish 缝（agent.py/server.py）。零新门/零新
  Agent/零原则变更（只是把既有门装到原则本要求的边界）。
  代价：通用文本的"主张抽取"较难校准（建议性语句非显式引用体）。
方案 B（路由缝收口·最小改动）：unknown_insurance_intent（schema
  语义即"保险域未知"）在切片缝并入 knowledge-qa 管线（server.py
  切片条件+1 项）→ 检索→生成→闭包门→grounded 或诚实拒答，
  fail-closed by construction。触点=一个条件。语义=保险域未知
  问题按证据治理路径作答（非"粗暴转 QA"——非保险 unknown 不受
  影响；但这是路由语义变更，需 Owner 授权）。
  代价：vague 问题多数将得到拒答（可用性降、安全性升）。
推荐：B 先行（最小、即fail-closed）+ A 作为结构性跟进（覆盖
  ④类出口）；两者不互斥。
禁止项核对：不删advice/不禁UNKNOWN/不放宽门/不hardcode——
  两案均满足。
```

## 6. S-1 Regression Matrix（设计）

| # | 输入 | 期望 |
|---|---|---|
| R1-1 | UNKNOWN 保险域问题，语料有权威证据 | 走治理路径：答案闭合于证据（引用可追溯）或诚实拒答；**禁止无闭包建议** |
| R1-2 | UNKNOWN 保险域问题，无可支撑证据 | fail-closed 拒答（零建议性交付） |
| R1-3 | UNKNOWN 保险域问题+诱导（"直接告诉我买啥"） | 无证据仍不产出推荐；转向澄清/拒答 |
| R1-4 | 非保险 general 问题（UNKNOWN 但非保险域） | 不被误并入保险 QA 管线（不误路由；保持通用处理且不含保险建议） |

锁定断言：交付文本与 knowledge-evidence 的引用闭合关系；事件流含
闭包判定记录；S06 样例回归（该输入在新语义下不可复现无闭包建议）。

## 7. S-2 Planning Delivery Block（事实）

insurance-report=0（4/4：28.K C、K.1 C′、K.5 S01t2、S08——同签名）。
前 5 阶段（intake→requirement→risk→coverage-gap→solution）全 PASS；
阻断点=product-candidate 阶段。

## 8. S-2 Actual Runtime Call Chain（trace.jsonl 实录，S01/S08 一致）

```text
planning（insurance_plan 切片→planning agent→8 阶段脊柱）
→ stages 1-5：eval PASS（EVAL-001..005）
→ product-candidate-provider（insurance-analysis.yaml:78-99）
   · 引擎=.trae/skills/.../product_candidate_engine.py（真目录+确定性
     过滤；无证据产品=MISSING——引擎自身对缺证据是诚实设计）
   · 阶段服务：knowledge-search（source=solution-plan，
     source_kind=solution，purpose=SOLUTION_VALIDATION，store_as=
     knowledge-evidence）
   · 查询构造（knowledge/evidence/loop.py:44-45 → request.py:
     from_solution:112-126）：domain=_domain_from_solution_type
     （如 MEDICAL→"medical"）——【无调用方自由文本，纯模板】
   · 查询文本（evidence-request.rules.json:5-22）：domain 模板+
     purpose 后缀拼接，如 medical+VALIDATION=
     「百万医疗险 保障范围 免赔额 社保目录外 适用性 策略验证」
→ 治理检索（WeKnora vector_search）：该复合串在试点语料=0 命中
   （TOOL_COMPLETED ok=True，evidence=[]）
→ 存 knowledge-evidence（空证据列表）
→ eval（eval_engine.py:159-172 + eval.rules.json required_non_empty/
   provenance_evidence_document_chunk）→ EVIDENCE_EVAL_FAIL：
   "required_non_empty(empty: payload.evidence)" ×3
→ repair（RERUN_FROM_UPSTREAM）：同源同模板同查询 → source_
   unchanged=True → 同样空 → REPAIR_EXHAUSTED（budget=3）
→ 质量门拒 → needs_review（消费者文案=K.1 固定模板，干净）
→ report-generation 永不执行 → insurance-report=0
```

## 9. S-2 Root Cause

> **查询模板-语料失配**：SOLUTION_VALIDATION 的确定性模板串在治理
> 试点语料（10 监管文档/304 chunks/194 嵌入）上 0 命中，且 repair
> 复跑同一确定性查询不可能改变结果。阻断层=**知识检索覆盖**（输入
> 数据层），非候选生成、非目录、非门规则逻辑。

## 10. S-2 Contract / Governance Assessment

- 拒绝**符合**现有 contract（eval.rules.json 明文要求证据非空+
  provenance；工作流声明该产物受 standard eval 约束）。
- 连续失败的成因=§9（数据/配置层）；输入数据层（检索语料）导致。
- 无 gate rule 与 planning contract 冲突；但存在**设计张力**（记录）：
  工作流将 knowledge-evidence 列为 candidate 阶段 `optional_consumes`
  （insurance-analysis.yaml:82）且引擎对无证据产品有诚实 MISSING
  语义（engine docstring :25-26），而 eval 对该阶段的
  SOLUTION_VALIDATION 证据强制非空——"引擎可选"与"eval 必填"不一致。
- **needs_review=正确终态**（证据不可得→人工升级，Principle 6/§44）。
- 部分产物（§B.7）：6 个 VALID 中间产物已存在于 case（内部可见），
  但无消费者面 partial artifact；新增 partial-report 语义=ADR-023
  artifact 语义变更 → **OWNER DECISION**，不在最小修复内。
- insurance-report=0 的直接原因=report-generation 位于阻断点下游。

## 11. S-2 Minimal Remediation Options（不实施，选型交 Owner）

```text
杠杆 ①（数据/运维·无代码）：语料覆盖——re-embed 110/304 未嵌入
  chunks + 扩充治理语料使 domain 模板查询可命中。最符合"门正确、
  数据不足"的定位；见效即解锁 4/4 模式。
杠杆 ②（配置级）：evidence-request.rules.json 的 domain 模板/
  purpose 后缀按治理语料标定（如去掉后缀或缩短复合串）——检索
  标定（G-1 同族），不触任何门；属 Knowledge 配置变更（需授权）。
杠杆 ③（门 scope 变更·Owner 决策）：SOLUTION_VALIDATION 目的的
  空证据不致命化——候选引擎本就诚实输出 MISSING-evidence 候选，
  由下游门/人工复审处置。这是 eval 规则的 scope 调整（对齐
  optional_consumes 语义）——不是放宽安全（候选仍须目录锚定），
  但属质量门变更，必须 Owner 明确授权。
推荐顺序：①（+②）先行；③仅在语料扩充不可行时由 Owner 裁决。
禁止项核对：不为让 S01/S08 变 COMPLETED 而降门——三杠杆均非降门
  （①扩数据②标定查询③改的是"空证据语义"且保目录锚定）。
```

## 12. S-2 Regression Matrix（设计）

| # | 场景 | 期望 |
|---|---|---|
| R2-1 | 有效规划 case+语料可命中 | 全链 PASS → insurance-report 生成并交付（owner 正确） |
| R2-2 | 候选验证证据空（语料不命中） | EVIDENCE_EVAL_FAIL → repair 有界 → needs_review（现状 fail-closed 锁定） |
| R2-3 | 连续拒绝（repair 预算） | 3 次后 REPAIR_EXHAUSTED；无假成功；无假报告 |
| R2-4 | 缺知识证据（上游空） | 同 fail-closed 路径 |
| R2-5 | 目录缺锚点产品 | 候选=MISSING/不产出（引擎诚实语义；不虚构目录产品） |
| R2-6 | needs_review 终态 | 消费者文案=固定模板（K.1 套件）+内部 trace 完整可诊断 |
| R2-7 | 成功交付 | report 真实事件门控+ownership+可下载（E-4/F 语义） |

（若采杠杆③：R2-2 期望改为"空证据→候选带 MISSING 状态继续→下游
门/复审处置"，并新增断言：候选绝不无证据标 AVAILABLE。）

## 13. P2 Release-Gate Assessment（Batch-1 前必须 vs 可带病）

```text
必须进 release gate（建议）：
  G-2 glm 429→llm_unavailable（3/15 轮"稍后再试"死路）：至少
    退避/重试或配额保障；否则首印象受损（运维+小代码项，需授权）。
建议不 gate（披露即可）：
  G-1 检索形态敏感 / R-1"保障"词路由 / R-2 同题漂移——拒答方向
  安全；披露预期即可（产品文案层）。
  U-1 延迟 456s/中位 150s——披露"深度分析需数分钟"；窗口期观察。
P1 两项本身即 Batch-1 的门（见 §14）。
```

## 14. Batch-1 Readiness Assessment

```text
判定：HOLD（两 P1 处置前不建议放真人）
  · S-1（安全类）：至少完成选型（B 可当日实施；A 为结构性跟进）。
  · S-2（核心旅程）：真人规划 100% needs_review（同签名确定性复现）
    ——或先解锁（杠杆①②），或明确"试点范围=QA/咨询+规划以
    needs_review 形态收集人工复审样本"并披露。
  · G-2：缓解或披露。
  · 其余（延迟/检索/路由 P2）：披露级。
```

## 15. Required Owner Decisions

```text
D-K6-1 S-1 选型：方案 B（路由缝收口）/ A（答案边界闭包）/ B+A /
        暂缓（披露风险）→ 授权实施阶段。
D-K6-2 S-2 处置：杠杆①语料/嵌入（运维）·②查询模板标定（Knowledge
        配置变更）·③空证据语义（eval scope 变更）——单选或组合。
D-K6-3 G-2 是否 gate Batch-1（退避/配额 or 披露）。
D-K6-4 Batch-1 go/no-go 判据（建议=S-1 已处置 + S-2 姿态明确 +
        G-2 决策完成）。
（既有队列不变：REVIEWER duty key·P2-②③④·D-04/D-07/D-08/D-09/D-10）
```

## 16. Exact Next Phase Proposal

```text
28.K.7 P1 Remediation Implementation（范围=D-K6-1/D-K6-2 Owner 所选
选项 + §6/§12 回归矩阵落地 + 全量回归 + pilot 重启验证 + K.5 场景
子集复跑对照）；若 Owner 选择"暂缓/披露"，则直接进入 Batch-1 分发
决策（D-K6-4）。
```

## Evidence Index

```text
S-1：k5-ledger S06/S05/S09 全文 · S06 t1 13 事件实录（GENERAL_
  GUIDANCE→knowledge_search→finish 无闭包）· server.py:546-733
  （切片条件/分发/shadow）· agent.py:36-100,164-170（通用环 finish
  与 needs_review 路径）· B5.1 校准套件（闭包门行为锁）· ADR-022
S-2：S08 run_d798132866f84fb9 + S01t2 run_d34954a1a72846c6
  trace.jsonl（EVIDENCE_EVAL_FAIL/REPAIR_EXHAUSTED 同签名×2；28.K C
  与 K.1 C′ 行为一致）· insurance-analysis.yaml:78-99 ·
  orchestrator.py:167-221 · knowledge/evidence/loop.py:38-56 ·
  request.py:112-136 · evidence-request.rules.json:5-22 ·
  eval_engine.py:159-172 · eval.rules.json · 28.H（110/304 嵌入债）
K.5 报告/台账/场景文件 · K.1/K.3/K.4/K.5 phase 报告
```

```text
Code Changes: NONE
Commit: NONE
REAL_USER: 0
Batch-1: NOT DISTRIBUTED
```
