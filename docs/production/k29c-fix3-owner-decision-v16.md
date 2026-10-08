# K.29-C FIX-3 · Owner Decision Package v16

Date: 2026-10-03 · 输入:Phase 15 扩张评审(READ-ONLY·零生产变更·
零新 LLM)。详报:k29c-fix3-phase15-authority-expansion-review.md;
证据:tmp/obs/k29c_fix3_phase15_*(8 件)。**只提交证据·不代决策。**

---

## 证据核心

- **两未交付案逐条解释(零 UNKNOWN)**:全部=判定层逐句审查后
  拒绝(fail-closed 按设计);交付 3/5=60% 且全部证据改写。
- **四维并列**:SAFETY 全零·QUALITY(交付句全引用)·UTILITY
  (3 交付正价值)·OPERATIONS(p95 20.81≤30·kill/rollback 实证)。
- **69 行 patch 静态审计 10/10**(零隐式 authority 路径)。
- **真实措辞样本 75**(62.6% 候选/37.4% 硬类·粗代理·未送判定)。
- Cohort 设计就绪(最小 3-5 用户·12 条件准入·无自动扩大)。
- **两项参数属 Owner 范畴**:G9 成本预算数值·G11 真实措辞最低
  样本量——证据面本身无缺口。

## Owner Decisions

**OD-FIX3-85 Phase 15 Review 是否通过?**
证据:READY(12 门中 10 PASS+2 OWNER_DECISION_REQUIRED——后者
为参数决策非证据缺口)。

**OD-FIX3-86 Authority-to-Delivery 数据是否满足进入真实用户
cohort 的证据要求?**
证据:3/5 交付·零 UNKNOWN·安全全零·四维达标。是否认可=Owner。

**OD-FIX3-87 cohort size** — 建议 3-5(Batch-2 key 持有者)。
**OD-FIX3-88 traffic percentage** — 建议 100% cohort QA 轮
(cohort=流量单位)。
**OD-FIX3-89 daily authority decision limit** — 建议 20。
**OD-FIX3-90 daily Judge call limit** — 建议 200。
**OD-FIX3-91 cost budget** — 需数值(COST_NOT_OBSERVABLE;建议以
judge 调用上限代行或给出月度金额)。
**OD-FIX3-92 observation duration** — 建议 3 天。
**OD-FIX3-93 kill threshold** — 建议维持 OD-FIX3-6 族>0 即 kill+
p95>30s 持续。
**OD-FIX3-94 rollback threshold** — 建议单高危逃逸即 OFF。
**OD-FIX3-95 是否允许 Controlled Authority Real-User Cohort?**
——本包不预定答案;若准,按 §九 cohort 设计执行(另需重启
:8123 移除 kill+watcher 在位)。

**OD-FIX3-96 Full Authority = NOT GRANTED** ✓
**OD-FIX3-97 Batch-2 Mode B = NOT STARTED** ✓

## 附加产品观察(非安全·供知悉)

R4 问句的用户可见行为在子集交付下从「拒答」变为「纯已验证事实
子集」(个性化成分被剥离·claim 级零逃逸)——产品政策层面
Owner 可选择 R4 问句路由到 planning(OD-H3 既有议程)或接受
该形态。

## 强制终态

Production Authority=OFF(kill 保持)·Full Authority=NOT
GRANTED·Batch-2 Mode B=NOT STARTED·Hybrid=OFF·taxonomy=
FROZEN·τ=FROZEN·生产代码改动=**0**。
