# Requirement Analysis Skill — 专业说明文档

> 版本：v1.0 · Production Ready（🟢 READY，新增 **统一运行时安全调用 + Output 强校验**）
> 本文档面向：Skill 使用者（保险经纪人 / 运营）、Skill 维护者（工程 / Prompt 工程师）、QA / 回归工程师。

---

## 一、这个 Skill 是干什么的

### 1.1 定位（一句话）

`Requirement Analysis` 是一个**保险需求分析 Skill**。它不推荐具体产品、不做方案、不计算保额保费，只负责**基于 client_intake 已经整理好的客户画像，做信息充分性判断、需求缺口识别、需求优先级判定，并输出带证据链的结构化分析结果**，作为后续「方案建议 / 产品匹配 / 代理人陪访」技能的输入。

### 1.2 边界（绝对不要让它做这些事）

| ✅ 可以做 | ❌ 绝对不能做（任一命中即本轮 FAILED / EVAL FAIL） |
|---|---|
| 按 Scope（life / accident / medical / critical_illness / savings）识别信息缺口 | 推荐具体产品、保险公司、投保计划、保费、保额计算（=越界推荐）|
| 输出每个 Scope 的需求类型（risk_map / coverage_gaps / requirements ）| 用销售话术、营销语言、产品对比（=越界营销）|
| 输出优先级（P0_CRITICAL / P1_HIGH / P2_MEDIUM / P3_LOW）| 把 UNKNOWN / ESTIMATED / ASSUMED 写成 KNOWN 结论（=虚构证据）|
| 为每个重要结论输出 Evidence（evidence_id + fact_refs + reasoning + conclusion）| 修改 Client Intake 任何文件 / Prompt / Schema / 测试（=跨域污染）|
| 主动按优先级生成 ≤3 条高价值追问（自然口语、去重、多轮）| 把「需求不足」写成「必须买 xxx 保险」（=产品语言泄露）|
| 独立 Eval 判定（6 类 Issue Taxonomy + 5 维打分）| 对客户健康 / 职业 / 财务做任何医学分级或定性风险判断（=越界医疗或金融判断）|
| 针对特定 Issue 做 Targeted Repair Loop（≤2 次，失败进入人工复核）| 用 Conflicts 直接覆盖事实而不显式写出冲突字段（=丢失可追溯）|

### 1.3 长线架构优势（为什么这个 Skill 可长期维护）

对比「一段 Prompt + JSON 就跑」的临时方案，本 Skill 的 Production Ready 架构解决了 6 类本质问题：

