# Phase 28.K.29 — 步骤级流式文本框按里程碑归位（嵌套渲染）

> 承接 28.K.27 / 28.K.28（step 级流式输出盒）。本次**不改数据层**，
> 只改**渲染位置**：每个 step 的文本框从「卡片最下方一叠」改为
> **挂在它自己产出的那条里程碑之下**。

## 1. 动机（用户反馈）

用户看到的是一列里程碑（`✓已了解家庭基本情况 / ✓已完成信息核实 / ✓已分析保障需求 / …`），
而**所有** stream 文本框都堆在列表最下方：

> 「我希望是下面这些每一个步骤下都有一个文本框，展示当前步骤下的 stream，
> 现在所有的文本框都在步骤列表的最下方，看起来不直观。」

文本框内容本身没问题（28.K.28 已让 reasoning 可见），问题是**归属关系丢失**：
用户无法知道哪段文本属于哪一步。

## 2. 改动（最小增量，未提交）

| 文件 | 改动 | 原因 |
|---|---|---|
| `web/src/state/activity.ts` | `consumerActivities` 抽出唯一实现 `foldConsumerActivities`，额外返回 `spans`（每个 activity **由哪个事件下标创建**）；公开 DTO `consumerActivities` 形状**完全不变** | 归属判断需要「事件顺序」这一事实；DTO 是对外契约，不动 |
| `web/src/state/stepAnchors.ts`（新增） | `activityAnchors(events, bucketKeys)`：把 step 桶映射到 activity key（纯事件序算术） | 归属规则独立可测 |
| `web/src/components/chat/AgentActivity.tsx` | 活动行 `<li>` 内：行元素 `data-activity-item` 拆成内层 `div`，同级渲染该步文本框（`ml-5 + border-l-2` 缩进，`data-testid="activity-step-outputs"`）；**底部容器降级为兜底**，只渲染无归属的桶 | 嵌套；行文本保持不变（`itemTexts()` 语义不变） |
| `web/src/state/stepAnchors.test.ts`（新增） | 11 条：产出新里程碑 / 无新里程碑 / QA 桶 / 零活动 / 前向解析一次后不动 / 未知 stage-tool 无幽灵锚点 / 纯函数 | 新契约 |
| `web/src/components/chat/stepOutput.test.tsx` | 9 → 15 条：新增 6 条嵌套断言（归属正确、DOM 顺序随行顺序、盒是行的**兄弟**而非子节点、光标跟随活跃步、无归属桶不丢、缩进与左边框存在） | 新契约 |

**没有删除任何测试**：原 9 条 step 盒测试、`stepOutputE2E`、`streamMessage`、
`AgentActivity`、`consumerDom` 全部原样通过。

## 3. 归属规则（确定性，无内容启发式）

`activityAnchors` 只做事件序算术：

1. `foldConsumerActivities` 报告每个 activity **首次被创建**的事件下标 `firstIndex`。
2. 每个 step 桶 `step-N` 的**原点** = 它那条 `agent_step_started` 的下标；
   隐式 QA 桶 `qa-composing` 由**瞬时 delta** 打开（delta 不入 `events[]`），
   原点取「时间线末端」。
3. **归属 = 原点之后第一个新建的 activity** —— 即这一步的 LLM 调用最终**产出的**里程碑
   （先推理 → 再决策 → 再 `stage_started`）。
4. 若该步没有产出新 activity（重复跑已见过的 stage、收尾步），
   **回退到原点之前最近的一条** activity。
5. 若事件序列里**没有任何 activity** → 归属 `null`，由底部兜底容器渲染，**绝不丢弃**。

`qa-composing` 在「检索已完成」的 QA 轮里归属 `composing`（正在整理回答），
无检索时回退 `work`。

**单调性**：未解析的桶只会**向前**解析一次（stage 开始时），此后新增事件不再移动它
（`stepAnchors.test.ts` 第 7 条固定该不变量）。

## 4. 明确保住的边界（未改动）

1. **`ConsumerActivity` 公开 DTO 仍是 `{key,label,status}`** ——
   `activity.test.ts` T12（键集合断言）与各处 `toEqual` 原样通过。
2. **activity 行文本不变** —— 文本框是行的**兄弟节点**，`itemTexts()` 仍是
   `✓已了解家庭基本情况`；`AgentActivity.test.tsx` 全部断言未改。
3. **不向 DOM 泄漏内部标识** —— 归属只用于选择渲染位置，**不落任何属性**；
   `consumerDom.test.tsx` 的 FORBIDDEN 全表仍通过。
4. **答案气泡仍 `content-only`**、`sanitizeConsumerText` 仍逐段生效（未触碰）。

## 5. 验证

- `tsc --noEmit` → **exit 0**
- 全量前端套件 → **35 files / 300 passed · 2 skipped（302）· exit 0**
  （改动前 283 passed；净增 17 条断言，0 失败）
- 视觉验证：用 `vite build` 产出的**项目自身 CSS** 渲染真实组件 DOM，
  生成 `web/dist/preview-step-nesting.html`（两个状态：运行中带光标 / 已完成）。
  `web/dist/` 与临时转储脚本均已清理，不入库。

## 6. 未做 / 残余风险

1. **live 浏览器端到端未执行** —— 后端 `:8123` 当前未运行，本文件所有结论
   基于组件级渲染 + 全量单测，**未声称真机通过**。
2. **归属在首步内可能「下跳一格」**：step 的 stage 尚未开始前，文本框暂时挂在
   上一条已存在的里程碑下，stage 一开始就移到正确位置。这是文档化的前向解析，
   不做延迟渲染（延迟会让首步整个推理阶段无任何可见输出，与 28.K.27 的修复目的冲突）。
3. 一步产出的文本若跨两个里程碑（同一 step 内先检索后分析），文本只会出现在
   **第一个**新建里程碑下。
