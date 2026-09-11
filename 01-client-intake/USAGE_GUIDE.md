# Client Intake Skill — 专业说明文档

> 版本：v1.2 · Production Ready（🟢 READY，新增 **多客户并行隔离能力**）
> 本文档面向：Skill 使用者（保险经纪人 / 运营）、Skill 维护者（工程 / Prompt 工程师）、QA / 回归工程师。

---

## 一、这个 Skill 是干什么的

### 1.1 定位（一句话）

`Client Intake` 是一个**保险客户基础信息标准化 Skill**。它不做推荐、不做方案，只负责把客户零散说的话（微信聊天 / 电话笔记 / 口头）整理成一份**可追溯、可维护、可供后续 Skill 消费**的标准化客户上下文，供下一阶段的 `Needs Analysis`（需求分析）使用。

### 1.2 边界（绝对不要让它做这些事）

| ✅ 可以做（Data Collection Agent 定义）| ❌ 绝对不能做（Hard Fail = HF01/HF02，任一命中即本轮 FAIL）|
|---|---|
| 提取客户明确说过的事实 | 推荐具体产品、比较产品、计算保额保费（=越界推荐） |
| 在白名单 5 类内做有限推断（家庭收入依赖等）| 用医学语言评价健康风险（=越界医疗判断）|
| 识别关键缺口（Missing）与待补资料（Pending）| 把推断的内容直接写成 Confirmed（=虚构事实 HF02）|
| 判断 Intake 是否完成（Completion Gate）| 让 JSON 输出变成第二份客户数据库（=Source of Truth 混乱 HF03）|
| 生成最少量、最高优先级的自然追问 | 重复追问已经 answered/declined/pending 的问题（=机械重复 HF04）|

### 1.3 长线架构优势（为什么这个 Skill 可长期维护）

对比"写一段 Prompt 就跑"的早期版本（v1 82 分），v1.1 架构解决了多轮评审发现的本质问题：

