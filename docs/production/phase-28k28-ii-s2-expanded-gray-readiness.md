# 28.K.28-II-S2 · Expanded Gray 就绪审计与受控扩灰框架

Date: 2026-09-29 · Mode: **READINESS AUDIT（零修改·不执行扩灰）** ·
**K.28-II-S2-READINESS: PASS（→ READY_FOR_OWNER_APPROVAL）**

## 1. 冻结状态确认（§2·实测）

HEAD=**24082d5**（工作树≡提交 blob 逐字节）·D-08-K28-II-CLAIM-
SUPPORT=SEALED·OD-12=FROZEN·:8123 PID 25928 health 200（S1
CURRENT_GRAY·CLAIM_SUPPORT_ENABLED=1）·LLM Judge OFF·Planning
NOT ENABLED。Seal 工件零触碰。

## 2. 四能力审计（§3）

### A · 可控启用 → **ROLLOUT_CONTROL = READY（实例级二值）**

现有机制=env `CLAIM_SUPPORT_ENABLED` / rules 双开关——**全开/全关
二值**，无百分比路由（仓库无此系统；按任务 §3.A 不引入新的流量
路由）。既有扩灰惯例（K.33/K.35 实例级金丝雀先例+试点 key 批次
分发）支持受控扩大的表达方式=**在指定 runtime 实例上保持 flag=1 +
以 pilot key 批次（Batch-1→2→3 既有序列）扩大真实使用面**。
粒度限制如实记录：实例级，非请求级百分比。

### B · 可回滚 → **VERIFIED（本阶段复验）**

ON=拦截 / OFF(env=0)=旧路径直投 双向签名复验 VERIFIED（进程内
2026-09-29 本阶段）+ runtime 级（reverify PID 25928 实测）。六步
rollback 规程沿 OD-12 冻结（env=0→restart→OFF 签名→旧路径→
incident evidence→不自行修码）。

### C · 可观察 → **AVAILABLE（核心安全指标）+ 粒度限制如实**

既有内部观察通道（全部不暴露 consumer）：
- run 目录 `qa-answer-context.json`：answer/retrieval(query+计数)/
  evidence_map(锚)/grounding_status/failure_reason/attempts——
  **delivery/refusal 结果与 retry 计数逐 run 可查**
- run events（intent_classified/qa_answered/terminal）+ transcripts
  + server log + K.26 流式行为（delta 有无=流式泄漏检测面）
- **核心 Hard Safety 指标全部可观察**：Escape（=已交付答案中的
  unsupported 事实——transcript 审计面）·Leakage（consumer 面
  扫描）·Unsafe Streaming（delta 审计）·RV4-B（拒答形态）·
  False Refusal（拒答+attempts）
- **限制（如实）**：per-claim support 行未自动持久化（evidence_map
  仅锚不含 chunk 内容→离线逐 claim 复算需重检索）；深审计依赖
  in-process 探针+冻结语料 replay。S2 期间的安全判定不受阻；
  per-claim 持久化=Owner 可选未来项（本阶段不实现·§1）。

### D · 可审计 → **AVAILABLE**

每次观察可追溯：runtime version（commit+文件 sha）·configuration
state（env+rules）·evidence（run 目录/obs 文件/transcript）·
outcome（events+context）。

## 3. S1→S2 Entry Gate（§5·按封存证据）

| 维度 | 条件 | 证据 | 判定 |
|---|---|---|---|
| Safety | Escape=0·新增FP=0·Leakage=0·流式泄漏=0·RV4-B refused | Reverify/Seal（OD12_BASELINE） | ✅ |
| Quality | FR 无重复根因（0/6）·P/R 0.80 无恶化·负例全 blocked | 同上+by_class | ✅ |
| Operations | Rollback VERIFIED·Observation AVAILABLE·Audit AVAILABLE | 本阶段 §2 复验 | ✅ |
| Governance | OD-12 FROZEN·D-08 SEALED·**Owner 批准** | 前二✅·批准=**PENDING** | ⏳ |

→ **READY_FOR_OWNER_APPROVAL**（无批准不扩灰）。

## 4. Owner Decision Block（§4·不自填）

```
EXPANDED_GRAY_TRAFFIC   = OWNER_REQUIRED（建议沿既有 pilot key
                          批次序列表达——具体范围 Owner 指定）
EXPANDED_GRAY_WINDOW    = OWNER_REQUIRED（时长 Owner 指定）
Production Authority    = NOT GRANTED（S2 不自动 S3）
```

仓库无正式 rollout policy 可引用百分比/时长——留白。

## 5. S2 运行规则（引用冻结·不重述）

S2 唯一目的=更广受控范围内观察冻结版是否维持 OD-12 边界（§6）；
Hard Safety 规则（§8：Escape/Leakage/流式泄漏/RV4-B 放行→立即
ROLLBACK S0 六步·新增 FP→BLOCK EXPANSION+OWNER REVIEW）；False
Refusal→REVIEW·同根因重复→BLOCK EXPANSION·禁自动改规则（§9）；
Streaming 契约（§10）·Consumer 边界零新增 debug（§11）·冻结组件
零触碰（§12）·Planning/LLM 全程 OFF（§13）·S2 退出须重过全 Gate+
Owner 批准+Observation Report（§15-16）。

## 6. 产物与合规

本报告 + `tmp/obs/k28ii_s2_readiness.json`（审计快照）；D-08/
OD-12/历史报告/baseline/语料/测试零修改；生产逻辑修改=0。

---

```
K.28-II-S2-READINESS: PASS
S1 CURRENT_GRAY → READY_FOR_OWNER_APPROVAL → S2 EXPANDED_GRAY
Owner approval required. Traffic/window required.
Production Authority = NOT GRANTED
```
