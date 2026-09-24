# Human Feedback Loop Architecture v0.1

Status: DESIGN (Phase 27.6, 2026-09-24 — architecture only, no
implementation) · Companion ADR: ADR-018 (separation decision
only; the entity model below is a RECOMMENDATION, not frozen) ·
Upstream: governance-layer-v0.1.md / ADR-017 · Baseline: a57e006

---

## 1. What is Feedback?

现有系统已经有 Decision(决定):

```
Decision = What happened
(APPROVE / REJECT + reason — 已在后端持久化,不可编辑)
```

本设计引入的 Feedback(反馈)是另一个实体:

```
Feedback = Why it happened, and how the Agent should improve
```

区分(为什么 Decision 不够):

| | Decision | Feedback |
|---|---|---|
| 回答 | 放行还是拒绝? | 为什么错/对?Agent 哪里该改? |
| 生命周期 | 终态、不可编辑 | 可被归一化、归类、转为评估用例 |
| 消费者 | 审批工作流(运行时) | 评估/工程(离线) |
| 数量 | 每审批 ≤1 条 | 每决定可 0..n 条,可跨对象 |

反例(不是 Feedback):审批状态、workflow 状态、孤立的用户
评论(没有结构与指向的 comment 只是原始材料)。

---

## 2. Feedback Entity Design — 三种归属模型

### Option A — Feedback belongs to Decision(审批为锚)

```
Approval → Decision → Feedback
```
例:"REJECT:覆盖推荐忽视了收入替代需求(REQ-LIFE 未被满足)。"

- ✅ 优点:采集点唯一(决定时刻、审阅者注意力最高);天然
  关联 run/case/artifact 的上下文链(经 approval context 与
  workspace 拼装);与现有 pilot 审查表单(pilot-review-
  template 的 8 节判定)直接对齐;实现增量最小。
- ❌ 缺点:非决定场景的反馈(浏览 dashboard 时发现的 knowledge
  过时)没有锚点;反馈粒度绑定审批生命周期。

### Option B — Feedback belongs to Skill

```
Skill → Feedback
```
例:"risk-analysis 漏掉了家庭依赖分析。"

- ✅ 优点:直接指向改进目标(工程消费方便)。
- ❌ 缺点:**由人判断"该改哪个 skill"是越权归因** —— 审阅者
  看到的是业务现象,不是代码结构;归因应由评估/工程完成;
  且 Phase 27 试点证明表象常在别的层(F27-02 是目录内容而非
  runtime)。

### Option C — Feedback belongs to Evidence

```
Evidence → Feedback
```
例:"知识来源过时(01_medical_insurance 条款已更新)。"

- ✅ 优点:证据治理是本项目强项(provenance/registry),证据
  级反馈可直达知识治理流程。
- ❌ 缺点:只覆盖证据类问题(试点 taxonomy 18 类中仅 F07/F08)。

### 推荐:Anchor on Decision, reference everything(A 为主,
B/C 降级为引用)

Feedback **锚定在 Decision**(采集唯一入口),但通过结构化
引用指向任意对象:

```
Feedback {
  anchor:  decision(approval_id, decision)
  refs:    [requirement_id | risk_id | artifact_id |
            evidence_id | skill_name | knowledge_source | stage]
}
```

理由:采集成本最低、上下文最全;归因(skill vs knowledge vs
catalog vs prompt)交给评估阶段,避免人被迫做工程归因;证据/
技能视图(B/C 的价值)成为 Feedback Dataset 上的**投影**而非
独立实体。Option B/C 保留为查询视图。

---

## 3. Feedback Taxonomy

沿用并收编 Phase 27 已实测的分类体系(pilot-failure-taxonomy
F01–F18 在 12 个真实 case 上验证过其可用性),归并为六个
一级类:

| Type | 含义 | 来源映射 | 为什么存在 |
|---|---|---|---|
| A. Agent Reasoning Issue | 推理/分析结论错误 | F01,F03–F06,F10 | 最直接的 Agent 改进信号;须挂 artifact/chain 引用 |
| B. Missing Information | 信息不全被不当处理 | F02 | 区分"该问没问"(agent 错)与"客户不给"(数据问题) |
| C. Wrong Recommendation | 推荐/产品层面错误 | F09,F10 | 高风险输出层,单独统计 |
| D. Evidence Problem | 证据不足/引用错误/链断 | F08 | Evidence-before-decision 的质量回路 |
| E. Knowledge Gap | 知识源缺失/过时 | F07,F27-02 实证 | 直达知识治理(registry/WeKnora),不是 prompt 问题 |
| F. UX / Report Issue | 报告可读性/呈现 | F11,F12 | 不进评估集,进产品 backlog |

原则:一级类**稳定封闭**(评估管道依赖),细节用自由文本 +
现有 F/OF 编号;新增一级类需要架构评审。

---

## 4. Feedback Lifecycle

```
Human Review
    → Decision(运行时,已有,后端权威)
    → Feedback Capture(治理层 UI,决定后的结构化表单)
    → Normalization(离线:分类校验、引用解析、去重)
    → Feedback Dataset(评估域的持久数据集)
    → Evaluation Harness(现有 eval 体系)
    → Agent Improvement(工程变更,经人审)
```

