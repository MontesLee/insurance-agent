# D-08 · K.28-II Claim Support Span Seal

Date: 2026-09-29 · **D-08 Status: SEALED**

```
Seal ID:               D-08-K28-II-CLAIM-SUPPORT
Scope:                 QA / Product QA Claim Support
Rollout:               CURRENT_GRAY（S1）
Production Authority:  NOT GRANTED
Planning:              NOT ENABLED
LLM Claim Judge:       OFF
```

## Seal Gate 核验（§16 全过）

| 条件 | 结果 |
|---|---|
| 全部源报告在位（8 报告+测试+语料+基线索引） | ✅ |
| Evidence 引用可解析（tmp/obs 十条+文档清单） | ✅ |
| Baseline 不可变（原样引用·未重算覆盖） | ✅ |
| FIX1 溯源验证（根因/修复/安全不变/FR 3/3→0/3→0/6/三回归） | ✅ |
| Runtime 溯源（PID 25928=证据进程存活·hash 与基线逐位一致） | ✅ |
| 冻结组件溯源（Intent/C1/C2/K.26 零回归） | ✅ |
| Scope 审计（本阶段生产逻辑修改=0；其余 tracked diff=既有 span 原样保留） | ✅ |
| OD-12 FROZEN · Current=S1 · Authority NOT GRANTED · Planning/LLM OFF | ✅ |

详细矩阵：`phase-28k28-ii-release-evidence-index.md`（本 seal 的
组成部分）。

## Seal Commit（§18）

范围=K.28-II 已验证 span（零内容变更·纯 staging）：
生产代码（claim_support.py 新·loop.py 纯挂接 diff·rules 块·
additive schema）+ shadow 工具包 + 测试（48 检查）+ 冻结语料 +
评测器 + 10 份文档（8 阶段报告+evidence index+本 seal 报告）。
message：`chore(production): seal K.28-II claim support evidence`
（复用仓库 conventional-commit 规范）。

## Boundary 重申（§11）

本 Seal 不证明 Production Authority 已获得、不证明真实线上错误率=
baseline、不证明 Planning 已通过、不证明 LLM Judge 可上线。下一步
（S1→S2 扩灰）= **OWNER 决策**。
