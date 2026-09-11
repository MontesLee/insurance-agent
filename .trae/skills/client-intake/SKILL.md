---
name: "client-intake"
description: "保险客户信息收集与整理。当开始与新客户沟通、收集客户基本信息、更新客户档案、或需要识别缺失信息并生成下一步问题时调用。"
---

# Client Intake Skill

本文件是 Trae 的注册入口。真正规则统一写在 `01-client-intake/SOP.md`。

---

## 多客户并行能力总开关（Step 0：客户上下文切换 —— 所有执行前必须先跑）

> 🟢 **本 Skill 原生支持同时维护多位客户的独立档案，互不串数据。**
>
> 执行**原来的 10 步流程前（Step 1~Step 10）**，必须先跑 **Step 0：客户上下文切换**，确定当前这轮对话服务的是哪一位客户。严格遵守下面 4 条触发逻辑。

### Step 0 的触发逻辑（4 条，按优先级 1 > 2 > 3 > 4）

1. **最高优先级：用户本次 Prompt 里明确写了客户标识（`【客户 ID】` / `【客户别名】` / `【切到客户 C001】` 这类标记）** → 直接用它。
2. **其次：本次对话的记忆里，存在「上一次使用的客户」，且用户本次 Prompt 没有明确说要切客户或新建客户** → 默认继续用「上一次的客户」。
3. **其次：用户本次 Prompt 明确表示要「新客户 / 新建客户」** → 进入下面 §Step 0-A 「新客户创建流程」。
4. **兜底（三条都不满足，没有任何客户上下文信息）：** → 进入下面 §Step 0-B 「向用户询问：新客户 or 已有客户」的交互，不得直接执行 Step 1~10。

### Step 0-A：新客户创建流程

```
Step 0-A-1：读取 `01-client-intake/clients/INDEX.md`，找到里面最大的客户编号（例：已有 C001 / C002 / C003 → 下一位 = C004；INDEX 空 → 第一位 = C001）

Step 0-A-2：⚠️ 不要纯文本打字问别名！直接调用 AskUserQuestion 弹出「客户类型预设单选框」，用户点一下就自动生成别名（6 个常用预设覆盖 90% 场景 + 1 个自定义兜底）：
            【问题】「🆕 请选择客户类型（直接点选自动生成别名，90% 场景用前 5 个预设；想自己写就选最后一项）：」
            【Header】客户别名
            【选项】
              1. 👨‍👩‍👧 标准三口之家（夫妻 + 1 个孩子）
                 描述：最常见场景。别名自动填「X先生/女士+三口之家」（X 为客户姓，不知道就先填 C00{nn}-三口之家）
              2. 💼 企业主家庭（自雇 / 公司股东 / 个体户）
                 描述：收入结构较复杂。别名自动填「X总企业主家庭」
              3. 👩‍👦 单亲家庭（独自带娃）
                 描述：家庭责任集中在单人。别名自动填「X姐/哥单亲家庭」
              4. 🧑 单身青年（无子女 / 未婚 / 暂无家庭经济依赖）
                 描述：仅关注个人保障。别名自动填「X先生/女士单身青年」
              5. 💎 高净值家庭（年收入 > 100 万 / 有较多资产配置需求）
                 描述：家族保障综合规划。别名自动填「X总高净值家庭」
              6. ✏️ 我自己输入别名（不常用，仅前 5 个都不合适时选）
                 描述：选这项后 Skill 会问你具体叫什么，你直接打字说别名就行
            【默认选中】👨‍👩‍👧 标准三口之家（推荐）
            【multiSelect】false
            → 用户点选前 5 个之一：直接按对应规则自动生成别名，进入 Step 0-A-3
            → 用户点选第 6 个「我自己输入」：Skill 再纯文本问「请输入客户别名：」，用户打字回复后进入 Step 0-A-3（为了 10% 的特殊场景兜底）

Step 0-A-3：建客户目录 `01-client-intake/clients/C00{nn}-{客户别名}/`
Step 0-A-4：把 SOP §2.3 定义的三份状态文件空模板（CLIENT_PROFILE / CONVERSATION_LOG / PENDING）各自完整写入目录
Step 0-A-5：把「客户编号 / 别名 / 创建时间 / 当前轮次 R0 / intake_complete=false / 最近更新=创建时间」追加写入 INDEX.md
Step 0-A-6：「当前选中客户」设为 C00{nn}，并写入对话记忆（便于后续轮次默认继承）
Step 0-A-7：回复用户（固定格式 4 条，少任何一条不算完成）：
          ① ✅ 新客户已创建：【C00{nn} - {客户别名}】
          ② 📁 档案目录：01-client-intake/clients/C00{nn}-{别名}/
          ③ 🔢 当前轮次：R0（全新空白档案，可开始 R1 首轮信息输入）
          ④ 💡 使用提示：直接复制 USAGE_GUIDE.md §5.4 R1 模板，把客户原话粘贴进去发送即可；也可以直接说「我要开始 R1，客户说：我30岁上海做互联网年收入50万」
```

