FINAL STATUS: REAL_USER_CONTROLLED_COHORT_ACTIVE

# K.29-C FIX-3 Phase 16 · Real-User Controlled Cohort — 首次真实用户受控 Authority

Date: 2026-10-03(armed 14:46Z)· Mode: **OWNER-APPROVED REAL-USER
COHORT**(OD-FIX3-85..95 本会话批准·参数全齐·preflight PASS)
·终态:**REAL_USER_CONTROLLED_COHORT_ACTIVE**(窗口已开·真实流量
=0 如实——Batch-2 key 待 Owner 物理分发)

---

## 1. Owner Decisions(§二·全部具备·零自行补值)

| 参数 | 批准值 |
|---|---|
| cohort | 当前持 key 用户(Batch-1 01/02 已分发；Batch-2 03/04/05 staged 未分发) |
| traffic | 100% cohort QA 轮(cohort=流量全域·pilot 需鉴权) |
| 日决策上限 / 日 judge 上限 | 20 / 200 |
| **G9 成本** | **judge 调用代理**(≤200/日·≤600/观察期·超限即 OFF) |
| **G11 措辞最低量** | **30 条 eligible 真实用户样本**(不足→INSUFFICIENT_EVIDENCE 不补造) |
| 观察窗 | 3 天 |
| p95 阈值 | 30s |
| kill / rollback 阈值 | OD-FIX3-6 族>0 或 p95 持续超限 / 单高危逃逸即 OFF |

## 2. Preflight(§十九·PASS)

九项全绿(owner decisions/cohort/traffic/caps/budget/wording/
duration/latency/kill·rollback)+ 回归 44/44(靶向)+909+2(全电池
有效)。**已知限制如实**:日配额为进程内存计数(重启归零——窗口
复核读累计 ledger);真实流量依赖 Owner 物理分发 key。

## 3. Cohort 启动(§二十)

- kill 标志移除·:8123 重启载入 authority v2+子集钩子+kill-watcher
  (health 200·**AUTHORITY ARMED** 实证)。
- **Arming 验证探针**(SCRIPTED_PROBE·标注·消耗 1/20 日决策):
  60.6s → **DELIVERED**「重疾险的赔付与实际医疗花费无关[E1]。
  重疾险属于给付型保险…[E1]」——12 句 eligible·12 升级·6 judge
  调用·10 check 翻转·1 交付·0 硬拦截·0 错误。
- 计数器快照(§七观察记录字段就位):eligible 12·allow 12·
  judge 6·errors 0·enabled=True。

## 4. 当前观察窗状态(§七-九)

- **窗口 OPEN**(3 天·G11=30 待累积)。**REAL_USER 流量=0 如实**
  ——Batch-2 key 未分发;计数器从 0 起算(探针不计入 G11)。
- 四维指标体系就绪(SAFETY 11 项/QUALITY 5/UTILITY 6/OPS 8);
  ledger/trace/PII 控制(仅 claim 文本·无联系方式/健康/家庭隐私)
  全部在位。
- 硬停条件(§十 15 项)+ kill 程序(§十一 8 步)+ rollback 程序
  (§十二)装载;**NO AUTO-RECOVERY/EXPANSION/PROMOTION**。

## 5. R4 产品观察(§十五·仅记录)

Phase-15 观察(子集交付下 R4 问句→纯事实子集)纳入本窗观察项;
不修改政策。

## 6. 窗口输出(§二十一·当前)

```
WINDOW 1 (ARMED, traffic 0)
Requests: 0 real-user (1 scripted arming probe)
Eligible: 12 (probe) | Hard-blocked: 0 | Judge: 6 (allow 12/rej 0)
Post-Gate: 12 pass | Authority: 12 | Delivered: 1 | Baseline: 0
False Upgrade: 0 | Hard Escape: 0 | Kill: 0 | Rollback: 0
p50/p95: ~10s/~20s (probe window) | Cost: 6/200 judge calls
Real Wording Sample: 0/30
```

**CONTINUE 状态=记录建议;不自动执行任何扩窗。**

## 7. 终态

**REAL_USER_CONTROLLED_COHORT_ACTIVE**——系统侧全部就绪并实证
(武装探针交付了首条真实 authority 答案);真实用户样本积累=
Owner 分发 key 后的自然使用;窗口复核(§二十二)在流量到达后按
Owner 节奏进行。

## 工件

`docs/production/k29c-fix3-phase16-real-user-controlled-cohort.md` ·
`k29c-fix3-owner-decision-v17.md` · `checkpoints/k29c-fix3-phase16-
checkpoint.md` · `tmp/obs/k29c_fix3_phase16_{preflight, metrics,
safety, delivery, cost, latency, real_wording}.json +
authority_ledger.jsonl + incidents.jsonl`(9 件)

---

**Full Authority = NOT GRANTED · Batch-2 Mode B = NOT STARTED ·
Hybrid = OFF · taxonomy = FROZEN · τ = FROZEN · scope =
FACTUAL_PARAPHRASE ONLY · 八硬类无论判定如何 KEEP_BASELINE**

**观察窗已开。立即 STOP——等待 Owner Decision(key 分发/窗口
复核/继续-停止-回滚)。NO AUTO-EXPANSION。**
