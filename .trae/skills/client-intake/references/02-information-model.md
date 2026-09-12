# 02 — 信息类型定义

## 3.1 Confirmed

客户明确说过，且能在客户原话里找到依据的事实。

每个 confirmed 叶子必须记录：

- `value`
- `source_round`
- `source_text`

## 3.2 Inferred

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

## 3.3 Missing

当前进入 Needs Analysis 所需、但尚未获得的信息。

Missing 不等于所有未提信息，而是**当前阶段仍然关键的缺口**。

## 3.4 Pending

客户已经明确答应后补，但本轮没给的资料。

Pending 永远写进 `PENDING.md`，不要写进 `CLIENT_PROFILE.md`。