### Step 0-B：向用户询问「新客户 or 已有客户」（兜底交互）

**⚠️ 不要用纯文本列 A/B！直接调用 `AskUserQuestion` 工具在聊天窗口弹出单选框组件（和 brainstorming 技能一样），用户点一下就选好，不用打字。**

单选框参数：
- 问题：「🔹 请确认本次操作的客户：」
- Header 标签：`客户类型`
- 2 个选项：
  1. **🆕 新客户（推荐第一次聊的新客户用）** → 描述：「这位客户还没建过档案，自动分配 C00{n} 编号 + 独立目录」
  2. **📋 已有客户（之前建过档案，继续补信息）** → 描述：「从已有客户清单里选一位，自动切到他的专属目录并告诉你当前该第几轮」
- 默认选中：「🆕 新客户」（推荐）
- 单选项：`multiSelect: false`

用户点选后：
- 如果选了「🆕 新客户」→ 进入 Step 0-A 新客户创建流程
- 如果选了「📋 已有客户」→ 进入下面 Step 0-C 弹出「已有客户选择单选框」

### Step 0-C：已有客户清单选择

**⚠️ 不要用纯文本输出表格！直接调用 `AskUserQuestion` 工具在聊天窗口弹出单选框组件，用户直接点客户名字就行，不用打「选 C002」这种字。**

执行步骤：
```
Step 0-C-1：读取 `01-client-intake/clients/INDEX.md`
Step 0-C-2：遍历 INDEX 每一行客户条目（跳过表头），为每个客户生成一个选项：
            【选项 label】= "C00{nn} - {客户别名}  （{当前轮次} / {完成状态图标}）"
            例：C001 - 张三三口之家  （R2 / ✅ 已完成）
            例：C002 - 李姐企业主    （R1 / ❌ 未完成）
            【选项 description】= "最近更新：{最近更新日期} · 档案目录：clients/C00{nn}-{别名}/"
Step 0-C-3：组装 AskUserQuestion 参数：
            - 问题：「📋 请选择本次要服务的已有客户：（共 {N} 位，点一下即可自动切换）」
            - Header 标签：`选择已有客户`
            - 选项列表：按 Step 0-C-2 生成的所有客户选项
            - 默认选中：INDEX 里「最近更新」时间最新的那一位（通常用户继续最近在聊的客户）
            - multiSelect: false
Step 0-C-4：用户点选后，「当前选中客户」设为这位，写入对话记忆；然后按 INDEX 里的「当前轮次」回复用户：「✅ 已切到【C00{nn} - {别名}】，当前轮次 = R{n}，请复制对应 R{n} 模板或直接把客户这一轮说的话发给我。」（例：INDEX 里记录该客户当前轮次 = R2 → 就告诉用户请用 R2 模板）
```

> 💡 **向后兼容**：如果用户不点点选框，而是直接打字说「选 C001」「选张三」「第2个」，也照样能识别并切换。

### Step 0 完成后：所有文件路径自动切换为「该客户专属目录下的版本」

Step 0 跑完、确定了客户（例：C001 - 张三三口之家）之后，原来「状态唯一性原则」里写死的 4 个根目录文件路径，**全部替换为以下路径**（后续 Step1~Step10 读写都只操作这些路径，严格隔离）：

