# K.27-RV4-C2 LIVE Verification — QA Evidence Relevance Qualification

Date: 2026-09-29 · Status: **K.27-RV4-C2 LIVE VERIFIED — PASS
（P1-B CLOSED）** · 验证任务零产品代码改动（探针/观察文件仅 tmp/）

## 1. Restart Evidence（§1 Precheck）

机器在会话前约 09:17 重启过（docker 容器 Up 22min、pilot 孤儿进程
尽数消失）。按授权与 runbook 恢复：

| 项 | 值 |
|---|---|
| backend | :8123 **PID 5392**·start **2026-09-29 09:44:45**·`/api/health` 200 |
| C2 revision 载入证明 | `qa_agent/agent.py`+`qa-grounding-rules.yaml` mtime **09-28 23:13** < 进程启动 09:44:45（+§4 行为证明） |
| frontend | :5273 vite 200（proxy→:8123） |
| WeKnora | `docker start WeKnora-app`（重启后 Exited 127）→ Up healthy·:8080 **401-alive** |
| PG | agent-postgres :5433 LISTENING |
| config | glm-5.3 / fast=flashx / qa=flash（Stage 1·未动） |
| 鉴权 | probe-alpha whoami=consumer:probe-alpha CONSUMER |

**恢复过程中的环境事实（非代码问题，如实记录）**：hd2.env 缺三样
启动必需（INSURANCE_AGENT_API_KEYS 仅 2 把旧钥→须覆盖为 pilot-keys
11 身份；DATA keyfile / WeKnora API key / PG password 须从 tmp/ 文件
读入导出）——首次两拉起分别败于 ENCRYPTION_REQUIRED 与
PRODUCTION_KNOWLEDGE_REQUIRED（strict 预检 fail-closed 正确工作），
第三次按 runbook 全量密钥后成功。**runbook 建议补一页「密钥文件→
env 映射」**（观察项 O-3，未改任何文件）。

## 2. Exact RV4 Messages（§2·逐字复放）

- **T1**：`我40岁，孩子5岁，有社保，重疾险200万，家庭年收入30万，有房贷，每年愿意投入2万在保险，担心收入中断和大病医疗费用，帮我看看家庭保障有没有明显缺口`
- **T2/Q**：`200万重疾险是我的，我和配偶都有百万医疗险，孩子没有保险。房贷还剩100万。配偶35岁，有100万重疾险，家庭主要收入是我一个人`

主体=probe-alpha（SCRIPTED_PROBE·REAL_USER 台账零污染）。全程
7 轮 live run（下详）。

## 3. C1 Continuation Result（§3）

**本日 T1 5/5 全部直跑完成（70–105s·insurance_plan conf1.0·完整
缺口分析交付·文末以文本形式请求补充信息）——WAITING_USER 前置
均未成立 = reproduction variance（模型采样差异），按任务规则不计
为 C2 失败、不改代码。**

C1 preserved 以三重证据确立：
1. **代码同一性**：classifier.py / server.py / intent-rules.yaml
   mtime=09-28 22:20–22:21（C1 实施时刻）——C2（09-28 23:13·仅
   qa_agent+yaml）未触碰 C1 表面。
2. **套件绿**：本会话早前全电池 865+2 含 C1 专项 12/12（RV4 真实
   两轮一等回归）零失败。
3. **C1-LIVE（09-28·同一代码）**已 live 证明延续形态（T2
   insurance_plan conf1.0 [plan:continuation]→planning 全管线）。

本日 shadow 记录 5/5 意图正确（T1→insurance_plan
[rule:plan:保障+ctx:家庭/孩子]；无 pending 信号=无 waiting_user
所致，与 C1 语义一致）。**观察 O-1：ask-vs-proceed 方差本日 5/5
同向偏 proceed**（C1-LIVE 时 1/2）——规划一致性 UX 观察，Owner
裁决线（不属本验证范围）。

## 4-8. C2 Evidence Qualification（核心验证）

### 4.1-4.2 RetrievedEvidence ≠ QualifiedEvidence（LIVE 实证）

**Q leg（T2 原文·新 chat·run_e1ac3ef906d0441d·5.0s）**：

