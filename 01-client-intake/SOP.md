# Client Intake Skill — 标准操作手册（SOP）

> 版本：v1.1
> 状态：按长期可运行 Agent 结构重构
> 本文件是 Client Intake Skill 的唯一规则来源。入口、状态文件、评估、测试案例均以本文件为准。

---

## 一、定位与边界

### 1.1 Skill 定位

Client Intake 是一个**客户上下文标准化 Skill**。

它的目标不是推荐保险，也不是做方案，而是把客户零散输入整理成一个可持续更新的标准化客户上下文，供后续 `Needs Analysis` 使用。

### 1.2 严格边界

可以做：

- 提取客户明确说过的事实
- 在白名单范围内生成 inferred
- 识别关键缺口与 pending
- 判断是否已经可以结束 Intake
- 生成最少量、最高优先级的自然追问

不可以做：

- 推荐产品、比较产品、计算保额保费
- 用医学语言评价健康风险轻重
- 把 inferred 当 confirmed
- 让 JSON 输出变成第二份客户数据库

客户一开始就问产品时，统一回复：

> "可以的。不过为了不给您判断偏了，我先把您的情况了解清楚，确认几个关键点，再进入分析，会更准确一些。"

---

## 二、文件结构与 Source of Truth

### 2.1 目录结构（v1.2 多客户并行版）

```text
.trae/skills/client-intake/SKILL.md   ← 入口（新增 Step 0：客户上下文切换）

01-client-intake/
├── SOP.md                            ← 规则唯一源（所有客户共享，不存客户数据）
├── EVAL.md
├── USAGE_GUIDE.md
├── runs/                             ← 执行快照（回归报告 / 多轮沙箱 / 注册入口实跑）
└── clients/                          ← ★ 多客户隔离根目录（每位客户 = 一个独立子文件夹）
    ├── INDEX.md                      ← ★ 客户索引（所有客户的元数据清单：编号/别名/当前轮次/完成状态/最近更新）
    ├── C001-张三三口之家/
    │   ├── CLIENT_PROFILE.md         ← 客户 1 的唯一长期状态源
    │   ├── CONVERSATION_LOG.md       ← 客户 1 的对话历史 + QID 注册表
    │   └── PENDING.md                ← 客户 1 的待补资料 + 提醒节奏
    ├── C002-李姐企业主/
    │   ├── CLIENT_PROFILE.md         ← 客户 2 的唯一长期状态源（完全独立，和 C001 没有任何共享字段）
    │   ├── CONVERSATION_LOG.md
    │   └── PENDING.md
    └── C003-王哥高净值家庭/...       ← 以此类推，新建客户自动分配下一个 C{nnn}

test-cases/
└── client-intake/
    ├── CASE_001.md ~ CASE_008.md
```

#### 2.1.1 `clients/INDEX.md` 固定格式（所有新增 / 切换客户都以这里为唯一真源）

```markdown
# Client Intake 客户索引（INDEX）

> 本文件由 Skill 的 Step 0-A（新客户创建）/ Step 9（写回轮次）自动维护，禁止手动改内容。
> 只有这 3 种情况会写 INDEX：新客户创建 / 每轮状态写回后轮次 +1 / Completion Gate true 时标记已完成。

| 行号 | 客户编号 | 客户别名            | 档案目录（相对路径）           | 创建时间   | 当前轮次 | Intake 完成状态 | 最近更新   | 备注 |
|------|----------|---------------------|--------------------------------|------------|----------|-----------------|------------|------|
| 1    | C001     | 张三三口之家        | clients/C001-张三三口之家/    | 2026-09-06 | R2       | ✅ 已完成       | 2026-09-06 |      |
| 2    | C002     | 李姐企业主          | clients/C002-李姐企业主/      | 2026-09-07 | R1       | ❌ 未完成       | 2026-09-07 |      |
```

### 2.1.2 向后兼容 & 根目录遗留文件说明

根目录 `01-client-intake/` 下现在仍存在的 `CLIENT_PROFILE.md / CONVERSATION_LOG.md / PENDING.md` 三份文件是 v1.0/v1.1 单客户架构遗留产物，**多客户并行模式（v1.2+）下它们是「空壳占位」，绝对禁止写入**。所有客户数据只进 `clients/C00{nn}-{别名}/` 独立目录。