| 原来的单客户硬编码路径 | 多客户并行模式下的实际路径（例：C001-张三三口之家）|
|---|---|
| `01-client-intake/SOP.md` | 不变，还是 `01-client-intake/SOP.md`（规则唯一源，所有客户共享一份）|
| `01-client-intake/CLIENT_PROFILE.md` | `01-client-intake/clients/C001-张三三口之家/CLIENT_PROFILE.md` |
| `01-client-intake/CONVERSATION_LOG.md` | `01-client-intake/clients/C001-张三三口之家/CONVERSATION_LOG.md` |
| `01-client-intake/PENDING.md` | `01-client-intake/clients/C001-张三三口之家/PENDING.md` |

> 🔴 **红线：绝对不能再读写根目录下的 CLIENT_PROFILE / CONVERSATION_LOG / PENDING 这三份（根目录的这三份是 v1 遗留产物，多客户模式下视为空壳占位，禁止写入）。多客户模式下所有写操作必须只进 `clients/C00{nn}-{别名}/` 对应子目录。**
> 🔴 **红线：INDEX.md 只有「客户创建（Step 0-A）/ 每轮 Step9 状态写回后更新『当前轮次+1』/ 客户完成时更新 intake_complete=true」这 3 个时机可以写，别手改里面的内容。**

---

## 状态唯一性原则（多客户并行版，在 Step0 切换完成后适用）

`01-client-intake/clients/C00{nn}-{别名}/CLIENT_PROFILE.md` 是**该客户唯一长期状态源**。

每次执行（确定客户后）必须遵守：

1. 先读取 `01-client-intake/SOP.md`（共享规则）
2. 再读取 `01-client-intake/clients/<当前客户目录>/CLIENT_PROFILE.md`
3. 再读取 `01-client-intake/clients/<当前客户目录>/CONVERSATION_LOG.md`
4. 再读取 `01-client-intake/clients/<当前客户目录>/PENDING.md`
5. 将本轮客户输入与上述状态文件合并
6. 所有 confirmed / inferred / missing / pending 以状态文件为准
7. JSON 输出仅表示**本轮执行结果**，不是下一轮的状态来源
8. 若 JSON 与状态文件冲突，以下列文件为准：
   - 客户目录下 `CLIENT_PROFILE.md`
   - 客户目录下 `PENDING.md`
   - 客户目录下 `CONVERSATION_LOG.md`

## 执行流程

严格按 `SOP.md` 中定义的 10 步执行：

1. Resolve Previous QIDs
2. Extract
3. Classify
4. Merge State
5. Gap Analysis
6. Completion Check
7. Prioritize
8. Generate Questions
9. Update State Files  （⚠️ 完成后**额外操作**：回写 INDEX.md，把该客户的「当前轮次 +1」/「最近更新时间 = now」/「intake_complete 状态同步」三条字段刷新）
10. Output Execution Result

> **补充 Step 9 额外回写 INDEX.md 的规则：**
> - 如果本轮是 R1（R0 → R1）→ INDEX 中该行「当前轮次」从 R0 改成 R1，「最近更新」写现在时间
> - 如果本轮 Completion Check 结果 intake_complete=true → INDEX 中「Intake 完成状态」从未完成 → ✅ 已完成
> - 其他情况：「当前轮次」+1；「最近更新」= now

---

## 主流程 4 个交互式决策节点（全部用 AskUserQuestion 单选框，别用纯文本让用户打字回复）

以下 4 个节点发生在 Step 1~10 主流程中，检测到对应条件时 **必须先弹出单选框让用户点选决策**，再继续后面的执行步骤。不要输出纯文本后等用户打字，那样会多一轮对话。

### 🎯 节点 4/7：Step 4 Merge State → MR2 客户新旧信息冲突时（3 选 1 单选框）

**触发条件：** Step 4 合并状态时，本轮 Extract 提取到的 Confirmed 值，与 `CLIENT_PROFILE.md` 里已存在的旧值 **明显矛盾**（例：旧值年龄=30 / 本轮新说法=32；旧值已婚 / 本轮新说法=未婚）。

**⚠️ 不要纯文本列冲突描述让用户打字回复「用新的/用旧的」！直接弹 AskUserQuestion 单选框：**

