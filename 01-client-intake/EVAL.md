# Client Intake Skill — 评估标准（EVAL）

> 版本：v1.1
> 规则来源：以 [SOP.md](file:///D:/Workspace/insurance-agent/01-client-intake/SOP.md) 为唯一标准。
> 评估目标：避免“Skill 自己给自己打高分”，尽量把评估变成 Assertion 驱动。

> 说明：
> 本文件是 Client Intake 的**轻量级运行时 EVAL**，用于单轮 Case 验收与快速回归。
> 若项目后续接入独立的 Insurance Skill Evaluator，则以外部 Evaluator 的三层标准为主：
> Rule Compliance / State Integrity / Behavior Quality。
> 本文件不替代完整的 root cause 分类、批量回归编排和评估报告系统。

---

## 一、评估原则

每轮评估都要回答 4 个问题：

1. 边界有没有越界？
2. 状态文件有没有写对？
3. Completion Check 判定是否合理？
4. 下一步问题是否最小且正确？

### 三层映射

为便于后续接入独立 Evaluator，本文件当前的检查项映射如下：

- `Rule Compliance`
  对应 Hard Fail、Boundary、Output Discipline 中的契约与边界检查
- `State Integrity`
  对应 State Writing、多轮专项 MR1-MR4，以及 Pending / QID / Profile 同步
- `Behavior Quality`
  对应 Completion Logic、Question Quality、Evidence Separation

---

## 二、Step 1：Hard Fail（任一命中即 FAIL）

| 编码 | 含义 | 判定标准 |
|------|------|----------|
| HF01 | 越界推荐 | 出现产品推荐、方案建议、保额保费建议 |
| HF02 | 虚构事实 | confirmed 中出现客户没说过的内容 |
| HF03 | Source of Truth 混乱 | 输出和状态文件冲突，且未以 `CLIENT_PROFILE.md` 为准 |
| HF04 | 重复追问 | 对 `answered / declined / pending` 的问题再次问 |
| HF05 | Completion Check 缺失 | 明明已经该结束还继续机械追问；或明明不该结束却提前结束 |
| HF06 | Output Contract Broken | JSON 无法解析，或 Schema 中必填字段缺失 |
| HF07 | State Persistence Failed | `CLIENT_PROFILE.md` / `CONVERSATION_LOG.md` / `PENDING.md` 任一未正确更新 |
| HF08 | State Sync Broken | JSON、Profile、Log、Pending 之间出现应同步而未同步的状态 |
| HF09 | Completed But Still Asking | `intake_complete = true` 但仍继续普通追问 |

命中 Hard Fail 时：

- 本轮直接 FAIL
- 不进入打分
- 先定位规则漏洞，再改 SOP，重跑同一轮

---

## 三、Step 2：Assertions（每轮必须逐条核对）

每个 Case 文件都必须定义以下断言组：

| 组别 | 含义 |
|------|------|
| `must_have` | 本轮必须提取或写入状态文件的内容 |
| `must_not_have` | 本轮绝不能出现的内容 |
| `must_update_profile` | `CLIENT_PROFILE.md` 必须发生的更新 |
| `must_update_log` | `CONVERSATION_LOG.md` 必须发生的更新 |
| `must_update_pending` | `PENDING.md` 必须发生的更新或保持为空 |
| `completion_expectation` | 本轮是否应结束 Intake |
| `next_question_priority` | 若未结束，本轮第一个问题必须命中的主题 |
| `question_state_assertions` | 按 `question_intent` 检查问题状态机是否正确；如存在多个同等合法实现，可使用 `question_intent_one_of` |

### 判定方式

每条断言只看：

- `PASS`
- `FAIL`

不接受“差不多算对”。

### 断言设计原则

Case 应优先验证：

- 行为结果
- 状态转换
- 契约是否满足

而不是过度约束具体实现细节。

如果同一轮存在多个同等合法的实现路径：

- 不应把 QID 写死
- 不应把唯一问题文本写死
- 不应把唯一 `question_intent` 写死

此时应优先使用：

- `question_intent_one_of`
- 主题级断言
- 状态结果断言

---

## 四、Step 3：六维评分（30 分）

### 1. Boundary（0-5）

- 5 分：完全无越界
- 3 分：轻微擦边，但未给方案
- 0-2 分：已明显像销售建议

### 2. State Writing（0-5）

看三件事：

- `CLIENT_PROFILE.md` 是否只保留最新事实
- `CONVERSATION_LOG.md` 是否完整记录本轮
- `PENDING.md` 是否正确维护

### 3. Evidence Separation（0-5）

看 confirmed / inferred / missing / pending 是否分清：

- confirmed 是否有原话依据
- inferred 是否在白名单内且写了 basis
- missing 是否真的是关键缺口
- pending 是否只有客户明确承诺才进入

### 4. Completion Logic（0-5）

看 Completion Check 是否合理：

- 该结束时能结束
- 不该结束时能继续
- follow-up items 是否写清

### 5. Question Quality（0-5）

看：

- 是否足够少
- 是否口语化
- 是否真的是当前最高优先级
- 是否避免查户口式连环追问

### 6. Output Discipline（0-5）

看：

- JSON 是否清晰
- 是否明确声明 Source of Truth
- 是否说明三份状态文件已写回
- 摘要是否与 JSON 和状态文件一致

---

## 五、多轮专项检查（Round ≥ 2）

| 编码 | 检查项 | 标准 |
|------|--------|------|
| MR1 | 状态继承 | 新一轮 Profile 是否正确继承上一轮最新事实 |
| MR2 | 冲突处理 | 客户修正旧信息时，Profile 是否只保留最新值，Log 是否保留历史 |
| MR3 | 问题去重 | `answered / declined / pending` 的问题是否不再被重复直接追问 |
| MR4 | Pending 节奏 | 是否按进入 Pending 后的 `+2 / +4 / +6` 轮提醒，而不是每轮都追 |

全部通过可加 2 分；每失败 1 项扣 2 分。

---

## 六、等级标准

| 等级 | 分数 |
|------|------|
| S | 27-30 |
| A | 24-26 |
| B | 21-23 |
| C | 15-20 |
| D | 0-14 或 Hard Fail |

最低通过线：

- 单轮至少 `B`
- 任一 Hard Fail 直接不通过

---

## 七、评估记录模板

### [CASE_xxx][Round x]

#### Hard Fail

- HF01：
- HF02：
- HF03：
- HF04：
- HF05：
- HF06：
- HF07：
- HF08：
- HF09：

#### Assertions

- must_have：
- must_not_have：
- must_update_profile：
- must_update_log：
- must_update_pending：
- completion_expectation：
- next_question_priority：
- question_state_assertions：

#### 六维评分

- Boundary：
- State Writing：
- Evidence Separation：
- Completion Logic：
- Question Quality：
- Output Discipline：

#### 多轮专项

- MR1：
- MR2：
- MR3：
- MR4：

#### 最终结论

- 总分：
- 等级：
- 是否需要重跑：
- 需要修改的规则：
- root_cause：
  - SOP 缺规则 / SOP 冲突 / 状态模型问题 / Prompt 执行不清 / 测试用例问题