---

### 2.2 状态唯一性原则（多客户并行版）

**先确定客户上下文，再读状态文件是第一优先级（Step 0 > 所有 10 步）。**

`clients/C00{nn}-{别名}/CLIENT_PROFILE.md` 是**该客户唯一长期状态源**，和其它客户的文件严格隔离、互不影响。

规则如下：

0. **（新：Step 0 强制执行）** 任何执行前先跑 SKILL.md §Step 0 客户上下文切换逻辑确定客户目录；4 种触发顺序：
   - ① Prompt 里明确写了 `【客户 ID】/【客户别名】` → 直接用
   - ② 对话记忆里存在「上一次用的客户」且本轮没说要切客户 → 默认继续用
   - ③ Prompt 说「新客户 / 新建」→ Step 0-A 建新客户
   - ④ 都不满足 → Step 0-B 先问「新客户 or 已有客户」，不得擅自推断
1. 确定客户后，必须按以下固定顺序读取，不得跳过：
   - `SOP.md`（全客户共享规则）
   - `clients/<当前客户目录>/CLIENT_PROFILE.md`
   - `clients/<当前客户目录>/CONVERSATION_LOG.md`
   - `clients/<当前客户目录>/PENDING.md`
2. 读取完成后，以该客户目录下：
   - `CLIENT_PROFILE.md` 判断当前客户事实
   - `CONVERSATION_LOG.md` 判断历史问题状态
   - `PENDING.md` 判断待补资料及提醒节奏
3. 本轮新输入先与该客户的 `CLIENT_PROFILE.md` 合并，再决定后续动作
4. `CONVERSATION_LOG.md`（客户目录下）只保存该客户问答历史和 QID 注册表，不作为长期事实源
5. `PENDING.md`（客户目录下）只保存该客户答应补的资料和提醒节奏，不混入客户事实
6. JSON 输出仅是**本轮该客户执行结果**，不是下一轮的输入来源
7. 如果 JSON 与状态文件冲突，以「客户目录下的 3 份」为准（Client > Pending > Log > JSON）
8. **当前 Round 的唯一判断有 2 个独立来源互相对照（防止跳轮次）：**
   - ① `clients/INDEX.md` 中该客户行的「当前轮次」字段（由 Skill Step 9 写回，官方权威）
   - ② 该客户自己的 `CONVERSATION_LOG.md` 中最后一个已记录 Round
   - 如果两者不一致 → 本轮先按 INDEX 的为准，执行完 Step9 后同时把两者同步一致
9. **（新：不变量 I8——多客户数据隔离）** 执行客户 C00{aa} 时，任何读写操作不得触碰 C00{bb}（bb≠aa）的目录，哪怕 C00{bb} 的内容和本轮话题很像。

### 2.3 三份状态文件分工（都在客户目录下）

| 文件（相对 `01-client-intake/clients/C00{nn}-{别名}/` 路径）| 职责 | 读者 |
|------|------|------|
| `CLIENT_PROFILE.md` | 该客户当前最新画像、白名单 inferred、缺口摘要、完成状态。Needs Analysis 等后续 Skill **只读这份**。 | 后续 Skill + 当前 Skill |
| `CONVERSATION_LOG.md` | 该客户历史轮次原文、Asked Questions Registry、每轮状态变更记录（QID 状态转换/Conflict Notes）。只用于多轮记忆 & 追溯，不作为长期事实。 | 当前 Skill |
| `PENDING.md` | 该客户答应补的保单/资料/数据；提醒节奏（进入 Pending 的轮次 +2/+4/+6，最多 3 次）；三态与 QID 同步规则（received→answered / declined→declined / expired→ignored）。 | 当前 Skill |

---

## 三、信息类型定义

### 3.1 Confirmed

客户明确说过，且能在客户原话里找到依据的事实。

每个 confirmed 叶子必须记录：

- `value`
- `source_round`
- `source_text`

### 3.2 Inferred

inferred 必须保留，因为它负责做**事实与推断分离**。

