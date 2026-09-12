# 06 — 文件结构、Source of Truth 与状态文件更新规则

## 2.1 目录结构（v1.2 多客户并行版）

```text
.trae/skills/client-intake/          ← Skill 本体（本目录）
├── SKILL.md                          ← 入口（Step 0 客户上下文切换 + 路由）
├── references/                       ← 规则（按需加载，替代原 SOP.md）
├── schemas/                          ← 输出契约
├── resources/                        ← 交互节点 / 模板
├── scripts/                          ← 确定性校验
└── evals/                            ← 评估策略 + 用例

client-intake-data/                     ← 业务数据（不存规则）
├── runs/                             ← 执行快照（回归报告 / 多轮沙箱）
└── clients/                          ← ★ 多客户隔离根目录
    ├── INDEX.md                      ← ★ 客户索引（编号/别名/轮次/完成状态/最近更新）
    ├── C001-张三三口之家/
    │   ├── CLIENT_PROFILE.md         ← 客户 1 的唯一长期状态源
    │   ├── CONVERSATION_LOG.md       ← 客户 1 的对话历史 + QID 注册表
    │   └── PENDING.md                ← 客户 1 的待补资料 + 提醒节奏
    └── C002-李姐企业主/...
```

### 2.1.1 `clients/INDEX.md` 固定格式（所有新增 / 切换客户都以这里为唯一真源）

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

运行时根目录 `client-intake-data/` 下**不应出现** `CLIENT_PROFILE.md / CONVERSATION_LOG.md / PENDING.md` 三份顶层文件——它们是 v1.0/v1.1 单客户架构遗留产物，已在重构中删除。**多客户并行模式（v1.2+）下，所有客户数据只进 `client-intake-data/clients/C00{nn}-{别名}/` 独立目录**，顶层根目录保持为空。

---

## 2.2 状态唯一性原则（多客户并行版）

**先确定客户上下文，再读状态文件是第一优先级（Step 0 > 所有 10 步）。**

`clients/C00{nn}-{别名}/CLIENT_PROFILE.md` 是**该客户唯一长期状态源**，和其它客户的文件严格隔离、互不影响。

规则如下：

0. **（Step 0 强制执行）** 任何执行前先跑 SKILL.md §Step 0 客户上下文切换逻辑确定客户目录；4 种触发顺序：
   - ① Prompt 里明确写了 `【客户 ID】/【客户别名】` → 直接用
   - ② 对话记忆里存在「上一次用的客户」且本轮没说要切客户 → 默认继续用
   - ③ Prompt 说「新客户 / 新建」→ Step 0-A 建新客户
   - ④ 都不满足 → Step 0-B 先问「新客户 or 已有客户」，不得擅自推断
1. 确定客户后，必须按以下固定顺序读取，不得跳过：
   - Skill 规则（本 `references/` 目录，替代原 `SOP.md`）
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
6. JSON 输出仅是**本轮该客户端执行结果**，不是下一轮的输入来源
7. 如果 JSON 与状态文件冲突，以「客户目录下的 3 份」为准（Client > Pending > Log > JSON）
8. **当前 Round 的唯一判断有 2 个独立来源互相对照（防止跳轮次）：**
   - ① `clients/INDEX.md` 中该客户行的「当前轮次」字段（由 Skill Step 9 写回，官方权威）
   - ② 该客户自己的 `CONVERSATION_LOG.md` 中最后一个已记录 Round
   - 如果两者不一致 → 本轮先按 INDEX 的为准，执行完 Step9 后同时把两者同步一致

### 2.3 三份状态文件分工（都在客户目录下）

| 文件（相对 `client-intake-data/clients/C00{nn}-{别名}/` 路径）| 职责 | 读者 |
|------|------|------|
| `CLIENT_PROFILE.md` | 该客户当前最新画像、白名单 inferred、缺口摘要、完成状态。Needs Analysis 等后续 Skill **只读这份**。 | 后续 Skill + 当前 Skill |
| `CONVERSATION_LOG.md` | 该客户历史轮次原文、Asked Questions Registry、每轮状态变更记录（QID 状态转换/Conflict Notes）。只用于多轮记忆 & 追溯，不作为长期事实。 | 当前 Skill |
| `PENDING.md` | 该客户答应补的保单/资料/数据；提醒节奏（进入 Pending 的轮次 +2/+4/+6，最多 3 次）；三态与 QID 同步规则（received→answered / declined→declined / expired→ignored）。 | 当前 Skill |

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
