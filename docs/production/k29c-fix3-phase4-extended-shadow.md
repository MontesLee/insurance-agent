# K.29-C FIX-3 Phase 4 · S1' Extended Shadow Observation — 终报

Date: 2026-10-02 · Status: **EXTENDED_SHADOW_PASS(观察完成·零硬停)**
Mode: READ / OBSERVE / MEASURE ONLY（本阶段生产行为变更=0·mtime 证）

---

## 1-3. Window / Traffic / Sample

- 流量:**FIXTURE_TRAFFIC 54 轮**(分层 E1×6/E2×6/E3×6/E4×4/REPEAT×6/
  HIGH×16/R3R4×6/META×4)·REAL_TRAFFIC=0(如实·Batch-2 未分发);
  叠加 Phase-3 受控 25 轮→**累计 79 轮**。
- 影子累计:**337 claim 记录·170 判定·9 硬类前置拦截·0 影子错误**
  ·判定调用累计 157·预算内(qa 槽·≤20/轮·τ=0.7·S0 同配未动)。
- 交付面:hedge 率 92.6%(5 轮交付全部为安全形态)——B/D+S1' 定位不变。

## 4-11. 分类指标

**判定分布**:ALLOW 74 / KEEP 262 / UNCERTAIN 1(0.3%)。
**确定性基线**:SUPPORTED 136/PARTIAL 112/UNSUPPORTED 65/EXEMPT 24。

### E 类分析(Phase 3 问:「ALLOW 是否稳定重复出现?」——**是**)

| 子类 | 判定数 | ALLOW | ALLOW% |
|---|---:|---:|---:|
| E1 给付型 | 69 | 20(+1 UNCERTAIN) | 29.0% |
| E2 自由支配 | 30 | 5 | 16.7% |
| E3 报销型 | 37 | 17 | **45.9%** |
| E4 其他 | 201 | 32 | 15.9% |

E 类 ALLOW 在扩展窗中**稳定重复**(Phase-3 8 例→累计 74;E1/E3 信号
最强)——与词法天花板假拒的离线画像一致。不作为 authority 论据(如
任务书)。

### 高危安全(OD-FIX3-6 八项·全部 0)

numeric/product/regulatory/payment/date/contradiction/R3/R4 escape=
**0**。注(Phase 7 充分性如实):管线级高危零逃逸=**硬类前置的结构
保证**(高危形态 claim 不达判定——设计非抽样);判定单独高危行为=
仅 S0 离线 82 例证据(1 FU·恰被设计拦截)——**判定单独面
INSUFFICIENT_EVIDENCE**(不得把结构零写成抽样零)。

### ALLOW 二审(Phase 6)

74 ALLOW:**SAFE 73·FALSE 0·REVIEW 1(已人工裁 SAFE)**——ACR-023
「重疾险不属于按比例报销的方式」=否定方向与证据一致的**否定形真
paraphrase**(证据本身即该对比句·人工对照 KB 复核);二层 negation
正则无法区分方向=确定性层固有限制(→OD-FIX3-11 素材)。高危 ALLOW=
仅此 1 例 negation 形(数字/产品/监管/赔付/日期 ALLOW=0)。

### evidence-meta 专项(Phase 4 watch)

meta 形 claim 36·ALLOW 12·**全部 NON_BUSINESS_META**(证据叙述/来源
陈述·零风险升级路径:无一带数字/产品/监管/赔付/日期)→
**WATCH_ONLY**(未修规则/未改判定——如令)。风险推演:若未来 meta
prose 携带高危词,硬类前置仍先拦(词形命中即前置)——升级路径闭合。

### 稳定性(Phase 5)

重复 claim 簇 43·**一致率 95.3%**(漂移例=KEEP↔UNCERTAIN 边界);
分层:低危稳定性=95.3%;**高危层无判定样本(前置拦截)——
「高危稳定性」不可报(样本=0·如实)**。

### 运营(Phase 9)

判定延迟 p50 **12.5s**/p95 29.3s/max 60.7s(旁路·门路径零增:灰度
运行全程生产延迟形态与无影子栈一致);malformed/timeout/model error
=0;成本 **COST_NOT_OBSERVABLE**(coding plan 无按调用遥测·调用数
157 实测)。

## 12. Batch-2 Gate Review(Phase 8)

**BATCH2_READY_FOR_OWNER_REVIEW**(证据成熟度:79 轮零不安全交付·
B/D 灰度稳定·回滚 A/B 实证·拒答=安全正确[K.28-Final 先例];窗口
起算/分发=Owner)。**未启动。**

## 13. Authority Readiness(Phase 9)

**EVIDENCE_SUFFICIENT_FOR_OWNER_REVIEW**(≠GRANTED):零硬停·E 类
稳定信号·稳定性 95.3%·SAFE 73/74;限制清单=fixture-only 无真实用户
措辞·单模型·τ 未压测·判定单独高危面仅 S0 证据·negation 方向判定
属语义层。Observation→Owner Review→Authority Decision 三段严格区分。

## 14. Rollback(Phase 10)

B/D OFF→C1(Phase-3 live A/B 逐字一致+单测);Shadow OFF/judge 不可用
→生产答案不变(结构性:loop 不 import judge·observer 异步+吞噬·单测
+live);零新依赖(本阶段零代码改动)。

## 15. Remaining Risks

真实用户措辞分布未知(fixture 覆盖)·UNCERTAIN 率 0.3% 未压测(τ
敏感度)·meta-prose ALLOW 12 例的消费者面语义(若未来 authority)
需 UX 裁决·coding plan 端点生产配额面持续观察。

## 16. 工件

tmp/obs/k29c_fix3_phase4_{traffic_ledger,analysis}.json·
k29c_fix3_phase3_shadow.jsonl(累计)·shadow_stats.json·
checkpoints/k29c-fix3-phase3-checkpoint.md(Phase4 节)。
