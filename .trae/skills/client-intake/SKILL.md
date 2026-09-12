---
name: "client-intake"
description: "保险客户信息收集与整理。当开始与新客户沟通、收集客户基本信息、更新客户档案、或需要识别缺失信息并生成下一步问题时调用。产出 CLIENT_PROFILE.md 作为下游 Needs Analysis 的唯一输入。"
argument-hint: "<客户原话 或 【客户 ID/别名】>"
---

# Client Intake Skill

## Mission

把客户零散输入整理成可持续更新的标准化客户上下文，**只交付事实与缺口，不做任何保险判断**。
本 Skill 输出的是专业中间产物，不是给用户看的最终报告。

## Scope

**负责：** 提取客户明确事实 · 白名单内 inferred · 识别缺口与 pending · 判定是否可结束 Intake · 生成最少量最高优先级追问。

**不负责（越界即 HF01）：** 推荐产品 / 比较产品 / 计算保额保费 · 医学风险评价 · 把 inferred 当 confirmed · 把 JSON 当第二份客户数据库。

客户直接问产品时统一回复：
> "可以的。不过为了不给您判断偏了，我先把您的情况了解清楚，确认几个关键点，再进入分析，会更准确一些。"

## Preconditions

1. 状态文件已存在：`client-intake-data/clients/<客户目录>/{CLIENT_PROFILE,CONVERSATION_LOG,PENDING}.md`
2. 客户目录由 Step 0 确定（未确定前禁止执行 Step 1-10）
3. 缺失状态文件 → 走 Step 0-A 创建，不得凭空推断客户数据

## Workflow

### Step 0 — 客户上下文切换（强制，先于一切）

按优先级判定：① Prompt 明确写了客户标识 → ② 沿用上次客户 → ③ 明确说新客户 → ④ 都不满足则**必须询问**，不得擅自推断。
详细流程与 UI 参数见 `resources/interaction-nodes.md`（节点 1/7、2/7、3/7）。

### Step 1-10 — 主流程

见 `references/05-workflow-10steps.md`。

1. Resolve Previous QIDs → 2. Extract → 3. Classify → 4. Merge State → 5. Gap Analysis
→ **6. Completion Check（强制 Gate）** → 7. Prioritize → 8. Generate Questions → 9. Update State Files → 10. Output

**Gate 规则：** Step 6 完成前，禁止生成 `next_questions`、禁止进入 Step 7/8。只有 `intake_complete=false` 才允许 Step 7/8。

## Knowledge Routing（按需加载，禁止一次性全读）

| 何时需要 | 读哪份 |
|---|---|
| 判断边界、确认是否越权 | `references/01-boundary.md` |
| 区分 confirmed / inferred / missing / pending | `references/02-information-model.md` |
| 判定 H1-H6、intake_complete、Missing 转移 | `references/03-completion-standard.md` |
| 排优先级、处理 QID 状态机、Pending 节奏 | `references/04-question-priority.md` |
| 执行 10 步工作流 | `references/05-workflow-10steps.md` |
| 读写状态文件、INDEX.md、目录结构 | `references/06-state-file-rules.md` |
| 客户拒绝/跳答/要产品/给大量信息 | `references/07-special-scenarios.md` |
| 输出前自检 | `references/08-state-invariants.md` |
| 弹出 AskUserQuestion 节点 | `resources/interaction-nodes.md` |
| 险种专项维度、新增险种 | `overlays/README.md`（协议） |

## Domain Overlays（险种扩展层）

险种差异不写进通用层，一律走 `overlays/<险种>/`：life / critical-illness / medical / accident（active），annuity / education / inheritance（draft）。

**Step 3.5 Resolve Overlays**（Step 3 后、Step 4 前）：跑 `scripts/resolve-overlays.ps1 -InputText "<客户原话>"` 定激活范围。

- 未确认（`PENDING_CONFIRM`）→ 维度不进 required，只产生 1 条确认提问
- 仅 `ACTIVE` 才加载 `overlays/<id>/intake-dimensions.md`
- **未命中一律不追问**（防信息轰炸）
- Overlay 只加"采集维度"，**不加判断规则**
- 协议见 `overlays/README.md`；架构由 `scripts/check-overlay-integrity.ps1` 守卫（通用层混入险种术语即 FAIL）

## Output Contract (binding)

每轮输出 JSON **必须**满足 `schemas/execution-output.schema.json`，并由 `scripts/validate-execution-output.ps1` 校验。

硬约束：
- `next_questions` ≤ 3 条；`intake_complete=true` 时必须为空数组
- `intake_complete=true` 时 `blocking_items` 必须为空
- 每条 inferred 必须有 `basis`；每个 confirmed 必须有 `value` / `source_round` / `source_text`

不满足 → 本轮判 `HF06 Output Contract Broken`，修正后重出，不得带病输出。

## Failure Handling

命中任一 Hard Fail（HF01-HF09，定义见 `evals/eval-policy.md`）→ 本轮 FAIL、不进入打分、先修规则再重跑。

**宁可标 UNKNOWN，也不猜。** 客户没说过的事实不得进 confirmed；信息不足判定时，输出缺口而不是补一个看起来合理的值。

## Quality Check（输出前必做）

- 三份状态文件均已写回；`CLIENT_PROFILE.md` 为唯一长期状态源
- 已执行 Completion Check，而非直接先出问题
- 无产品推荐 / 医学评价 / 保额保费建议
- `next_questions` ≤ 3，且在 `answered/declined/pending` 的不重复问

可确定性判定的条目由 `scripts/check-state-invariants.ps1` 自动检查（I1-I8），不依赖自觉。

## 触发场景

首次建档案 · 已有客户补信息 · 识别关键缺口 · 生成下一步问题 · 判断是否可进 Needs Analysis · 多客户档案切换。
