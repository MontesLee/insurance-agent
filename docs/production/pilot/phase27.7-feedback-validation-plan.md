# Phase 27.7.5 — Human Feedback Validation Plan

Status: DESIGN (2026-09-24; validation not yet run) · Feature
under test: Phase 27.7 Capture MVP @ commit 55ac759 · Upstream
design: docs/architecture/human-feedback-loop-v0.1.md + ADR-018

---

## 1. Validation Objective

本验证**不是**测试 UI(UI 已有 113 项测试)。验证的是:

**Human Feedback Quality** —— 真实审核者在使用 MVP 后,

1. 是否**愿意**产生结构化反馈(行为)
2. 反馈是否**足以**成为评估数据源(信号质量)
3. 六类 taxonomy 是否**合身**(分类学)
4. 是否值得投入 Phase 27.8(决策)

对应 ADR-018 的核心赌注:反馈作为"证据"而非"控制信号"是否
能在真实使用中沉淀出价值。

---

## 2. Pilot Scenario Design

### Case Selection(6–8 个,复用 Phase 27 资产)

从 Phase 27 已有合成 case 证据(tmp/pilot27 工件 + owner-review
工作台)中选取,必要时重跑流水线生成新 approvals:

| 槽位 | Case 来源 | 覆盖 |
|---|---|---|
| R1 | C02(single_adult,有 primary C001)| recommendation case |
| R2 | C01(child_protection,无 primary)| recommendation 缺证据场景 |
| R3 | C10(complex_family)| risk analysis case |
| R4 | C11(kb-empty,NEEDS_REVIEW)| evidence retrieval fail-closed |
| R5 | C08(WAITING_FOR_USER)| missing information 场景 |
| R6 | C12(empty requirements)| 输入边界 |
| R7–8 | 复跑 1–2 个新 case(report 类)| report generation |

说明:harness approvals 需真实存在于 approvals.jsonl(可由
harness 运行时或最小 fixture 造出 PENDING→WAITING_HUMAN 记录;
不伪造已决定记录)。审阅者在**知情同意**下参与(合成数据,
无客户隐私)。

### Reviewer Flow(全部走真实 UI)

```
打开 Review Queue → 选择项目 → 进入待审条目
  → Review Workspace:读 A-F 节(摘要/上下文/时间线/产物/证据链)
  → Decision Panel:Approve 或 Reject(+意见)
  → Feedback Panel(G 节):可选填写结构化反馈 → Submit
```

要求:审阅者**不被告知**"应该填反馈"(测真实意愿);每人独立
完成 6–8 个 case;记录每个 case 的起止时间。

### 数据采集说明(MVP 存储为 localStorage)

反馈记录在审阅者浏览器内(key `webui:feedback:v1`)。采集
流程:每位审阅者完成后,用 DevTools 或一行
`JSON.parse(localStorage.getItem("webui:feedback:v1"))` 导出
JSON 交给分析者(与 GAP-27.7-01 一致 —— 这是 MVP 存储的已知
边界,也是本验证要顺带确认的可操作性问题)。

---

## 3. Metrics

### Metric A — Feedback Completion Rate
`填了反馈的决定数 / 总决定数`,按 APPROVE / REJECT 分开统计
(预期 REJECT 侧显著更高;APPROVE-with-comment 是加分信号)。

### Metric B — Feedback Quality(Actionable?)
分析者对**每条**反馈做双评(不一致时讨论定分):
- **Actionable?** Yes/No —— 是否能指导后续改进
- 高质量例:`MISSING_INFORMATION:"未询问客户已有百万医疗险,
  导致重复保障分析"`(对象+原因+影响)
- 低质量例:`"模型不好"`(无对象、无原因)

### Metric C — Taxonomy Fit
统计:无法选分类的次数(记录为 "unclassable" 事件)、分类
分布(是否存在某类长期为 0 或爆满)、审阅者是否口头要求
"Other"。

### Metric D — Conversion Potential
每条反馈独立判断可否转化为:Evaluation Case / Knowledge
Issue / Product Requirement(可多选/可均否)。

---

## 4. Feedback Review Rubric(0–4)

| 分 | 标准 |
|---|---|
| 0 | 无行动价值("不好""不对") |
| 1 | 描述了问题(有对象,无原因) |
| 2 | 包含原因(对象+为什么错) |
| 3 | 包含期望行为(对象+原因+本应如何) |
| 4 | 可直接形成 Evaluation Case(2 或 3 + 可复现输入/引用) |

统计分布;≥2 记为 Actionable(与 Metric B 交叉校验)。

---

## 5. Data Collection(pilot 分析用,不动 production schema)

每条反馈的分析记录(电子表格/JSONL,离线):

```
feedback_id, decision_id, category, description,
reviewer(匿名编号), case_id, quality_score(0-4),
actionable(Y/N), conversion_type(eval_case|knowledge|
product_req|none), notes
```

另记会话级:每 case 审查时长、completion(Metric A)、
unclassable 事件、导出摩擦(采集流程是否顺畅)。

---

## 6. Success Criteria(校准型 —— 首轮不拍脑袋定死)

**首轮定位:校准基线**,以下阈值为**先验假设**,数据回来后
修订,再作为 27.8 的进入门槛:

| 假设阈值 | 含义 |
|---|---|
| Completion(REJECT 侧)≥ 50% | 拒绝时人愿意说原因 |
| Completion(APPROVE 侧)≥ 15% | 正向信号也存在 |
| Actionable(≥2 分)≥ 40% | 值得做转化管道 |
| 至少 2 条 4 分反馈 | 存在可直接转 eval case 的样本 |
| unclassable < 20% | taxonomy 基本合身 |

任何阈值不达 ≠ 直接失败 —— 结合定性访谈判断是 UI 摩擦、
引导不足还是真无价值(见 §7)。

---

## 7. Failure Scenarios(预设解释框架)

**A. 审阅者不填反馈** → 可能:流程成本高(表单位置/字段数)、
无价值感(看不到反馈去向)。对策候选:表单前移至决定确认
弹窗、显示"你的反馈将进入评估集"。先访谈再改。

**B. 反馈太泛("结果不好")** → 可能:taxonomy 或引导不足。
对策候选:description 占位文案给句式模板(对象/原因/期望)、
分类选中后显示该类的高质量示例。

**C. 反馈无法进入 Evaluation**(Metric D 全 none 但 B 高)→
模型问题:缺 expected_behavior 或引用。对策候选:采集时强化
refs/expected 字段引导,或承认该类反馈只进 backlog。

---

## 8. Decision Gate(pilot 后三选一)

- **Continue** → Phase 27.8 Feedback→Evaluation Dataset
  Pipeline(阈值达成本质要求 + 定性确认有意愿)
- **Iterate** → 调整 taxonomy / UI / guidance 后小样本重跑
  (改动限于治理层,runtime 边界不变)
- **Stop** → 反馈无法产生有效信号:保留决定+理由记录,
  v0.4 反馈环降级为"决定审计"能力(ADR-018 边界不变)

---

## 9. Explicit Non-Goals(重申)

本验证与后续分析**不做**:automatic learning、prompt update、
skill update、model training、反馈直接改任何运行时行为。
反馈只作为评估候选证据,经人工策展进入既有评估/工程流程。

---

## Verification

Code changed: NO · Runtime changed: NO · Backend changed: NO ·
Documentation only: YES