但 inferred 不是自由发挥，必须同时满足：

1. 由多个 confirmed 之间的直接逻辑关系推出
2. 不涉及医学判断
3. 不涉及保险方案判断
4. 不改变任何 confirmed 数据
5. 必须写出 `basis`

允许的 inferred 白名单只有以下 5 类：

1. 家庭收入依赖关系
2. 赡养责任关系
3. 收入稳定性趋势
4. 已知负债导致的责任压力
5. 信息之间明确的逻辑关系

明确禁止的 inferred：

- 性格判断
- 消费习惯判断
- 风险偏好判断
- 健康严重程度判断
- 职业稳定性脑补
- 客户购买意愿判断

### 3.3 Missing

当前进入 Needs Analysis 所需、但尚未获得的信息。

Missing 不等于所有未提信息，而是**当前阶段仍然关键的缺口**。

### 3.4 Pending

客户已经明确答应后补，但本轮没给的资料。

Pending 永远写进 `PENDING.md`，不要写进 `CLIENT_PROFILE.md`。

---

## 四、Intake 最低完成标准

### 4.1 Hard Required

进入 Needs Analysis 的最低要求：

| 编码 | 内容 | 最低要求 |
|------|------|----------|
| H1 | 年龄 | 明确数字 |
| H2 | 城市 | 到市级 |
| H3 | 职业 | 足够判断职业类别 |
| H4 | 家庭责任结构 | 已明确婚姻/子女等主要家庭责任；并能够判断是否存在他人明显依赖本人收入。若不存在相关责任，也可明确记录“当前未发现明显家庭经济依赖关系” |
| H5 | 收入 | 本人收入，配偶如有收入也需大致知道 |
| H6 | 家庭年支出 | 至少有范围 |

### 4.2 Soft Required

这些尽量收，但不阻塞结束 Intake：

- 配偶详细信息
- 父母健康与赡养细节
- 负债细节
- 现有保障细节
- 客户本人健康细节
- 核心风险关注点

### 4.2.1 H4 判定规则

H4 不要求机械收集完整家庭成员信息。

只要当前信息足以判断：

1. 是否存在配偶
2. 是否存在需要承担主要经济责任的子女
3. 是否存在明显依赖本人收入的家庭成员

即可满足。

若客户明确表示：

- 未婚
- 无子女
- 无需赡养父母

则可以视为 H4 满足。

H4 不是单一事实字段，而是基于 Confirmed Facts 与允许的家庭责任关系 inferred 的综合判断。

H4 满足时，必须在 `Completion Status` 的说明中写明判断依据。

### 4.3 Completion Check

每轮完成 Gap Analysis 后，必须先执行 Completion Check，再决定是否继续追问。

满足以下条件时，`intake_complete = true`：

1. H1-H6 已达到进入 Needs Analysis 的最低要求
2. 不存在完全空白的重大阻塞项
3. `CLIENT_PROFILE.md` 已经足够支撑下一阶段做需求分析

一旦 `intake_complete = true`：

- 停止继续追问一般信息
- `next_questions` 可为空
- 输出 `"基础信息收集已完成，可以进入 Needs Analysis"`
- 把仍待补的项目写入 `follow_up_items`，而不是继续强追

### 4.4 Intake 完成后的 Missing 转移规则

当 `intake_complete = true` 时：

1. 所有仍会阻塞 Needs Analysis 的 `Critical Missing Items` 必须为空
2. 原属于 Soft Required 的未获取信息：
   - 不再记录在 `Critical Missing Items`
   - 统一转入 `Follow-up Items`
3. `CLIENT_PROFILE.md` 中：
   - `Critical Missing Items` 应为空
   - `Follow-up Items` 保存后续可补充的信息

---

## 五、问题优先级规则

不使用权重计算，不写 50/30/20。

只用离散规则：

| 优先级 | 规则 |
|--------|------|
| `P0` | 如果缺失会导致无法进入下一阶段，必须优先问 |
| `P1` | 对家庭责任或风险判断影响大，且回答成本低 |
| `P2` | 重要，但可以下一轮再问 |
| `P3` | 需要找资料、高成本获取、适合后补 |

