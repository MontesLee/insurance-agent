FINAL STATUS: CONTROLLED_AUTHORITY_REENTRY_VERIFIED

# K.29-C FIX-3 Phase 14 · Minimal Sealed Delivery Hook

Date: 2026-10-03 · Mode: **SEALED MINIMAL PATCH**(OD-FIX3-77 Owner
本会话批准)·终态:**CONTROLLED_AUTHORITY_REENTRY_VERIFIED**(答案级
交付闭合·最小 re-entry probe 成功·authority 探毕 KILLED OFF)

---

## 1. Owner Approval

OD-FIX3-77=APPROVED(本会话交互确认:批准 loop.py 最小 verified-
subset 组装钩子·默认 OFF·回归+续封材料)。

## 2-3. 控制流与插入点(§十四)

- **现状**:`generate_grounded` 循环末尾——整答门失败→
  `gctx.refused(citation_gate_rejected)`(loop.py 原 392-399)。
- **插入点**:循环后、最终拒答前——verified-subset 组装块。
- **为何外围不可行**(Phase-13 已证):交付文本控制点在函数内部;
  csupp/ggate/gctx.refused 缝隙或无答案文本或不可改写。
- **为何不改变安全门**:钩子只调用**同一 `_full_gate`**(引用门+
  claim support+进程内 authority 链)逐句判定;组装后**整体重过
  同一门**;任一句失败→正常拒答。无门被绕过/放宽。

## 4. Patch 内容(§二十二 审计)

| 项 | 值 |
|---|---|
| 修改文件 | **仅 `runtime/grounding/loop.py`**(+`import os` 1 行) |
| diff | **+69 行**(含 12 行注释·纯代码 ~50 行:env 门+句子切分+逐句门+终结符保留 join+整体重门+grounded 交付) |
| 默认 | `AUTHORITY_VERIFIED_SUBSET_DELIVERY=0`(OFF=代码路径不可达) |
| 新测试 | `tests/runtime/test_fix3_phase14_subset.py`(14 测试=T1-T16 合并) |
| 其他生产文件 | **0** |

**实施中发现并修正**(如实):①初版把 `production_final_source` 等
三键写入 generation dict → **封闭 schema 拒绝**(internal_error
降级)→ 改为 schema-标准记录+ops 层 trace 记 source(§十三 四值
契约在 trace 层满足);②join 丢失句末终结符 → 终结符保留 join
(重门验证);③**kill 契约缺口**:kill 文件未联动 env 旗→kill 后
仍交付确定性子集(安全但违反 §19)→ 启动器 kill-watcher 线程
(2s 轮询清 env)→ 修复后 2/2 探针拒答实证。

## 5. 粒度证明(§八)

assembly_unit = `ggate.split_sentences` = **生产引用门同一函数同
一粒度**(句子级·同 separators)——`assembly_unit ==
production_gate_unit` 由构造保证+T4/T5 单测锁定。未发明新粒度。

## 6. 语义(§五-七)

verified_subset 内每句都过完整门链(evidence/citation/硬类/风险/
judge/post-gate/quota/version——进程内 authority 链随 csupp.check
执行);组装=**仅选择已过门文本单元重组**(终结符保留·无新增/
改写/拼接新 claim);重门兜底「组装产生新 claim→拒答」。
无 candidate/judge/preflight/shadow 直写路径(结构+T11/T12)。

## 7. §十五 测试:**14/14 PASS**(T1-T16)

OFF→baseline ✓·全过→交付 ✓·零过→baseline ✓·混合→仅子集 ✓·
未引用句排除 ✓·numeric/product/R4→baseline ✓·门失败/judge-ALLOW-
但门拒→baseline ✓·直写不可能 ✓·source 合法 ✓·畸形→baseline ✓·
空证据→baseline ✓·OFF 不可达 ✓。

## 8. §十六 Regression

**909 passed / 0 failed / 2 skipped**(=895 基线+14 新)。

## 9. §十七-十八 答案级 Probe(10 轮 live)

| 结果 | 值 |
|---|---|
| **正例交付** | **3/5 delivered(>0——答案级闭合)** |
| 负例安全 | 5/5 refused(产品 slice fail-closed/引用门拒答) |
| 交付答案安全扫描 | 未引用数字扫描 1 hit(「100%」)——**证据逐字验证**(领域包百万医疗险:「按比例报销(通常 100% 或经社保结算后较高比例)」)·已引用·过全门 |
| 2 例正例未交付 | 逐句门合法拒绝致子集空(确定性解释·fail-closed) |
| 追溯 | claim→evidence→门链→子集→组装→production_final(交付句带 [E#]·ops ledger 逐单元) |

## 10. §十九 Kill/Rollback

1 缺口发现+修复(§4③);修复后 kill→2/2 探针 baseline·零自动
恢复·kill event+时间戳在案。**KILL_CONTRACT_VERIFIED**。

## 11. §二十 Latency

n=21·p50 10.27·p95 **20.81**·p99/max 25.54·kill 未触发·
judge_timeouts 1(坍缩 KEEP)·cache_hits 17——**≤30s 达标**
(钩子本身=确定性切分+重门·无新增 LLM)。

## 12. §二十四 最终安全矩阵

| Gate | Result |
|---|---|
| FACTUAL_PARAPHRASE scope | PASS(3 交付全为证据改写) |
| Numeric/Product/Regulatory/Payment/Date/Contradiction/Universal/R4 | PASS(硬拦截 16·负例 5/5·单测) |
| Citation | PASS(句级同粒度·未引用排除) |
| Claim Support | PASS(65-check 不变·子集重门) |
| Independent Post-Gate | PASS(链内执行) |
| Version | PASS(Phase-11 契约不变) |
| Kill Switch | PASS(修复后实证) |
| Rollback | PASS(env=0 → 路径不可达·单测+live) |
| Latency | PASS(p95 20.81≤30) |
| Production Traceability | PASS(ops trace+schema 记录) |
| **Answer Delivery** | **PASS(3/5·>0·逐条可溯)** |

## 13. §二十三 Rollback

`git checkout -- runtime/grounding/loop.py`(或 env=0 即时行为
回退)+删测试文件;ops 侧=启动器还原。kill 文件保持(当前态)。

## Owner Decisions OD-FIX3-78..84

见 `k29c-fix3-owner-decision-v15.md`。

---

**Authority=KILLED OFF(探毕)· Full Authority=NOT GRANTED ·
Batch-2 Mode B=NOT STARTED · Hybrid=OFF · taxonomy=FROZEN ·
τ=FROZEN · 生产文件变更=loop.py(+69·授权内)**

**Phase 14 完成——立即 STOP。等待 Owner Decision。**
