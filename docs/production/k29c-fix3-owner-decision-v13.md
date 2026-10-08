# K.29-C FIX-3 · Owner Decision Package v13

Date: 2026-10-03 · 输入:Phase 12 首次 Controlled Authority 运行
(Owner 本会话批准·34 scripted 探针·12 bounded 升级·延迟守卫 kill·
全安全门零)。详报:k29c-fix3-phase12-controlled-authority-rollout.md;
证据:tmp/obs/k29c_fix3_phase12_*(10 件)。**只提交证据·不代决策。**

---

## 运行摘要

- **首次真实生产 Authority 已运行并正确终止**:12 次升级全部为真
  factual-paraphrase(scope audit 逐条复验);九类逃逸+八类硬门
  **全部零**;kill-switch/回滚/配额/版本/隔离全实证。
- **终止原因=运营阈值**(判定延迟 p95 40.98s>30s Owner 预算→自动
  kill·fail-closed 正确);安全事件 0。
- **用户可见答案变化=0**(12 次门级升级未转化为交付答案——交付
  路径设计议题·见 OD-63)。

## Owner Decisions

**OD-FIX3-57 Controlled Authority 实际开启时间确认**
事实:2026-10-03 18:14-18:55Z(本会话 Owner 批准后·34 探针窗)。

**OD-FIX3-58 Scope=FACTUAL_PARAPHRASE only 确认**
事实:12/12 升级逐条复验为真 paraphrase;3 硬类拦截;4/4 阻断探针
保持 baseline;零 scope 违规。

**OD-FIX3-59 窗口时长确认**
事实:本窗≈40 分钟(34 探针)——中途因 OD-64 阈值终止;原提案为
会话受控窗。是否认可该窗为「已完成观察窗」由 Owner 裁定。

**OD-FIX3-60 Minimum eligible claims 确认**
事实:113 eligible claim 记录(≥30 达标)。

**OD-FIX3-61 Max authority decisions/day 确认**
事实:12/20(未触顶·kill 冻结)。

**OD-FIX3-62 Max judge calls/day 确认**
事实:20/200(未触顶)。

**OD-FIX3-63 Cost budget 确认**
事实:COST_NOT_OBSERVABLE(coding plan);调用数代行=20/200。

**OD-FIX3-64 Latency threshold 确认**
事实:30s 预算·实测 p95 40.98s→自动 kill。选项:维持 30s(后续窗
同样会终止)/上调(建议 ≤60s·依据 Phase-9 max 60.7s)/判定槽位
换档(main 模型延迟未测)。

**OD-FIX3-65 自动 Kill 条件确认**
事实:延迟 kill 正确触发;全部 16 类安全 kill 条件零触发。

**OD-FIX3-66 Rollback protocol 确认**
事实:live 演练(kill 后 baseline 拒答·65s 零自动恢复·状态冻结·
零残留)。

**OD-FIX3-67 窗口完成后下一步:CONTINUE / ROLLBACK / TERMINATE**
现状=已回滚(kill 保持);证据支持三者皆可行——安全面全零(CONTINUE
的依据);延迟重尾(需先裁 OD-64);utility 转化未证(交付路径
设计)。**三项证据并列提交·不代选。**

**OD-FIX3-68 Full Authority = NOT GRANTED 确认**
事实:维持——本阶段从未申请。

## 附加发现(供 Owner 议程·非本包决策)

- **交付路径缺口**:权威升级翻转门裁决后,regen 循环消费了升级
  但未产出交付答案(用户可见变化=0)——「升级→交付」的完整路径
  需 29-D 式设计(升级应跳过重生成直接交付已验证答案)。这解释了
  utility=0,不影响安全结论。
- 首验接线锚点(gloop.csupp 属性替换对局部 import 无效)已修正为
  包属性+sys.modules 双替换——教训入档。

## 强制终态

Candidate-C=BOUNDED PRODUCTION AUTHORITY(已运行·KILLED·保持
OFF)·Full Authority=NOT GRANTED·Batch-2 Mode B=NOT STARTED·
Hybrid=OFF·taxonomy=FROZEN·τ=FROZEN·生产代码改动=**0**。
