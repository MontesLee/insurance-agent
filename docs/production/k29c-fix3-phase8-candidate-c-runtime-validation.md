# K.29-C FIX-3 Phase 8 · Candidate-C Offline Runtime Validation

Date: 2026-10-03 · Mode: **ISOLATED REFERENCE VALIDATION**(
`tools/k29c_fix3_candidate_c.py`——零生产接线·零生产改动·判定 raw
全部复用 Phase-5/6 缓存·**0 次新 LLM 调用**)·终态:
**CANDIDATE_C_EVIDENCE_READY**(≠AUTHORITY_GRANTED)

---

## 0. 冻结态

全部一致后执行::8123 灰度+加固影子 LIVE·生产 mtime 未变·authority
未授予·Hybrid OFF·S2 未变·Batch-2 未分发·D-08 SEALED。

## 1-2. 实现与合取(严格 Phase-7 定义)

隔离参考实现按 C3 严格合取:baseline==PARTIAL ∧ cited ∧ hard_
prefilter PASS ∧ risk_boundary PASS ∧ judge ALLOW ∧ post_gate PASS;
判定 FAIL/timeout/malformed/UNCERTAIN/exception → KEEP;唯一 ALLOW
返回点位于六段检查之后(结构性·无 fail-open)。
**Phase-8 新规则(C2 严格读法)**:类型豁免(NOT_APPLICABLE)不得
绕过硬类——硬类 claim 的 REC 豁免在 prefilter 处被否决(仅证据
支持的 SUPPORTED 可过)。该规则为隔离实现内规则·非生产变更。

## 3. 语料重放(246 例·全风险面)

| 语料 | n | BASELINE_PASS | KEEP | ALLOW | **FU** |
|---|---:|---:|---:|---:|---:|
| v2 冻结 82 | 82 | 19 | 63 | 0 | **0** |
| Phase-6 60 | 60 | 9 | 50 | 1 | **0** |
| 金标 104 | 104 | 35 | 69 | 0 | **0** |
| **合计** | **246** | 63 | 182 | 1 | **0** |

唯一 ALLOW=BF2-12 对照件(设计内正确升级)。重点重放全含:F5-05/
BF1-16/BF2-01/BF3-01+全部历史 FU+全部高危/R3/R4/数字/产品/监管/
日期/矛盾类。FU 口径含 gold_judge 语义(对照件 gold=确定性拒但
判定 ALLOW 正确——非 FU·留痕)。

## 4. 六段运行时 trace

每 claim 全 trace 落盘(`k29c_fix3_phase8_runtime_trace.jsonl`·
246 条·每段 decision+reason+block_stage)——错误阻断位置逐条可查
(block 段统计:cited/baseline-not-partial/baseline-contradicted/
hard_prefilter/risk_boundary/semantic_judge/prefilter-exempt-hardclass)。

## 5-6. 已知错误注入+失败注入矩阵(13 行全过)

**四阻断强制注入(judge=ALLOW_UPGRADE 强制)**:

| 案 | 历史判定 | Candidate-C 终局 | 阻断段 |
|---|---|---|---|
| F5-05 | ALLOW(0.9) | **KEEP** | baseline-not-partial |
| BF1-16 | ALLOW(0.97) | **KEEP** | baseline-contradicted |
| BF2-01 | ALLOW(0.8) | **KEEP** | baseline-not-partial(范围词双保险在 prefilter) |
| BF3-01 | ALLOW(0.8) | **KEEP** | **prefilter-exempt-hardclass**(新规则) |

**失败注入矩阵**(judge ALLOW/REJECT/UNCERTAIN/timeout/malformed/
exception·prefilter/risk/post-gate FAIL·缺引用·缺证据)= **13/13
PASS**;两个反证行证明非「一票否决式永拒」:control(全健康+ALLOW
→ ALLOW ✓)与 soft-twin(硬探针的软孪生句升级 ✓·证明否决源=硬门
而非整体拒绝)。

## 7. 安全性质 P1-P6

全 PASS(`k29c_fix3_phase8_safety_properties.json`·每性质附证据+
结构性论证:唯一 ALLOW 返回点在六段之后·全部 block 段被语料+注入
穷举覆盖)。

## 8-9. 零逃逸门+效用

**九类 FALSE_UPGRADE 全部=0**(246 例)。效用(安全优先·未放宽任何
门):严格 C3(PARTIAL-only)下 v2 升级=0——E 类 UNSUPPORTED 改写
按 Phase-7 定义不可升级(效用扩张=C3 修订=Owner 设计决策·非验证
发现);保守副作用如实记录(含硬词的 meta-prose 现被 KEEP)。

## 10. 关键区分(§13 强制)

**判定层:仍然 NOT SAFE**(Phase-5/6 发现不变·本阶段未重测未改写)。
**Candidate-C 管线:有界安全已离线实证**。正确表述:
> Semantic Judge remains individually non-authoritative; Candidate-C
> demonstrated bounded safety as the FULL CONJUNCTION (offline).

## 11. 生产回归

生产代码零改动;全电池运行中(结果见下)。隔离实现零 runtime
import(grep 证)。

## 12. 就绪矩阵

19 项全 PASS(`k29c_fix3_phase8_authority_matrix.json`)·post-gate
独立组件注记(现=同文本重扫·真正独立性=交付证据重查·属实现阶段)。

## 工件

7 件(runtime_trace.jsonl 246·failure_injection·known_blockers·
safety_properties·utility·authority_matrix)+ 本报告 + OD v9 +
checkpoint。调试修正史如实:trace 文件 jsonl/array 混读两处+
BF3-01 baseline-pass 发现→新规则+FU 对照语义——全部留痕。

## 终态

**CANDIDATE_C_EVIDENCE_READY**——Candidate-C 作为完整合取链在离线
重放中阻断全部已知判定错误且零逃逸;实现与验证均为隔离件。**绝不
表示 AUTHORITY_GRANTED。**