每轮问题选择顺序：

1. 先看 `P0`
2. `P0` 没有时再看 `P1`
3. 然后 `P2`
4. `P3` 默认延后，不主动占据本轮名额

单轮提问规则：

- 最多 3 个
- 一问一个点
- 口语化，不像表单
- 优先回答成本最低的问题
- 已在 `Asked Questions Registry` 中标记 `answered / declined / pending` 的，禁止重复问

### 5.1 Asked Questions 状态定义

- `unanswered`
  已提出，客户尚未回应

- `answered`
  客户已明确回答，不得重复问

- `declined`
  客户明确拒绝回答，不得重复问

- `pending`
  客户明确承诺后续补充，不得重复直接追问，按 Pending 节奏提醒

- `ignored`
  客户未回答且转向其他话题，可在后续轮次重新提问，但不得连续两轮重复同一问题

### 5.2 Ignored 处理规则

同一 QID：

1. 第一次被忽略后，可在后续轮次重新提问
2. 不得连续两轮重复同一问题
3. 连续被 ignored 2 次后，自动降级优先级
4. 若该问题属于 P0 Hard Required，则不降级，但提问方式必须调整得更自然、更短

### 5.3 Pending 与 QID 关联规则

当一个已有 QID 的问题被客户明确承诺后补时：

1. 原 QID 状态更新为 `pending`
2. 在 `PENDING.md` 创建对应 Pending Item
3. Pending Item 必须记录 `related_qid`
4. 后续提醒不得创建新的 QID
5. 提醒行为仍视为对原 QID 的跟进
6. 客户提供资料后：
   - Pending Item 更新为 `received`
   - `related_qid` 更新为 `answered`
7. 客户明确拒绝提供：
   - Pending Item 更新为 `declined`
   - `related_qid` 更新为 `declined`
8. Pending 超过最大提醒次数后：
   - Pending Item 更新为 `expired`
   - `related_qid` 更新为 `ignored`
   - 不再主动提醒

补充规则：

若客户在**未被当前轮次显式追问**的情况下，主动承诺后续补某项资料，例如：

- “保单我晚点发你”
- “我回头把体检报告找给你”

也允许直接创建 `Pending Item`。

此时：

1. 可以直接在 `PENDING.md` 新增条目
2. 若需要统一追踪，可同步新增一个对应的 `Question Intent`
3. 该记录用于状态跟踪，不视为“重复追问”
4. 后续提醒仍不得创建新的重复 QID

### 5.4 Unanswered 与 Ignored 判定规则

- `unanswered`
  当前 QID 已提出，但尚未进入下一轮客户输入。

- `ignored`
  已进入下一轮客户输入，客户没有回答该问题，且输入内容明显转向其他信息或其他话题。

规则：

1. QID 在提出后的下一轮之前保持 `unanswered`
2. 一旦客户进入下一轮且未回答该问题：
   - 明确转向其他信息 -> `ignored`
   - 表示稍后提供 -> `pending`
   - 明确拒绝 -> `declined`
   - 已回答 -> `answered`
3. 不允许一个问题跨轮次长期保持 `unanswered`

### 5.4.1 每轮进入时的旧 QID 状态处理

处理新一轮客户输入前，必须先检查上一轮所有状态为 `unanswered` 的 QID。

逐个判断：

1. 客户明确回答 -> `answered`
2. 客户明确拒绝 -> `declined`
3. 客户承诺后补 -> `pending`
4. 客户未回答且明显转向其他信息 -> `ignored`

处理完成后，才开始本轮 Extract。

禁止存在跨越一个完整客户 Round 后仍保持 `unanswered` 的 QID。

---

## 六、标准工作流（10 步）

### Round 的定义

一次 Round = 一次新的客户输入触发的一次完整 Skill 执行。

Agent 自身的输出、状态写入或 Pending Reminder 不单独增加 Round。

所有 Pending Reminder 的 `+2 / +4 / +6`，均以客户输入 Round 为计数单位。

### Workflow Gate Rule

Step 6 Completion Check 是强制 Gate。

在 Completion Check 完成之前：

- 不得生成 `next_questions`
- 不得进入 Step 7
- 不得进入 Step 8

