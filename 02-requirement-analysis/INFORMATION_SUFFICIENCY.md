# Requirement Analysis Information Sufficiency

> 状态：Phase 2 Implemented
> 目标：判断当前输入是否足以支撑指定 `analysis_scope` 下的需求分析。

---

## 1. 设计原则

Information Sufficiency 不是检查“字段有没有填”。

它判断的是：

1. 当前分析范围是什么
2. 该范围依赖哪些信息
3. 当前已有信息是否足以支撑稳定结论
4. 缺失信息的影响有多大
5. 是否存在冲突信息

---

## 2. 三层信息分类

每个需求类型的信息依赖都分成三层：

1. `required_information`
   缺失后会显著影响当前需求分析可靠性
2. `recommended_information`
   不一定阻塞初步分析，但会显著影响精度和不确定性
3. `optional_information`
   用于增强分析细节，但不应机械阻塞

规则配置见：

- `02-requirement-analysis/config/information-sufficiency.rules.json`

---

## 3. 五类需求依赖图

### 3.1 Medical

核心依赖：

- required: 年龄、健康情况、社保医保、已有医疗保障、预算
- recommended: 就医偏好、家庭医疗需求
- optional: 城市

### 3.2 Critical Illness

核心依赖：

- required: 年龄、健康、收入、家庭责任、已有重疾保障
- recommended: 家庭财务情况、预算
- optional: 风险偏好

### 3.3 Accident

核心依赖：

- required: 年龄、职业、已有意外保障、家庭责任
- recommended: 收入、工作方式
- optional: 生活方式

### 3.4 Life

核心依赖：

- required: 收入、家庭责任、房贷、子女、配偶收入、已有寿险
- recommended: 父母赡养、资产、支出
- optional: 房贷剩余年限

### 3.5 Savings

核心依赖：

- required: 收入、支出、资产、负债、现金流、财务目标
- recommended: 流动性需求、时间目标、预算
- optional: 风险偏好

---

## 4. 评分规则

### 4.1 权重

- required 总权重：`0.70`
- recommended 总权重：`0.20`
- optional 总权重：`0.10`

每层内部平均分配权重。

### 4.2 不同值状态的覆盖贡献

- `KNOWN` = `1.0`
- `ESTIMATED` = `0.7`
- `ASSUMED` = `0.3`
- `UNKNOWN` / 缺失 / 冲突 = `0.0`

### 4.3 阈值

- `>= 0.85`
  可视为 `SUFFICIENT`，支持正式分析
- `0.60 - 0.84`
  视为 `PARTIAL`，允许初步分析，但必须明确不确定性
- `< 0.60`
  视为 `INSUFFICIENT`，必须补关键资料

若存在关键冲突信息，则优先进入 `CONFLICTING`，而不是只看分数。

---

## 5. 缺口分类

每个缺口输出以下字段：

- `field`
- `importance`
- `impact`
- `reason`
- `gap_type`

其中 `gap_type` 取值：

- `NOT_PROVIDED`
- `EXPLICIT_UNKNOWN`
- `CANNOT_INFER`
- `CONFLICTING_INFORMATION`

---

## 6. Overall Status 规则

### 6.1 Scope Result

每个 `requirement_type` 都有独立结果：

- `scope_score`
- `scope_status`
- `blocking_fields`
- `conflict_fields`

### 6.2 Overall Result

整体结果按以下优先级判断：

1. 任一 scope 存在关键冲突 -> `CONFLICTING_INFORMATION`
2. 任一 scope 为 `INSUFFICIENT` 或 overall score < `0.60` -> `NEED_MORE_INFORMATION`
3. 任一 scope 为 `PARTIAL` 或 overall score < `0.85` -> `PRELIMINARY`
4. 否则 -> `COMPLETE`

---

## 7. 测试覆盖

Phase 2 至少覆盖以下场景：

1. 信息完整
2. 缺少低影响信息
3. 缺少高影响信息
4. 多项信息缺失
5. 信息冲突

测试脚本：

- `scripts/test-requirement-analysis-sufficiency.ps1`
