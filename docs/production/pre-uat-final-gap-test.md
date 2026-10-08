# Pre-UAT Final Gap Test（G-06 Network/SSE · G-07 PostgreSQL · G-08 Artifact）

Date: 2026-09-30 · Mode: **TEST/EVIDENCE ONLY**（零生产修改·零修复·
S2/Batch-2 未动）· **PRE-UAT FINAL GAP TEST: COMPLETE** ·
**UAT readiness = READY_FOR_UAT**（P0=0·P1=0）

## 1. Frozen Baseline（§0 实测）

HEAD **e1aba0e**（D-08 intent span RESEALED）·:8123 PID 31740 health
200（灰度 CLAIM_SUPPORT_ENABLED=1·含 OBS-1 修复）·:5273 200·WeKnora
401-alive·agent-postgres/WeKnora-postgres Up·LLM Intent OFF·Det=
AUTHORITY·Authority NOT GRANTED·S2 OPEN-UNSTARTED·Batch-2 未分发。

## 2. G-06 Network/SSE → **PASS**

| Case | 方法（live :8123） | 结果 | 判定 |
|---|---|---|---|
| G6-01 流中中断 | QA 流中 client abort（2 events 后断） | 断后 run 正常 completed·**durable 事件 6·终态事件恰 1**·assistant 消息 1·run 恰 1·泄漏 0 | **PASS** |
| G6-02 SSE 重连（既有 cursor 协议） | 断开→`?after_event_id=<last>` 重连 | 首段 1 event+续段 5 events·**overlap=0·并集 6=durable 6（无损无重无跳）** | **PASS** |
| G6-03 运行中「刷新」 | run 进行中 chat GET + 终态后 GET | mid=1 user msg·post=2 msgs·run 恰 1·终态 waiting 一致——**同进程刷新=完全恢复**（与后端重启=ADR-024 限制严格区分） | **PASS** |
| G6-04 网络失败+retry | 早期断流→原 run 到终态→重发消息 | 原 run 终态保持·retry=合法**新 run** completed·chat runs=2 msgs=4（**无重复消息/无重复 run/上下文无重复注入**） | **PASS** |

SSE 协议事实（代码+行为双证）：`_sse_generator` 以 cursor 重放
durable 历史+CLOSE 补齐——重连语义=既有 K.22 I9 契约，本轮零新增。
注（如实）：第一版探针 socket 读法未捕获事件（探针缺陷）——以
urllib 行级读法复测为准（g6_sse_redo.json）。

## 3. G-07 PostgreSQL → **PASS（事实澄清：PG=启动期依赖）**

| Case | 方法（安全注入=错误密码 env·零数据破坏） | 结果 | 判定 |
|---|---|---|---|
| G7-01 受控 PG 失败 | 进程内 `AGENT_PG_PASSWORD=错误值` 构造 service | **ProviderConfigError fail-closed**（拒绝回落 JSON registry）·错误消息无凭据泄漏·无栈 | **PASS** |
| G7-01b 用户面 | BadSvc（PG 断连签名）注入 run_qa_turn | `kb_unavailable` 诚实拒答（固定文案「知识服务当前不可用…不会在缺少证据的情况下作答」）·**无栈/无 false success** | **PASS** |
| G7-02 恢复 | live 服务器（PG 正常）正常请求 | completed·消息 2·run 1 | **PASS** |
| G7-03 会话完整性 | G6-04 chat 前后对照 | runs=2 msgs=4 无重复/无消失/无串扰 | **PASS** |
| G7-04 用户隔离 | A=坏 PG 组合拒答·B=live probe-beta 正常 | B completed·零 A 内容/run/错误态污染 | **PASS** |

**架构事实（如实记录）**：PG registry 为**启动期**依赖（strict 预检
+KnowledgeService 单例缓存）——运行中 PG 宕机不影响已启动进程内
新 QA 轮（缓存 registry）；真实影响面=重启失败（fail-closed·已由
三次启动先例实证）。非缺陷·记录为部署特性。