只有当 `intake_complete = false` 时，才允许：

- Step 7 `Prioritize`
- Step 8 `Generate Questions`

### Step 1：Resolve Previous QIDs

在处理本轮客户输入之前，必须先清算上一轮所有状态为 `unanswered` 的 QID。

处理规则：

1. 客户已明确回答 -> `answered`
2. 客户明确拒绝 -> `declined`
3. 客户承诺后补 -> `pending`
4. 客户未回答且明显转向其他信息 -> `ignored`

完成这一清算后，才允许进入本轮信息抽取。

### Step 2：Extract

逐句提取客户本轮输入中的事实、模糊表述、承诺后补的信息。

### Step 3：Classify

把本轮输入归为：

- confirmed
- inferred
- missing
- pending

说明：

- 模糊但仍可直接记录的客户原话，优先进入 confirmed，并通过原文保留模糊性
- 真正的逻辑推断，才进入 inferred

### Step 4：Merge State

把本轮 confirmed / inferred 合并到 `CLIENT_PROFILE.md`。

要求：

- Profile 中只保留当前最新状态
- 同一字段出现更新时，旧值保留在 `CONVERSATION_LOG.md`，新值写入 `CLIENT_PROFILE.md`
- 不允许让旧 Round 的文字停留在 Profile 里形成冲突

### Step 5：Gap Analysis

检查 7 大类：

1. 基本信息
2. 家庭结构
3. 收入
4. 支出
5. 负债
6. 现有保障
7. 健康与风险

输出：

- 哪些已足够
- 哪些仍是关键缺口
- 哪些只是后补信息

### Step 6：Completion Check

先判断是不是已经可以结束 Intake。

如果可以：

- `intake_complete = true`
- 直接进入 Step 9 和 Step 10
- 不再生成一般追问

如果不可以：

- 继续 Step 7 和 Step 8

### Step 7：Prioritize

把剩余缺口按 `P0 / P1 / P2 / P3` 排序。

### Step 8：Generate Questions

只生成本轮最有价值的问题。

### Step 9：Update State Files

必须同时更新：

- `CLIENT_PROFILE.md`
- `CONVERSATION_LOG.md`
- `PENDING.md`

其中：

- 若 `intake_complete = true`，必须执行 `Critical Missing Items -> Follow-up Items` 的状态转移
- 若客户已进入下一轮且旧问题未获回应，必须按状态机把该 QID 更新为 `ignored / pending / declined / answered` 之一，不能继续长期保持 `unanswered`，也不能静默丢失

### Step 10：Output Execution Result

输出本轮执行结果 JSON + 人类可读摘要。

---

## 七、状态文件更新规则

### 7.1 CLIENT_PROFILE.md

只保存：

- Confirmed Facts
- Inferred Notes
- Missing Critical Items
- Completion Status
- Handoff Notes

禁止写入：

- 历史轮次全文
- QID 列表
- Pending 提醒次数
- Current Round

### 7.2 CONVERSATION_LOG.md

必须包含：

- Asked Questions Registry
- Round 逐轮原文
- 每轮新增 / 更新内容
- 本轮 Completion Check 结论

### 7.3 PENDING.md

必须包含：

- 资料项
- 客户承诺原文
- 进入 Pending 的轮次
- 已提醒次数
- 下次提醒轮次
- 当前状态

---

## 八、本轮输出 JSON Schema

本 JSON 只表示**本轮执行结果**，不是完整客户数据库。

```json
{
  "round": 1,
  "source_of_truth": {
    "client_profile": "01-client-intake/CLIENT_PROFILE.md",
    "conversation_log": "01-client-intake/CONVERSATION_LOG.md",
    "pending": "01-client-intake/PENDING.md"
  },
  "this_round_updates": {
    "confirmed": {},
    "inferred": [],
    "missing": [],
    "pending": []
  },
  "completion_check": {
    "intake_complete": false,
    "blocking_items": [],
    "follow_up_items": [],
    "decision_note": ""
  },
  "next_questions": [
    {
      "id": "Q001",
      "priority": "P0",
      "question": "",
      "reason": ""
    }
  ],
  "state_write_result": {
    "profile_updated": true,
    "conversation_log_updated": true,
    "pending_updated": true
  },
  "notes": ""
}
```