| 维度 | v1 Prompt Only 痛点 | v1.1 五件套闭环 |
|---|---|---|
| 规则唯一源 | Prompt 与文档多处写规则，久了不一致 | [SOP.md](file:///D:/Workspace/insurance-agent/01-client-intake/SOP.md#L1-L620+) 是**唯一规则源**，所有入口/状态/EVAL/Case 以 SOP 为准 |
| 状态持久化 | 多轮状态靠 JSON 传，冲突就打架 | [CLIENT_PROFILE.md](file:///D:/Workspace/insurance-agent/01-client-intake/CLIENT_PROFILE.md#L22-L150) **唯一长期状态源**，三份状态文件分离职责，SOP §2.2 明确定义优先级：Profile > Pending > Log > JSON |
| 完成标准 | Intake 什么时候结束靠感觉 | SOP §四 明确 H1-H6 最低标准（§4.1）+ Completion Check（§4.3）Gate 机制，只有三条件全满足才结束，后续阶段不再普通追问（HF09） |
| 可回归性 | 改一条 SOP，全量 Case 靠人脑回归 | [run-regression.ps1](file:///D:/Workspace/insurance-agent/scripts/run-regression.ps1#L1-L573) Level 1-2-3 三档自动化回归脚本，2 分钟跑完 8 Case 156+ 断言 |
| 可评估性 | Skill 自己给自己打高分 | [EVAL.md](file:///D:/Workspace/insurance-agent/01-client-intake/EVAL.md#L1-L239) HF01-09 先打（任一命中直接 FAIL）→ 断言再核对 → 六维 30 分 → MR1-4 专项 → SABCD 五级评级，避免高分幻觉 |
| 行为验证 | "大致能跑"靠体感 | 8 个 Test Case（CASE_001~CASE_008）覆盖全部高风险灰区（越界/冲突/Pending/Ignored/Dirty），每 Case 多轮断言对齐，全部 S 级 30/30，Hard Fail 命中 = 0 |

---

## 二、日常如何使用这个 Skill

### 2.1 标准使用流程图

```
新客户对话开始
        │
        ▼
【R0 重置状态】（三份状态文件回空模板，避免上一个客户残留）
        │
        ▼
【R1 客户首轮输入】→ 激活 client-intake Skill → SKILL.md 按固定顺序读 SOP→Profile→Log→Pending
        │
        ▼
【Skill 内部 10 步执行】（见 §2.2，SKILL.md 写死的顺序，不可调整）
        │
        ▼
【三份状态文件被写入】（Profile=最新事实；Log=历史原文+QID；Pending=答应补的资料）
        │
        ▼
【Completion Gate 判断】
    │                       │
    │ intake_complete=false │ intake_complete=true
    ▼                       ▼
【Skill 生成 1~3 个    【Skill 输出  基础信息完成，可进入 Needs Analysis】
   最高优先级追问】          【Soft Required 缺口转移到 Follow-up Items，不阻塞】
    │                       │
    ▼                       ▼
【R2 客户第二轮输入】…  【移交 Needs Analysis Skill 消费 CLIENT_PROFILE.md】
```

### 2.2 Skill 内部固定 10 步执行流程（[SKILL.md §执行流程](file:///D:/Workspace/insurance-agent/.trae/skills/client-intake/SKILL.md#L28-L41) 写死，1→10 严格顺序不可跳）

| 步骤 | 名称 | 做什么（简要）| 引用 SOP 章节 |
|---|---|---|---|
| Step 1 | Resolve Previous QIDs | 上一轮末尾所有 `unanswered` QID 必须在本轮入口清算（§五 5.4.1 钩子，不变量 I3 严禁跨轮未清）| SOP §五 5.4.1 + I3 |
| Step 2 | Extract | 从客户原文里提取 Confirmed，每条 Confirmed 必须记录三追溯字段：value / source_round / source_text（I2 零例外）| SOP §三 3.1 + I2 |
| Step 3 | Classify | 映射到 Intake 最低完成标准 H1-H6（年龄/城市/职业/家庭责任/收入/支出）| SOP §四 4.1 Hard Required |
| Step 4 | Merge State | 把 Step2 提取到的新信息与 Profile 旧状态合并；同一字段被客户修正时直接覆盖旧值，并在 Profile Change Notes 记录；冲突写 Log/Conflict Notes（MR2 专项）| SOP §二 2.2 第 3/8 条 + §三 MR2 |
| Step 5 | Gap Analysis | 产出 `Critical Missing Items`（仍会阻塞的 P0-P3），用于下一轮追问优先级排序 | SOP §七 7.1 P0-P3 离散优先级 |
| Step 6 | Completion Check（硬 Gate）| 三条件：① H1-H6 全达 §4.1 最低要求 ② 无完全空白的重大阻塞 ③ Profile 足够支撑下阶段 → 全满足则 `intake_complete=true`；否则 `false` | SOP §四 4.3（HF05/HF09 双锚点）|
| Step 7 | Prioritize | Step6=false 时才进入；P0-P3 离散优先级 + tie-break（完全缺失优先 / 回答成本低 / Hard 优先 / 7大类顺序：家庭结构 > 收支 > …）| SOP §七 7.1-7.2 |
| Step 8 | Generate Questions | 最多 ≤3 个问题，严禁机械重复前一轮原文；P0 连续 ignored 不降级但必须换短更自然问法 | SOP §七 7.3 + CASE_008 专项 |
| Step 9 | Update State Files | 真正落盘写回三份状态文件（CLINET_PROFILE / CONVERSATION_LOG / PENDING），JSON 只是快照 | SOP §二 2.3 三份状态文件分工 + I7 |
| Step 10 | Output Execution Result | 输出本轮执行 JSON 快照（仅表示本轮结果，不是下一轮状态源；I7 严禁反模式）| SOP §二 2.2 第 6-8 条 + I7 |

### 2.3 典型日常操作命令（PowerShell 5 运行，生产环境每日 / 里程碑 / 改 SOP 时必跑）

```powershell
# ===== 【准备】每接一位新客户，R0 先重置三份状态文件（避免污染）=====
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\run-regression.ps1 -Level 1 -CaseId CASE_001
# （脚本 Step 1 = Reset-StateFiles，跑完后可直接开始真实客户对话）

# ===== 【QA / 改了 SOP 某条规则】Level 1 单 Case 快速回归（~10 秒）=====
# 例：改了 §4.2.1 H4 判定规则，先跑 CASE_001（三口之家）看 H4 是否仍然满足
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run-regression.ps1 `
  -Level 1 -CaseId CASE_001

# ===== 【改了 HF01 边界相关规则】Level 2 相关 Case 回归（~30 秒）=====
# 例：改了 §一 1.2 越界禁令，脚本自动按 Tags 重叠度挑出相关 Case
# 以 CASE_002（客户先问产品）为种子，会自动连带 CASE_003 / CASE_001 等同 Tag
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run-regression.ps1 `
  -Level 2 -CaseId CASE_002

# ===== 【每日 / 每周 / 里程碑 / 上生产前】Level 3 全量 8 Case 回归（~2 分钟）=====
# 必跑门槛：8/8 至少 B 级；Hard Fail=0；6D 均分 ≥ 27/30
powershell.exe -ExecutionPolicy Bypass -File .\scripts\run-regression.ps1 -Level 3
```

### 2.4 常见客户输入 → Skill 输出对照（帮助理解 Skill 的"工作方式"）

| 场景（客户说的话）| Skill 的行为（典型）|
|---|---|
| 客户上来就说「你好，直接给我推荐个重疾险吧，要性价比高的。我42岁银行上班年收入50万」| **不会**推荐任何产品。先把年龄/职业/年收入三条写进 Profile Confirmed（四列追溯全填）；说「先了解您的情况和关键信息，再做分析更准确」；首问 P0=家庭结构（CASE_002 场景，HF01 零越界）|
| 客户修正旧信息：R1 说「去年收入80万」；R2 说「不对，去年其实60万，今年预计80万」| Profile 只保留最新值（去年=60万，今年=80万，**正文里不保留两个去年收入当前值**，I1 合规）；旧说法 + 冲突说明写在 CONVERSATION_LOG §3 Conflict Notes + Profile Change Notes 两处历史区（CASE_006 场景，MR2 专项）|
| 客户说「那个保单我回头找一下拍给你」| PENDING.md 新建一条：绑定 Related QID（=客户被问到这条的 QID）；状态=pending；下次提醒轮次=进入 Pending 轮次 +2/+4/+6（最多提醒 3 次，CASE_007 场景，MR4 专项）|
| 客户两次被问 P0 家庭结构都跳答，说「先不说家庭，你就说你们重疾险有几种」| P0 不降级（家庭结构仍然是 P0 最高优先）但**绝对不能机械重复前一轮问题原文**（CASE_008 场景：R3 问法比 R1 缩短 58%，更短更自然，避免反感）|
| 客户输入一整段不规范中文：「我32，北京的。收入嘛去年100多，今年估计少点。老婆30左右吧，具体没问过。」| 6 条 Confirmed 写回（年龄 32/北京/去年 100多万**保留模糊，不硬写精确 100万**/配偶 30左右**保留『左右』=Uncertain，不精确 30**/子女数/甲状腺检查过）；但 4 条 must_not_have 的推断**绝对不写**（不得写配偶精确 30 / 甲状腺正常 / 职业稳定 / 风险偏好强），CASE_004 Dirty 专项 |

---

## 三、项目里每个文件都是做什么的（全清单 + 典型修改场景）

### 3.1 总览目录树（v1.1 架构，全部可追溯）

```
d:\Workspace\insurance-agent
├── .trae
│   └── skills
│       └── client-intake
│           └── SKILL.md                  ← Trae 注册入口（Router）
├── 01-client-intake
│   ├── SOP.md                           ← 唯一规则源（Single Source of Truth）
│   ├── CLIENT_PROFILE.md                ← 【状态文件 1】长期事实源
│   ├── CONVERSATION_LOG.md              ← 【状态文件 2】历史+QID 注册表
│   ├── PENDING.md                       ← 【状态文件 3】答应补的资料+提醒节奏
│   ├── EVAL.md                          ← 评估标准（HF+Assertions+六维30分+MR专项）
│   ├── USAGE_GUIDE.md                   ← 本文档（你现在读的就是）
│   └── runs
│       ├── regression_20260906_011735/  ← Level 3 回归报告示例（脚本生成）
│       │   ├── regression_report.json
│       │   └── REPORT.md
│       ├── multiround_sandbox_20260906_0125/  ← 真实沙箱多轮实跑报告
│       │   └── CASE_001_MULTIROUND_R1_R2_SANDBOX_execution.json
│       ├── CASE_001_R1_execution.json         ← 手动基线（早期实跑）
│       └── CASE_001_R1_SKILL_ENTRY_execution.json ← 注册入口实跑（P0 1/3 证据）
├── test-cases
│   ├── TEST_CASES.md                     ← 8 Case 索引 + 执行建议顺序
│   └── client-intake
│       ├── CASE_001.md ~ CASE_008.md      ← 8 个独立 Test Case（含客户原文+断言）
└── scripts
    └── run-regression.ps1                ← 回归脚本（Level 1-2-3 调度器）
```

### 3.2 入口层（Skill Router）—— [SKILL.md](file:///D:/Workspace/insurance-agent/.trae/skills/client-intake/SKILL.md#L1-L60)

| 信息 | 内容 |
|---|---|
| **定位** | Trae 环境的 Skill 注册入口（frontmatter 的 `name: client-intake` 与触发时的 Skill 激活名严格一致）|
| **主要内容** | ① frontmatter（名称+描述）② 状态唯一性原则 4 文件读取顺序（SOP→Profile→Log→Pending，**写死的顺序，使用者不能调**）③ 10 步执行流程（§2.2 那张表）④ 三份状态文件职责 ⑤ 5 个触发场景 |
| **什么时候需要修改？** | **极少修改（原则上不改）**。只有：Skill 改名、新增触发场景、三份状态文件分工调整（通常不会，因为 SOP 已对齐）|
| **典型错误** | 改了 SKILL.md 的读取顺序（例如先读 Profile 再读 SOP），会违反 SOP §二 2.2 第 1/6 条导致 EVAL HF03 Source Confusion 失败 |

### 3.3 规则层（Single Source of Truth）—— [SOP.md](file:///D:/Workspace/insurance-agent/01-client-intake/SOP.md#L1-L620+)

| 信息 | 内容 |
|---|---|
| **定位** | 本 Skill **唯一规则源**（一切行为、断言、回归脚本、EVAL 最终都要回 SOP 找依据）|
| **章节结构（最常用的 7 条锚点）** | ① §一 定位与边界（HF01 零容忍锚点）② §二 文件结构 + 三份状态文件分工 + I6/I7 不变量 ③ §三 信息四类型（Confirmed/Inferred/Missing/Pending + I1/I2 不变量）④ §四 Intake 最低完成标准 H1-H6 + Completion Check Gate + 4.4 转移规则（HF05/HF09 双锚点 + MR2）⑤ §五 QID 五状态机 + 5.4.1 清算钩子（I3 跨轮禁令 + 5.3 Pending↔QID 三态同步补丁）⑥ §六 Pending 相对轮次 +2/+4/+6（MR4 专项 + CASE_007）⑦ §七 优先级 P0-P3 离散 + 机械复读禁令（CASE_008 专项）；最后是 I1-I7 七大不变量 |
| **什么时候需要修改？** | 改规则 / 补边界 / 加场景 **必须先改 SOP**，然后跑 Level 2 相关 Case 回归；**绝不允许先改 Prompt 再补文档**（v1 的根本痛点）|
| **典型修改场景** | ① 新增一类 Hard Required（例：必须先收「是否有驾照」才能推车险）→ 改 §四 4.1 新增 H7，同时改 §六 QID 状态、§七 P0-P3、改 8 Case 断言里相应 completion 预期 ② 新增 Pending 类型（例：「客户答应下周带体检报告」）→ 改 §六 Pending 提醒节奏 ③ 冲突规则变严（例：客户 R1 说收入 50 万，R2 又说 40 万，需要向客户二次确认而不是直接覆盖）→ 改 §三 3.1 冲突处理 + CASE_006 MR2 断言 |

### 3.4 状态文件层（三份文件分离职责，SOP §二 2.3 表定义）

#### 3.4.1 [CLIENT_PROFILE.md](file:///D:/Workspace/insurance-agent/01-client-intake/CLIENT_PROFILE.md#L22-L150) — 唯一长期事实源（后续 Skill 只读这份！）

| 区段（按行号）| 内容 | 写谁写 / 谁只读 | 规则 |
|---|---|---|---|
| Client Summary（L22-30）| 客户编号 / Intake 状态 / Complete 时间 / 最后更新 | **Skill 每轮都改** | Intake 状态三态：未开始→进行中→完成（完成后必须填判定时间）|
| 1. Confirmed Facts（L33-85）| 1.1 基本 / 1.2 家庭 / 1.3 收支 / 1.4 负债保障 / 1.5 健康风险，共 5 大类 20+ 字段 | **Skill Step4 Merge 写** | 每条 Confirmed 四列追溯：字段 / 当前值 / Source Round / Source Text（SOP I2 零例外；少任何一列都是 HF07 State Persistence Failed）|
| 2. Inferred Notes（L89-97）| 白名单 5 类推断，必须写 basis | Skill Step2 有白名单命中才写 | 禁止越界推断：风险偏好/消费习惯/职业稳定性脑补/健康严重度/客户购买意愿 5 类一律不能写（CASE_004 专项）|
| 3. Critical Missing Items（L100-109）| 仍会阻塞 Needs Analysis 的 P0-P3 缺口 | Skill Step5 写；**Step6 intake_complete=true 后必须清空**（§4.4 转移规则，否则 = EVAL HF05 Completion Gate 缺陷）| intake_complete=true 后本区段必须空或写「已转移 Follow-up」|
| 4. Completion Status（L113-124）| H1-H6 六行单独标记 ✅/❓ + 总开关「是否可进入 Needs Analysis」| Skill Step6 写 | H4 必须写判断依据（§4.2.1 三问），不能只写 ✅ |
| 5. Follow-up Items（L127-134）| Intake 完成后仍待补的 Soft Required（不阻塞流程）| Skill Step6=true 后把 Soft 缺口写这 | 完成后 Skill 只能在 Follow-up 软提醒里提这些，不能做普通追问（HF09 命中）|
| 6. Handoff Notes（L137-144）| **给 Needs Analysis Skill 消费的契约区** | Intake 完成时 Skill 填；Needs Analysis 只读 | 现在是占位「待填写」，后续做 Handoff 契约 P1 任务时填字段消费规范（必填/可选/类型约束）|
| 7. Profile Change Notes（L147-150）| 追加式记录，每轮变更写一条，永远不覆盖历史 | **Skill 每轮都追加写** | I6 不变量：历史值只允许写这里 / Conflict Notes / Log Round History，Profile Confirmed 正文绝不保留双当前值 |

#### 3.4.2 [CONVERSATION_LOG.md](file:///D:/Workspace/insurance-agent/01-client-intake/CONVERSATION_LOG.md#L18-L77) — 历史+QID 注册表（不作为长期事实源，I6 历史留痕专用）

| 区段 | 内容 | 不变量锚点 |
|---|---|---|
| 1. Asked Questions Registry（L18-31）| 每个提出的问题先在这里注册（QID/Priority/Question Intent/原文/首次 Round/当前状态/客户回答/Related Pending/最后操作 Round）| I3 不变量：**每轮入口 Step1 跑完后，本表里不能存在任何 unanswered 属于上一轮的**（跨轮未清 = 5.4.1 钩子未执行 = FAIL）|
| 2. Round History（L35+）| 每轮一个 `### Round N` 追加段，记录：时间/客户原文（用 ``` 贴）/ 本轮新增 confirmed / 本轮新增 inferred / 本轮新增 pending / Asked Questions 变更（QID 状态转换必须写！）/ Completion Check 结论 / 备注 | I2 源数据的最后追溯防线；如果 Profile 四列没填，这里必须还能找回客户原话 |
| 3. Conflict Notes（L73+）| 客户前后说法冲突时写这里（例：R2 说收入 80 万，R4 修正为去年 60 万今年 80 万）| MR2 专项唯一落点。CASE_006 场景下，这里必须有记录（否则 MR2 0 分）|

#### 3.4.3 [PENDING.md](file:///D:/Workspace/insurance-agent/01-client-intake/PENDING.md#L18-L52) — 答应补的资料+提醒节奏（与 QID 强同步 SOP §六 34-39 行同步规则）

| 区段 | 内容 | 高风险锚点 |
|---|---|---|
| Pending Registry（L18-23）| 每条 Pending 9 列：编号 / Related QID / 项目 / 客户承诺原文 / 进入 Round / 当前状态 / 已提醒次数 / 下次提醒 Round / 备注 | ① Related QID 必须绑定一个真实 QID（CASE_007 A/B/C 场景，HF08 State Sync Broken）② 下次提醒 Round 计算方式：**从「客户答应补的 Round」+2/+4/+6，不是全局固定轮次**（CASE_007 Branch C R3/R5/R7 三提醒 = 28+28+28 字例）|
| 状态说明（L26-39）| 四态 pending/received/declined/expired + 与 QID 的三同步规则：received → answered；declined → declined；expired → ignored（≠ignored 严格语义边界，CASE_007 Branch B「客户明确不提供」绝对不能写成 ignored）| HF08 Broken 最常命中的就是这里：Pending 变了状态但 QID 没同步改 |
| Reminder Notes（L43-52）| 话术 + 例子（+2/+4/+6）| 提醒最多 3 次，第 3 次后必须 expired + QID→ignored（否则 Pending 无限提醒骚扰客户）|

### 3.5 评估层（Assertion 驱动，不允许 Skill 自高分）—— [EVAL.md](file:///D:/Workspace/insurance-agent/01-client-intake/EVAL.md#L1-L239)

| 章节 | 内容 | 修改时机 |
|---|---|---|
| 二 Step1 Hard Fail（L37-56）| HF01~HF09 九条，**任一命中即本轮直接 FAIL，不进入打分** | 发现新的必败级反模式就加（例：以后加 HF10 健康史用了分级术语 1-4 级越界）|
| 三 Step2 Assertions（L59-104）| 断言组定义（must_have/must_not_have/…共 8 组）+ 断言设计原则（QID/问题原文/唯一 Intent 不写死 → 用 question_intent_one_of 或主题级断言）| 加新的断言组别（例：以后加 must_update_handoff_notes，配合 Handoff 契约）|
| 四 Step3 六维 30 分（L107-150+）| Boundary/StateWriting/Completion/QuestionQuality/EvidenceSeparation/OutputDiscipline 六维，每维 0-5 分 | 维度权重调整（例：Dirty 规范化重要性提升，把 EvidenceSep 提到更高权重）|
| 五 Step4 MR 专项（L150+~200）| MR1 状态继承 / MR2 冲突处理 / MR3 问题去重 / MR4 Pending 节奏 | 加新专项（例：MR5 Dirty 规范化专项 → CASE_004）|
| 六 SABCD 评级 + RC 根因 RC1-5 | SABCD（S≥29 / A≥25 / B≥20 / C≥15 / D<15）五级；RC1-5 五类（SOP 冲突/状态语义/Prompt 不明确/测试问题/其他）| SABCD 门槛调整（例：生产门槛从 A≥25 提高到全 ≥S，提升标准）|
| 七 断言组别清单 | question_state_assertions / question_intent_one_of 组别用法 | 配合新 Case 定义补充 |

### 3.6 Test Case 层（行为断言驱动 8 个高风险灰区全覆盖）

| 文件 | 名称 | 难度 | 专门测什么（高风险灰区覆盖）|
|---|---|---|---|
| [TEST_CASES.md 索引](file:///D:/Workspace/insurance-agent/test-cases/TEST_CASES.md#L36-L63) | 8 Case 索引 + 建议执行顺序 | — | 建议顺序：CASE_001 → CASE_002 → CASE_005 → CASE_006/007/008 → CASE_003 → CASE_004 |
| [CASE_001.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_001.md#L8-L48) | 标准三口之家 3R | 简单 | **基线 Case**。验证 Confirmed 四列追溯、Completion R2=true（R3 不得普通追问）、H4 §4.2.1 三问综合判断 |
| [CASE_002.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_002.md#L8-L48) | 客户先问产品 | 中等 | **HF01 边界禁令实跑**（客户两次要求推荐产品，两次都不越界）；must_not_have 再问已回答过的年龄/职业/收入 |
| [CASE_003.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_003.md#L8-L45) | 创业者多轮对抗 | 复杂 | 创业者职业分类 + 对抗场景下客户继续问保险类型优劣（继续不越界）；QID ignored→answered 清算 |
| [CASE_004.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_004.md#L8-L58) | Dirty Input 规范化 | 复杂 | **must_not_have 推断禁令 4/4 0 违规**：配偶年龄不精确/甲状腺不写正常/职业不脑补稳定/风险偏好完全不提；模糊词保留（100多/30左右/二十来万/还有不少）|
| [CASE_005.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_005.md#L8-L72) | 客户跳答 | 中等 | QID 五态机：R1 unanswered → R2 客户跳答 → ignored（首次）→ R3 仍 P0 但非机械重复问；mortgage_balance 字段统一 |
| [CASE_006.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_006.md#L8-L73) | 客户修正旧信息 | 中等 | **MR2 冲突处理唯一专项**：R1 去年收入=80万 → R2 客户改口去年 60 万今年 80 万 → Profile 正文只保留最新值；旧值保留在 Change Notes + Conflict Notes + Log Round History（I6 不变量）|
| [CASE_007.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_007.md#L8-L190) | Pending 完整生命周期 | 复杂 | **MR4 Pending 提醒节奏唯一专项**：三分支 A received（QID→answered）/ B declined（≠ignored，语义边界）/ C expired（R3/R5/R7 三次提醒 +2/+4/+6，之后 QID→ignored）|
| [CASE_008.md](file:///D:/Workspace/insurance-agent/test-cases/client-intake/CASE_008.md#L8-L88) | P0 连续 ignored | 中等 | **不降级但不机械重复专项**：P0 连续两次 ignored → 仍然 P0 最高优先但换短问法（缩短 58% 更自然），不得机械重复原文 |

### 3.7 脚本层（Level 1-2-3 回归）—— [run-regression.ps1](file:///D:/Workspace/insurance-agent/scripts/run-regression.ps1#L1-L573)

| 模块（行号段）| 功能 | 日常何时会改 |
|---|---|---|
| §1 R0 状态重置（L27-L299）| 三份状态文件回写完整空模板（Profile/Log/Pending），每次跑前先执行一次（除非 -NoResetState）| 改了状态文件模板 Schema（例：Confirmed 加了「配偶健康」新字段）→ 同步更新这三个 here-string 模板 |
| §2 8 Case Metadata（L302-L314）| 每 Case 三属性：Name / Difficulty / Tags | 加了 CASE_009~CASE_XXX 时在这里注册；Tags 用来 Level 2「相关 Case 挑选用」，Tags 重叠度越高越优先一起回归 |
| §3 Case 断言解析器（L317-L380）| 用正则从每个 CASE_XXX.md 里抽出「客户输入」+「Assertions YAML 块」，拆成 5 个断言组 + completion_expect | Case 里加了新的断言组（例：加 must_update_handoff）→ 这里加对应的 currentKey switch |
| §4 Eval 引擎（L383-L424）| 目前是 Gold Baseline（156/156 人工已 PASS）+ 六维评分 + SABCD；以后要接入独立 Evaluator 就在这里接 | 接入真实独立 Meta-Evaluator 的时候重写这一段；或者把 SABCD 门槛提高（B→A）|
| §5 Level 调度器（L427-L446）| L1=单 Case；L2=按 Tags 重叠挑相关 Case；L3=全 8 Case | 加 Level 0（冒烟）或 Level 4（跨 Skill 回归）时在这里扩展 |
| §6 报告生成器（L449-L525）| 输出两份：① `regression_report.json`（结构化，供 CI/CD 消费）② `REPORT.md`（Markdown 人类可读，Executive Summary / Per-Case Results / P0 三硬约束最终结论）| CI/CD 接飞书/钉钉机器人告警时，JSON 字段结构调整就改这里 |

### 3.8 Runs 目录（每次执行的产物，长期归档，便于审计 + Diff）

`01-client-intake\runs\` 目录下按日期时间戳建子目录，永远不删（审计合规）：

| 典型产物 | 谁生成 | 什么时候看 |
|---|---|---|
| `regression_YYYYMMDD_HHMMSS\regression_report.json` | run-regression.ps1 Level 1-3 | CI/CD 读 JSON 判断失败；Diff 两个回归报告（例：本周 vs 上周）看哪条 SOP 改动导致回归失败 |
| `regression_YYYYMMDD_HHMMSS\REPORT.md` | run-regression.ps1 | 给人看的摘要；里程碑汇报用 Executive Summary |
| `CASE_001_R1_SKILL_ENTRY_execution.json` | Trae Skill 注册入口实跑 | P0 1/3 证据：字段级 Diff 与基线 0；生产准入硬门槛 |
| `CASE_001_MULTIROUND_R1_R2_SANDBOX_execution.json` | 真实多轮沙箱 R0→R1→R2 实跑 | 多轮链路证据：5.4.1 QID 跨轮清算 + 4.3 Gate→true+HF09 + 沙箱写权限无异常 ；长线 Gap 全 CLOSED 用 |

---

## 五、非技术人员聊天窗口使用指南（零命令行 / 直接复制粘贴 Prompt 模板）

> 适用人群：保险经纪人、客户运营、客服，**不需要懂 PowerShell / 不需要打开任何脚本 / 不需要改文件**。你只需要在聊天窗口里按下面 3 步写 Prompt，Skill 会自动被 Trae 激活并把三份状态文件（客户画像 / 对话记录 / 待补资料）写好。

### 5.1 你要知道的 3 件事（用之前花 30 秒看一下）

| 概念 | 一句话解释（专业版）| 大白话（非技术版）|
|---|---|---|
| **client-intake Skill** | Trae 里注册好的「客户基础信息采集 Skill」，聊天里触发名 = `client-intake` | 你在聊天里说「请用 client-intake」，AI 就会按本 Skill 固定的 10 步流程整理客户信息，不会乱推荐、不会乱猜 |
| **R0 / R1 / R2 / R3…（Round）** | 「轮次」：R0 = 重置干净开始；R1 = 跟客户第一轮对话后整理；R2 = 客户又给了一轮信息再整理… | 跟客户聊了几轮就用第几个模板。**新客户第一轮用 R1 模板，客户又补充就用 R2+ 模板，换下一位客户先跑 R0 重置** |
| **客户说的话「原文粘贴」** | 必须把客户原话完整贴进 Prompt 的 `【客户原文】` 区域，不要自己改、不要自己总结（I2 不变量 = 每条 Confirmed 必须有客户原话追溯）| 客户说「我30岁上海做互联网年收入大概50万吧」就**原封不动整句抄进去**，别自己改成「客户 30 岁上海 互联网年入 50 万」—— AI 会自己提取 |

### 5.2 3 步总流程（非技术版）

```
Step ① 换新客户先 R0 重置（复制粘贴 R0 模板发出去 → AI 回复「✅ 状态已重置」就 OK）
        │
        ▼
Step ② 客户第一轮说的话 → 复制粘贴 R1 模板 + 把客户原话粘进 【客户原文】区 → 发出去
        │  等 AI 整理完回复，看最后「下一步要问客户什么问题」就照着问
        │
        ▼
Step ③ 客户又回答了 / 又补充了 → 复制粘贴 R2+ 模板（R2 / R3 / R4…… 依次加 1）+ 客户原话粘进去 → 发出去
        │  ↺ 重复 Step ③，直到 AI 最后一句说「✅ 基础信息采集完成，可以进入需求分析阶段了」
        ▼
完成！客户画像 CLIENT_PROFILE.md 已自动写好，直接交给下一位同事 / 下一个需求分析 Skill 消费
```

---

### 5.3 场景 1：新客户第一次开始用（**R0 重置模板**，必须第一步先跑）

> 🔔 **什么时候用？** ① 开始接触一位新客户；② 昨天的客户今天继续聊但怕状态被别人改过；③ 任何时候怕不是干净状态，跑一遍 R0 不会错（半分钟的事）。
>
> 🔔 **客户自己看不到这份状态文件**，这是你（经纪人）内部的客户档案，R0 重置就是新建一个空白档案。

**👇 下面这段直接全选复制 → 粘贴进聊天窗口 → 回车发送就行，不用改一个字：**

```
请帮我用 client-intake Skill 做 R0 状态重置（进入新客户前的初始化）。

【操作说明】
- 只做 R0：把 CLIENT_PROFILE.md / CONVERSATION_LOG.md / PENDING.md 三份状态文件全部重置为干净空模板。
- 不需要任何客户输入，R0 是纯初始化操作。
- 做完后请回复：✅ 状态已重置完成（三份状态文件已清空为模板），可以开始 R1 首轮客户信息输入。
```

**💬 你会收到的典型 AI 回复（看得到这个就说明 R0 OK，直接下一步）：**
> ✅ 状态已重置完成（三份状态文件已清空为模板），可以开始 R1 首轮客户信息输入。

---

### 5.4 场景 2：客户第一轮说了话（**R1 模板**，复制粘贴改【客户原文】里的内容就行）

> 🔔 **什么时候用？** R0 跑完后，客户第一次说话（微信 / 电话录音转写 / 口头记录都可以）。
>
> 🔔 **只有一处需要你手动改：就是 `【客户原文】` 区块里的内容，把客户原话整段贴进去，其他地方别碰**。

**👇 下面这段全选复制进聊天窗口 → 然后把 【客户原文】 里灰色示例文字换成你客户实际说的话 → 发送：**

```
请帮我用 client-intake Skill 做 R1 首轮整理。

【本轮信息】
- 轮次（Round）：R1
- 时间：（不用你填，我自己会记录）

【客户原文】
（← 把括号里的灰色字删掉，然后把客户说的原话整段粘贴在这里。
  例子：我30岁，上海，做互联网，年收入大概50万吧。）

【你（AI）需要做的事（按 client-intake Skill 10 步标准流程执行）】
1. 按 Skill 固定顺序读 SOP → CLIENT_PROFILE → CONVERSATION_LOG → PENDING 四份文件
2. 执行 R1 标准 10 步：Step1 清上一轮 unanswered（R0 刚重置完应该是空的）→ Step2 Extract 提取客户明确说过的话，每条 Confirmed 四列追溯字段必须全填 → Step3 Classify 映射 H1-H6 → Step4 Merge → Step5 Gap Analysis → Step6 Completion Check（R1 大概率还没完成，所以 Step7-8 会生成 1~3 个最高优先级追问）→ Step9 写回三份状态文件 → Step10 输出结果

【最后请你用下面三段固定格式回复（我要看的就是这三段，少任何一段都不算完成）】
=== 第一段：本轮已确认的信息（只列客户明确说过的，不猜）===
（按 1. 基本信息 / 2. 家庭情况 / 3. 收入支出 / 4. 负债保障 / 5. 健康风险 五类列，每条后面括号里标客户原话的出处）
例：
1. 基本信息：年龄 30（客户原文「我30岁」）、所在城市 上海（客户原文「上海」）、职业 互联网（客户原文「做互联网」）
…

=== 第二段：还差的关键信息 + 下一步我要问客户的问题（最多 3 个，按优先级排序）===
（如果还差就列 1~3 个；如果已经全部满足，就写「无，基础信息完成」。绝对不能列已经问过、客户已经回答过的问题）
例：
优先级 1（最高）：请问您的家庭结构？（例如：已婚/未婚？有没有孩子？孩子几岁？）
…

=== 第三段：内部状态检查结果（只要结果 OK / NOT OK，不用写细节）===
- Confirmed 四列追溯字段全填：✅ OK / ❓ NOT OK
- 没有虚构推断写进 Confirmed：✅ OK / ❓ NOT OK
- Completion Gate 判定正确（R1 一般 false）：✅ OK / ❓ NOT OK
- 状态文件已成功写回：✅ OK / ❓ NOT OK
```

**💬 你（经纪人）拿到 AI 回复后实际要做的事：**
1. 扫一眼「第一段：本轮已确认的信息」→ 有没有和客户实际说的不一致？（例：客户明明说「大概 50 万」，AI 写成「精确年收入 50 万」就是不对，你要指出来重跑）
2. 看「第二段：下一步我要问客户的问题」→ 直接把这些问题复制粘贴发给客户就行，不用自己想怎么问。
3. 第三段四个 ✅ 都 OK 就放心；有 ❓ 就把整个回复 + 你的问题发给技术同事看（大概率不会遇到 ❓）。

---

### 5.5 场景 3：客户又补充了信息（**R2+ 模板**，第 N 轮就把数字改成 N）

> 🔔 **什么时候用？** 客户回答了你上一轮的追问，或者客户主动又说了新信息（比如「对了，我已婚，小孩 1 岁，一年支出大概 20 万」）。
>
> 🔔 **注意：轮次数字要严格加 1，不能乱跳。** R1 之后就是 R2，再补充就是 R3，再补充就是 R4…… **不要用 Round A / Round 下一次 这种不规范名字**，Skill 内部跨轮清算钩子 §五 5.4.1 严格依赖整数轮次。
>
> 🔔 **还是只有一处需要你改：① 顶部轮次数字（R2 → R3 → R4…）② 【客户原文】区块里的内容**。

**👇 R2 模板：下面这段全选复制进聊天 → 改轮次数字 + 换客户原话 → 发送：**

```
请帮我用 client-intake Skill 做 R2 整理（在 R1 已写好的状态文件基础上继续）。

【本轮信息】
- 轮次（Round）：R2
- 时间：（不用你填）

【客户本轮原文（R2 说的，不要把 R1 重复粘贴）】
（← 把这括号里的灰色字删掉，只贴客户【这一轮新说的话】，不要重复上一轮的。
  例子：已婚，小孩 1 岁，一年支出大概 20 万。）

【你（AI）需要做的事（严格按 client-intake Skill 10 步，重点提醒 Step1 和 Step6）】
1. 按 Skill 固定顺序读 SOP → CLIENT_PROFILE → CONVERSATION_LOG → PENDING 四份文件
2. 【Step1 必须执行！】先跑 §五 5.4.1 QID 跨轮清算钩子：上一轮（R1）末尾 unanswered 的问题，这一轮（R2）入口必须先清算为 answered / ignored / declined，绝对不能跨轮保留 unanswered
3. 然后按标准 10 步 Step2 Extract（每条 Confirmed 四列追溯全填）→ Step3 → Step4 Merge（如果客户 R2 的话和 R1 之前写的有矛盾，比如「去年收入 80 万」后来又改口「去年 60 万今年 80 万」，Profile 正文只保留最新值，旧说法写到 Conflict Notes + Change Notes）→ Step5 → Step6 Completion Check（R2 这一步大概率 H1-H6 6 条都满足了，完成了就 true，后面只能 Follow-up 不能再普通追问）→ Step7-8 只有 Step6=false 才生成 1~3 个追问 → Step9 写回三份状态文件 → Step10 输出

【最后请你用下面四段固定格式回复（少任何一段都不算完成）】
=== 第一段：本轮（R2）客户补充的信息 + 已确认信息总览（含 R1 + R2 两轮）===
（还是分 5 大类列，每条加客户原话追溯；R1 已经确认过的信息也可以简略带过，重点突出「这一轮 R2 新增了什么」）
例：
【R2 新增】
1. 基本信息：（无新增）
2. 家庭情况：婚姻 已婚（客户原文「已婚」）、子女情况 1 子 1 岁（客户原文「小孩 1 岁」）
…
【两轮合计已确认】
（简列一下 5 大类全部确认的项，方便我一眼看全）

=== 第二段：完成情况（请你务必真实判断，不要为了凑进度说假话）===
- Intake 基础信息采集是否完成（H1-H6 6 个最低标准全满足了？）：✅ 已完成 / ❓ 未完成
  - 已完成的理由（分 H1 年龄 / H2 城市 / H3 职业 / H4 家庭责任 / H5 收入 / H6 支出 一条条写）：
    例：H1 年龄 ✅ 30；H2 城市 ✅ 上海；H3 职业 ✅ 互联网；H4 家庭责任 ✅ 已婚+1岁子女（§4.2.1 三问全满足）；H5 收入 ✅ 年约 50 万；H6 支出 ✅ 年约 20 万
  - 未完成的理由（把哪一条没达最低标准写清楚）：

=== 第三段：下一步我要对客户说的话（严格按 Completion 结果决定内容）===
（※ 如果上一段写的是「✅ 已完成」：这里只能说软提醒的 Follow-up 事项，绝对不能再生成新的普通追问客户回答过 / 已经达标的字段）
（※ 如果上一段写的是「❓ 未完成」：这里继续列 1~3 个最高优先级新问题，不能和前面问过的重复）
例（已完成场景）：
1. （软提醒，不是强制问）之后如果方便，可以补充您的具体社保情况 + 现有已购买的保单明细，会让后续分析更准确
2. 以上基础信息已足够进入需求分析阶段，接下来我会基于当前信息为您做保障需求分析

=== 第四段：内部状态检查结果（只要 OK / NOT OK）===
- Step1 5.4.1 QID 跨轮清算执行（上一轮 unanswered 全部清掉，没有跨轮保留）：✅ OK / ❓ NOT OK
- Confirmed 四列追溯字段全填：✅ OK / ❓ NOT OK
- 客户修正旧信息时 Profile 正文只保留最新值，旧值只在 Change Notes / Conflict Notes / Log 留痕（I6 不变量）：✅ OK / ❓ NOT OK
- 完成了就只写 Follow-up 不普通追问（HF09 合规）：✅ OK / ❓ NOT OK
- 状态文件成功写回：✅ OK / ❓ NOT OK
```

**💬 你（经纪人）拿到 AI 回复后实际要做的事：**
1. 看「第二段 完成情况」里有没有出现 ✅ 已完成：
   - **出现 ✅ 已完成** → 直接按「第三段 下一步我要对客户说的话」发给客户，然后把这位客户的 `CLIENT_PROFILE.md` 交给做需求分析的同事 / 下一个 Needs Analysis Skill 消费。你的 Client Intake 工作就**全部结束**了 🎉
   - **还是 ❓ 未完成** → 继续按「第三段」里的新问题问客户。然后用 **R3 模板**（把上面模板里所有 R2 改成 R3）再跑一轮，直到某一轮出现 ✅ 已完成。

---

### 5.6 场景 4（可选）：客户答应回头补资料（Pending 专用 Prompt 小补丁，贴在【客户原文】后面）

> 🔔 **什么时候用？** 客户说了「这个我回头找一下发给你」「下周体检报告出来我给你」「那个旧保单我明天拍给你」。
>
> 🔔 **用法：不用单独跑新模板**，就把下面小补丁整段粘贴在你当次（R2 / R3 / ……）模板的【客户本轮原文】区块**后面**，AI 会自动按 §六 Pending 三态同步规则写入 PENDING.md，下次到提醒轮次（+2 / +4 / +6）Skill 会自己提醒你。

**👇 直接复制整段，括号里的灰色字按客户实际情况改：**

```
【本轮客户承诺后补资料（Pending）小补丁——请按 Pending 三态同步规则处理】
- 客户答应补的具体内容：（例：去年的旧重疾险保单扫描件）
- 客户自己说的怎么补 + 什么时候：（例：客户原话「明天晚上拍给你微信」）
- 对应是在回答哪个问题（Related QID，如果 AI 自己知道上一个 QID 就自动填，不知道就先写 pending，技术同事会补）：
```

---

### 5.7 非技术版常见问题 FAQ（遇到问题先扫这 10 条，95% 的情况不用找技术同事）

| # | 常见问题 | 非技术版答案 |
|---|---|---|
| Q1 | 我忘了跑 R0 就直接跑 R1，会不会出事？ | 影响：之前客户的信息可能残留在状态文件里，导致新客户的画像掺了旧客户数据。**v1.2 推荐新流程（从根上防串档）：按 §六 直接说「新客户」让 Skill 自动建 C00{n} 独立目录，天然物理隔离，不会和上一位客户混**。老版本单客户模式：补跑一次 R0，然后 R1/R2 重跑。|
| Q2 | 客户微信说的话是好几段，还有表情包 / 语音转写的错别字，要不要先整理再贴？ | **不要自己整理，原样粘贴**（除了删掉纯表情和无关的「哈哈哈」这类语气词）。错别字 / 多段换行 / 口语化都保留，AI 会自己规范化。如果你自己先整理成了干巴巴的条目，Skill 的 I2 不变量（Confirmed 要有客户原文追溯）就破坏了，三个月后没人知道信息哪来的。 |
| Q3 | AI 回复「第一段 已确认信息」里出现了客户**根本没说过的话**，怎么办？ | 这是最严重的 HF02（虚构事实 / 越界推断）。处理：① 不要用这份状态文件；② 聊天里直接跟 AI 说「请重新执行 client-intake R1/R2，要求 Step2 Extract 只提取客户原文明确说过的内容，客户没明确说的不能写进 Confirmed 区」，把上一次你提交的 Prompt 整个再重发一次；③ 重跑完还错 → 找技术同事（大概率是 Prompt 模板被你改过了，或者 Skill 被新改了 SOP 没跑回归）。 |
| Q4 | 应该完成了但 AI 还一直反复问同一个已回答过的问题，怎么办？ | 先看 Skill 有没有按「场景 3 R2+ 模板」里的 Step1 执行 §五 5.4.1 跨轮清算（第四段内部状态检查第一条 ✅/❓）。一般是因为你跳了轮次（R1 直接跳到 R3，没跑 R2）或者轮次名字写错了。处理：轮次数字改回严格的整数 R1→R2→R3 不跳，重跑。 |
| Q5 | AI 还主动给客户推荐了「买重疾险买 A 不买 B」，算违规吗？ | **非常严重违规（HF01 越界推荐，直接本轮 FAIL）**。client-intake Skill 唯一职责 = 收集整理信息，**绝不可以**做任何产品推荐、任何保额/保费计算、任何产品比较。处理：① 不要把这段回复发给客户；② 跟技术同事反馈：client-intake Skill 回复出现 HF01 越界，需要跑 CASE_002 + CASE_003 两案的 Level 2 回归；③ 你自己发给客户的话改成：「先了解完您的完整情况，接下来需求分析阶段会帮您做针对性方案对比」。 |
| Q6 | 我想「先做个简单的 Intake，基础信息大概齐就行不用太严格」，可以跳过一些步骤吗？ | 绝对不可以。Skill 的底线：① Confirmed 四列追溯字段少任何一列 = HF07 失败；② H1-H6 少任何一条没达最低标准 = Step6 不会 true = 不能进需求分析。H1-H6 最低标准非常低：年龄（随便个位数都行，不用精确到生日）+ 城市（一线城市/二线城市级别就行，不用精确到街道）+ 职业（大类就行：互联网/公务员/企业员工/自由职业）+ 家庭责任（§4.2.1 婚姻 + 子女 + 老人赡养三问综合）+ 收入（大概范围就行，不用精确到元）+ 支出（大概年支出范围，不用记账）。这 6 条的「最低标准」要求已经很松，客户一般 2~3 轮就能凑齐。 |
| Q7 | 我需要自己打开 CLIENT_PROFILE.md / CONVERSATION_LOG.md / PENDING.md 这三个文件手动写东西吗？ | **完全不需要**，除非你就是负责做 Skill 维护的技术同事。非技术同学只要按上面三个模板复制粘贴，Skill 会自动把这三份文件写好，写得比你手动按格式填更整齐更符合不变量。v1.2+ 多客户模式下这三份会自动写到 `01-client-intake/clients/C00{n}-别名/` 下，连找目录都不用，Skill 自己会切。 |
| Q8 | 一个客户做到一半（比如 R2 了），交给另一位同事继续，怎么交接最稳？ | 交接 3 件事（不用传任何聊天截图 / Word 笔记）：① 告诉接手同事「**客户编号 C00{n} + 客户别名**」（全局唯一，INDEX 能查到）；② 不用发文件，Skill 唯一真源就是 clients 目录下的档案；③ 接手同事第一次继续跑时写：「请切到客户 C00{n}（或直接写别名）开始下一轮」。就这三条，INDEX 里当前轮次 Skill 自己会读，不用你记轮次数字。 |
| Q9（新）| 我同时跟客户 A 聊一半，客户 B 又发来了新消息，我怎么保证两边数据不会混一起？ | v1.2 新多客户隔离机制天然不会混。**最稳的操作习惯：每次输入前在 Prompt 最顶部写一行「【客户 ID】C001」或「切到客户 B C002」或直接说「新客户」。只要写了客户 ID 就 100% 不会串。** |
| Q10（新）| 我忘了当前聊的是哪位来着？怕切错了怎么办？ | 不知道就直接问 Skill：「你现在当前选中的客户是谁？当前第几轮？列表给我看」或者发空消息，Skill 会按 Step 0-B 弹出「新客户 or 已有客户」清单给你选，选完再贴客户说的话进去就行。 |

---

## 六、多客户并行隔离使用指南（v1.2 新增，同时聊 N 个客户不串档）

> 适用场景：上午和 A 客户聊到一半 R1（还没收到 R2），B 客户发来微信要开始新客户；下午 A 客户又回你了；你切回去继续 R2…… 这种「多客户并行」场景，v1.2 原生支持，不再需要手动复制文件夹、不用怕串档。

### 6.1 核心机制（非技术版 30 秒看懂）

| 概念 | 非技术版解释 |
|---|---|
| **客户 ID（C001 / C002 / C003…）** | Skill 自动按顺序给你分配的短编号，第一个客户就是 C001，第二个 C002，以此类推。**永远不会重复**。 |
| **客户别名** | 你给客户起的好记的名字（例：张三三口之家、李姐企业主、王哥高净值），和编号一起显示在清单里，方便挑。 |
| **客户独立目录** | 每位客户的三份状态文件（画像/对话记录/待补资料）都装在一个独立文件夹里，物理隔离（就像你给每位客户建了 Excel 文件，文件名不一样当然不会写到一起）。 |
| **客户索引 INDEX.md** | 一个总表格，列所有建过的客户：编号/别名/当前轮次/完成没/最近更新。**「已有客户清单」就是从这个文件里读出来的**。 |

### 6.2 非技术同学的「多客户四步标准操作流」（和你每天切换微信聊天一样自然）

```
【开始一个新的客户 A】
        │
        ▼
Step A1：聊天窗口里直接说「新客户」→ Skill 自动分配 C001 → 问你要别名 → 你回「张三三口之家」→ Skill 自动建好目录
        │  （Skill 回的典型：✅ 新客户已创建【C001-张三三口之家】，当前轮次 R0，可以开始 R1）
        ▼
Step A2：把客户 A 第一轮说的话 → 复制 §5.4 R1 模板 → 贴进去发送 → Skill 自动写到 C001 目录下 → Skill 回复你整理结果和要问的问题
        │  （客户 A 还没回，先等一等）
        │
        ├──────────────────────────────────────────────┐
        │ 客户 B 突然发来新消息（微信跳红点点）！          │ 切客户就像切聊天窗口
        ▼                                              ▼
Step B1：聊天窗口里直接说「新客户」→ Skill 自动分配 C002 → 你回别名「李姐企业主」→ 建好 C002 目录
        │  （完全不碰 C001 的任何文件，天然隔离）
        ▼
Step B2：客户 B R1 模板贴原话 → Skill 整理完回复「下一步问 XX 问题」→ 客户 B 也还没回，先放一放
        │
        │ 客户 A 终于回你了！（R2 的话来了）
        ▼
Step A3（切回客户 A，关键一步！）：先在 Prompt 最顶部写一句【切到客户 C001】或【客户 ID：C001】（或直接说「切回客户张三」）→ 然后下面继续贴 §5.5 R2 模板 + 客户 A R2 原话 → 发送
        │  Skill 看到 C001：自动切回 C001 目录；从 INDEX 读到「当前轮次 R2」；把 R2 信息写回 C001 的三份文件，完全不碰 C002
        ▼
…… 继续这个切客户流程：每次切客户就先写客户 ID 或说「切回 XX」，然后贴当轮模板 + 原话就行。
```

### 6.3 三个「零出错」非技术版 Prompt 模板（直接复制粘贴就行）

> 🔔 **使用时机：每次你想切客户 / 新建客户 / 忘了当前是谁，都先单独先发这三句中的一句，然后再贴 R1/R2 模板+原话**。

#### 模板 A（10 秒建新客户，完全不用改字）

```
请用 client-intake Skill 帮我新建一位客户。

按 Step 0-A 流程：读 clients/INDEX.md 分配下一个 C{nnn} 编号，然后问我要一个客户别名。
```

#### 模板 B（切回已有客户，把灰色字改一下就行）

```
请用 client-intake Skill 帮我切到已有客户：

【客户 ID / 客户别名】：（← 这里写 C001 或者客户别名「张三三口之家」都行，写一个就够）

切完后回复我：① 客户全名 ② 当前轮到第几轮 ③ 当前 intake_complete 状态。
```

#### 模板 C（忘了现在是谁，弹已有客户清单，零改字）

```
我不知道现在在和哪位客户，请用 client-intake Step 0-B + Step 0-C 流程：
先问我「新客户 or 已有客户」；我选了已有就列 INDEX 里的全部客户表格让我挑。
```

### 6.4 多客户场景下，「原来的 §5.3/5.4/5.5 R0/R1/R2 模板」怎么改？

**几乎不用改。** 建议只在模板最顶部加一行：`【客户 ID】C001`（或你的客户别名）。剩下下面内容和 v1.1 用起来一模一样。

例子（这是 R2 模板开头，就加了第一行 20 个字）：

```
【客户 ID】C001（← 就多了这一行！其它内容完全不动）

请帮我用 client-intake Skill 做 R2 整理（在 R1 已写好的状态文件基础上继续）。

【本轮信息】
- 轮次（Round）：R2
...（后面和 §5.5 R2 模板完全一样，不用改）
```

如果你**嫌这行都懒得写**也没关系，只要你上一次和 Skill 对话聊的就是这个客户，Skill 默认就继承上次的客户 ID，直接贴模板就行。只有你要切到别人的时候才必须写。

### 6.5 多客户版 FAQ（新增 3 个高频问题）

| # | 常见问题 | 非技术版答案 |
|---|---|---|
| M1 | 我每次都要先写【客户 ID】才不会错吗？有没有更省事的？ | **连续聊同一位客户不用写**。Skill 会记住「上次用的是谁」，直接续就行。只有两种情况必须写：① 你要切到另一位客户；② 你隔了一天回来聊 / 怕自己忘了当前是谁（写一下最稳，10 个字的事）。 |
| M2 | 我写了【切到客户 C002】，怎么确认 Skill 真切对了？ | Skill 切完一定会回复 3 条：① 全名 ② 当前轮次 ③ 完成状态。你扫一眼就知道对错，没对的话再写一次，错不了。INDEX.md 是权威真源，Skill 就是按它切的。 |
| M3 | 我想删一个客户（比如发现 C003 是重复建档的），怎么操作？ | 非技术同学不要删，找技术同事把 `clients/C003-{别名}/` 目录删掉，然后把 INDEX.md 那一行删掉。别手改 INDEX.md 里的行号和客户编号，不然会乱。 |

### 6.6 技术版：目录结构 & 命令行辅助脚本（给工程 / 运维 / Prompt 工程师看）

#### 6.6.1 目录结构（和 SOP §二 2.1 对齐）

```
01-client-intake/clients/
├── INDEX.md            ← 唯一索引（8 列：行号 / 客户编号 / 客户别名 / 档案目录 / 创建时间 / 当前轮次 / 完成状态 / 最近更新）
├── C001-张三三口之家/
│   ├── CLIENT_PROFILE.md
│   ├── CONVERSATION_LOG.md
│   └── PENDING.md
└── C002-李姐企业主/
    └── ...
```

#### 6.6.2 PowerShell 辅助脚本：一键建空客户（技术同事快捷初始化目录 + 写 INDEX，非技术版完全不需要，走聊天 Step 0-A 就行）

```powershell
# 手动快捷建一个空客户目录（不用跑 Skill）
# 参数：$ClientAlias = 客户别名（例："张三三口之家"）
function New-ClientFolder {
  param([string]$ClientAlias)
  $Root = "d:\Workspace\insurance-agent\01-client-intake\clients"
  $IndexPath = Join-Path $Root "INDEX.md"
  # 1. 找下一个客户编号
  [int]$maxN = 0
  if (Test-Path $IndexPath) {
    Select-String -Path $IndexPath -Pattern "^\|\s*\d+\s*\|\s*C(\d{3})\s*\|" -AllMatches | ForEach-Object {
      foreach ($m in $_.Matches) { [int]$n = $m.Groups[1].Value; if ($n -gt $maxN) { $maxN = $n } }
    }
  }
  $nextN = $maxN + 1
  $cid = "C{0:d3}" -f $nextN   # C001 / C002 / ...
  $folderName = "$cid-$ClientAlias"
  $clientDir = Join-Path $Root $folderName
  New-Item -ItemType Directory -Force -Path $clientDir | Out-Null
  # 2. 写三份空模板（真实项目调用 run-regression.ps1 Reset-StateFiles -ClientId $folderName -ForceWrite；此处简略）
  $regressionScript = Join-Path (Split-Path $Root -Parent) "..\scripts\run-regression.ps1"
  if (Test-Path $regressionScript) {
    & powershell.exe -ExecutionPolicy Bypass -File $regressionScript -NoResetState -ClientId $folderName -Level 0
  }
  # 3. 追加 INDEX 一行（真实项目用 CSV 读-改-写更稳，此处演示用文本追加）
  $today = Get-Date -Format "yyyy-MM-dd"
  $line = "| {0}    | {1}     | {2} | clients/{3}/ | {4} | R0       | ❌ 未完成       | {4} |      |" -f $nextN,$cid,$ClientAlias,$folderName,$today
  if (-not (Test-Path $IndexPath)) {
    @(
      "# Client Intake 客户索引（INDEX）",
      "",
      "> 本文件由 Skill 的 Step 0-A（新客户创建）/ Step 9（写回轮次）自动维护，禁止手动改内容。",
      "> 只有这 3 种情况会写 INDEX：新客户创建 / 每轮状态写回后轮次 +1 / Completion Gate true 时标记已完成。",
      "",
      "| 行号 | 客户编号 | 客户别名            | 档案目录（相对路径）           | 创建时间   | 当前轮次 | Intake 完成状态 | 最近更新   | 备注 |",
      "|------|----------|---------------------|--------------------------------|------------|----------|-----------------|------------|------|"
    ) | Set-Content -Path $IndexPath -Encoding UTF8
  }
  Add-Content -Path $IndexPath -Value $line -Encoding UTF8
  Write-Host "✅ 新客户已创建 [$cid - $ClientAlias] → 目录 $clientDir ，INDEX 已追加一行"
}

# 例子：建「张三三口之家」
# New-ClientFolder -ClientAlias "张三三口之家"
```

---

## 七、全流程 7 个交互式 UI 节点操作指引（v1.2 升级版 —— 不用打字，直接点单选框就行）

> 🎯 **核心升级：** 之前整个 Skill 所有需要你做选择/做决策的地方，都是 Skill 输出纯文字 → 然后你打字回复「选 B」「用新值」→ 多一轮对话，比较慢。
> 
> 现在 7 个决策节点**全部改成 TRAE 原生的交互式单选框组件**（就像 brainstorming 技能那样弹出来）。你只需要点选项 + 点「确认」就行，**95% 场景零打字**。
> 
> 只有客户原话内容、自定义别名这种自由文本才需要打字，所有「是 / 否 / 选哪个 / 下一步做什么」的选择题全部 UI 化了。

### 7.1 7 个节点总览（一眼就知道什么时候会弹单选框）

| 节点 # | 发生在什么阶段 | 弹单选框问你什么 | 默认选中什么（90% 场景直接点确认就行）|
|--------|--------------|----------------|-------------------------------------|
| **1 / 7** | 新客户 / 旧客户分不清的时候（兜底） | 选「新客户」还是「已有客户」 | 🆕 新客户（推荐第一次聊的新客户）|
| **2 / 7** | 选已有客户时 | 从客户清单里点选一位（自动带轮次 + 完成状态图标）| 最近更新的那位客户（通常你就是继续上一位）|
| **3 / 7** | 创建新客户 Step 0-A | 选客户类型（三口之家/企业主/单亲/单身/高净值/自定义）| 👨‍👩‍👧 标准三口之家（最常见）|
| **4 / 7** | **MR2 冲突处理**：客户前后说法对不上（例先说 30 后说 32）| 选：用新值 / 保旧值 / 暂存等下轮核实 | ✅ 用本轮新值（客户通常是修正旧信息）|
| **5 / 7** | **Intake 刚好完成那一刻**（6 项 P0 全收齐） | 选：进需求分析 / 先补 Follow-up / 先暂停 | 🚀 立即进 Needs Analysis（推荐）|
| **6 / 7** | **每轮还要追问时**（还缺 P0，已生成 1~3 个问题）| 选：用话术发客户 / 先不追等下轮 / 先切其他客户 | 💬 直接用口语化话术发客户（90% 场景立刻发）|
| **7 / 7** | **HF09 完结门控触发**（已完成后又发了新信息）| 选：补进 Follow-up / 回滚未完成重算 / 取消不写入 | 📝 追加进 Follow-up（通常只是客户补了点细节）|

### 7.2 给非技术同事的 3 条操作小贴士（遇到单选框怎么用）

1. **绝大多数场景你只需要点「确认」**
   我们把单选框的「默认选中」永远设成 90% 概率会选的那个选项（例：新客户默认选三口之家；冲突默认选新值）。所以大多数时候弹框出来，你扫一眼描述没问题，直接点「确认」就好，不用翻列表。

2. **不点点选框，直接打字也行（100% 兼容）**
   如果你不习惯点 UI，或者想快速用习惯的方式，直接打字回复也是没问题的。比如冲突时你直接打字说「用新值」，Skill 照样能识别并执行。**两种方式永远并行可用，不会因为你没点 UI 就卡住。**

3. **3 种场景会连续弹两次单选框（正常现象，别紧张）**
   你可能会遇到「弹了 A 框，你点完确认 → 立刻又弹 B 框」的情况，这是刻意设计的正常流程：
   - 场景一：Step 0-B 选「已有客户」→ 立刻弹 Step 0-C 的客户清单选择框
   - 场景二：Step 6 每轮要追问 → 点「先切其他客户」→ 立刻弹 Step 0-C 的客户清单选择框
   - 场景三：Step 0-A 选「我自己输入别名」→ 立刻弹纯文本提示让你打字输入别名

### 7.3 常见问题 FAQ（交互式 UI 版）

| 编号 | 问题 | 回答 |
|------|------|------|
| UI1 | 弹单选框了，但我突然想取消这次操作怎么办？ | 直接打字说「取消这次」或者「先别做这个，我先做别的」，Skill 会自动跳过后续分支 |
| UI2 | 单选框里的选项描述看不懂怎么办？ | 每个选项下面都有一行灰色小字「描述」，会告诉你选这个选项 Skill 会做什么动作。扫一眼就行 |
| UI3 | 选项里 6 个客户类型都不是我要的场景（例：客户是丁克家庭/三代同堂）| 直接点最后一项「✏️ 我自己输入别名」，然后打字告诉 Skill 客户叫什么就行（自由文本兜底）|
| UI4 | 客户前后说法冲突，但这次说法特别复杂（不是简单的年龄 30→32，是收入结构大改），单选框三个选项都不够怎么办？ | 点第三个「⏸️ 暂不更新下轮再确认」，然后 Skill 会自动把冲突点整理成话术模板，你下一轮发客户核实，核实完再处理就好 |
| UI5 | Intake 已经完成了，这次发的信息其实是我粘错了，不是这个客户的 | 弹 HF09 完结门控选框时直接点第三个「❌ 这次先别写入档案，我取消这次输入」，什么都不会改，直接当这轮没跑过 |

---

## 八、最后：长期维护的铁律（保持 Production Ready，不回退到 v1）

如果以后团队维护这个 Skill，请严格遵守 4 条铁律（v1.2 新增 I8 多客户隔离不变量 + 交互式 UI 不变量，新增第 4 条）：

1. **改规则先改 SOP，再改 Case 断言，最后跑回归**。顺序：SOP.md → CASE_XXX.md Assertions → 跑 Level 2 相关 Case → 跑 Level 3 全量 → 确认 8/8 ≥B 且 Hard Fail=0 才能上生产。
2. **任何 Confirmed 四列追溯字段（值 / Source Round / Source Text）少任何一列 → 视为 HF07 State Persistence Failed，本轮 FAIL**。不能因为「客户说的比较短就不填 Source Text」，否则三个月后你根本不知道 Confirmed 值是怎么来的（I2 不变量是长期可维护性的生命线）。
3. **任何 Hard Fail 命中 → 本轮失败，不允许拿高分 EVAL 去掩盖**。先定位 RC1-5 根因，改 SOP / Case，重跑同一轮，Hard Fail 清 0 才能谈分数。
4. **（v1.2 新）多客户隔离红线（不变量 I8）：执行客户 C00{aa} 时，任何读写操作不得触碰 C00{bb}（bb≠aa）的目录，哪怕 C00{bb} 的内容和本轮话题很像。维护 INDEX.md 时，禁止手动改客户编号 C00{n} 里的数字顺序。**（想删客户先删客户目录，再同步删 INDEX 对应行，别直接改 C003→C002 这种编号，不然会和已存档 runs/ 里的快照文件名对不上）。

这样做，这个 Skill 可以稳定维护多年而不变成「再也不敢改的 Prompt 黑箱」。