```
【问题】「⚠️ 检测到客户前后说法冲突，请选择本次合并方式：
  旧值：{字段名} = {旧值}（来源：{Source Round} {Source Text 摘要}）
  新说法：{字段名} = {新值}（来源：本轮 R{n}）」
【Header】冲突处理
【选项】
  1. ✅ 用本轮新值覆盖（客户修正了旧信息）
     描述：Profile 写入新值；Log 记录 Conflict Notes；Profile Change Notes 追加本次变更说明
  2. 📌 保持原来的旧值（本轮是客户口误/说错了）
     描述：Profile 保持旧值不变；Log 记录 Conflict Notes 并标注「忽略本轮新说法，用户确认保留旧值」
  3. ⏸️ 暂不更新，下一轮再向客户确认（现在不确定谁对谁错）
     描述：Profile 两边都不改；把冲突项以 ❓冲突状态 标记在 Critical Missing 的 P2；本轮结束时 Skill 把冲突话术整理好，用户下一轮发给客户核实后再处理
【默认选中】✅ 用本轮新值覆盖（推荐，绝大多数场景是客户纠正了之前说不准的信息）
【multiSelect】false
→ 用户点选后，按对应分支执行 Step 4 后续 Merge，再继续 Step 5~Step10
```

---

### 🎯 节点 5/7：Step 6 Completion Check → intake_complete = true（P0 全收齐，3 选 1 单选框）

**触发条件：** Step 6 判定 H1-H6 全部达到最低完成标准，`intake_complete` 从 false 变为 true（客户基础信息第一次收集完成那一刻）。

**⚠️ 不要纯文本说「完成了可以进需求分析了」然后等用户打字！直接弹单选框让用户立刻点下一步做什么：**

```
【问题】「🎉 好消息：该客户 P0 六项 Hard Required 全部收齐，Intake 基础信息已达标！
  （当前 Confirmed {N} 项 / 仍有 {M} 项 Soft Required 可后续补 Follow-up）
  请问接下来做什么？」
【Header】Intake 完成后下一步
【选项】
  1. 🚀 立即进入 Needs Analysis（需求分析阶段）
     描述：结束 Client Intake，关闭这个 Skill；把 CLIENT_PROFILE.md 交给 Needs Analysis Skill 读取，正式开始分析客户需求和方案
  2. 📋 先补 Follow-up Items 软信息（不阻塞 Intake，但对方案有帮助的细节）
     描述：本轮不结束；按 Soft Required 清单（配偶详细/父母赡养/现有保障细节/客户健康细节）生成 P2 追问；用户下一轮补进来自动进 Follow-up Items
  3. ⏸️ 先存档暂停，我下一轮再决定
     描述：Intake_complete 保持 true；Client 状态写入「待交接 Needs Analysis」；本轮就先到这，用户下一轮随时可以重新触发继续
【默认选中】🚀 立即进入 Needs Analysis（推荐）
【multiSelect】false
→ 用户点选后，按对应分支决定 Step9 是否把 intake_complete 写 true / 生成 P2 Follow-up 追问 / 直接进入 Handoff Notes 交接
```

---

### 🎯 节点 6/7：Step 6 Completion Check → intake_complete = false（还缺 P0，要生成追问，3 选 1 单选框）

**触发条件：** Step 6 判定还有 H1-H6 未达标，`intake_complete=false`；Step7/Step8 已排好优先级并生成本轮 1~3 个 next_questions。

**⚠️ 不要纯文本列完问题就结束对话，让用户自己复制去发给客户！直接弹单选框问用户对这批追问怎么处理：**

