# 28.K.28 · D-08 Intent Fix Commit & Release Seal

Date: 2026-09-29 · Result: **D-08 STATUS: PASS**

## A. Release Identity

| 项 | 值 |
|---|---|
| commit | **e306118** |
| message | `feat(intent): seal K28 intent production fix`（正文含三修复+全部验证数据+治理边界） |
| timestamp | 2026-09-29 13:47:30 +0800 |
| HEAD before | 46dbe0f |
| HEAD after | **e306118**（main） |
| 变更量 | 10 files · +5469 insertions（纯新增为主·test_agent_intent.py +83 为纯插入） |

## B. Scope（D08_ALLOWED_SCOPE·逐文件反向审计通过）

**Production（2）**：
- `runtime/intent/classifier.py`（Fix C 4.5 负向并入·Fix A 规则 4 守卫+豁免·规则 5 question_form 窄接管；自包含无 runtime 内依赖）
- `config/intent-rules.yaml`（question_protection 块·序数指称·negative_signals·plan signals +怎么配/怎么安排）

**Tests（3）**：
- `tests/golden/intent-golden-corpus.v1.json`（冻结 v1·224 例·D 规则发布；expected 零改动）
- `tests/runtime/test_agent_intent.py`（diff 审计=纯 C1 三节 +83·「C1 regression tests」在册）
- `tools/intent_production_eval.py` + `tools/intent_fix_regression.py`（K28I_FIX_REGRESSION 可执行回归）

**Governance docs（4）**：audit / fix-design / fix-impl / fix-live 四份阶段报告。

**排除（正确）**：`phase-28k28-latency-profiling`/`-reasoning-displayable-buffer`（K.28 性能线非本 scope）·`tmp/obs/*` 全部运行证据（§2 禁入）·既有 span 其余 40 modified + 191 untracked（27.7.6-D..K.27 系列遗留·非本次提交组成）。

## C. Verification

| 项 | 结果 |
|---|---|
| K.28-I-FIX-IMPL | PASS（D5 六项全达标） |
| K.28-I-FIX-LIVE | PASS（18 探针矩阵·零 MISMATCH） |
| Pre-commit 金标回归 | acc 95.91 / F1 0.9486 / 不稳定 0——与 IMPL PASS 数值逐位一致 |
| C1 专项 | 12/12 |
| 全电池 | **865 passed + 2 skipped**（389s·零失败） |
| 安全 | 本阶段零新代码（无泄漏面）；live 侧九零在案 |
| C1 | preserved（continuation 100%/97.62%） |
| C2 | untouched（qa_agent/grounding 零触碰） |

**Diff invariants（§3）**：negative_signals/序数/question_protection 三修复在文件中在案；无删除/简化/未授权规则。**Frozen decisions（§4）**：vocabulary=5（D2 零扩）·裸 这个/那个/那这个/它 缺席（D3·仅复合计号 这个产品）·无 elliptical 块（D4 B2 未提前实现）·high_risk_llm_min_confidence=0.75（D5 阈值未动）。

## D. Runtime（§6·未重启）

| 项 | 值 |
|---|---|
| :8123 | health 200 · **PID 26352**（=live 验证进程·未重启） |
| classifier | 工作树 sha `1fa5d8d6725b0dc5` |
| intent-rules.yaml | 工作树 sha `f05a5c0669465dd8` |
| **提交≡运行** | `git show HEAD:<f>` 与 live 文件 **CRLF 归一后逐字节相等**（提交 blob 038d33dc…/f28e7376… 为 LF 归一形态） |
| LLM Candidate | **OFF**（启动 env 未设——hd2.env/.env 零命中 + 18/18 shadow conf_src=rule） |
| Router Authority | full（pilot 基线·未动） |

## E. Residual Debt（保留·本阶段零修复）

- RV4 exact-T2 live 自然流量样本债（等价机制已证）
- ask-vs-proceed planning UX 方差（Owner 线·非 intent 层）
- FU-03 无锚序数 fail-closed（corpus v1.1 勘误候选）
- Taxonomy debt：SW-10（服务元问题）·SW-03（pending 推荐）·REC-01..03（推荐类）——D2 维持 fail-closed/既有映射
- 既有未提交 span（40M+191??·27.7.6-D..K.27 系列）——后续 D-08 续封 Owner 决策

## F. Boundary

```
Phase 2 NOT IMPLEMENTED
Phase 2 remains Owner-gated
LLM Intent Candidate remains OFF
Router Authority unchanged
C2 unchanged / sealed
```

## Seal

D-08 十四项判定全过（IMPL PASS·LIVE PASS·pre-commit PASS·865+2·
C1 preserved·C2 untouched·candidate OFF·authority unchanged·scope
exact·commit successful·post-commit audit PASS·零未授权行为变更·
零 Phase 2·零 taxonomy 扩展）→ **D-08 STATUS: PASS**。
