# Phase 28.K-Final Controlled Pilot Exit Audit

Date: 2026-09-27 · AUDIT ONLY（零改动·零重启·真实代码/runtime/test
为唯一事实源）。

## 1. Result

```text
CONTROLLED_PILOT_READY_WITH_LIMITATIONS
（工程闭环成立；限制=in-memory 持久层/供应商间歇/半 cohort 真实
样本/公网部署未做——均非 Controlled Pilot 阻断项）
```

## 2. Current Runtime

```text
Backend:   :8123 PID 13520 · startup 2026-09-27T12:13:32Z · LIVE ·
           controlled_pilot · strict 预检过 · **K.24+K.25+K.25-S1
           全载**（run_deadline+consumer_hygiene importable·
           frontend composing 在 served 代码·S1 行为学复验在 §7-8）
Frontend:  :5273 PID 37032（vite dev·最新前端）
WeKnora:   :8080 401-alive · agent PG :5433 OPEN · deps READY
Auth:      keys 模式（11 identities·8 受邀 CONSUMER·2 probe·1 ops）
REAL_USER: ON（Batch-1 2 用户·key 已交付·自然使用中——真实人类
           会话 7+ 次，pilot-user-01/02 均活跃）
Router authority: full（pilot 临时·代码默认 slices 未变）
```

## 3. Architecture Integrity

```text
Intent: 独立 schema+规则分类器（K.7 受治理 unknown 扩展）✓
Router: deterministic（registry lookup·authority 分层）✓
Agent Registry: config-based·启动校验 ✓
Runtime: 单一 orchestrator 脊柱（B4 等价 7/7）✓
EventBus: 单一（transient+durable 双通道）✓ SSE: 单一·resumable ✓
Artifact: registry+lineage+owner 继承 ✓
Grounding: WeKnora 治理链+引用闭包门+fail-closed ✓
（证据：815+2 全量含 B4/M4/M3/E6/B-02/HD-2/GOV/K.7/K.22/K.24/
 K.25/S1 套件）
```

## 4. Consumer Boundary

```text
Auth: keys 模式 401 fail-closed（本审计 live：anon read=401）✓
Ownership: live 复验——B self-read 200·A cross-read 404·A
  cross-delete 404·B delete own {deleted:true} ✓（B-02 15/15 含于全量）
Opaque refs: issue/resolve/ownership 复检/revoke-on-parent-delete
  （S1 live report ref 交付 50.6KB + GOV 套件）✓
Cross-user: 统一 404（本审计 live）✓ Anonymous: 401 ✓
Content hygiene: S1 三层——本审计 live 拒答轮零 ID 泄漏 ✓
```

## 5. Consumer Execution Progress

```text
K.17: delta-驱动活性行+真静默心跳 ✓（16/16）
K.20: 消息位流式气泡+失败 partial 保留 ✓（streamMessage 9/9）
K.22: 门后 validated 分块流 ✓（6/6·S1 live QA_ANSWERED 实证链）
K.25: tool_* 检索里程碑+composing 派生+○ pending+terminal 冻结 ✓
  （progressProjection 9/9）
```

## 6. Timeout / Reliability

```text
K.24: run_deadline_s=900·generation_wall_s=240·min_retry=5（只读
  核验）；deadline supervisor 独立终态+幂等 _finish_run+closed 后
  delta 抑制 ✓（K.24 8/8 含于全量）
Terminal closure: 正常/QA/crash/deadline 五路恰一终态 ✓
```

## 7. QA Evidence

```text
QA normal: S1 live——等待期 70s→completed/QA_ANSWERED（首次 live
  过引用门）·[E1] 引用·零泄漏 ✓
QA refusal: 本审计 live——医疗vs重疾 ret=0→8s 诚实拒答·零泄漏 ✓
QA long generation: R3（70s 生成窗·citation 门拒→零 delta）+
  S1（门过→validated 流）——SCRIPTED_PROBE 证据 ✓
```

## 8. Planning Evidence

```text
S1 live 两轮（289s+233s）：intent→8 stages 真实顺序→11 agent
  steps→10 tools（1 retry 稳定）→9 evals→9/9 VALID artifacts→
  insurance-report 交付 50.6KB→COMPLETED·ID 泄漏 NONE ✓
（K.25-RV R2 同类场景曾泄漏 ART-009——S1 后归零）
```

## 9. Artifact Integrity

```text
Create/Store/Retrieve/Ownership/Download（50.6KB ref 解析）/
Deep link（#/report/{ref}）/Deletion（GOV 级联+404 复验）: 全 PASS
（live+GOV 11/11+G/B-02 套件）
```

