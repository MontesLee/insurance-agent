# Pending Items

> 角色：保存客户答应补充但尚未提供的资料
> 不存客户长期事实

---

## 使用规则

1. 只有客户明确说"晚点给你 / 我找一下 / 回头发你"才进入这里
2. 每条 Pending 单独维护提醒节奏
3. Pending 最多提醒 3 次
4. 已完成、已拒绝、已失效都需要更新状态
5. `下次提醒 Round` 必须按"进入 Pending 后的 +2 / +4 / +6 轮"计算

---

## Pending Registry

| 编号 | Related QID | 项目 | 客户承诺原文 | 进入 Pending Round | 当前状态 | 已提醒次数 | 下次提醒 Round | 备注 |
|------|-------------|------|--------------|-------------------|----------|------------|----------------|------|
| | | | | | | | | |

---

## 状态说明

- `pending`：客户答应给，但还没给
- `received`：客户已经提供
- `declined`：客户明确不提供
- `expired`：提醒多次仍未提供，默认转失效

### 与 QID 的同步规则

- 创建 Pending 时，必须绑定一个 `Related QID`
- 提醒时，不得创建新的 QID
- `received` -> 对应 QID 同步为 `answered`
- `declined` -> 对应 QID 同步为 `declined`
- `expired` -> 对应 QID 同步为 `ignored`

---

## Reminder Notes

- 第 1 次提醒：进入 Pending 后第 2 个后续 Round
- 第 2 次提醒：进入 Pending 后第 4 个后续 Round
- 第 3 次提醒：进入 Pending 后第 6 个后续 Round
- 提醒话术尽量温和，不每轮追问