# Phase 28.K27 — Controlled Pilot Observation & Productionization Decision

Date: 2026-09-27 · OBSERVATION-ONLY（零代码改动·零重启·零 synthetic·
零用户指导）。窗口：K.26 封版（46dbe0f 推送）后 ~30 分钟轮询×2 +
全部历史真实用户证据汇编。

## 1. Pilot Window

```text
时间范围： 2026-09-26 12:05Z – 2026-09-27 13:55Z（跨 K.12..K.26）
用户数量： Batch-1 = 2（pilot-user-01/02·key 已交付·均验证有效——
           本窗口 whoami 双双 authenticated）
真实 Session 数： 7 轮 REAL_USER（user-01×3·user-02×4）
本窗口新增： 0（K.26 封版后两次轮询零自然流量——如实；
           服务 LIVE·key 有效·audit 含 operator 读记录）
运行实例： :8123 孤儿 PID 3204（K.26 代码·LIVE）·:5273 正常·
           WeKnora 401-alive
```

## 2. Observation Infrastructure Audit

```text
字段可得性（全部复用现有数据·零新增系统）：
✓ run meta（run_id/owner/started_at/completed_at/status/
  result_status/mode/stage_order/event_count）
✓ events（intent/tool/stage/eval/artifact/delta[transient]/
  terminal——完整事件链含 payload）
✓ qa-answer-context.json（grounding_status/failure_reason/
  retrieval{provider,allowed,denied,query}/generation{provider,
  attempts,request_id}/evidence_map）
✓ artifact registry（type/status/lineage）
✓ F2 llm.call（request_id/duration/error_class/retryable/attempt）
✓ 治理审计（consumer_data_read/deletion）
✗ 无法从服务端观测：user_retry（前端行为）·user_feedback（无
  反馈通道接线）·first_delta_at（transient 不落盘——仅 SSE 捕获
  时可得，如 K.26 R1/R2 探针）
判定：不阻碍观察（user_retry 可从同 chat 后续 run 推导；feedback
  为 Owner 人工渠道；first_delta 用探针抽样）
```

## 3. Observation Ledger（全部真实用户场景）

| Date | User | Scenario | Intent | Dur | Retrieval | Evidence | Citation | Stream | Artifact | Terminal | Provider | Retry | UserRetry | Feedback | Security | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 09-26 12:05 | u01 | A 知识咨询 | plan(规则)→GUIDANCE | 64s | 2 次均 0 hit | 0 | N/A(无生成) | 无 | 无 | completed | glm 正常 | agent 自查 1 | 否 | 无 | 0 | 诚实披露"无引用"→通用思路 |
| 09-26 15:16 | u01 | A 概念区别 | insurance_qa | 5s | 0 hit | 0 | 未到门 | 无 | 无 | completed/QA_REFUSED | 未调用 | 0 | 否 | 无 | 0 | 8s 内诚实拒答 |
| 09-26 16:02 | u02 | D 不完整信息 | plan→ask | 39s | — | — | — | — | 无 | waiting | glm 正常 | 0 | —（等待中） | 无 | 0 | 结构化澄清 4 问 |
| 09-26 16:34 | u02 | A 知识问答 | insurance_qa | 128s | 1 hit | 1 | gen 尝试→llm_unavail | 无（K.26 前） | 无 | completed/QA_REFUSED | **glm 不可用** | gw 1 | 否 | 无 | 0 | provider 故障→诚实拒答 |
| 09-26 17:56 | u02 | D 不完整信息 | plan→ask | — | — | — | — | — | 无 | waiting | glm 正常 | 0 | — | 无 | 0 | 新会话重问同题（澄清重发） |
| （K.12..K.25 期间 operator 只读读取共 5 次 consumer_data_read——职责观察·全部入审计） |

**真实用户场景覆盖判定**：A✓（2 例）·B 产品事实✗（零真实样本）·
C 完整规划✗（两例均止于澄清 waiting——用户未提供家庭信息走完
8 阶段）·D✓（2 例·行为正确）·E✓（2 例拒答+1 例 provider 拒）·
F 长回答流式✗（K.26 后零真实用户长答案样本——仅探针 R1/R2）。