## 4. G-08 Artifact → **PASS**

| Case | 方法 | 结果 | 判定 |
|---|---|---|---|
| G8-01 正常 artifact | live 规划 run（G6-04 retry） | **9 artifacts**（client-profile→…）·ART-001.. 序号正确·关联正确 | **PASS** |
| G8-02 artifact 失败 | 既有注入套件（F01-F13：planner/agent/eval/HOTL 故障族） | **28/28**（failure_injection+K.24 deadline+p26c4 recovery）——false success=0·partial invalid=0·栈=0（套件断言） | **PASS** |
| G8-03/04 retry/重复重试 | 同上（repair/replan/block+幂等终态） | 终态幂等 first-wins（K.24）·无重复 artifact/终态/消息 | **PASS** |
| G8-05 失败后刷新 | artifact-bearing run 同进程重读 | run/artifact 状态一致 | **PASS** |
| G8-06 长 artifact | 既有 live 证据（47.8/50.6KB 报告·K.25-RV/S1-fix） | 渲染/交付已证——本轮**不造新超长 fixture**（如实引用历史 live 证据） | **PASS（证据引用）** |

HTML/PDF=NOT_IN_CURRENT_SCOPE（沿 coverage audit）。

## 5-7. Cross-Cutting（全 G6/G7/G8）

- Security：内部 ID/栈/DB 凭据/runtime 元数据泄漏=**0**（G6-01
  transcript 扫描+G7 错误消息检查+拒答文案固定模板）
- Correctness：wrong answer=0（全部失败路径=诚实拒答/合法终态）·
  false success=0·跨用户/跨 chat 污染=0
- Idempotency：duplicate run/message/artifact/terminal=**0**（G6-01/03/
  04 计数证据+G8 幂等套件）
- Streaming：unsafe partial=0（中断后 durable 事件重放=已验证内容）·
  terminal-after-terminal=0（终态事件恰 1×全 run）·T_first<T_final
  沿 K.26 sealed

## 8-11. Failure Classification / Remaining

- **P0=0 · P1=0**
- P2：①SSE 中断时用户侧提示依赖前端实现（本轮后端 durable 一致性
  已证；前端断线 UX=Batch-F/G 观察）②运行中 PG 宕机无进程内告警面
  （部署特性·监控建议）
- P3：无新增（沿既有 P3-1..4 观测债）
- KNOWN_V0_1_LIMITATION：后端重启丢 chat/run 内存态（ADR-024·与
  browser-refresh 已严格区分）；同进程刷新=完全恢复（G6-03 实证）

## 9. Coverage Matrix 更新

- G-06 Network/SSE：**TESTED→E2E_VERIFIED**（live 中断/重连/刷新/
  retry 四路；cursor 协议行为级证明）
- G-07 PG Failure：**TESTED→E2E_VERIFIED（fail-closed+隔离）**+
  部署特性记录（启动期依赖）
- G-08 Artifact：**TESTED→E2E_VERIFIED**（live 9-artifact+注入套件
  28/28+历史长报告证据）

## 12. Owner Decisions（沿袭·无新增）

Batch-2 分发时刻（窗口起算）·03/07/10 量词语义·claim-support span
续封（P2-1+FIX2 未入 git）·G-01 持久化/Planning 轨道·28.C-3 JWT。

## 13. UAT Readiness Impact

**READY_FOR_UAT**——P0=0·P1=0·安全/正确性/幂等/流式四横切全零·
P2/P3 均为 known limitation 且不阻塞（前端断线 UX=UAT 观察项·
V0.1 重启限制已如实告知范畴）。

---

```
PRE-UAT FINAL GAP TEST: COMPLETE
G-06 = E2E_VERIFIED · G-07 = E2E_VERIFIED（+部署特性记录） · G-08 = E2E_VERIFIED
P0 = 0 · P1 = 0 · P2 = 2 · P3 = 沿袭
UAT readiness = READY_FOR_UAT
```
