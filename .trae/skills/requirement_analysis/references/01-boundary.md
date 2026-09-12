# 01 — 边界与定位（Boundary）

> 来源：原 CONTRACT.md §1、§10；原 SKILL.md「严格边界」节。
> 本文件定义 `requirement_analysis` 能做什么、绝对不能做什么。任何实现不得越过本边界。

---

## 1. 定位

`requirement_analysis` 是一个**需求分析 Skill**，职责不是收集原始客户事实，也不是推荐保险产品，而是：

1. 读取 `client_intake` 已沉淀的客户画像
2. 识别当前分析范围内的信息是否足够
3. 输出结构化需求分析结果
4. 显式标记：哪些结论有证据、哪些仍未知、哪些只是估计、哪些属于假设

## 2. 可以做

- 分析客户保障需求
- 标记信息缺口
- 输出需求优先级
- 输出证据链

## 3. 绝对不可以做

- 修改 `client_intake` 的任何文件、Prompt、Schema、测试或逻辑
- 输出具体保险产品
- 输出保险公司名称
- 输出销售话术
- 把未知信息当成事实

## 4. Requirement / Product 边界（硬边界）

`requirement_analysis` 输出的是：

- 客户要解决什么风险问题
- 风险优先级如何
- 哪些信息足够，哪些不足

`requirement_analysis` 绝对不能输出：

- 具体保险产品
- 保险公司
- 产品比较
- 销售话术
- 购买建议文案

Eval 中对应失败类型：`PRODUCT_RECOMMENDATION_LEAK`（见 `evals/eval-policy.md`）。

## 5. 与 Client Intake 的接口边界

- 上游来源（已随 client-intake 重构迁移）：
  1. `client-intake-data/clients/<客户目录>/CLIENT_PROFILE.md`
  2. `client-intake-data/clients/<客户目录>/PENDING.md`
  3. `client-intake-data/clients/<客户目录>/CONVERSATION_LOG.md`
  4. `client_intake` 的本轮 JSON 输出（仅补充，不作为长期真源）
- 若字段不完全匹配，必须使用 Adapter 做字段映射，**不得反向修改 `client_intake`**。
- 零修改原则：发现必须改 `client_intake` 才能跑通时，停下并报告，不要私自改。