## 4. Runtime Metrics（真实用户+探针合并·如实标注）

```text
Duration（真实用户）：5s-128s（QA 类）·39s（澄清）
First Delta：真实用户=不可得（K.26 前历史）·探针 R1=24.1s·R2=33.9s
Streaming Span：探针 R1≈70s·R2≈164s·delta 9/33
Retrieval（真实用户 QA 3 例）：0/0/1 hit——2/3 零命中（G-1 形态）
Citation：真实用户 0 例过门（2 例证据层拒·1 例 provider 拒）·
  探针 1 例过门（R1 QA_ANSWERED）·1 例流 33 句后门拒（R2）
Artifact：真实用户 0（无完整规划）·探针 9/9 VALID
Retry：真实用户 agent 自查 1·gw 1·探针正常
```

## 5. Safety

```text
全部窗口（真实用户 7 轮+探针全系列）：Internal ID=0·CoT/Reasoning=0·
Tool=0·Skill=0·Agent internal=0·Raw event=0·Exception=0·
Cross-user=0·Fake artifact=0·Grounding bypass=0
（K.25-S1 后 live 扫描全 NONE；K.25-RV 发现的 ART-009 已修复并
经 S1 live 复验归零）
SECURITY INCIDENT：无
```

## 6. Failure Taxonomy

```text
P0：无 · P1：无
P2：①GLM 间歇（真实用户 1/4 QA 轮 llm_unavailable；探针 R2 门拒
    属 D-04 非provider）②G-1 检索形态（真实用户 2/3 QA 零命中——
    儿童重疾咨询+医疗vs重疾概念题）③首响延迟（首 delta 20-35s·
    澄清轮 39s·用户静默期仅心跳）④真实用户长答案样本缺失（K.26
    流式未被真人体验过）
P3：用户重发同题未提供信息（17:56 重问——澄清 UX 摩擦观察项）·
    user_feedback 通道未接线
```

## 7. User Feedback（事实记录）

```text
无主动反馈提交（通道未接线——Owner 人工渠道收集）。
间接行为证据：u02 在 16:02 澄清后 ~1.5h 以新会话重问同题（17:56）
——仍得到澄清（未提供信息）；无退出/重复轰炸/异常行为证据。
```

## 8. Engineering Findings

```text
已证实：安全五零跨全部窗口成立（含 K.26 流式）·真流式 T_first<
T_final（探针）·澄清行为正确（D 场景 2/2）·拒答诚实（E 场景
3/3）·provider 故障与 agent 逻辑可区分（F2 记录在案）
仅观察现象（未定位根因）：G-1 零命中形态（2 真实样本·方向一致
但样本小）·glm 间歇窗口（YELLOW 沿袭）
数据缺口：真实用户 B/C-完整/F 三类场景零样本——归因于用户自然
使用模式（咨询型提问为主·未提供规划所需个人信息）
```

## 9. Deferred Tracks（状态核查）

```text
D-04 Citation Calibration：证据增强——R2 流 33 验证句后终门拒=
  generation_success/delivery_refusal 典型样本；真实用户 0 过门
G-1 Retrieval Governance：2 真实 obs+方向一致；语料/分词/嵌入
  轨道待 Owner
Provider Reliability：1 真实用户轮 llm_unavailable+F2 归因就绪
Persistence：重启丢会话（今日多次重启实证）——生产前必须
D-07 Permanent Full Authority：证据齐备待决
Batch-2：前置=观察覆盖补齐（B/C/F 真实样本）
Productionization：依赖 Persistence+D-04+G-1+部署决策
```

## 10. Owner Decision Matrix