| 层 | 事实 |
|---|---|
| Intent | insurance_qa conf1.0 [rule:qa:重疾险, rule:qa:医疗险]——**与原始事故分类逐字一致**（规则链 faithfully 复现 QA 路径） |
| Retrieval | WeKnora governed **allowed_count=1**·status=success |
| 直查身份 | 同 query 只读直查=**唯一治理命中即《农业保险条例》**（与 RV4-A 原始事故同一命中） |
| Qualification | **不合格**（词项重叠<2）→ `evidence_refs=[]`·`evidence_map={}` |
| Grounding | `grounding_status=refused`·**≠grounded**·无 [E1]·无「模型明知无关仍被系统标权威」面（生成从未发生） |
| Generation | `provider=(not-attempted)`·**attempts=0**·gateway 未调用（零 LLM 浪费） |
| Terminal | `QA_REFUSED`·failure_reason=**insufficient_evidence**（既有拒答路径） |

**原始 RV4-A 失败链被逐环节复现并阻断于资格层**：检索到农业条例
（允许）→ C2 淘汰（合格集空）→ 既有诚实拒答。

### 4.4 最终用户可见行为

> 「知识库暂无可靠依据，暂时无法回答这个问题。您可以换个说法再
> 问，或稍后再试。」

零编造·零农业条例桥接·零强行方案·零 citation stuffing·零把用户
自述包装成 [E#]（§6 user-fact 边界：全文无 [E）。

### §5 Retry Bypass

拒答发生在生成**之前**（attempts=0）——重试/重生成路径位于
generate_grounded 内（其前提=非空合格证据集），结构上无从以原始
检索重扩张（离线 R5 双 attempt 证据集逐字节相同 + 本 live
attempts=0 双证）。

### 阳性对照（不过度过滤·live）

相关问法「重疾险的等待期是什么」（run_a87de0df68ad443e·30s）：
insurance_qa → allowed_count=1（健康险法规·相关）→ **资格通过**
（进入生成·gateway=true·attempts=2·request_id 在案）→
`citation_gate_rejected`（fact_sentence:no_citation×4——**既有
C-4 校准线签名，与 C2 无关**）→ 诚实拒答文案。

**分层判据成立**：insufficient_evidence=C2 资格层；
citation_gate_rejected=校准层。C2 精确拦截无关证据、放行相关证据。

## 9. Security Nine-Zero（§7·全部用户面 transcripts+终态消息扫描）

internal_id=0 · CoT=0 · reasoning=0 · tool_leak=0 · skill_leak=0 ·
agent_leak=0 · raw_event=0 · exception=0 · cross_user=0
（tmp/obs/rv4c2_secscan.json；[E 引用与「农业保险条例」在全部
用户面文本 grep=0）。

## 10-13. C1 Regression + 结论

- C1：代码零触碰+套件 12/12+shadow 5/5 正确+既往 live 证明 →
  **preserved**（本日 live 延续复放因方差未再现前置，如实记录）。
- QA bypass（waiting 场景误入 QA）：本日无 waiting 场景可测；
  覆盖由 C1 套件回归承担。
- **C2：K.27-RV4-C2 LIVE VERIFIED — PASS。P1-B CLOSED。**
  （P1-A 已于 09-28 闭——RV4 两 P1 全闭环。）

## 14. Observations / Deferred（STOP 后不进入 Phase 2）

- **O-1**：规划 ask-vs-proceed 方差 5/5 偏 proceed（本次窗口）——
  UX 一致性 Owner 观察（与 C1-LIVE 记录同源，强度增加）。
- **O-2**：qualification 对真实相关问法的 recall 本日仅 1 样本
  （通过）；真实流量拒答率变化=后续观察（过度过滤→调
  `min_query_bigram_overlap`，无需改码）。
- **O-3**：hd2.env 缺启动密钥映射（API_KEYS 旧集/DATA/WEKNORA/PG）
  → runbook 补页建议。
- **O-4**：机器重启后 WeKnora-app 不自启（Exited 127）→ 重建
  restart policy 建议（运维项）。
- Phase 2（claim-support 抽查·user-fact 语义·citation 密度）与
  ADR-024/LLM 候选=**等 Owner 授权，本验证后即 STOP**。

## 附：运行态与服务处置

pilot 服务保持运行（:8123 PID 5392=C2 代码·:5273·WeKnora 栈·PG）
——pilot 窗口沿 Batch-1 既有状态；本验证 7 轮均为 SCRIPTED_PROBE
主体，REAL_USER 台账零污染。证据文件：tmp/obs/rv4c2_*.json/.txt·
tmp/webui-runs/run_{e1ac3ef9,a87de0df,…}/。