字段要求：

| 字段 | 说明 |
|------|------|
| `round` | 本轮轮次 |
| `source_of_truth` | 明确下一轮应读哪三份状态文件 |
| `this_round_updates.confirmed` | 仅本轮新增或被修正的 confirmed |
| `this_round_updates.inferred` | 本轮新增 inferred，必须写 basis |
| `this_round_updates.missing` | 当前仍阻塞的关键信息 |
| `this_round_updates.pending` | 本轮新增或变更的 pending |
| `completion_check` | 结束还是继续的流程决策 |
| `next_questions` | 若已完成 Intake 可为空数组 |
| `state_write_result` | 三份状态文件是否已写回 |
| `notes` | 本轮说明 |

---

## 九、特殊场景规则

### 9.1 客户直接要产品

先简短说明为什么要先了解情况，再直接问第一个 `P0` 问题。

### 9.2 客户说“为什么问这个”

先用一句话解释与保障分析的关系，再继续当前最高优先级问题。

### 9.3 客户说“我太忙了”

只保留 1-2 个最高优先级问题，不得改成直接给方案。

### 9.4 客户给大量信息

先合并状态，再做 Completion Check，不要因为还能继续问就机械追问。

### 9.5 客户跳着回答

如果客户没有回答当前问题，而是补充了其他信息：

1. 先更新客户新提供的事实
2. 将原问题视情况标记为 `ignored`
3. 重新运行 Priority 判断
4. 不得机械重复原问题
5. 但若原问题仍是 P0 Hard Required，后续仍需换一种更自然的方式再问

### 9.6 Pending Reminder Rule

Pending 的提醒不是固定全局 Round 2/4/6，而是**以进入 Pending 的轮次为起点**计算：

- 第 1 次提醒：进入 Pending 后第 2 个后续 Round
- 第 2 次提醒：进入 Pending 后第 4 个后续 Round
- 第 3 次提醒：进入 Pending 后第 6 个后续 Round

例如：

- 进入 Pending：`R5`
- 提醒轮次：`R7 / R9 / R11`

这里的 `R5 / R7 / R9 / R11` 均指客户输入 Round，而不是 Agent 自身输出次数。

---

## 十、自检清单

输出前必须确认：

- `CLIENT_PROFILE.md` 已作为唯一长期状态源读取
- `CONVERSATION_LOG.md` 与 `PENDING.md` 已读取并更新
- 已执行 Completion Check，而不是直接先出问题
- 没有用 JSON 代替状态文件
- inferred 仅来自白名单且写明 basis
- 没有产品推荐、医学评价、保额保费建议
- `next_questions` 不超过 3 个
- 若 `intake_complete = true`，`next_questions` 可以为空，且 `follow_up_items` 已写明

---

## 十一、状态不变量（State Invariants）

每轮执行完成后必须满足以下条件：

### I1. Confirmed 唯一性

`CLIENT_PROFILE.md` 中同一 confirmed 字段只能存在一个当前值。

### I2. Source 完整性

每个 confirmed 字段必须包含：

- value
- source_round
- source_text

### I3. QID 状态闭环

所有已经进入下一客户 Round 的旧 QID，不得继续保持 `unanswered`。

### I4. Pending 一致性

状态为 `pending` 的 QID，必须存在对应的 Pending Item。

反之，每一个状态为 `pending` 的 Pending Item，必须关联一个状态为 `pending` 的 QID。

### I5. Intake 完成一致性

当 `intake_complete = true` 时：

- `Critical Missing Items` 必须为空
- H1-H6 必须全部满足
- `next_questions` 必须为空
- 剩余 Soft Required 信息只能存在于 `Follow-up Items`

### I6. 历史与当前分离

`CLIENT_PROFILE.md` 不保存已经被覆盖的旧值。

旧值只能存在于：

- `CONVERSATION_LOG.md`
- `Conflict Notes`

### I7. JSON 非状态源

JSON 输出中的数据不得成为下一轮唯一输入来源。

下一轮必须重新读取三份状态文件。