```text
Decision: Batch-2 扩员时机
Evidence: 真实覆盖 A/D/E ✓·B/C完整/F ✗（用户自然模式未触达）
Risk: 扩员可能仍不触达 B/F（需引导或等待）；不扩则观察停滞
Options: (a)继续 Batch-1 观察+Owner 引导用户尝试规划全流程
  (b)授权 Batch-2（3 用户）扩大样本 (c)结束观察进入裁决
Required: Owner 选择

Decision: 观察通道补齐（user_feedback 接线）
Evidence: 反馈通道未接线·仅行为证据
Risk: 低（小工程项）
Options: 接线（需授权）/维持 Owner 人工渠道
Required: Owner 授权与否

Decision: D-04/G-1/Provider/Persistence 优先级
Evidence: §9 各自证据在案
Risk: 均非安全阻断·影响可用性/口碑
Required: Owner 排序

Decision: D-08 剩余 span commit（34 modified+133 untracked）
Evidence: K.26 已单独封版推送（46dbe0f）；其余 28 系列未提交
Required: Owner 授权范围（全量/分批）
```

## 11. Observation Exit 条件核查

```text
1 QA✓ 2 产品事实✗ 3 Planning（完整）✗ 4 澄清✓ 5 拒答✓
6 长答流式（真实用户）✗ 7 真实反馈✗（通道未接线）
8 P0/P1=0✓ 9 安全五零✓ 10 问题归因六分类能力✓
→ **未达 Exit（4 项缺口：B/C完整/F/反馈）**——继续 Controlled
Pilot 观察（推荐 Owner 引导两位用户尝试一次完整规划+一条产品
事实+观察流式体验），或 Owner 直接裁决进入下一步。
```

## STOP

```text
零代码/配置/架构改动·零 synthetic·零用户指导·未触碰任何进程
（孤儿 backend 保持运行供窗口使用）
```

---

## K.27-RV2 Evidence Completion（2026-09-27 深夜·观察窗口 ~25 分钟）

### 1. New Real User Sessions

```text
新增真实 Session： 1（run_a7d9ccb9b08742d3 · consumer:pilot-user-02）
新增用户：         0（既有 Batch-1 用户·K.26 代码上的首次自然使用）
窗口：            两次轮询（6min+10min）——该轮为窗口内唯一自然流量
```

### 2. 新增 Session 详情

```text
用户问题： "一家三口需要哪些保险？"（自然·规划型提问）
Intent：   unknown_insurance_intent（受治理 unknown → K.7 知识-qa 管线）
Retrieval：weknora allowed=0 denied=0 → G-1 第 3 次真实用户复现
          （家庭保险主流问法零命中——方向与儿童重疾/概念区别一致）
Citation：  未到门（证据层 fail-closed）
Terminal：  completed/QA_REFUSED · 5s 诚实拒答 · 零泄漏
场景归类：  E（拒答）观察样本 + G-1 检索形态第 3 obs
K.25 进度： tool_started/completed 事件链正常（正在核实相关资料→
            已完成资料核对→拒答——消费者可见真实进度）
```

### 3. 新发现（记录·未修复）

```text
Finding:   QA 拒答消息在 transcript 中【重复出现两次】
           （chat 消息列表：1 条 user + 2 条相同 assistant 拒答）
Root cause: server.py QA 切片路径双重写入——_finish_run(chat_message=
           answer) 已写一次（含 K.25-S1 sanitize）+ 残留的直接
           add_assistant_message(:845) 再写一次（【绕过 sanitize】）
Impact:    ①UX 噪声（重复文案）②第二份写入绕过 K.25-S1 交付卫生
           层（门已过的答案中若含内部 ID 将经此路泄漏——本次
           observed=0，为防御层削弱非实际泄漏）
Severity:  P1（交付语义缺陷+卫生旁路；非安全事件——泄漏观测=0）
Fix（待授权）：删除 server.py:845 的残留直接写入（一行）
```

### 4. Scenario Evidence（RV2 后更新）

