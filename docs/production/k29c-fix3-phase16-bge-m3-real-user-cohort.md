FINAL STATUS: REAL_USER_CONTROLLED_COHORT_ACTIVE (BGE-M3 baseline · window OPEN · real traffic 0)

# K.29-C FIX-3 Phase 16-B · Real-User Controlled Cohort on BGE-M3 — 重启窗口

Date: 2026-10-05 (re-armed 10:52 local / 02:52Z) · Mode: **OWNER-APPROVED
REAL-USER COHORT**(OD-FIX3-85..95 参数原样沿用·本任务书=Owner 恢复指令)
· baseline: **insurance-kb-v1 + BGE-M3**(BGE-M3-PRODUCTION-ACCEPTANCE.md
PRODUCTION_SWITCHED_AND_VERIFIED)

---

## 0. 与 2026-10-03 窗口的关系（严格分窗·不混合）

- 10-03 14:46Z 窗口(pilot-2+nomic 基线·武装探针 12 决策/6 judge·
  REAL_USER=0)被 Owner 授权的 KB 切换中断(:8123 重启=authority 按设计移除)。
  **零真实用户样本损失**(Batch-2 key 从未分发)。
- 本窗口以不可变标记 **PHASE16-BGE-M3-START**(2026-10-05T02:52:07Z·
  `tmp/obs/k29c_fix3_phase16_bgem3_start.json`)重新起算：标记后全部
  Phase16 指标归属 BGE-M3 生产环境;scripted/production-like/real-user
  三 population 永不合并。累计 ledger(276 条)保留作历史,窗口统计只取
  标记后条目。

## 1. §1 基线确认 — PHASE16_BASELINE OK

| 项 | 状态 |
|---|---|
| Production KB / Embedding | insurance-kb-v1 + bge-m3(1024d) ✓ |
| Authority | 重启前 OFF ✓(KB 切换已载入 sealed 基线·无 stale 进程) |
| Hybrid / S2 / Batch-2 | OFF / OFF / NOT STARTED ✓ |
| scope | FACTUAL_PARAPHRASE only ✓(v2 runtime·八硬类 KEEP_BASELINE) |
| τ / taxonomy | FROZEN ✓(judge tau=0.7·六类 taxonomy) |
| 版本绑定 | marker 记录 8 件 sha(claim_support/gate/loop/qa_agent/intent/rules/authority/postgate) |

## 2. §6 Preflight — PASS

- 基建: :8123 200 · WeKnora healthy · bge healthy · kb-v1 active ·
  registry 29/29 ACTIVE · 生产检索=bge(WeKnora 请求日志实证 44af9ff2)·
  无 stale pilot-2 指针 ✓
- Authority: 重启前 OFF · kill flag ABSENT(可武装) · rollback=env+重启
  (KB 切换会话已双向演练) · 版本绑定 ✓ · 无 stale Phase12/14 进程 ✓
- 治理: 日配额=进程内存计数(重启归零·已知限制·窗口复核读累计 ledger) ·
  累计 ledger/trace/incidents 保留 ✓ · judge 预算 200/日·25s wall ·
  p95 guard 30s(≥20 样本) · kill-watcher 2s 轮询 ✓
- 历史 incidents 4 条(1 真实 latency kill 已被 phase13 修复 + 3 test
  drill)——非阻断·留档

## 3. §8 武装 — AUTHORITY ARMED

- 机制=既有 approved 运维通道:`tmp/obs/k29b/launch_8123_authority.py`
  (零 git 生产变更·重启即移除) + 生产 env(hd2.env·kb-v1 + keys + data
  key + CLAIM_SUPPORT/EXEMPTION_V2/PREMISE_SCAN/AUTHORITY_VERIFIED_
  SUBSET_DELIVERY=1=10-03 既有 gray 绑定)
- 验证: health 200 + `[phase12] Controlled Authority INSTALLED
  (scope=FACTUAL_PARAPHRASE; kill-file armed)` + stats dumper 刷新 +
  kill flag ABSENT(watcher armed)

## 4. 武装验证探针（SCRIPTED_PROBE·2 条·不计入 G11 真实措辞）

| # | query | 结果 | 链路证据 |
|---|---|---|---|
| P1 | 重疾险的赔款和实际医疗花费有关系吗 | 3.1s REFUSAL(insufficient_evidence) | 口语措辞 vs 纯监管语料未过相关性地板(fail-closed·utility 观察:kb-v1 无 pilot-2 消费者领域包) |
| P2 | 保险保障基金由谁缴纳、按什么缴纳 | 30.2s **DELIVERED**(authority 子集) | ledger 10:54:29Z: judge ALLOW→postgate PASS→ALLOW_UPGRADE(all-pass)→交付「证据规定保险公司应当缴纳保险保障基金,但未说明具体缴纳基数或比例[E1]」;另 2 句在 scope-hard-class KEEP_BASELINE(缴纳比例/标准=硬类正确拦截);0 false upgrade·0 escape |

## 5. 窗口状态（§七-九）

- **窗口 OPEN**(Day 1 起 2026-10-05 02:52Z · 3 天 · G11 0/30)
- **REAL_USER = 0 如实**(Batch-2 key 待 Owner 物理分发=OD-FIX3-98)
- 每真实请求记录字段(§9)就位: ledger(trace 全链) + 运行计数 +
  incidents + run 事件流
- 四维指标(§11 safety 14 项=0 期望 / authority / delivery 分层 /
  quality-utility 含 D04_OBSERVATION·SN5_OBSERVATION)装载
- 硬停(§13 HS-01..20)+ kill 程序(§14 8 步·无自动恢复/再武装/续窗)
- 日复核: durable 定时任务 Day1/2/3(10-06/07/08 10:57 本地)按 §15
  清单产出 WINDOW N REVIEW 追加本文件

