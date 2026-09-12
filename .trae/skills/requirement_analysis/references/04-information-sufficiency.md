# 04 — 信息充分性引擎（Information Sufficiency）

> 来源：原 INFORMATION_SUFFICIENCY.md + 原 CONTRACT.md §12。
> 本文件定义「当前信息是否足以支撑分析结论」的判断逻辑。规则数据见 `resources/config/information-sufficiency.rules.json`。

---

## 1. 设计原则

Information Sufficiency 不是字段存在性检查，而是：

1. 基于 `analysis_scope`
2. 基于 requirement dependency map
3. 基于现有信息状态
4. 判断是否足以支撑当前阶段的分析结论

## 2. 三层信息分类

每个需求类型的信息依赖都分成三层：

- `required_information`：缺失后会显著影响当前需求分析可靠性
- `recommended_information`：不一定阻塞初步分析，但会显著影响精度和不确定性
- `optional_information`：用于增强分析细节，但不应机械阻塞

规则配置见 `resources/config/information-sufficiency.rules.json`。

## 3. 五类需求依赖图

- **Medical**：required 年龄/健康情况/社保医保/已有医疗保障/预算；recommended 就医偏好/家庭医疗需求；optional 城市
- **Critical Illness**：required 年龄/健康/收入/家庭责任/已有重疾保障；recommended 家庭财务情况/预算；optional 风险偏好
- **Accident**：required 年龄/职业/已有意外保障/家庭责任；recommended 收入/工作方式；optional 生活方式
- **Life**：required 收入/家庭责任/房贷/子女/配偶收入/已有寿险；recommended 父母赡养/资产/支出；optional 房贷剩余年限
- **Savings**：required 收入/支出/资产/负债/现金流/财务目标；recommended 流动性需求/时间目标/预算；optional 风险偏好

## 4. 评分规则

### 4.1 权重

- required 总权重 `0.70`；recommended 总权重 `0.20`；optional 总权重 `0.10`。每层内部平均分配权重。

### 4.2 不同值状态的覆盖贡献

- `KNOWN = 1.0`
- `ESTIMATED = 0.7`
- `ASSUMED = 0.3`
- `UNKNOWN / 缺失 / 冲突 = 0`

### 4.3 阈值

- `>= 0.85` → `SUFFICIENT`，支持正式分析
- `0.60 - 0.84` → `PARTIAL`，允许初步分析，但必须明确不确定性
- `< 0.60` → `INSUFFICIENT`，必须补关键资料
- 若关键冲突存在 → 优先 `CONFLICTING`，而不是只看分数

## 5. 缺口分类

每个 gap 输出：`field` / `importance` / `impact` / `reason` / `gap_type`。

`gap_type` 取值：`NOT_PROVIDED` / `EXPLICIT_UNKNOWN` / `CANNOT_INFER` / `CONFLICTING_INFORMATION`。

## 6. Overall Status 规则

### 6.1 Scope Result

每个 `requirement_type` 都有独立结果：`scope_score` / `scope_status` / `blocking_fields` / `conflict_fields`。

### 6.2 Overall Result（按优先级判断）

1. 任一 scope 存在关键冲突 → `CONFLICTING_INFORMATION`
2. 任一 scope 为 `INSUFFICIENT` 或 overall score < `0.60` → `NEED_MORE_INFORMATION`
3. 任一 scope 为 `PARTIAL` 或 overall score < `0.85` → `PRELIMINARY`
4. 否则 → `COMPLETE`

## 7. 未知检测

必须区分：`NOT_PROVIDED` / `EXPLICIT_UNKNOWN` / `CANNOT_INFER` / `CONFLICTING_INFORMATION`。禁止自动补全。

## 8. Phase 2 输出要求

`information_sufficiency` 至少支持：overall sufficiency status / overall score / per-scope result / blocking fields / conflict fields。