各步归属:

| 步骤 | 归属 | 说明 |
|---|---|---|
| Decision | Runtime(已有)| 后端审批端点,不动 |
| Capture | Governance UI(未来 27.7)| 只新增采集表单;可复用 pilot 表单字段 |
| Normalization | 离线工具/脚本 | 引用解析(refs→真实对象)、分类校验、去重;**非实时、非运行时** |
| Dataset | 评估域(evals/)| 与 golden cases 同级的数据资产,版本化 |
| Harness→Improvement | 评估+工程(已有模式)| 见 §5 |

关键边界:Capture 之后的一切都不在请求路径上 —— 反馈是异步
沉淀,不阻塞审核,不影响运行时。

---

## 5. Relationship With Existing Evaluation System

现有评估资产(全部保留,反馈是**增量输入**,不替换):

- Golden cases(42/42 benchmark)+ domain evals + mutation
  testing + repair 规则。

集成设计:

```
Human Feedback
    → (候选)New Evaluation Case
        · REJECT + Type A/C + 可复现输入 ⇒ 生成回归用例
          (合成化:脱敏 + 最小化复现,复用 pilot mutation 机制)
        · Type E(Knowledge Gap)⇒ 知识 registry 的缺口工单,
          不生成 eval case
        · Type F(UX)⇒ 产品 backlog,不进 eval
    → Regression Test(进入 benchmark/golden 集,门槛与现有
      用例相同:可复现、有预期输出)
    → Skill Improvement(经工程评审的代码/规则/目录变更)
```

判定规则(哪些反馈升级为评估用例)是评估域的策略,首版用
人工策展(curation),规模后再自动化 —— 避免噪声反馈直接
污染回归基线。

---

## 6. Relationship With Runtime(硬边界)

Feedback **绝不**:

- 直接修改 prompts / skills / workflow / 目录 / 知识库
- 触发 Agent 重跑或自动"修复"
- 在运行时路径上被同步消费

唯一通路:

```
Feedback → Evaluation → Human Review(工程评审)
        → Engineering Change(正常开发流程 + 全量回归)
```

这与 ADR-017 的治理分离原则同构:反馈是**证据**,不是**控制
信号**。任何"反馈自动改 prompt"的提案都违反本边界,需要新
ADR 推翻。

---

## 7. Data Model(概念,不建 schema 文件)

```
Feedback {
  id:                 feedback_id
  anchor: {
    approval_id, decision, decided_by, decided_at
  }
  category:           A|B|C|D|E|F (+ legacy F/OF code 可选)
  description:        自由文本(人写的"why")
  refs: [             // 结构化指向,Normalization 解析校验
    {type: requirement|risk|artifact|evidence|
          skill|knowledge_source|stage|run|case,
     ref: <id>}
  ]
  expected:           期望行为(可选,"Agent 本应…")
  created_by / created_at
  status: captured|normalized|converted(backlog|eval_case|
           knowledge_ticket)|discarded
  provenance:         采集来源(ui|pilot_form|owner_review)
}
```

存储位置候选(实现阶段决策):评估域文件化(JSONL,与 golden
cases 同库同版本化)优先于新建 PG 表 —— 首版量级(试点期
几十条)不需要数据库;升级路径明确。

---

## 8. Architecture Diagram

```
                 Human Reviewer
                       |
                       v
                Decision Record          (Runtime, 已有)
                       |
                       v
              Feedback Collection        (Governance UI, 27.7)
                       |
                       v
              Feedback Dataset          (评估域, 版本化)
                       |
        +--------------+---------------+
        |              |               |
        v              v               v
  Eval Case(回归)  Knowledge 工单   Product Backlog
        |              |
        v              v
   Evaluation Harness  知识治理
        |
        v
   Agent Improvement(工程变更 + 全量回归 + 人审)
```

---

## 9. Open Questions(未决,留给实现阶段)

1. Feedback 是否要求 REVIEWER 角色?(倾向:是 —— 与决定权限
   一致;观察者反馈走 owner-review 通道)
2. REJECT 时反馈是否必填?(倾向:REJECT 必填 category,自由
   文本可选 —— 已有 pilot 表单实践可参考)
3. 反馈是否自动成为训练/评估数据?(否 —— 人工策展门槛,§5)
4. 谁批准 skill 变更?(现有工程流程;反馈只是输入)
5. 反馈是否可编辑/撤回?(倾向:captured 前可改,normalized
   后 append-only —— 与审计一致)
6. 非 REJECT(APPROVE-with-comments)是否允许反馈?(倾向:
   允许 —— 正向样本同样有价值,Type 可标注"good practice")
7. Dataset 存储文件 vs PG?(首版文件化,§7)
8. 与 Phase 27 owner-review 工作台(OF-xx)的合并策略?

---

## ADR 状态

- **ADR-018 Human Feedback Loop Separation:已创建** —— 冻结
  的只有"分离"决策(§6 硬边界:反馈经评估与工程变更起作用,
  绝不直接改运行时);该决策稳定且经 Option A/B/C 评估支撑。
- 实体模型(§2 推荐 A)与 taxonomy(§3)**未冻结** —— 留在
  本设计文档,实现阶段(27.7)验证后可升 ADR。
