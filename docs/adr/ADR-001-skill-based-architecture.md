# ADR-001 · Skill-based architecture

## Context
保险顾问任务天然可分解为若干判断层：客户事实、需求、风险、保障缺口、解决策略、证据、产品候选、推荐、报告。
早期做法是一个大 Prompt / 一个大函数依次做完，任何一层想改都牵动全链。

## Decision
把每一层做成**独立的 Specialist Skill**，各自声明：消费哪些 Canonical Artifact、产出恰好一个 Canonical Artifact、遵循哪份契约。
Skill 之间**不直接互相调用**，只通过 Artifact 协作。

## Alternatives
- 单体 Prompt（一次生成全部结论）：无法分层校验，一处幻觉污染全链。
- 单体 Python 大函数：可测但不可演；改一层要动全文件。
- 链式 Skill 直接调用（A 里 `import B`）：把依赖烧死在代码里。

## Why
分层使「每一层的正确性」可**独立**定义、独立校验、独立修复。风险层错了不影响事实层；缺口层改了不必重训推荐层。
每层一个 artifact 也意味着每次改动都可 diff、可回溯、可在一份样本上复现。

## Trade-offs
- 需要额外维护契约层（9 份 schema + adapter），前期成本高。
- 层间存在**语义漂移**风险（同一概念两处定义）——用「契约即单一真源 + canonical-first」压制，但要持续治理。
- 一次跑通需要更多步骤（更多 artifact 落盘），但对**高风险决策**场景，可解释性 > 步骤数。