## 10. Governance

```text
Retention: 5 类 policy（180/30/90/365/0·只读核验）·env 可换 ✓
Deletion: 级联（chat→runs→dirs→bus→refs→tombstone）+删后 404 ✓
Eval: 零自动复制（golden 哈希）✓ Audit: 元数据级·独立存活 ✓
Operator: 职责读留痕（consumer_data_read）✓ Developer: 内部通道 ✓
```

## 11. Security

```text
CoT/Reasoning/Internal ID/Tool/Skill/Agent/Raw Event/Exception/
Cross-user = 全 0（本审计 live 双场景+S1 live 规划扫描+全套泄漏
套件含于 815+2/258+2）
```

## 12. Regression（本审计新鲜复跑）

```text
Backend: 815 passed · 0 failed · 2 skipped（HD-2 live 门）
Web: 258 passed · 0 failed · 2 skipped · TS: PASS
Security: PASS · Pilot: PASS（§7-8 live）
```

## 13. Historical Debt（当前态重分类）

```text
P0: 无
P1: 无
P2: ①GLM 间歇（YELLOW 沿袭——突发窗口 llm_unavailable·F2 可归因
    就绪）②G-1 检索形态（真实用户 2 obs·拒答方向安全·影响可用性
    口碑）③首响延迟（中位 ~150s·规划 ~250s+）
Deferred: in-memory 持久层（重启丢会话——已披露·PERSISTENCE 立项）·
  F2 agent-loop 网关覆盖（agent 步 LLM 不经 gateway）·治理 UI·
  retention scheduler·accident/savings 语料·:8000 生产部署·
  D-04 引用校准·D-07 permanent authority·D-08 commit（span 32+
  untracked）·D-09 清理·D-10 HTML/PDF
```

## 14. Evidence Classification

```text
REAL_USER: 7+ 真实人类会话（user-01×3·user-02×4·含规划澄清+QA+
  拒答）——全部到达终态·零安全事件·零 ID 泄漏（S1 后）
SCRIPTED_PROBE: S1/RV/R2/R3 等 live 复验（真实栈·如实标注）
SYNTHETIC: 无（不冒充）

Evidence Matrix:
Scenario  | Evidence Type    | Result
QA normal | SCRIPTED_PROBE   | QA_ANSWERED·引用过门·零泄漏
QA refuse | REAL_USER+PROBE  | 8s 诚实拒答·零泄漏
Planning  | SCRIPTED_PROBE   | 9/9 VALID·报告交付·零泄漏
Long gen  | SCRIPTED_PROBE   | 70s·门语义双向实证
Refusal   | REAL_USER        | 跨 3 轮·安全
```

## 15. Closed Scope

```text
28.A（intent/router/registry）·28.B（等价迁移）·28.C（QA 切片）·
28.D（planning）·28.M4/M5（authority 灰度）·28.E（Consumer Surface
E1-E7）·28.F（B-03）·28.G（B-02）·28.H（B-01）·28.I（B-04）·
28.J（复审计）·28.K.1-K.13（文案/进度/心跳）·K.17（活性行）·
K.20（流式）·K.22（QA 流式）·K.24（deadline）·K.25（进度投影）·
K.25-S1（ID 卫生）
```

## 16. Remaining Limitations

```text
①in-memory 持久层（重启丢会话——受控试点可接受·已披露用户）
②GLM 供应商间歇（YELLOW·突发死路率存在）
③G-1 检索形态（2 真实 obs·主流概念题可能拒答）
④首响延迟（QA 中位 ~70-150s）
⑤pilot 为 loopback 部署（公网/多机=部署决策未做）
⑥半 cohort 未充分使用（user-02 4 轮 vs user-01 3 轮——样本量小）
```

## 17. Owner Decisions

```text
①D-08 commit 授权（span：32 tracked-modified+全部 untracked——
  28.A..K 全部工作）
②Batch-2 扩员（3 用户）或 Batch-1 CONTINUE
③D-07 Permanent Full Authority（证据齐备）
④PERSISTENCE 立项（重启丢会话→生产前必须）
⑤G-1 检索治理轨道（语料/分词/嵌入）
⑥D-04 引用合规校准（live 过门率仍部分）
```

## 18. Recommended Next Phase

```text
工程事实：受控试点工程闭环已成立——自然选项=(a)Batch-1 继续积累
真实样本→(b)Owner 逐项裁决 §17（commit/Batch-2/PERSISTENCE/G-1）→
(c)窗口关闭→Rollback→Batch-2 或生产化立项。本审计不实施任何项。
```

STOP
