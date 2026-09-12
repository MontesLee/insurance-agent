# AGENTS.md — 保险 Agent 项目约定

本文件是项目级硬约定。任何 Agent（Codex / WorkBuddy / Claude Code / 其他）在本仓库**创建或修改 Skill 之前必须先读本文件**。

---

## 1. 命名规范（强制）

| 对象 | 风格 | 示例 |
|---|---|---|
| Skill 目录 / Skill ID | **kebab-case** | `client-intake`、`requirement-analysis`、`risk-analysis` |
| 文档文件名 | kebab-case | `risk-taxonomy.md`、`eval-policy.md` |
| 脚本名 | `<动词>-<skill-id>-<stage>.ps1` | `invoke-risk-analysis-analysis.ps1` |
| Python 模块 | snake_case | `risk_analysis` |
| JSON / YAML 字段 | snake_case | `risk_category`、`residual_risk` |
| 枚举值 | UPPER_SNAKE | `PRELIMINARY`、`P0_CRITICAL`、`NEEDS_REVIEW` |

> **目录名 ≠ Python 模块名。** 文件系统 / Skill ID 用 kebab-case；代码层真正需要包时再用 snake_case。两者可以不同，不要混用。

**历史遗留例外**：`requirement_analysis` 目录使用下划线，为既有 Skill 且已完成回归基线，**不重命名**（重命名会破坏 adapter 路径、守卫脚本与回归基线）。新建 Skill 一律 kebab-case。

---

## 2. Skill 分层与职责（不得越界）

| Skill | 核心问题 | 主要产物 | 明确禁止 |
|---|---|---|---|
| `client-intake` | 客户有哪些**事实**？ | Client State | 任何保险判断（越界即 HF01） |
| `requirement-analysis` | 客户想解决什么**问题**？ | Requirements | 产品推荐（越界即 `PRODUCT_RECOMMENDATION_LEAK`） |
| `risk-analysis` | 客户暴露什么**风险**？ | Risks | 产品推荐、重复产出 requirement |
| `coverage-gap-analysis` | 现有保障哪里**不足**？ | Coverage Gaps | 产品推荐 |
| `solution` | 怎么**解决**？ | Solutions | — |
| `product-recommendation` | 具体用什么**产品**？ | Products | — |

数据链（单向，不可倒流）：

```text
FACT → REQUIREMENT → RISK → GAP → SOLUTION → PRODUCT
```

---

## 3. Canonical Client State（唯一事实源）

```text
              client-intake
                    │
                    ▼
            Canonical Client State
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
requirement-analysis        risk-analysis
        │                       ▲
        ▼                       │
   Requirements ────────────────┘
```

- `client-intake` 负责采集事实 → 规范化为 **ClientState**
- 下游所有 Skill 一律引用 `client_state.<profile>.<field>`，**不得**直接引用 `client-intake.<field>` 或 `requirement-analysis.<field>` 作为事实源
- 每个字段必须携带四元组：`value` / `status` / `source` / `confidence`
- `status` **五态**：`KNOWN` / `UNKNOWN` / `ESTIMATED` / `ASSUMED` / `INFERRED`
- `INFERRED` **只允许由消费方 Skill 自身推导产生**；上游透传字段不得标 `INFERRED`

### 上游 4 态 → ClientState 5 态映射（固定，不得自定义）

| 上游 `value_status` | ClientState `status` | 说明 |
|---|---|---|
| `KNOWN` | `KNOWN` | 原样透传 |
| `ESTIMATED` | `ESTIMATED` | 原样透传 |
| `ASSUMED` | `ASSUMED` | 原样透传 |
| `UNKNOWN` | `UNKNOWN` | 原样透传 |
| （上游无此字段 / 字段不存在） | `UNKNOWN` | 同时记入 `missing_from_upstream[]` |
| — | `INFERRED` | **仅**由下游 Skill 自身推导，必须带 `note` 说明推导依据 |

---

## 4. 上游不可变原则

- 已完成的 Skill（`client-intake`、`requirement-analysis`）**禁止修改**任何文件、Prompt、Schema、行为逻辑或测试
- 数据结构不兼容 → 在下游用 **adapter / mapper / normalization** 解决
- 上游数据缺失 → 显式标记 `MISSING_FROM_UPSTREAM` 并降级为 `UNKNOWN`，**严禁反向给上游加字段**
- 禁止为了兼容下游而改变上游输出格式

---

## 5. 确定性优先

- 评分 / 分级 / 充分性 / 优先级判定一律由**脚本按外置规则文件**计算，**禁止 LLM 自由发挥**
- 规则文件放 `resources/config/*.rules.json`，脚本只消费不算
- 引擎必须可离线回归，不依赖 LLM

---

## 6. Eval 纪律

- Eval 是**独立步骤**，不得写成"请检查一下"
- 只有**可机检断言**才判 PASS；自然语言断言记 `MANUAL` 且**不计通过**
- 未真正执行的 case 记 `NOT_EXECUTED` / `UNVERIFIED`，**不计通过**
- Eval FAIL → Repair → 重跑，`MAX_REPAIR_ATTEMPTS = 2`；仍失败 → `NEEDS_REVIEW`
- 必须做**负向自检**：注入污染 → 必须报红 → 清理 → 复绿

---

## 7. Skill 目录骨架

```
.trae/skills/<skill-id>/
  SKILL.md                      # 轻量 manifest（≤100 行），只放 Identity/Trigger/Input/Workflow/Output/Boundary/References/Eval
  CONTRACT.md                   # 契约（可选，跨 Skill 依赖复杂时必备）
  references/NN-<topic>.md      # 深层规则，按编号路由
  schemas/*.schema.json         # draft-07
  evals/eval-policy.md          # Eval 唯一真源
  evals/cases/*.json            # 数据集
  evals/fixtures/               # 单元测试夹具
  resources/usage-guide.md      # 调用模板
  resources/config/*.rules.json # 外置规则
  overlays/<domain>/            # 仅在确有 Context-specific modification 时使用
  scripts/invoke-*.ps1          # 确定性引擎
  scripts/test-*.ps1            # 单元测试
  scripts/run-*-dataset.ps1     # 全量回归
  scripts/check-skill-anatomy.ps1
  scripts/lib/*-runtime.ps1
  tmp/                          # 运行产物，不计入基线
```

> Skill 目录在 `.trae/skills/`，不是仓库根的 `skills/`。

---

## 8. 何时使用 overlay（默认不使用）

`overlay = Base + Context-specific modification`。

**默认不使用 overlay。** 只有当出现"同一套基础规则需要按地区 / 客群 / 公司业务规则做增量覆盖"时才引入。

基础领域模型（如风险分类 R1–R5）直接写进 `references/`，**不要为了"以后可能需要"提前引入 overlay**。

---

## 9. 禁止创造事实（最高优先级）

```text
事实 > 推断 > 假设 > 猜测
UNKNOWN > fabricated certainty
```

- 输入"客户有房" → **不得**推断"房产价值 800 万"
- 输入"家庭收入较高" → **不得**推断"家庭收入 100 万"
- 输入"有医保" → **不得**推断"医保覆盖 80%"
- 确需估计 → `status: ESTIMATED` 且必须写明估计依据

宁可 `UNKNOWN`，不得假装知道。
