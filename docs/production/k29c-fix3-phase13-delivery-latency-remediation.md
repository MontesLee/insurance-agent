FINAL STATUS: DELIVERY_NOT_READY

# K.29-C FIX-3 Phase 13 · Delivery Path + Latency Remediation

Date: 2026-10-03 · Mode: **REMEDIATION**(修复+受控验证;零生产代码
改动;authority 探针后已重新 kill·OFF)

---

## 1. §四 Delivery Trace(Phase-12 真实链路·零猜测)

Phase-12 ledger 113 条逐段解剖 + 本阶段 live 复验,根因**三层**:

| # | 根因 | 证据 |
|---|---|---|
| **D1 粒度错配** | 生产引用门在**句子**级执法;v1 authority 要求**子句**级 [E#]——句子有引用而子句碎片无 → 90/113 wrongly ineligible | ledger keep 段=citation×90(全部为句子内有引用的子句碎片) |
| **D2 混合调用搁浅** | 答案翻转需一次 check 调用内**全部**失败子句升级;混合(部分 allow 部分 reject)→升级搁浅答案仍拒 | judge_allow=12 vs judge_reject=8 同窗 |
| **D3 整答引用残缺** | 整答交付还需**每个句子**过引用门;模型残句无引用(D-04 既有限制)→整答级 ggate 失败→csupp(及 authority)根本不被调用 | Phase-13 复验:20 次 check 级翻转全部为**段级**(15-60 字);整答级最终门翻转=0;12/12 探针整答被拒均因其它未引用句 |

## 2. 修复(v2·ops 层·零安全削弱)

- **句子单元对齐**:authority 以句子为单元(与生产引用门同粒度)——
  句子携 [E#] 即满足引用条件(与 ggate 完全一致·非放宽);句内全部
  子句 PARTIAL-or-SUPPORTED 才可升级(UNSUPPORTED/CONTRADICTED 句
  不可)。
- **判定 memo**(同文复用·5 hits/31 calls)+ **25s 墙钟**(长尾坍缩
  KEEP·fail-closed)。
- **production_final_source 逐 check 记录**(BASELINE×68/
  AUTHORITY_REGEN_RESULT×20·无 UNKNOWN/直写)。

## 3. §七 Negative Controls:A-H **8/8 PASS**

合法 paraphrase→UPGRADE ✓;numeric/product/R4→hard 拦截 ✓;post-gate/
硬尾→拒 ✓;judge timeout→KEEP ✓;ALLOW-but-blocked→拒 ✓;kill/
unavailable→baseline ✓;交付 replay 翻转 1/1 ✓;混合案例正确不翻转 ✓。
**安全门未变装饰。**

## 4. §八-十 Latency:根因+修复+达标

根因=judge 单次长尾(coding plan 40s+)+段/最终门重复调用。
修复=墙钟 25s+memo。**Re-entry 实测:n=31·p50 10.8s·p90 18s·
p95 22.82s·p99/max 24.99s(max=墙钟悬崖实证)·timeout 0·kill 未
触发——p95≤30s WITHIN_THRESHOLD**(Phase-12 p95 40.98→22.82)。

## 5. §十一-十六 Delivery 转换:check 级闭合/答案级开放(如实)

| 层级 | 转换 | 结论 |
|---|---|---|
| check 级 | **20/20=100%**(每次升级都翻转其 csupp.check 裁决;source=AUTHORITY_REGEN_RESULT 逐条可溯) | **闭合** |
| 答案级 | **0/20**(12/12 探针整答仍拒) | **开放——D3** |

未交付原因=**确定性**(逐条可溯):整答级引用门因模型残句失败;
authority 按契约不可升级未引用句(引用有效=前置条件)。
**无「升级成功但返回 baseline 无解释」情形。**

## 6. 剩余缺口=SEALED_COMPONENT_CHANGE_REQUIRED(§十八)

**verified-subset 答案组装**(K.29 设计 §8 部分交付:仅交付通过
门句子)需要控制**交付的答案文本**——该控制点在
`runtime/grounding/loop.py generate_grounded` 内部(SEALED)。ops 层
全部缝隙(csupp/ggate/gctx.refused)或无答案文本或不可改写。
**按任务书 §十八:STOP·不改 sealed·列 Owner Decision。**

最小修改提案(供 OD·未实施):loop.py 拒答路径前增加「子集组装
钩子」——整答门失败时以已验证句子子集重过全门并交付子集
(~15 行·默认 OFF·回滚=还原;全部安全门在子集上重跑·零绕过)。

## 7. §十二-十四 Re-entry(Owner 本会话批准·最小 probe)

批准→kill 移除→12 探针(正 7+负 5):**安全全零**(负例 6/6
baseline·hard 拦截 10·error/timeout 0·无 unsafe 交付);check 级
转换 20/20;答案级 0/20(§5);探毕 kill→post-kill 探针=baseline
(17.2s)。

## 8. §十九 Regression

全电池 **895 passed/0 failed/2 skipped**;OFF 等价=**代码级 PASS**
(killed→passthrough 逐位一致·单测证);答案级 1/3 差异=LLM 非确
定性(如实·非 authority 行为变化)。

## 9. 安全门状态(全程)

false upgrade=0·九类 escape=0·fail-open=0·post-gate bypass=0·
candidate/judge 直写=0·source UNKNOWN=0;authority 探毕 **KILLED
保持 OFF**。

## 10. 终态

**DELIVERY_NOT_READY**(答案级)——Latency 达标·安全维持·check 级
闭合;唯一阻断=sealed 答案组装缝隙(§6 提案待 Owner)。
修复史如实:kill-file 跨案例污染(测试侧修)·OFF 等价判读区分
代码级/答案级。

## Owner Decisions OD-FIX3-69..76

见 `k29c-fix3-owner-decision-v14.md`。

---

**Authority=KILLED OFF · Full Authority=NOT GRANTED · Batch-2 Mode
B=NOT STARTED · Hybrid=OFF · taxonomy=FROZEN · τ=FROZEN · 生产代码
改动=0**