| 维度 | Prompt-Only 典型痛点 | v1.0 Production Ready 架构 |
|---|---|---|
| 行为契约 | Prompt/文档/代码三处写规则，久了漂移 | [CONTRACT.md](file:///D:/Workspace/insurance-agent/references/01-boundary.md#L60-L170) + [input.schema.json](file:///D:/Workspace/insurance-agent/schemas/input.schema.json) + [output.schema.json](file:///D:/Workspace/insurance-agent/schemas/output.schema.json) 三者合一，所有脚本以 Schema 为准 |
| 信息充分性 | 「觉得够了就分析」靠体感 | [information-sufficiency.rules.json](file:///D:/Workspace/insurance-agent/resources/config/information-sufficiency.rules.json#L14-L120) 定义 5 Scope 的 required/recommended/optional + weighted scoring + blocking fields + conflict fields，结果可解释、可回归、可逐 Scope 审计 |
| 问题生成 | 每次问一堆、重复问、机械问 | [question-generation.rules.json](file:///D:/Workspace/insurance-agent/resources/config/question-generation.rules.json) 定义 priority formula（importance/impact/gap_type/difficulty/repeat_penalty），每轮最多 ≤3 条，重复字段自动跳过 |
| 可评估性 | 分析自己给自己打高分 | [invoke-requirement-analysis-eval.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-eval.ps1) 独立 deterministic 引擎，6 类 Issue Taxonomy + 5 维打分，与分析脚本完全解耦 |
| 可修复性 | 改坏了重跑一遍就好 | [invoke-requirement-analysis-repair-loop.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-repair-loop.ps1#L37-L48) Targeted Repair（realign_evidence / rebuild_analysis / sanitize_product / sync_priority / drop_formal_for_insufficient），MAX_RETRY=2，失败进入 HUMAN_REVIEW_REQUIRED |
| 可回归性 | 改一条规则全靠人脑 | [run-requirement-analysis-dataset.ps1](file:///D:/Workspace/insurance-agent/scripts/run-requirement-analysis-dataset.ps1#L329-L390) 统一跑三类场景（analysis_only / multi_turn_update / mutated_eval）× 15 case，100% PASS 才能上生产 |

---

## 二、日常如何使用这个 Skill

### 2.1 两种使用方式（先看这个）

| | 方式 A：对话式（日常主用法）| 方式 B：脚本直调式（维护者 / QA）|
|---|---|---|
| 谁用 | 保险经纪人 / 运营 / 任何业务使用者 | 工程 / Prompt 工程师 / QA 回归工程师 |
| 怎么用 | 在 Trae 对话里直接说话（见 §2.2）| PowerShell 跑 `scripts/` 下的引擎脚本（见 §2.5）|
| 典型场景 | 「客户资料刚录完，帮我分析一下他的保障需求」 | 单测某条规则、全量回归、批量离线分析 |
| 需要懂脚本吗 | **不需要**，Agent 会自己调用一切 | 需要 |

### 2.2 方式 A：在 Trae 对话里直接用（日常主用法）

#### 什么时候会触发

当你的对话意图命中「需求分析」——例如要求判断客户信息够不够、识别保障缺口、分析需求优先级——Trae 会自动激活 `requirement_analysis` Skill（注册入口 [SKILL.md](file:///D:/Workspace/insurance-agent/.trae/skills/requirement_analysis/SKILL.md)），无需手动指定任何文件或命令。

#### 你可以这样说（触发示例）

```
「张三的 intake 刚做完，帮我分析一下他的保障需求」
「李四的信息够不够做需求分析？还缺什么？」
「客户说去年收入 80 万今年又说 60 万，这个冲突确认一下再分析」
「根据王五的客户画像出一份需求优先级报告」
```

#### 触发后 Agent 自动做什么（内部 6 步，你无感知）

1. **读注册入口**：读 SKILL.md → 定位全部真源文档与脚本
2. **找输入**：优先读 `client-intake-data/clients/<客户>/CLIENT_PROFILE.md`（要求 Client Intake 已 `intake_complete=true`）；若你直接给了结构化 JSON 则直接用
3. **Adapter**：用 `scripts/adapter-from-client-profile.ps1` 把 CLIENT_PROFILE.md 的事实转成符合 Input Schema 的 Input JSON——已知事实标 `KNOWN`，没说清的标 `ESTIMATED/UNKNOWN`，**绝不虚构**；`UNKNOWN` 字段不会进 `answered_fields`（保证后续能继续追问）
4. **跑分析链**：调用 `invoke-requirement-analysis-analysis.ps1`（内部自动 Sufficiency → 判断是否需要追问 → Analysis）
5. **按状态分支**：
   - 信息不够（NEED_MORE_INFORMATION）→ Agent 把 `question_plan` 里的 ≤3 条问题翻译成自然语言**问你**，等你回答
   - 有冲突（CONFLICTING_INFORMATION）→ 先让你确认哪个值算数，再继续
   - 信息足够（COMPLETE / PRELIMINARY）→ 产出完整需求分析 + 独立 Eval 审查（FAIL 自动走 Repair Loop，最多 2 次）
6. **人话报告**：把最终 Output JSON 转成可读报告——需求类型、优先级（P0~P3）、每条结论的证据链；同时声明「本报告只是需求分析，不含任何产品推荐」

#### 你需要怎么配合

| Agent 问你什么 | 你怎么答都行，效果不同 |
|---|---|
| 追问（如「家庭年收入大概是多少？」）| 给准确值 → `KNOWN`；给大概值（"50 万左右"）→ `ESTIMATED`；拒绝回答 → `UNKNOWN`（该字段可能阻塞对应 Scope 分析）|
| 冲突确认（如「去年收入 80 万还是 60 万？」）| 明确说哪个为准，冲突解除后才能出正式分析 |
| 你要产品推荐 | **不会给**——这是 Skill 边界；Agent 会说明只能做需求分析，产品匹配属于后续技能 |

#### 你会看到什么结果

- **需求分析报告**：按 Scope 分组的 risk_map / 需求清单 / 保障缺口，每条带 P0~P3 优先级
- **证据链**：重要结论都能回溯到客户说过的原话（fact_refs），不是 Agent 猜的
- **状态声明**：PRELIMINARY 报告会明确标注哪些结论是初步的、缺什么字段补齐后可升级为正式结论

### 2.3 端到端示例（从「intake 完成」到「拿到报告」）

```
你：张三的 intake 刚做完，客户目录是 client-intake-data/clients/zhangsan，帮我分析保障需求
Agent：（激活 skill → 读 CLIENT_PROFILE.md → 生成合法 Input JSON → 跑分析）
Agent：目前信息只够做初步分析。要做正式分析还差 2 个关键信息：
      1. 家庭年收入大概多少？（用于寿险保额缺口判断）
      2. 有没有房贷？还剩多少年？
你：年收入大概 50 万吧，房贷还剩 15 年，差不多 200 万
Agent：（update-requirement-analysis-context.ps1 合入回答 → 重跑分析 → Eval PASS）
Agent：需求分析完成。结论：P0 = 寿险定寿需求（收入替代 + 房贷覆盖）…
      依据：年收入 50 万（ESTIMATED）、房贷 200 万/15 年（KNOWN）…
```

### 2.4 标准生产 Workflow（6 步数据流，方式 A / B 共用同一条链路）

```
Client Intake 已完成（CLIENT_PROFILE.md 存在 + intake_complete=true）
        │
        ▼
【Step 0 Adapter】scripts/adapter-from-client-profile.ps1 把 CLIENT_PROFILE.md → Input JSON（见 §2.2 / §2.5-0）
        │
        ▼
【Step 1 信息充分性】invoke-requirement-analysis-sufficiency.ps1 → 判断 analysis_status
        │
        ├── status = NEED_MORE_INFORMATION / CONFLICTING_INFORMATION
        │        │
        │        ▼
        │   【Step 2a 主动追问】invoke-requirement-analysis-questioning.ps1 → 最多 3 条高价值问题
        │        │
        │        ▼
        │   客户补充回答 → update-requirement-analysis-context.ps1 合入 Input JSON
        │        │
        │        ▼
        │   回到【Step 1】直到 analysis_status 进入 COMPLETE / PRELIMINARY
        │
        └── status = COMPLETE / PRELIMINARY
                 │
                 ▼
          【Step 2b 需求分析】invoke-requirement-analysis-analysis.ps1 → risk_map / requirements / coverage_gaps / priorities / evidence / assumptions
                 │
                 ▼
          【Step 3 独立 Eval】invoke-requirement-analysis-eval.ps1 → eval_status（PASS/FAIL）+ 5 维得分 + issues 列表
                 │
                 ├── eval_status = PASS
                 │        │
                 │        ▼
                 │   【交付】Output JSON → 交给后续技能 / 保险经纪人查看需求分析报告
                 │
                 └── eval_status = FAIL
                          │
                          ▼
                    【Step 4 Repair Loop】invoke-requirement-analysis-repair-loop.ps1 → 针对 Issue 类型做定向修复（最多 2 次）
                          │
                          ├── 修复成功且 Eval PASS → 【交付】
                          └── 仍失败 → 标记 HUMAN_REVIEW_REQUIRED → 人工复核
```

### 2.5 方式 B：PowerShell 直接调用脚本（维护者 / QA 用）

> **重要**：所有 `invoke-*.ps1` / `test-*.ps1` / `run-*.ps1` 都要用下面的显式 Bypass 形式启动。生产运行时已经内置了运行时库的强校验，但你自己手动单跑时也必须遵守，否则会继承沙箱的 Restricted Policy 导致静默失败。

```powershell
# ================================================================
# 0. Adapter：client-intake 画像 → 结构化 Input JSON（跨 Skill 唯一官方入口）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\adapter-from-client-profile.ps1 `
  -ProfilePath    ..\client-intake\examples\C009-张先生三口之家\CLIENT_PROFILE.md `
  -OutputJsonPath .\tmp\C009.input.json `
  -Scope          life,critical_illness,accident
# 参数说明：
#   -ProfilePath    client-intake 产出的 CLIENT_PROFILE.md（必填）
#   -OutputJsonPath 产出的 Input JSON（必填，UTF-8 BOM，符合 schemas/input.schema.json）
#   -Scope          可选，默认全 5 个险种；按客户真实关注点收窄可显著提升充分性
# 内置行为（不可绕过）：
#   中文表头 → RA 规范字段词表映射；❓/空 → UNKNOWN；含"约/大概/左右" → ESTIMATED
#   派生 family_responsibility / existing_life_coverage / liabilities
#   UNKNOWN 字段绝不进 answered_fields（防漏问，见 §四 常见错误）

# ================================================================
# 1. 单文件：只跑信息充分性（判断"现在够不够做分析"；不生成任何需求、不跑追问）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\invoke-requirement-analysis-sufficiency.ps1 `
  -InputJsonPath  .\evals\fixtures\unit\sufficiency\complete_info.input.json `
  -OutputJsonPath .\tmp\suff-out.json
# 典型关键字段：analysis_status（COMPLETE/PRELIMINARY/NEED_MORE/CONFLICTING/FAILED）
#                information_sufficiency.sufficiency_score（0~1，≥0.85 才算 SUFFICIENT）
#                information_sufficiency.blocking_fields（缺了这些字段就会阻塞）
#                information_sufficiency.scope_results[*].scope_status（每个 Scope 的局部状态）

# ================================================================
# 2. 单文件：跑主动追问（信息不够时，生成 ≤3 条最高优先级问题）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\invoke-requirement-analysis-questioning.ps1 `
  -InputJsonPath  .\evals\fixtures\unit\questioning\priority_selection.input.json `
  -OutputJsonPath .\tmp\quest-out.json
# 典型关键字段：question_plan.question_status（READY_TO_ASK / CONFLICT_CONFIRMATION_REQUIRED / NO_QUESTIONS_NEEDED）
#                question_plan.selected_questions[*].field / why_ask / allow_approximate

# ================================================================
# 3. 单文件：跑完整需求分析（自动先做 Sufficiency → Questioning → Analysis）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\invoke-requirement-analysis-analysis.ps1 `
  -InputJsonPath  .\evals\fixtures\unit\analysis\life_complete.input.json `
  -OutputJsonPath .\tmp\ana-out.json
# 典型关键字段：risk_map[]（risk_type / requirement_type / impact / evidence_refs）
#                requirements[]（requirement_type / priority / summary / fact_refs）
#                coverage_gaps[]（gap / requirement_type / priority / reason / evidence_refs）
#                evidence[]（evidence_id / fact_refs / reasoning / conclusion —— 结论必须能回溯到这里）

# ================================================================
# 4. 单文件：独立 Eval（分析好的 Output JSON 再跑一遍确定性审查）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\invoke-requirement-analysis-eval.ps1 `
  -AnalysisJsonPath .\tmp\ana-out.json `
  -OutputJsonPath   .\tmp\eval-out.json
# 典型关键字段：eval_status（PASS / FAIL）
#                scores（completeness / evidence_grounding / information_sufficiency / logical_consistency / product_boundary —— 每项 0~100）
#                issues[]（type ∈ MISSING_RISK/UNSUPPORTED_CONCLUSION/LOGICAL_INCONSISTENCY/INSUFFICIENT_INFORMATION/PRODUCT_RECOMMENDATION_LEAK/INVALID_OUTPUT）

# ================================================================
# 5. 单文件：Repair Loop（对 Input JSON 先分析→再 Eval→再按 Issue 定向修复，最多 2 次）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\invoke-requirement-analysis-repair-loop.ps1 `
  -InputJsonPath .\evals\fixtures\unit\analysis\life_complete.input.json `
  -OutputJsonPath .\tmp\repair-out.json
# 典型关键字段：repair_summary（final_eval_status / repair_iterations / final_status）
#                final_analysis、final_eval（完整结果）
#                repair_history[]（每次 iteration 做了哪些修复、前后 Eval 得分变化）
#                final_status = HUMAN_REVIEW_REQUIRED 时就不要自动化继续了，必须人工介入

# ================================================================
# 6. 全量回归：上生产前 / 改了任何规则 / 改了 Prompt 时必跑（15 个 Case 全覆盖）
# ================================================================
powershell -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-requirement-analysis-dataset.ps1 `
  -OutputJsonPath .\evals\fixtures\unit\dataset\dataset-report.json
# 硬性门槛：dataset-report.json 里 overall_pass_rate = 100，且 5 维均分最低不得 < 90
```

### 2.6 输入 JSON 的最低格式要求（从 Client Intake 过来时必须满足，否则 Schema 会 FAIL）

Input Schema 完整定义在 [input.schema.json](file:///D:/Workspace/insurance-agent/schemas/input.schema.json)。生产环境调用前**先用 Phase 1 Schema Test 单测跑一下输入文件是否合法**，否则分析脚本会直接抛强错误：

```powershell
# 把你要跑的客户输入 JSON 路径写到 input.valid.json（或改名）里，然后：
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\test-requirement-analysis-schema.ps1
# 必须出现 [PASS] input.valid，否则这个 Input 不合法，不能继续跑后续分析
```

最低必需字段（少一个 Schema 就直接 FAIL）：

| 字段 | 作用 | 合法值示例 |
|---|---|---|
| `source.skill` | 上游是谁（用于追溯）| `client_intake` |
| `analysis_scope[]` | 这次分析哪些 Scope（至少 1 项）| `["life", "savings"]`；必须在 `[medical, critical_illness, accident, life, savings]` 里 |
| `client_profile.facts[].field` | 客户事实字段名 | 如 `annual_income` |
| `client_profile.facts[].value_status` | 四态之一（少枚举会 FAIL）| `KNOWN / UNKNOWN / ESTIMATED / ASSUMED` |
| `question_context` | 必须存在，即使是空列表 | 至少 `{ "asked_questions": [], "answered_fields": [] }` |
| `metadata.client_alias` / `client_id` | 用于审计与回归隔离 | 客户编号或别名 |
| `conflicts[]` | 显式冲突列表（没有就空数组）| `[]` |

### 2.7 analysis_status 五态含义（决定后续走哪条分支）

| analysis_status | 含义 | 典型下一步 | 对应 sufficiency.sufficiency_status |
|---|---|---|---|
| **COMPLETE** | required 全满足、无冲突、总分 ≥0.85 | 直接出完整需求分析 + evidence + priority | SUFFICIENT |
| **PRELIMINARY** | required 只缺 1~2 个 medium-impact、总分不够 0.85 但 ≥ partial 阈值 | 出"初步分析+明确标注哪些结论是 PRELIMINARY 的"，建议先把缺口补齐再交付 | PARTIAL |
| **NEED_MORE_INFORMATION** | required_high 有缺失、或总分 < partial 阈值 | 必须进入 **主动追问 → 客户补充 → merge 回 Input JSON** 循环，不能做正式分析 | INSUFFICIENT |
| **CONFLICTING_INFORMATION** | `conflicts[]` 有字段，且 Scope Rules 里把该字段标为 conflict（一般 life 的 income / mortgage / children 都是 conflict）| 必须先做 **冲突确认（Question Plan 自动进入 CONFLICT_CONFIRMATION_REQUIRED）**，让代理人再次和客户确认哪个值为准 | CONFLICTING |
| **FAILED** | 脚本内部异常 / Schema 非法 / 输出 JSON 校验失败 | 走 **人工 + Debug 流程**（通常是上游 Input JSON 非法）| —— |

---

## 三、项目里每个文件都是做什么的（全清单 + 典型修改场景）

### 3.1 总览目录树（v1.0 架构，全部可追溯）

```
d:\Workspace\insurance-agent
├── .trae
│   ├── internal
│   │   ├── diag-ra-runner-update.ps1   ← DEBUG ONLY：调试多轮 update 合并链路
│   │   └── diag-ra-sufficiency.ps1     ← DEBUG ONLY：调试 sufficiency 逐 Scope 打分
│   └── skills
│       ├── client-intake
│       │   └── SKILL.md                 ← 【零修改保护区】上游 Client Intake 注册入口
│       └── requirement_analysis
│           └── SKILL.md                 ← 注册入口（Router），列出全部真源文档
├── requirement_analysis
│   ├── CONTRACT.md                      ← 唯一 Contract 源（Input/Output/Scope/Evidence/Boundary）
│   ├── INFORMATION_SUFFICIENCY.md       ← Sufficiency 引擎说明（加权打分/blocking/conflict）
│   ├── QUESTIONING.md                   ← 主动追问策略说明（优先级公式/少问/多轮去重）
│   ├── ANALYSIS.md                      ← 需求分析生成规则（Risk→Gap→Priority→Evidence 链路）
│   ├── EVAL.md                          ← 独立 Eval 规则（6 Issue Taxonomy + 5 维打分）
│   ├── REPAIR.md                        ← Repair Loop 策略（5 类定向修复 + MAX_RETRY=2）
│   ├── DATASET.md                       ← 15 个 Dataset Case 的三类场景说明
│   ├── USAGE_GUIDE.md                   ← 本文档（你现在读的就是）
│   ├── config
│   │   ├── information-sufficiency.rules.json  ← 5 Scope 的 required/recommended/optional + impact + weight
│   │   └── question-generation.rules.json      ← 追问优先级公式（importance/impact/gap_type/difficulty/repeat_penalty）
│   ├── schemas
│   │   ├── input.schema.json            ← Input JSON Schema（上游 Adapter 必须严格对齐）
│   │   ├── output.schema.json           ← Output JSON Schema（给后续技能消费）
│   │   └── eval-output.schema.json      ← Eval Output Schema（CI/CD 消费）
│   └── tests
│       ├── schema/                      ← 4 个 Schema 单测（input.valid/invalid × output.valid/invalid）
│       ├── sufficiency/                 ← 5 个 Sufficiency 单测（complete/low/high/multi/conflict）
│       ├── questioning/                 ← 4 个 Questioning 单测（priority/no_repeat/multi_turn/conflict）
│       ├── analysis/                    ← 4 个 Analysis 单测（life_complete/life_preliminary/need_more/multi_scope）
│       └── dataset/
│           ├── requirement-analysis.dataset.json  ← 15 个正式回归 Case（三类场景全覆盖）
│           └── dataset-report.json      ← 最近一次全量回归报告（15/15 PASS 才能上生产）
└── scripts
    ├── lib
    │   └── requirement-analysis-runtime.ps1   ← 【统一运行时】Bypass 启动 + Output JSON 强校验（PR-P01）
    ├── invoke-requirement-analysis-sufficiency.ps1    ← Phase 2 引擎
    ├── invoke-requirement-analysis-questioning.ps1    ← Phase 3 引擎
    ├── invoke-requirement-analysis-analysis.ps1       ← Phase 4 引擎
    ├── invoke-requirement-analysis-eval.ps1           ← Phase 5 引擎（独立）
    ├── invoke-requirement-analysis-repair-loop.ps1    ← Phase 6 引擎（Repair Loop）
    ├── update-requirement-analysis-context.ps1        ← 把客户补充回答合入 Input JSON
    ├── run-requirement-analysis-dataset.ps1           ← Phase 7 统一回归 Runner（15 Case）
    ├── test-requirement-analysis-schema.ps1           ← Phase 1 测试
    ├── test-requirement-analysis-sufficiency.ps1      ← Phase 2 测试
    ├── test-requirement-analysis-questioning.ps1      ← Phase 3 测试
    ├── test-requirement-analysis-analysis.ps1         ← Phase 4 测试
    ├── test-requirement-analysis-eval.ps1             ← Phase 5 测试
    └── test-requirement-analysis-repair-loop.ps1      ← Phase 6 测试
```

### 3.2 注册入口层（Skill Router）—— [SKILL.md](file:///D:/Workspace/insurance-agent/.trae/skills/requirement_analysis/SKILL.md#L6-L24)

| 信息 | 内容 |
|---|---|
| **定位** | Trae 环境的 Skill 注册入口（frontmatter 的 `name: requirement_analysis` 与激活名严格一致）|
| **主要内容** | ① frontmatter ② 10 个真源文档/路径/报告索引 ③ Production Ready 状态（15/15 case、5 维均分 >93）|
| **什么时候需要修改？** | 极少；只有 Skill 改名、新增真源文档、或者新能力模块上线（例如加了 Recommendation Guard 模块）|

### 3.3 统一运行时（PR-P01 生产加固核心）—— [requirement-analysis-runtime.ps1](file:///scripts/lib/requirement-analysis-runtime.ps1#L1-L91)

| 函数 | 做什么 | 生产意义 |
|---|---|---|
| `Invoke-RaScriptRaw` | 用 `powershell -NoProfile -ExecutionPolicy Bypass -File <script> @args` 显式启动子脚本 | **解决核心风险**：宿主 PowerShell 继承 Restricted Policy 会让 `& $script -args` 静默失败；Bypass 显式启动就不会 |
| `Invoke-RaScriptToObject` | ① Raw 调用 ② 输出非空 ③ `ConvertFrom-Json` 成功 ④ 指定的顶层属性（如 `analysis_status`）真实存在 | 防"看起来跑了其实 Output 空了"的静默失败；一旦少顶层属性直接抛明确错误 |
| `Invoke-RaScriptToFile` | ① Raw 调用 ② Output 文件存在 ③ 大小 ≥ MinSizeBytes 阈值 ④ JSON 可解析 | 防"脚本说写了 Output 其实只写了 20 字节空壳"的边界 |

> 原则：维护期**不要**把 `Invoke-RaScriptToObject` 又改回直接 `& $子脚本 | Out-String`——那样会把 PR-P01 的所有加固都废弃，生产会回到 ExecutionPolicy 静默失败的老问题。

### 3.4 配置层（改规则只改这里，分析引擎不用动）

#### 3.4.1 信息充分性规则 —— [information-sufficiency.rules.json](file:///D:/Workspace/insurance-agent/resources/config/information-sufficiency.rules.json#L14-L120)

每个 Scope（life/accident/medical/...）都写三段：
- `required`：缺了就会阻塞分析；impact = high 时直接进入 NEED_MORE_INFORMATION；impact = medium 进入 PARTIAL/PRELIMINARY
- `recommended`：不阻塞但会拉低 sufficiency_score，用于触发追问
- `optional`：只加分不扣分

**典型修改场景**：决定「分析 life 时，spouse_income 以后必须是 required high」→ 改 life.required 里 spouse_income 的 weight / impact，跑完 Dataset 回归仍然 15/15 才能合入。

#### 3.4.2 追问优先级规则 —— [question-generation.rules.json](file:///D:/Workspace/insurance-agent/resources/config/question-generation.rules.json)

每条字段规则含：`why_ask`（自然语言理由，用于 why_ask 字段）、`base_priority_weight`、`gap_type_bonus`、`repeat_penalty`、`allow_approximate`、`short_question_text`。

**典型修改场景**：客户反馈「问 assets 的方式太生硬」→ 改 assets 对应的 `short_question_text`，然后跑 Phase 3 Questioning Test，确保 naturalness（目前用 selected_questions[*].question 长度 + 机械重复断言做基础验证）仍然通过。

### 3.5 引擎层（5 个独立引擎，职责单一，SRP）

| 文件 | 输入 | 输出 | 典型修改时机 |
|---|---|---|---|
| [sufficiency.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-sufficiency.ps1) | Input JSON + rules JSON | analysis_status、sufficiency（per-Scope 得分 / blocking / conflict）、information_gaps[] | 加了新的 Scope（例如 annuity / pension / health_cash）→ 加规则 + 加引擎分支 |
| [questioning.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-questioning.ps1) | Input JSON | question_plan（question_status + selected_questions ≤3）| 调整追问上限（例如 ≤2 或 ≤5）、改冲突确认优先级排序 |
| [analysis.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-analysis.ps1#L399-L450) | Input JSON | risk_map / requirements / coverage_gaps / priorities / evidence / assumptions | 新增需求类型（例如 `INCOME_REPLACEMENT_NEED`）→ 改 Build-XXXAnalysis 分支 + 加 evidence_id 生成规则 |
| [eval.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-eval.ps1) | Analysis Output JSON | eval_status + 5 维 scores + issues[] | 发现新的高风险反模式 → 加 Issue Type，并在 Dataset 里补 mutated_eval Case 回归 |
| [repair-loop.ps1](file:///D:/Workspace/insurance-agent/scripts/invoke-requirement-analysis-repair-loop.ps1#L217-L244) | Input JSON 或 Existing Analysis JSON | final_analysis + final_eval + repair_summary + repair_history | 需要加一类定向修复（例如 "sync_conflicts_with_evidence"）→ 在 Apply-TargetedRepairs 里加分支 + MAX_RETRY 仍然 ≤2 |
| [update-context.ps1](file:///D:/Workspace/insurance-agent/scripts/update-requirement-analysis-context.ps1) | Input JSON + Update JSON（answered_facts / asked_questions / resolved_conflict_fields）| 新的 Input JSON | 改 merge 规则（例如空 value_status 不再覆盖 KNOWN）|

### 3.6 测试与回归层（必须全绿才能上生产）

| 测试脚本 | 覆盖 Phase | Case 数 | 必须通过的最低门槛 |
|---|---|---|---|
| [Schema Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-schema.ps1) | Phase 1 | 4 | 2/2 PASS + 2/2 EXPECTED FAIL（Schema 既接受合法也拒绝非法）|
| [Sufficiency Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-sufficiency.ps1) | Phase 2 | 5 | 5/5 PASS（每 case analysis_status 与 sufficiency_status 严格匹配）|
| [Questioning Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-questioning.ps1) | Phase 3 | 4 | 4/4 PASS（priority/no_repeat/multi_turn/conflict）|
| [Analysis Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-analysis.ps1) | Phase 4 | 4 | 4/4 PASS（complete/preliminary/need_more/multi_scope）|
| [Eval Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-eval.ps1) | Phase 5 | 6 | 6/6 PASS（baseline_pass + 5 类 FAIL 场景）|
| [Repair Loop Test](file:///D:/Workspace/insurance-agent/scripts/test-requirement-analysis-repair-loop.ps1) | Phase 6 | 4 | 4/4 PASS（unsupported_conclusion/missing_risk/product_leak/human_review）|
| [Dataset Runner](file:///D:/Workspace/insurance-agent/scripts/run-requirement-analysis-dataset.ps1) | Phase 7 | 15 | **15/15 PASS、overall_pass_rate=100**（硬性门槛，缺一不可）|

### 3.7 Dataset 15 Case 三类场景覆盖

三类场景详见 [DATASET.md](file:///D:/Workspace/insurance-agent/evals/eval-policy.md)：

| 类型 | Case 数 | 含义 | 典型代表 |
|---|---|---|---|
| `analysis_only` | 6 | 信息本身就足够，直接跑 analysis → eval 应当 PASS | RA_DS_001（life complete）、RA_DS_002（savings complete）|
| `multi_turn_update` | 3 | 首轮信息不足，经 updates 合并后补齐，analysis_status 应进入 PRELIMINARY | RA_DS_007（savings multi）、RA_DS_008（life multi）|
| `mutated_eval` | 6 | 信息本身 complete，但在 analysis 上做定向破坏（清空 evidence_refs / 清空 risk_map / 注入产品语言…）→ Eval 应当 FAIL + Repair Loop 能修好 | RA_DS_010 ~ RA_DS_015（6 类 Issue 各 1 个专项）|

---

## 四、常见错误 + 处理办法（维护者必读）

| 错误现象 | 最常见根因 | 一步处理 |
|---|---|---|
| 跑任何 invoke 脚本都没报错，但是 Output JSON 只有 20 字节或者根本不存在 | 宿主 PowerShell 继承了 Restricted Policy，`& $子脚本` 静默失败 | 必须用 `powershell -NoProfile -ExecutionPolicy Bypass -File <script>`；本仓库的 Phase7+统一运行时已经这么做了，但你手写单跑时也要遵守 |
| Schema Test 报 `$.client_profile.facts[0].value_status must be one of [KNOWN, UNKNOWN, ESTIMATED, ASSUMED]` | 上游 Adapter 写了别的状态（如 "CONFIRMED"）| 改 Adapter 输出为四态枚举；不要直接改 Schema 放水 |
| Dataset 某 case 报 `actual_status = NEED_MORE_INFORMATION`，但你明明以为 required 都齐了 | 信息充分性 rules 仍把某个字段标为 impact=high required（例如 life 的 spouse_income 是 required high，你以为补了其实没补 value_status=KNOWN）| 用 `.trae/internal/diag-ra-sufficiency.ps1 -CaseId XXX -ApplyUpdates` 打印 per-Scope 的 blocking_fields 与 scope_score，就能看到缺哪一个（debug 仅在本地 `.trae/internal/` 用，别进生产）|
| Repair Loop 一直返回 HUMAN_REVIEW_REQUIRED | MAX_RETRY=2 内 Issue 没被修复（通常是 Eval 里加了全新 Issue Type，还没对应 Targeted Repair 分支）| ① 看 final_eval.issues 是哪类 Issue ② 在 repair-loop.ps1 的 Apply-TargetedRepairs 里加对应分支 ③ 补 1 个 mutated_eval Case 到 Dataset，确保 15/15 再上 |
| Eval 报 `PRODUCT_RECOMMENDATION_LEAK` 但你觉得分析内容里没有产品名 | Runner 侧正式判定以 Eval 的 PRODUCT_RECOMMENDATION_LEAK 为准；关键词可能是 "buy / company / product plan / policy / 保险公司 / 购买 / 产品推荐 / 保单" 等短语 | 去 requirements[].summary 里删除这类表述；真正交付只能写 "需要 XXX 类保障（需求）"，不能写 "建议买 XXX 产品" |
| 想改规则但怕影响回归 | 人很容易低估规则修改的 ripple effect（例如把 life.required 的一个 medium 提到 high，会让多个 multi_turn 与 mutated_eval Case 的 status 预期失配）| 先改 rules，再单独跑一次 Dataset 回归，15/15 才能合并；只要有 1 个 FAIL 就先修 Case 的 expectations（语义必须变）或修规则（不要为过 Case 直接改阈值降级）|

---

## 五、与 Client Intake 的协作说明（跨 Skill 协作硬约束）

1. **零修改原则**：`requirement-analysis` 绝对不能改 `.trae/skills/client-intake/**`、`client-intake-data/**`、`test-cases/client-intake/**`、`scripts/run-regression.ps1`。发现必须改这些地方才能跑通时，**停下并报告**，不要私自改 Client Intake 的 Prompt/Schema/测试。
2. **字段不匹配走 Adapter**：Client Intake 的 Confirmed Facts 是 Markdown 表格（年龄/收入/支出/家庭结构等），Requirement Analysis 的 Input 是结构化 JSON（facts[].field + facts[].value_status）。两者不一致时走官方 Adapter 脚本 `scripts/adapter-from-client-profile.ps1`（映射表内置在 `requirement-analysis` 自己的代码里），而不是修改 Client Intake 的输出格式，也不要每次由 Agent 临时手写映射。
3. **输入合法性前 Check**：进入需求分析前，Client Intake 必须 `intake_complete=true`（或显式走 "PRELIMINARY 协作模式"——即 Client Intake 只满足最低完成标准，需求分析允许 PRELIMINARY 输出）。
4. **分析结果回写**：目前 Requirement Analysis 不回写 Client Profile；长期真源仍然只有 `CLIENT_PROFILE.md / PENDING.md / CONVERSATION_LOG.md`。如果以后要做回写，必须单独走 Client Intake 侧的 Handoff 契约修改流程，先在 Client Intake Handoff Notes 区段定义可写字段再接入。

---

## 六、生产上使用的 "最低合规清单"（每次上生产前逐条核对）

- [ ] Phase 1 Schema Test：4/4 PASS
- [ ] Phase 2 Sufficiency Test：5/5 PASS
- [ ] Phase 3 Questioning Test：4/4 PASS
- [ ] Phase 4 Analysis Test：4/4 PASS
- [ ] Phase 5 Eval Test：6/6 PASS
- [ ] Phase 6 Repair Loop Test：4/4 PASS
- [ ] Phase 7 Dataset Runner：15/15 PASS（overall_pass_rate=100）
- [ ] 5 维 Eval 均分最低维 ≥ 93（当前：Completeness 93.33 · Evidence Grounding 96.33 · Information Sufficiency 100 · Logical Consistency 100 · Product Boundary 97.33）
- [ ] Client Intake Protection Report：Modified/Schema/Prompt/Tests/Behavior 全 5 项 NO
- [ ] IDE GetDiagnostics：0 错误 / 0 警告

满足以上 10 条即可把 `requirement-analysis` Skill 作为正式生产能力投入使用 ✅