| Scenario | Real User | Result | Evidence |
|---|---|---|---|
| A QA | ✓（3 例） | PASS | 2×拒答+1×provider 拒——全部诚实 |
| B Product Fact | ✗ | NOT OBSERVED | 零真实产品事实样本 |
| C Planning（完整） | ✗ | NOT OBSERVED | 新样本亦为止于拒答（G-1） |
| D Clarification | ✓（2 例） | PASS | 结构化澄清正确 |
| E Refusal | ✓（4 例） | PASS | 新增 1 例 5s 诚实拒答 |
| F Streaming（K.26 后） | ✗ | NOT OBSERVED | 该轮 5s 快拒·无生成期 |
| Feedback | — | FEEDBACK_CHANNEL_NOT_CONNECTED | 无接线（如实） |

### 5. G-1 累计（真实用户）

```text
obs#1 儿童重疾配置考虑 → 0/0 → 通用思路（09-26 12:05 u01）
obs#2 医疗vs重疾概念区别 → 0 → 5s 拒答（09-26 15:16 u01）
obs#3 一家三口需要哪些保险 → 0 → 5s 拒答（09-27 14:56 u02·K.26 后）
模式：主流保险问法在治理语料零命中——3 obs 方向完全一致
```

### 6. Exit Decision

```text
OBSERVATION EXIT NOT READY
（B/C/F 三类真实用户证据仍缺+feedback 未接线+新 P1 发现待处置；
 安全五零维持·P0=0·无 Hard STOP 条件触发）
```

---

## K.27-S1 — QA Refusal Transcript Double-Write Fix（2026-09-27）

### Root Cause
server.py:845 残留的直接 `add_assistant_message` 写入——在
`_finish_run(chat_message=...)`（K.25-S1 sanitize 边界内）已写一次
后，再以未消毒文本重复写入同一拒答消息。全仓搜索确认：这是唯一
的绕过路径（chat 写入点仅 :286[_finish_run 内·sanitized] 与
:845[本残留]）。

### Fix
删除 :845 直接写入（两行），以注释固化"唯一 transcript 写入=
_finish_run 卫生边界"契约。未新增任何 sanitizer 层。

### Before / After
```text
Before: QA refusal → _finish_run(sanitized) + :845 direct(unsanitized)
        = transcript 2 条相同消息（K.27-RV2 真实用户实证）
After:  QA refusal → _finish_run(sanitized) = transcript 恰 1 条
```

### Tests（test_k27s1_single_write.py·4/4）
```text
T1/T6 拒答恰 1 条 transcript + 恰 1 个 terminal 事件 ✓
T1b grounded QA 同样单写 ✓
T2 边界卫生（毒化 chat_message → 零内部 ID）✓
T4 Planning transcript 不受影响（恰 1 条）✓
（T3=T1b·T5=S1/K22/K24/K25 套件含于全量）
```

### Security
Internal ID/CoT/Reasoning/Tool/Skill/Agent/Raw Event/Exception/
Cross-user = 全 0

### Regression
backend **829 passed + 2 skipped（零失败）**（=K.26 后 825+4 S1）·
web 258+2 · tsc clean

### Live Verification
```text
LIVE_VERIFICATION_PENDING_OWNER_RESTART
（orphan backend :8123 仍运行修复前代码——未自行重启；重启后一次
最小 QA refusal 验证即可确认 transcript 单条）
```

### K.27-S1 Live Verification（2026-09-28·Owner 授权重启后）
```text
Backend startup: 2026-09-27T17:02:19Z · PID 23880
Code revision:   K.26(46dbe0f)+K.27-S1（:845 直接写入已移除——
                 served 代码断言 direct write ABSENT ✓）
Scenario:        「我的百万医疗险和重疾险有什么区别？」（正常
                 Consumer Chat 路径·G-1 形态自然问题）
Intent:          insurance_qa
Terminal status: completed/QA_REFUSED（6s 诚实拒答）
Transcript assistant refusal count: **1**（修复前为 2）✓
Terminal event count: **1** ✓
Internal ID leakage（consumer-visible content）: 0 ✓
  （扫描命中 run_xxx 一次=消息元数据 run_id 字段——前端不渲染·
   content-only 复扫=0）
CoT/Reasoning/Tool/Skill/Agent/Raw Event/Exception/Cross-user: 0 ✓
Result: **K.27-S1 LIVE VERIFIED — PASS**
```
