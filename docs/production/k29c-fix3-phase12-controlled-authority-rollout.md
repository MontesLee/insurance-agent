FINAL STATUS: ROLLED_BACK_TO_BASELINE

# K.29-C FIX-3 Phase 12 · Owner-Controlled Controlled Authority Rollout — 首次受控生产 Authority 运行报告

Date: 2026-10-03 · Mode: **OWNER-APPROVED CONTROLLED AUTHORITY**(首次
真实生产影响·进程内接线·极窄 scope)·终态:**ROLLED_BACK_TO_BASELINE**
(观察窗中途延迟守卫自动 kill——按 Owner 批准阈值正确触发·**全部
安全门零触发**)

---

## 1. Owner Approvals(本会话交互确认·2026-10-03)

- **OD-FIX3-49..56 要点**:批准首次 Controlled Authority 实际运行·
  cohort=**SCRIPTED_PROBE**(Batch-2 未分发·无真实用户·如实标注)
- **OD-FIX3-59..65**:采用 Phase-11 提案值(≥30 eligible·≤20 决策/
  日·≤200 judge/日·p95≤30s·回滚阈值 0;成本=COST_NOT_OBSERVABLE·
  调用数限额代行)
- **接线方式**:进程内 ops 层(零 git 生产变更·重启即完全移除)

## 2. Actual Scope / 3. Window

FACTUAL_PARAPHRASE 唯一(19 条件合取);窗口=本会话受控 cohort
(34 scripted 探针:E×20+H×10+B×4);接线=`launch_8123_authority.py`
以包属性+sys.modules 双替换挂接权威代理(loop 的局部 import 锚点
实测修正一次:gloop.csupp 不够——首验零拦截发现·修复后单探针实证
judge_calls=1)。

## 4-12. 运行数据(34 轮·113 claim 记录)

| 指标 | 值 |
|---|---|
| authority 升级 | **12**(全部真 factual-paraphrase·见 §12 scope audit) |
| baseline keeps | 58 · hard 拦截 3 · citation 段拒 90 |
| judge allow/reject/uncertain | 12/8/0 · post-gate pass/fail 12/0 |
| **false upgrades** | **0** |
| **R3/R4/numeric/product/regulatory/payment/date/contradiction/universal escape** | **全部 0** |
| shadow/preflight leak / fail-open / rollback failure / kill failure / version allow / config fail-open | **全部 0** |
| 决策配额 12/20 · judge 20/200 | 未触顶(kill 冻结) |
| 延迟 p50/p95/max | ~10s/**40.98s**/60+s |

## 13. Kill Events(§十自动 kill 正确触发)

**18:55:45Z 自动 KILL:latency p95 超预算(40.98s > 30s)**。判定链:
coding plan 判定延迟重尾(Phase-9 已知 p95≈29.3/max 60.7)→ 本窗
20 样本 p95=40.98 超阈值 → 监控线程 kill。**这是 Owner 批准阈值
的正确 fail-closed 行为,非安全事件**(升级面全零)。

## 14. Rollback(§二十 live 演练)

kill 后探针=**baseline 拒答**(14.5s·引用门模板);65s 复查:
decisions 冻结 12·enabled=False·**零自动恢复**;kill flag 文件+
incident 记录在案;残留状态=无。**ROLLBACK_VERIFIED**。

## 15-18. Quota / Latency / Version / Traceability

配额守卫全程生效(12/20);六版本进程内钉扎·mismatch_allow=0;
逐 claim ledger(113 条·含 ts/claim/各段结果/版本/决策/kill 态/
counters 快照)——production_final 可反向追溯完整链。

## 19-20. User-visible / Utility

用户面零内部暴露(无 Judge/Candidate-C/Authority 字样);**用户可
见答案变化=0**——12 次升级翻转了门裁决,但 regen 循环消费升级后
未在该 cohort 产出交付答案(细节见 §22 R-3);E 类数据留档为未来
Utility Revision 证据(E 类未入 scope·未放宽)。

## 21. Incidents

1 起(延迟 kill·运营级);安全事件 0。

## 22. Remaining Risks(五类)

- **A Safety blocker:无**(九类逃逸+八类硬门全零)
- **B Operational blocker:判定延迟重尾**(coding plan p95 41s 超
  30s 预算→本窗因此终止;后续选项=预算上调 Owner 裁决/判定槽位
  换档/接受低流量)
- **C Utility debt**:12 次门级升级未转化为交付答案(R-3:升级让
  regen 循环继续而非直接交付——需要 29-D 式交付路径设计·Owner
  议题);E 类仍不在 scope
- **D Evidence limitation**:cohort=scripted 探针·真实用户措辞
  采样仍缺(Mode A 依赖)
- **E Owner decision**:OD-FIX3-57..68(见 v13)

## 23. Owner Decisions OD-FIX3-57..68

见 `k29c-fix3-owner-decision-v13.md`。

## 24. 终态

```
Candidate-C = BOUNDED PRODUCTION AUTHORITY(已运行·后被正确 kill)
仅限 Owner-approved FACTUAL_PARAPHRASE Scope
Full Authority = NOT GRANTED
Batch-2 Mode B = NOT STARTED · Hybrid = OFF · taxonomy = FROZEN · τ = FROZEN
生产代码改动 = 0(进程内接线·重启即移除;当前 authority=KILLED)
```

**观察窗按 Owner 批准参数执行完毕(中途因运营阈值正确终止)。
STOP——等待 Owner Decision。**
