# K.29-C FIX-3 · Owner Decision Package v17

Date: 2026-10-03 · 输入:Phase 16 真实用户 cohort 启动(Owner 本
会话批准 OD-FIX3-85..95·preflight PASS·窗口 ARMED·武装探针实证
交付)。详报:k29c-fix3-phase16-real-user-controlled-cohort.md;
证据:tmp/obs/k29c_fix3_phase16_*(9 件)。**只提交证据·不代决策。**

---

## 已生效的 Owner 决策(本会话批准)

OD-FIX3-85..95=APPROVED·参数:cohort=当前持 key 用户·100% cohort
QA 轮·20 决策/日·200 judge/日·G9=调用数代理(200/日·600/窗)·
G11=30 条·3 天窗·p95≤30s·硬停族 kill·单高危逃逸 rollback。

## 当前状态

- **REAL_USER_CONTROLLED_COHORT_ACTIVE**:authority ARMED on :8123
  (v2+子集钩子+kill-watcher);武装探针(SCRIPTED_PROBE·1/20)实证
  交付首条 authority 答案(12 句 eligible·12 升级·0 硬拦截·
  0 错误·60.6s)。
- **REAL_USER 流量=0**(如实):Batch-2 key staged 未分发——样本
  积累依赖 Owner 物理分发 key 后的自然使用。

## 后续 Owner Decisions(窗口治理)

**OD-FIX3-98 key 分发执行**
(真实流量前提:Owner 物理分发 Batch-2 key(03/04/05)给 3-5 名
真实用户——cohort 的实际构成由此确定)。

**OD-FIX3-99 窗口复核节奏**
(建议每日;每次产出 WINDOW N REVIEW(§二十一模板)——继续/停止/
回滚/修改 cohort 均需新 Decision)。

**OD-FIX3-100 G11 不满足时的处置**
(3 天窗到期但 eligible 真实措辞<30 → INSUFFICIENT_EVIDENCE:
延长窗/分发更多 key/终止——Owner 选择;不补造数据)。

## 观察项(仅记录·不修改)

- R4 问句在子集交付下的纯事实回答形态(产品政策·Phase-15 发现)。
- 真实用户措辞延迟尾部(§十三)。
- 进程重启对日配额计数的影响(已知限制·窗口复核以累计 ledger
  为准)。

## 强制终态

Full Authority=NOT GRANTED·Batch-2 Mode B=NOT STARTED·Hybrid=
OFF·taxonomy=FROZEN·τ=FROZEN·scope=FACTUAL_PARAPHRASE ONLY·
八硬类无论判定如何 KEEP_BASELINE·**NO AUTO-RECOVERY/
EXPANSION/PROMOTION**。
