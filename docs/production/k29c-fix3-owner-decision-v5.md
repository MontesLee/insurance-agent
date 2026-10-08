# K.29-C FIX-3 · Owner Decision Package v5

Date: 2026-10-02 · 输入:Phase 4 扩展影子观察(READ/OBSERVE ONLY·
零生产改动)·证据 tmp/obs/k29c_fix3_phase4_*.json + 累计影子 jsonl。
详报:k29c-fix3-phase4-extended-shadow.md。**只提交证据·不代决策。**

---

## 证据摘要(累计 79 轮·337 claim 记录·170 判定)

| 维度 | 数据 |
|---|---|
| HARD STOP(OD-FIX3-6 八项) | **全部 0**(未触发) |
| ALLOW 二审 | SAFE 73 / FALSE 0 / REVIEW 1→人工裁 SAFE(否定形真 paraphrase) |
| E 类稳定重复 | E1 29%/E3 46%/E2 17%/E4 16%(Phase-3 信号在扩展窗复现) |
| 高危面 | 管线级=结构零(硬类前置);判定单独=S0 仅 82 例(INSUFFICIENT) |
| evidence-meta | 12/36 ALLOW·全 NON_BUSINESS_META·零升级路径→WATCH_ONLY |
| 稳定性 | 95.3%(43 重复簇);高危层无判定样本(前置)·不可报 |
| 运营 | p50 12.5s/p95 29.3s(旁路零门开销)·错误 0·COST_NOT_OBSERVABLE |
| 生产 | 交付面仍全拒(定位不变)·零不安全交付·回滚 A/B 实证 |

## Owner Decisions

**OD-FIX3-7 是否继续保持 B/D gray?**
证据:灰度 LIVE 稳定·79 轮零不安全交付·旗关回 C1 逐字实证·收益
边际(交付不变·F-1 纵深关闭)。维持=零成本;回退=env 置 0 即时。

**OD-FIX3-8 是否继续扩大 S1' Shadow?**
证据:零硬停·稳定性 95.3%·但样本全 FIXTURE(无真实措辞)·UNCERTAIN
0.3% 未压测·τ 敏感度未测。扩大选项:真实窗口(需 Batch-2)/更大
fixture/τ 扫描(离线)。

**OD-FIX3-9 是否允许 Batch-2 进入受控观察?**
评估:**BATCH2_READY_FOR_OWNER_REVIEW**(拒答=安全正确先例+灰度栈
稳定+影子就绪可采集真实流量)。启动=Owner 定窗口与分发。

**OD-FIX3-10 是否启动 Semantic Judge Authority 独立评审流程?**
评估:EVIDENCE_SUFFICIENT_FOR_OWNER_REVIEW(≠GRANTED)。限制:fixture-
only·单模型·判定单独高危面=S0 证据·否定方向=语义层。评审若开:
OD-12 式门槛冻结+真实窗口数据建议为前置。

**OD-FIX3-11 evidence-meta prose 是否进入新 hard-safety taxonomy?**
证据:12 ALLOW 全 NON_BUSINESS_META·零升级路径(高危词形仍被硬类
前置拦截);但 meta-ALLOW 在未来 authority 下有消费者语义面。选项:
维持 WATCH / 入 taxonomy(需 corpus-revision)。

**OD-FIX3-12 是否继续保持 D-08 authority seal?**
现状:seal 保持·FIX-3 span(Phase1+2+3+4 工件)未续封。续封=独立
Owner 动作(建议与上述决策同批)。

## 状态

B/D gray=保持 LIVE(按本阶段决策书)·Shadow=LIVE(SHADOW ONLY)·
Authority=NOT GRANTED·Hybrid=OFF·S2=UNCHANGED·Batch-2=NOT
DISTRIBUTED·本阶段生产行为变更=**0**(mtime 证)。
