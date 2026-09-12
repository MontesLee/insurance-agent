# Domain Overlay 协议

> 设计来源：Lawgent 的 `Generic Skill + Domain Pack / Overlay` 模式。
> 本目录是 `client-intake` 的**险种扩展层**。

## 一、为什么需要 Overlay

保险有 7+ 个险种（重疾、医疗、寿险、意外、年金、教育金、传承……）。
如果为每个险种复制一份 Skill：

```
client-intake-critical-illness
client-intake-medical
client-intake-life
...
```

会产生 7 份重复规则，改一处要同步 7 次，必然漂移。

Overlay 模式把这些差异抽出来：

```
        client-intake (generic)
                 │
     ┌───────────┼───────────┬───────────┐
     ▼           ▼           ▼           ▼
 critical-    medical      life      accident ...
  illness
```

通用规则只有一份，险种差异按需叠加。

---

## 二、核心原则：Overlay 只加"信息维度"，不加"判断规则"

这是本 Skill 与 Lawgent 场景最大的不同，必须严格遵守。

`client-intake` 的边界是**只交付事实与缺口，不做保险判断**（见 `references/01-boundary.md`）。
因此 Overlay **只允许**增加：

| 允许 | 例子 |
|---|---|
| 该险种特有需要采集的**信息字段** | 医疗险要问社保类型、就医习惯 |
| 该险种的**事实记录口径** | 意外险的职业类别按客户自述记录 |
| 该险种的**触发条件** | 客户提到"重疾"→ 激活重疾 overlay |
| 该险种的**边界红线** | 不得评价疾病严重程度 |

Overlay **禁止**增加：

| 禁止 | 原因 |
|---|---|
| 产品推荐 / 产品比较 | 越界 HF01 |
| 保额、保费计算或建议 | 越界 HF01 |
| 医学风险评价、核保结论预判 | 越界（且是硬伤） |
| 修改通用层的 H1-H6 完成标准 | 通用层唯一真源 |
| 修改 QID 状态机、Pending 节奏 | 通用层唯一真源 |

一句话：

> **Overlay 决定"多问什么"，不决定"怎么判断"。**

---

## 三、目录结构

```
overlays/
├── README.md                 本文件（协议）
├── _template/                新增险种时复制此目录
│   ├── overlay.yaml
│   └── intake-dimensions.md
├── critical-illness/
├── medical/
├── life/
├── accident/
├── annuity/
├── education/
└── inheritance/
```

每个 overlay 目录**必须**包含两个文件：

- `overlay.yaml` — 机器可读的元数据与触发条件
- `intake-dimensions.md` — 该险种的采集维度（给人读，Agent 按需加载）

---

## 四、overlay.yaml 契约

```yaml
id: <kebab-case 唯一标识，与目录名一致>
name: <中文名>
version: 0.1
status: draft            # draft | active；draft 不会被自动激活
priority: 10             # 数字越大越优先；用于追问排序
triggers:
  keywords: [...]        # 命中任一关键词即命中该 overlay
  goal_types: [...]      # 结构化目标类型（如 critical_illness）
requires_confirm: true   # 命中后是否需向客户确认纳入本次范围
dimensions: intake-dimensions.md
contamination_terms:     # 险种专有术语，禁止出现在通用层
  - ...
boundary:
  must_not:              # 该险种下额外的禁止行为
    - ...
```

字段说明：

- **`status`**：`draft` 表示该 overlay 尚未验证，不会被 `resolve-overlays.ps1` 自动激活。新险种一律从 `draft` 起步。
- **`requires_confirm`**：多数险种应为 `true`。客户提到"重疾"不代表只关心重疾，需确认后才纳入必填范围，避免信息轰炸。
- **`contamination_terms`**：这个字段是**架构守卫**。它声明"这些词只属于本险种"，`check-overlay-integrity.ps1` 会扫描通用层（SKILL.md / references/ / schemas/）是否混入了这些词。一旦混入，说明通用层被领域污染，架构已退化。

---

## 五、Overlay 如何参与主流程

```
Step 3 Classify
     │
     ▼
Step 3.5 Resolve Overlays  ← 新增（本层负责）
     │   命中 triggers → 得到候选 overlay
     │   requires_confirm=true → 生成一条确认提问，客户确认后才纳入
     ▼
Step 4 Merge State
     │   激活的 overlay 维度并入本次 coverage checklist
     ▼
Step 5 Gap Analysis
     │   缺口 = 通用 H1-H6 缺口 + 已激活 overlay 维度缺口
     ▼
Step 6 Completion Check（Gate）
     │   intake_complete 需同时满足：
     │   - 通用 H1-H6 达标
     │   - 已激活 overlay 的 required 维度达标
     │   未激活的 overlay 维度一律不参与判定
     ▼
Step 7 Prioritize / Step 8 Generate Questions
         按 overlay.priority 参与排序（高的先问）
```

关键约束：

1. **未激活 = 不追问**。医疗险的免赔额偏好，对只看重疾的客户不产生任何问题。
2. **确认前不算 required**。`requires_confirm=true` 的 overlay，在客户确认前其维度只能记为 `missing`，**不得**成为 `intake_complete` 的阻塞项。
3. **Overlay 不改写通用层**。H1-H6、QID 五态、Pending 节奏仍以 `references/` 为唯一真源。

---

## 六、状态文件里的落点

Overlay 采集到的事实仍写进 `CLIENT_PROFILE.md`，但归入独立小节：

```
## 4. 险种专项信息
### 4.1 重疾险（overlay: critical-illness, active）
| 字段 | 当前值 | source_round | source_text |
```

好处：

- 下游 `requirement-analysis` 可直接按 overlay id 分块消费
- 未激活的险种不产生空小节，保持档案干净
- 结构与通用层一致（同四列），现有 `check-state-invariants.ps1` 的 I1-I8 能直接覆盖

---

## 七、新增一个险种的标准动作

1. `cp -r _template/ <new-id>/`
2. 填 `overlay.yaml`：id / name / triggers / contamination_terms / boundary
3. 写 `intake-dimensions.md`：只写采集维度与记录口径，不写判断
4. `status: draft` 起步
5. 跑 `scripts/check-overlay-integrity.ps1` 校验结构与污染
6. 至少补 1 个 `evals/cases/` 用例后，才允许改 `status: active`

---

## 八、与通用层的分工（对照表）

| 关注点 | 归属 |
|---|---|
| confirmed / inferred / missing / pending 定义 | 通用层 `references/02` |
| H1-H6 完成标准 | 通用层 `references/03` |
| QID 状态机、追问优先级 | 通用层 `references/04` |
| 10 步工作流 | 通用层 `references/05` |
| 状态文件读写 | 通用层 `references/06` |
| **某险种要额外问什么** | **Overlay** |
| **某险种的事实记录口径** | **Overlay** |
| **某险种的触发条件** | **Overlay** |
| **某险种特有的边界红线** | **Overlay** |