```
【问题】「📝 本轮生成了 {N} 个最高优先级追问（P0={x} / P1={y} / P2={z}）。
  问题摘要：{第 1 个问题简述}；{第 2 个问题简述}；{第 3 个问题简述}
  请问接下来怎么处理这批追问？」
【Header】本轮追问处理方式
【选项】
  1. 💬 直接用 Skill 生成的口语化话术发客户（展示可复制模板）
     描述：展示本轮 1~3 个问题的自然口语话术模板（直接复制粘贴给客户即可，不用改字），本轮执行正常结束，等下一轮客户回复
  2. ⏳ 先不追这批，等下一轮客户主动说新的信息再说
     描述：本轮不生成 next_questions 话术；Profile 状态正常写入但 QID 状态先不标 unanswered；等客户下一轮输入自然覆盖到缺口
  3. 🔀 先不处理这个客户，我要切到其他客户
     描述：本轮状态正常写入但不生成问题话术；直接回到 Step 0-C 弹「已有客户单选框」让用户选另一位客户继续服务（解决你同时跟 A/B/C 多位客户聊天的场景）
【默认选中】💬 直接用口语化话术发客户（推荐，90% 场景是立刻把问题发给客户）
【multiSelect】false
→ 用户点选第 1 项 → 展示话术模板后正常结束；点第 2 项 → Step10 输出空 questions；点第 3 项 → 回到 Step 0-C 弹客户单选框
```

---

### 🎯 节点 7/7：HF09 完结门控触发（已完成 Intake，又输入新信息，3 选 1 单选框）

**触发条件：** 当前客户 INDEX 中 `intake_complete = true`，但用户又新触发了一次 Skill（发了新一轮客户信息进来）。此时 HF09 硬约束不允许再生成 P0/P1/P2 阻塞性追问，只能 Follow-up 软提醒。

**⚠️ 不要纯文本提示「已完成，只能补 Follow-up」，直接弹单选框让用户明确这次新信息的处理意图：**

```
【问题】「🔒 门控提醒：该客户 Intake 已完成（上次标记为 ✅ 可进入 Needs Analysis）。
  HF09 规定：完成后不能再生成阻塞性追问。
  你刚发进来的这轮新信息（{字数摘要} / {Confirmed 命中字段数} 项），请问怎么处理？」
【Header】完结后新信息处理
【选项】
  1. 📝 追加到 Follow-up Items（不回滚完成状态）
     描述：把这轮 Confirmed 合并进 Profile；缺的 Soft Required 自动进 Follow-up；intake_complete 保持 true，状态仍可随时进 Needs Analysis
  2. 🔄 回滚为「未完成」，重新跑 Completion Check（这次发的是重要信息，可能影响 P0 判定）
     描述：INDEX 中 intake_complete 改回 ❌ 未完成；Profile Critical Missing 重新计算；后续可以重新生成 P0/P1 阻塞追问；等全部达标后再重算一次 Completion 完成
  3. ❌ 这次先别写入档案，我取消这次输入
     描述：什么都不改；Profile / Log / Pending / INDEX 全部维持这次触发前的样子；本轮 Skill 执行结束当没跑过
【默认选中】📝 追加到 Follow-up Items（推荐，大多数场景就是客户后来补充了点软信息）
【multiSelect】false
→ 用户点选后，按对应分支决定 Step9 是否回滚完成状态 / 写 Follow-up / 什么都不做退出
```

---

> 💡 **所有 7 个节点共同规则：**
> 1. 如果用户不点点选框，直接打字回复了决策（比如客户冲突时直接打字说「用新值」），也必须识别并按对应分支走，**不能因为用户没点 UI 就卡住不动**（向后兼容，100% 场景都可走通）
> 2. AskUserQuestion 的「默认选中」永远选最常见的 90% 场景，保证用户 90% 情况下只需要点「确认」不用翻列表

---

## 状态文件职责（都在客户目录下）

- `CLIENT_PROFILE.md`
  当前最新客户事实、有限白名单内的 inferred、缺口摘要、完成状态。后续 Skill（Needs Analysis 等）只读这份。
- `CONVERSATION_LOG.md`
  Asked Questions Registry + 每轮原始对话流水。只用于多轮记忆，不作为下阶段输入。
- `PENDING.md`
  客户答应补充但尚未提供的资料、提醒节奏、状态变更。

## 触发场景

满足任意一条即调用本 Skill：

1. 首次建立客户档案（Step 0-A 新客户创建）
2. 已有客户补充新信息，需要合并到现有档案（Step 0 先切到对应客户）
3. 需要识别关键缺口并决定是否继续 Intake
4. 需要生成最少量、最高优先级的下一步问题
5. 需要判断是否已可进入 Needs Analysis
6. 需要同时维护多位客户的独立档案切换（Step 0-C 已有客户选择）
