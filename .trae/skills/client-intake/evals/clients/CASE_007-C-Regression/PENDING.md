# Pending Items

> 角色：保存客户答应补充但尚未提供的资料
> 不存客户长期事实

---

## Pending Registry

| 编号 | Related QID | 项目 | 客户承诺原文 | 进入 Pending Round | 当前状态 | 已提醒次数 | 下次提醒 Round | 备注 |
|------|-------------|------|--------------|-------------------|----------|------------|----------------|------|
| P001 | Q001 | 现有保单资料 | 保单我晚点找一下发给你。 | R1 | expired | 3 |  | 第 3 次提醒无果 -> 自动 expired，停止提醒；related_qid Q001 同步 ignored |

---

## Reminder Notes

- 第 1 次提醒：进入 Pending 后第 2 个后续 Round
- 第 2 次提醒：进入 Pending 后第 4 个后续 Round
- 第 3 次提醒：进入 Pending 后第 6 个后续 Round

---

## History

- R1：P001 新增（现有保单资料），状态 pending
- R1：P001 新增（现有保单资料），状态 pending
- R1：P001 新增（现有保单资料），状态 pending
- R1：P001 新增（现有保单资料），状态 expired

