# Reviewer Guide — Human Reviewer Validation v2 (风险驱动的系统审核)

适用对象:Human Reviewer(人工审核者)。本指南定义你**要看什么、
回答什么、花多久**,以及什么时候必须深挖。它不要求你阅读全量产物
——那是自动化验证(automatic_validation)的工作。

---

## 1. 你的角色

你是 **Risk-based System Validator(风险驱动的系统可靠性验证者)**,
不是 Full Artifact Validator。

你回答的是**系统可靠性问题**,不是保险专业问题:

| ❌ 不要回答 | ✅ 要回答 |
|---|---|
| 这个保险方案是不是最好的? | 是否存在明显事实错误? |
| 这款产品适不适合客户? | 是否存在合规风险(绝对化用语/目录外产品/无据承诺)? |
| 换成我会推荐什么? | 推荐是否有客户依据(需求→风险→证据可追溯)? |
| | 是否存在无法追溯的信息(引用悬空/证据缺失)? |

## 2. 入口与层级

每个完成的 Run 会生成一张 **Review Card**
(`human_review_card.json`,schema 见 `review-card.schema.json`)。
卡片顶部的 `review_action` 决定你要做什么:

### Level 0 — AUTO_PASS(无需人工)
触发条件:四项自动检查全 PASS + 无 HIGH/MEDIUM 风险 + 未命中抽审。
**你不需要查看。**(抽审命中时会显示在 `reasons` 中并升级为 Level 1。)

### Level 1 — SUMMARY_REVIEW(卡片审核,目标 < 3 分钟)
触发:存在 MEDIUM 风险,或命中随机抽审。
只读 Review Card,核对四件事:

1. `customer_summary` 与 `agent_summary.objective` 是否自洽
   (推荐的需求方向与客户画像匹配);
2. `risk_flags` 中每条 MEDIUM 是否成立(如"无主推荐"是否确实是
   证据不足/无合格产品,而非系统漏推);
3. `automatic_validation` 四项是否全 PASS(有 FAIL 就不是 Level 1);
4. `unresolved` 客户未知字段是否都已被 `waiting_for_user.next_questions`
   覆盖(该问的都问了吗)。

**结论动作**:通过 → 在审批界面 APPROVE;存疑 → 升级为 Level 2。

### Level 2 — DEEP_REVIEW(深挖,全证据链)
触发:任一自动检查 FAIL(含 missing_evidence / false_product_information)
或任一 HIGH 风险。
在卡片之外,打开 Review Workspace(Web UI),用 `run_id` 定位该 Run,
逐项检查:

1. Section C 时间线:执行顺序是否合理,失败/重试后结论是否仍成立;
2. Section D 产物:`failed_checks` 里列出的每个检查,到对应 artifact
   里亲眼看那处数据;
3. Section E 证据链:每条 knowledge 引用是否能在知识证据中解析,
   `No evidence linked` 的项是否属于"系统正确拒绝编造"还是"漏取证";
4. `validation_status=FAIL` 的卡:默认动作是 REJECT 或退回修复,
   除非你能确认 FAIL 原因不影响交付质量(需写明理由)。

## 3. 判读速查

| 字段 | 值 | 含义 / 动作 |
|---|---|---|
| `validation_status` | PASS / FAIL | 四项自动检查的总结;FAIL 必然是 Level 2 |
| `review_action.reasons` | 列表 | 每一条都是升级到当前层级的具体触发者 |
| `risk_flags[].severity` | HIGH / MEDIUM / LOW | HIGH→Level 2;MEDIUM→Level 1;LOW 仅人工可标 |
| `automatic_validation.eval_summary` | 计数 | 评估记录总数与失败数,失败 id 列表 |
| `customer_summary.unresolved` | 列表 | UNKNOWN/冲突的客户字段——核对是否已追问 |
| `sampling.triggered` | bool | 随机抽审命中(确定性哈希,可复现) |

## 4. 边界与纪律

- **卡片即证据边界**:卡片不显示的内容,通过 `run_id` 深挖获取;
  不要凭记忆或想象补全卡片未给出的信息。
- **不做编造**:卡片里没有的字段就是系统没有的(NULL / unresolved),
  不代表"应该有"。
- **反馈闭环**:发现问题用 G 节 Feedback Panel 记录
  (6 个封闭分类);LOW 级(style/formatting)只有人工可以标注,
  生成器永不自动产生。
- **时间预算**:Level 1 目标 < 3 分钟/案例;超过说明该案例应按
  Level 2 处理,不要在 Level 1 硬猜。

## 5. 验收指标(Phase 27.7.6 v2)

| 指标 | 目标 |
|---|---|
| Average Human Review Time(SUMMARY 层) | < 3 min / case |
| High-risk case coverage(HIGH 触发的案例被人工复核) | > 95% |
| Human agreement rate(人工结论与自动结论一致率) | > 90% |
| Random audit pass rate(AUTO_PASS 抽审翻车率 < 5%) | > 95% |
