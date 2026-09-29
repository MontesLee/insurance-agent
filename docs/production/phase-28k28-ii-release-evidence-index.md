# K.28-II Claim Support · Release Evidence Index

Seal: **D-08-K28-II-CLAIM-SUPPORT** · Date: 2026-09-29 ·
HEAD-before-seal: e306118 · 基线索引：`tmp/obs/k28ii_od12_baseline.json`

> 任何 Reviewer 仅读本 Index 即可回答 §14 全部问题（为什么做/怎么
> 验证/FIX1 为何发生/是否安全放宽/当前状态/谁决定）。

## Evidence Table（§3）

| Evidence | 文件 | Purpose | Status |
|---|---|---|---|
| Design | phase-28k28-ii-claim-evidence-design.md | 设计冻结（citation≠support·六类 taxonomy·D-hybrid） | PASS |
| Shadow | phase-28k28-ii-claim-evidence-shadow.md | Shadow baseline（escape 88.2%→0·攻击面全捕） | PASS |
| Ledger Audit | phase-28k28-ii-shadow-ledger-audit.md | baseline 数字审计（Case A 笔误更正留痕） | PASS |
| Implementation | phase-28k28-ii-claim-support-impl.md | 生产实现（DoD 18/18·默认 OFF 灰度发布） | PASS |
| Live Gray | phase-28k28-ii-claim-support-live-gray.md | 首次 live gray（安全三零；发现 False Refusal 缺陷→BLOCKED 如实） | **PASS after FIX1 closure** |
| FIX1 | phase-28k28-ii-claim-support-fix1.md | false-refusal 修复（FR 3/3→0/3·安全零变化） | PASS |
| Reverify | phase-28k28-ii-live-gray-reverify.md | FIX1 live 复验（FR 0/6·全门禁绿） | PASS |
| OD-12 | phase-28k28-ii-od12-acceptance.md | acceptance governance 冻结 | FROZEN |
| Tests | tests/runtime/test_k28ii_claim_support.py（48 检查·含 FIX1-01/02/03 永久回归）+ tests/golden/claim-evidence-shadow.v1.json（114 冻结+勘误 2 留痕） | regression evidence | PASS |
| Runtime | :8123 PID 25928（=FIX1/Reverify/OD-12 证据进程·未重启）·CLAIM_SUPPORT_ENABLED=1 | deployment state | VERIFIED |
| Commit | e306118 + 本 seal commit（span 代码与证据） | implementation provenance | VERIFIED |

Observation evidence（tmp/obs·不入 git）：k28iish_results/llm·
k28ii_prod_metrics/live_gray/live_sup/live_api/fix1_sup·
k28ii_reverify_matrix/fr/metrics·k28ii_od12_baseline。

## OD12_BASELINE（§4·原样冻结·禁止重算覆盖）

```
False Support        = 5          （历史语料基线；新增增量口径独立=0）
Unsupported Escape   = 0          （当前验证范围内未观察到）
False Refusal        = 0/6        （FIX1 live reverify）
Support P/R          = 0.80/0.80
Frozen regression    = 865 passed + 2 skipped
```

**范围声明**：以上为 shadow corpus + Golden + Live Gray/FIX1/Reverify
验证范围内的观测——**不是对全部线上流量的统计推断**。

## FIX1 Provenance（§5）

```
Root Cause : 单侧 CJK normalization 不一致（claim 侧去标点产生跨标点
             bigram·证据侧原始文本成员检查 → 逐字引用 PARTIAL 误拒）
Fix        : 共享 _cjk_norm()·Claim 与 Evidence 双侧统一 normalization
Safety     : Unsupported Escape 未增加（0→0）·False Support 未增加（5→5）
False Refusal: 3/3 → 0/3（FIX1 live）·Reverify 0/6
Tests      : FIX1-01（列举标点逐字）/FIX1-02（冒号顿号+缺失对照）/
             FIX1-03（年份括号零锚污染）——tests/runtime/
             test_k28ii_claim_support.py::fix1_normalization
```

## Runtime Provenance（§6·一致·无 STOP 项）

```
Commit: e306118（+本 seal）
Current Gray: CLAIM_SUPPORT_ENABLED=1（S1）
LLM Claim Judge: OFF
Planning: NOT ENABLED
代码 hash: claim_support.py c28957d8b059cbf7 / qa-grounding-rules.yaml
           258950b5eaf4d5a5 ——与 OD-12 基线索引逐位一致
```

## Security Provenance（§7）

```
Unsupported Escape        = 0
Consumer Metadata Leakage = 0
Unsafe Streaming Leakage  = 0
RV4-B = REFUSED / NO DELIVERY      RV4-A = C2 0 QUALIFIED
Claim Support 未改变 C2 qualification boundary（RV4-A 实证）
```

## Frozen Component Provenance（§8）

```
Intent = SEALED（no regression）   C1 = SEALED（12/12）
C2     = SEALED（k27rv4c2 绿）     K.26 = SEALED（k22 绿·实现零触碰）
```

## OD-12 State（§10）

```
S0 OFF → S1 CURRENT_GRAY（当前）→ S2 EXPANDED_GRAY → S3 PRODUCTION_AUTHORITY
OD-12 = FROZEN · Production Authority = NOT GRANTED
```

## §14 速答

为什么做：Citation 存在 ≠ Evidence 支持 Claim（RV4 15×[E1] stuffing）。
怎么验证：Shadow→Ledger Audit→Implementation→Live Gray→FIX1→Reverify。
FIX1 为何：claim/evidence normalization 不对称。安全放宽？没有
（FP=5·Escape=0 不变）。当前状态：CURRENT_GRAY。全量？NO。Planning？
NO。LLM Judge？NO。下一步谁决定：OWNER（S1→S2）。

## Seal Boundary（§11·明确不证明）

本 Seal 只证明：K.28-II 当前版本已完成实现/FIX1/Gray/Reverify 并具
冻结 OD-12 治理。**不证明**：Production Authority 已获得；真实线上
错误率=baseline；Planning Claim Support 已通过；LLM Judge 可上线。

## 叙事完整性（§15）

**LIVE-GRAY initially BLOCKED 保留在案**：Live Gray → 发现 False
Refusal（LIVE_CODE_DEFECT）→ FIX1 → Reverify PASS——这是生产工程
证据的一部分，Index 与原始报告均不删除该历史。
