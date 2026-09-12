# Client Profile

> 角色：客户信息唯一长期状态源
> 读取优先级：最高
> 供谁使用：当前 Client Intake Skill + 后续 Needs Analysis Skill

---

## Client Summary

| 项 | 值 |
|----|----|
| 客户编号 | CASE_008-Regression |
| Intake 状态 | 进行中 |
| 已完成轮次 | R3 |

---

## 1. Confirmed Facts

### 1.1 基本信息

| 字段 | 当前值 | Source Round | Source Text |
|------|--------|--------------|-------------|
| 年龄 | 35 | R1 | 我35岁 |
| 性别 | ❓ | | |
| 城市 | 北京 | R1 | 北京 |
| 职业 | ❓ | | |
| 婚姻状况 | ❓ | | |

### 1.2 家庭结构

| 字段 | 当前值 | Source Round | Source Text |
|------|--------|--------------|-------------|
| 配偶年龄 | ❓ | | |
| 配偶职业 / 状态 | ❓ | | |
| 子女人数 | ❓ | | |
| 子女信息 | ❓ | | |
| 父母赡养情况 | ❓ | | |

### 1.3 收入与支出

| 字段 | 当前值 | Source Round | Source Text |
|------|--------|--------------|-------------|
| 本人收入 | 80万 | R1 | 收入80万 |
| 配偶收入 | ❓ | | |
| 家庭年支出 | ❓ | | |
| 收入来源 | ❓ | | |

### 1.4 负债与保障

| 字段 | 当前值 | Source Round | Source Text |
|------|--------|--------------|-------------|
| 房贷余额 | ❓ | | |
| 房贷剩余年限 | ❓ | | |
| 其他负债 / 担保 | ❓ | | |
| 社保医保 | ❓ | | |
| 商保概况 | ❓ | | |
| 团险 / 福利 | ❓ | | |

### 1.5 健康与风险

| 字段 | 当前值 | Source Round | Source Text |
|------|--------|--------------|-------------|
| 客户本人健康 | ❓ | | |
| 配偶健康 | ❓ | | |
| 子女健康 | ❓ | | |
| 父母健康 | ❓ | | |
| 生活习惯 | ❓ | | |
| 核心风险关注点 | ❓ | | |

---

## 2. Inferred Notes

> 仅允许记录 `references/02-information-model.md` 白名单内的 inferred。

| 编号 | 推断内容 | Basis | 来源 Round |
|------|----------|-------|-----------|
| | | | |

---

## 3. Critical Missing Items

> 这里只保留仍会阻塞进入 Needs Analysis 的关键缺口。

| 优先级 | 项目 | 原因 |
|--------|------|------|
| P0 | 家庭责任结构（H4） | Hard Required 未满足 |
| P0 | 家庭年支出（H6） | Hard Required 未满足 |
| P0 | 职业（H3） | Hard Required 未满足 |

---

## 4. Completion Status

| 检查项 | 当前状态 | 说明 |
|--------|----------|------|
| H1 年龄 | 已满足 | 已收集 |
| H2 城市 | 已满足 | 已收集 |
| H3 职业 | 未满足 | 已收集 |
| H4 家庭责任 | 未满足 | 已收集 |
| H5 收入 | 已满足 | 已收集 |
| H6 支出 | 未满足 | 已收集 |
| 是否可进入 Needs Analysis | 否 | 仍有 3 项 Hard Required 未满足 |

---

## 5. Follow-up Items

> Intake 完成后仍待补的内容写这里。

- [空]

---

## 6. Handoff Notes

```
由 apply-execution.ps1 依据 evals/executions/CASE_008.json 渲染
```

---

## 7. Profile Change Notes

- Round 1：年龄、城市、本人收入
- Round 2：无
- Round 3：无