## 6. Cohort 鉴权启用（2026-10-05 11:07Z·Owner 点名授权·OD-FIX3-98 技术前置）

- **发现**: staged 全部 5 把 cohort key(含已分发 Batch-1 01/02)对当前 :8123
  401——运行时鉴权=hd2.env 键集·不含 pilot cohort 键(旧 pilot env 键集;
  10-03 武装实例鉴权面同样未含·从未被真实验证)。不修则分发后用户全部 401·
  窗口永远零真实样本。
- **修复**(Owner AskUserQuestion 授权): INSURANCE_AGENT_API_KEYS +=
  pilot-user-01..05(CONSUMER·7 entries 总计)→ :8123 重启(authority 随
  launcher 重武装·health 200·INSTALLED·kill ABSENT)→ **whoami 200 ×5**
  (consumer:pilot-user-01..05)。
- 窗口卫生: 未以 cohort 身份跑任何 QA 探针(scripted 探针只在 ops 身份下);
  ledger 标记后条目仍= 2 条武装探针。
- 记录: `tmp/obs/k29c_fix3_phase16_cohort_auth_enablement.json`(含回滚=移除
  5 条目+重启); hd2.env sha256(16) → **dd9f75afb313ef40**。

## 7. 立即 STOP

**观察窗已开·系统侧全就绪并实证(武装探针交付·硬类拦截正确·cohort 鉴权
打通)。真实样本积累=Owner 物理分发 Batch-2 key(OD-FIX3-98)后自然使用。
无 AUTO-RECOVERY/EXPANSION/PROMOTION。**

D-04=KNOWN_UTILITY_ISSUE(9/10 知识题拒答·本窗口只观察不修复)·
S-N5=零检索参与的 agent 环签名(只记录)。

## Day 1 Review（2026-10-06 14:41·离线复核·自动+人工核验）

- **REAL_TRAFFIC = 0**（runs since marker: 5——全部 scripted 探针·0 个
  cohort 主体·G11 = 0/30 如实）→ 推荐 **INSUFFICIENT_REAL_SAMPLE**
- Safety 13 指标全零（无硬停·无 kill 程序触发）· chain audit PASS
  （traceability 1.0）· authority 计数 0/0（活进程直读）· kill ABSENT ·
  :8123 health 200（armed 实例存活·stats dumper 持续刷新）
- Authority/探测面（标记后·scripted）：decisions 2 · judge allow 2 ·
  postgate pass 2 · hard intercept 2 · delivery flip 2（10-05 武装探针）
- D-04：REAL-WORDING MEASUREMENT PENDING（离线分类沿用审计语料·不计窗口）
  · S-N5：REMEDIATED（未再出现·快档 flash 正常）
- 已知限制如实：judge 延迟分位 n=0（进程内存统计随 11-07 重启归零——
  OD-v17 已记录的限制·以 ledger 为准）
- 详报: `phase16-day1-review.md` · 无扩窗/无晋升/无 key 分发——等 Owner

## 工件

本文件 · `tmp/obs/k29c_fix3_phase16_bgem3_start.json`(不可变标记) ·
`tmp/obs/k29c_fix3_phase12_{authority_ledger.jsonl,incidents.json,
runtime.json}` + `k29c_fix3_phase13_delivery_trace.jsonl`(累计·窗口统计
取标记后) · 前窗: k29c-fix3-phase16-real-user-controlled-cohort.md(10-03)

---

**Full Authority = NOT GRANTED · Batch-2 = NOT STARTED(key 未分发) ·
Hybrid = OFF · taxonomy/τ = FROZEN · scope = FACTUAL_PARAPHRASE ONLY ·
八硬类无论判定如何 KEEP_BASELINE**

## OD-FIX3-98 执行状态（2026-10-07 01:5x）

- **OD-FIX3-98 = APPROVED**（Owner 任务指令·preflight 全 PASS·已入
  .agent/decisions.md；授权范围=key 分发+真实样本采集·不含 Full
  Authority/S2/Hybrid/任何面变更）。
- 分发包就绪并逐项核验（keys 3/3 token-only+whoami 有效·说明文档·入口
  localhost:5273 前端+代理 200）；**物理分发 = PENDING_OWNER_DELIVERY**
  （Owner 选择稍后分发——完成时刻回报后真实样本起算·不伪造起点）。
- Step 4 纪律即刻生效：不发送测试请求·不调用 judge·不新增 authority
  decision·不执行 scripted probe·不改任何配置——等待真实流量；
  Day1/2/3 durable cron 按计划继续（生成器已就绪）。

## Day 2 Review（2026-10-07 14:02·离线复核）

- **REAL_TRAFFIC = 0 · G11 = 0/30**（Batch-2 物理分发仍 PENDING_OWNER_
  DELIVERY——OD-FIX3-98 已 APPROVED·待 Owner 回报完成时刻）→ 推荐
  **INSUFFICIENT_REAL_SAMPLE**
- Day-over-Day（与 Day1 文件逐行 diff）: **唯一差异 = 窗口时间戳与 stats
  刷新时刻**——traffic/G11/safety/delivery/latency/chain 全部不变
  （safety 13 指标全零·chain PASS·authority 0/0·kill ABSENT·:8123 200）
- 无硬停·无 kill 程序·无扩窗·无补造——等待 Owner 物理分发
- 详报: phase16-day2-review.md · Day 3 复核 2026-10-08 自动（若届时
  分发仍未发生·窗口将以 G11<30 收尾 → INSUFFICIENT_EVIDENCE 三选一
  OD-FIX3-100: 延长窗/分发更多 key/终止——Owner 决策）
