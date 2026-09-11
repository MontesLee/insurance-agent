# Requirement Analysis Skill Contract

> 状态：Phase 1 Contract Locked
> 目标：只定义 Input / Output / State / Schema / Adapter，不实现完整业务分析流程。

---

## 1. 定位与边界

`requirement_analysis` 是一个**需求分析 Skill**。

它的职责不是收集原始客户事实，也不是推荐保险产品，而是：

1. 读取 `client_intake` 已沉淀的客户画像
2. 识别当前分析范围内的信息是否足够
3. 输出结构化需求分析结果
4. 显式标记：
   - 哪些结论有证据
   - 哪些仍未知
   - 哪些只是估计
   - 哪些属于假设

严格禁止：

- 修改 `client_intake`
- 越界进入产品推荐
- 把 `UNKNOWN / ESTIMATED / ASSUMED` 当成 `KNOWN`

---

## 2. 与 Client Intake 的接口关系

### 2.1 上游来源

`requirement_analysis` 的主要输入来自 `client_intake`，优先级如下：

1. `01-client-intake/clients/<客户目录>/CLIENT_PROFILE.md`
2. `01-client-intake/clients/<客户目录>/PENDING.md`
3. `01-client-intake/clients/<客户目录>/CONVERSATION_LOG.md`
4. `client_intake` 的本轮 JSON 输出（仅补充，不作为长期真源）

### 2.2 为什么需要 Adapter

原因不是 `client_intake` 错了，而是两个 Skill 的职责不同：

- `client_intake` 输出的是**客户事实视图**
- `requirement_analysis` 需要的是**分析消费视图**

因此本 Skill 增加 Adapter 层，把 `client_intake` 的事实结构映射为分析输入，而不是修改 `client_intake` 的输出格式。

### 2.3 Adapter 原则

1. 只做字段映射，不篡改原事实
2. 保留来源追溯信息
3. 未知就是未知，不做自动补全
4. 冲突信息不合并为单一事实，必须显式进入冲突列表

---

## 3. Input Contract

### 3.1 设计原则

Input 不是直接复制 `CLIENT_PROFILE.md` 的 Markdown 文本，而是一个**适配后的结构化输入对象**。

这个输入对象必须能表达：

1. 来源是谁
2. 分析范围是什么
3. 当前有哪些客户事实
4. 哪些事实是确认的，哪些是推断的
5. 哪些信息仍待补充
6. 是否存在冲突

### 3.2 Input 顶层结构

```json
{
  "source": {
    "skill": "client_intake",
    "adapter_version": "v1",
    "profile_path": "...",
    "pending_path": "...",
    "conversation_log_path": "...",
    "intake_complete": true
  },
  "analysis_scope": [
    "medical",
    "critical_illness"
  ],
  "client_profile": {
    "facts": [],
    "inferred_notes": [],
    "follow_up_items": [],
    "handoff_notes": ""
  },
  "conflicts": [],
  "constraints": [],
  "metadata": {
    "client_id": "C009",
    "client_alias": "张先生三口之家"
  }
}
```

### 3.3 Input 核心对象

#### Fact

```json
{
  "field": "annual_income",
  "value": "约 60 万 / 年",
  "value_status": "KNOWN",
  "source_round": "R2",
  "source_text": "年收入大概60万",
  "source_section": "Confirmed Facts"
}
```

#### Conflict

```json
{
  "field": "annual_income",
  "values": [
    "去年收入80万",
    "去年实际60万"
  ],
  "reason": "前后说法不一致",
  "resolution_status": "UNRESOLVED"
}
```

#### Constraint

```json
{
  "type": "customer_preference",
  "description": "客户更关注重疾/失能风险，不希望身故保障过高",
  "source": "CLIENT_PROFILE handoff / inferred"
}
```

---

## 4. Output Contract

### 4.1 设计目标

Output 必须服务于后续分析、Eval 和 Repair，因此必须：

1. 结构化
2. 可追溯
3. 可区分确定性和不确定性
4. 严格停留在 Requirement 层，不进入 Product 层

### 4.2 Output 顶层字段

```json
{
  "analysis_status": "PRELIMINARY",
  "analysis_scope": [
    "medical",
    "critical_illness",
    "life"
  ],
  "information_sufficiency": {},
  "information_gaps": [],
  "risk_map": [],
  "coverage_gaps": [],
  "requirements": [],
  "priorities": [],
  "evidence": [],
  "assumptions": [],
  "unknowns": [],
  "next_actions": [],
  "adapter_trace": {},
  "guardrails": {
    "product_recommendation_included": false
  }
}
```

### 4.3 Output 字段定义

- `analysis_status`
  当前分析状态，见 §5
- `analysis_scope`
  当前分析覆盖的需求类型
- `information_sufficiency`
  当前信息是否足以支持结论
- `information_gaps`
  当前还缺哪些高影响信息
- `risk_map`
  每类需求对应的风险暴露、财务影响、已有保障、保障缺口
- `coverage_gaps`
  风险与现有保障之间的缺口结论
- `requirements`
  客户需要优先解决的需求，不包含产品名
- `priorities`
  需求优先级结果
- `evidence`
  证据链对象，支持 `Evidence -> Reasoning -> Conclusion`
- `assumptions`
  明确列出假设，不得混入事实
- `unknowns`
  明确列出未知，不得伪装成已知
- `next_actions`
  下一步动作，可用于补信息或继续分析
- `adapter_trace`
  记录本轮分析消费了哪些上游字段
- `guardrails`
  安全边界检查结果

---

## 5. Analysis Status

必须支持以下状态：

- `COMPLETE`
  信息足够，分析可作为正式需求结论输出
- `PRELIMINARY`
  可以给出初步分析，但存在明确不确定性
- `NEED_MORE_INFORMATION`
  信息不足，必须先补关键资料
- `CONFLICTING_INFORMATION`
  存在关键冲突信息，不能直接给出稳定结论
- `FAILED`
  分析失败，通常用于结构错误、运行错误或 Eval 拒收

---

## 6. Requirement Types

必须支持以下需求类型：

- `medical`
- `critical_illness`
- `accident`
- `life`
- `savings`

说明：

1. 当前先锁定这 5 类
2. 后续允许扩展
3. 输入和输出都必须使用统一 enum

---

## 7. Priority Definition

### 7.1 枚举

- `P0_CRITICAL`
- `P1_HIGH`
- `P2_MEDIUM`
- `P3_LOW`

### 7.2 含义

- `P0_CRITICAL`
  若不先处理，该需求会显著影响家庭核心风险承受能力或后续分析可靠性
- `P1_HIGH`
  风险明显，应优先纳入近期保障规划
- `P2_MEDIUM`
  有必要处理，但优先级低于当前核心缺口
- `P3_LOW`
  可后置观察或在后续补充信息后再判断

---

## 8. Evidence / Reasoning / Conclusion Contract

### 8.1 结构要求

每个重要结论必须至少能追溯到一条证据链：

```json
{
  "evidence_id": "EV001",
  "fact_refs": [
    "annual_income",
    "mortgage_balance",
    "children_info"
  ],
  "value_status": "KNOWN",
  "reasoning": "家庭主要收入来源承担房贷与子女抚养责任，收入中断将直接影响家庭现金流。",
  "conclusion": "life 需求优先级至少为 P1_HIGH"
}
```

### 8.2 硬约束

1. 没有证据支持的结论，不得进入正式 `requirements`
2. 推理必须引用事实，不能只写抽象判断
3. `reasoning` 不能替代 `evidence`

---

## 9. KNOWN / UNKNOWN / ESTIMATED / ASSUMED

### 9.1 四种状态必须严格区分

- `KNOWN`
  客户明确说过，或可直接追溯到上游事实
- `UNKNOWN`
  没有提供，且不能可靠推导
- `ESTIMATED`
  只能给出区间或近似值，必须明确说明依据
- `ASSUMED`
  为了继续分析暂时采用的假设，必须显式标出，后续可被推翻

### 9.2 规则

1. `UNKNOWN` 不能伪装成 `KNOWN`
2. `ESTIMATED` 必须写依据
3. `ASSUMED` 必须写假设原因
4. Eval 必须能识别这四种状态混淆

---

## 10. Requirement / Product Boundary

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

---

## 11. Schema Files

本 Contract 对应以下结构化 Schema：

- `02-requirement-analysis/schemas/input.schema.json`
- `02-requirement-analysis/schemas/output.schema.json`
- `02-requirement-analysis/config/information-sufficiency.rules.json`

Schema Test 使用：

- `scripts/test-requirement-analysis-schema.ps1`

---

## 12. Information Sufficiency Contract

### 12.1 核心原则

Information Sufficiency 不是字段存在性检查，而是：

1. 基于 `analysis_scope`
2. 基于 requirement dependency map
3. 基于现有信息状态
4. 判断是否足以支撑当前阶段的分析结论

### 12.2 Dependency Map

依赖图定义文件：

- `02-requirement-analysis/config/information-sufficiency.rules.json`

每个需求类型都必须定义：

1. `required_information`
2. `recommended_information`
3. `optional_information`
4. `information_impact`

### 12.3 Sufficiency Score

当前采用分层加权方案：

1. `required` 总权重 `0.70`
2. `recommended` 总权重 `0.20`
3. `optional` 总权重 `0.10`

值状态贡献系数：

1. `KNOWN = 1.0`
2. `ESTIMATED = 0.7`
3. `ASSUMED = 0.3`
4. `UNKNOWN / 缺失 / 冲突 = 0`

阈值：

1. `>= 0.85` -> `SUFFICIENT`
2. `0.60 - 0.84` -> `PARTIAL`
3. `< 0.60` -> `INSUFFICIENT`
4. 若关键冲突存在 -> `CONFLICTING`

### 12.4 Unknown Detection

必须区分以下情况：

- `NOT_PROVIDED`
- `EXPLICIT_UNKNOWN`
- `CANNOT_INFER`
- `CONFLICTING_INFORMATION`

禁止自动补全。

### 12.5 Information Gap Output

每个 gap 必须输出：

- `field`
- `importance`
- `impact`
- `reason`
- `gap_type`

### 12.6 Phase 2 输出要求

`information_sufficiency` 必须至少支持：

1. overall sufficiency status
2. overall score
3. per-scope result
4. blocking fields
5. conflict fields

---

## 13. Phase 1 完成标准

Phase 1 只要求：

1. Input Schema 锁定
2. Output Schema 锁定
3. Status / Requirement Type / Priority 锁定
4. Client Intake Adapter 边界锁定
5. Schema Test 可运行

不包括：

1. 信息充分性算法
2. 主动追问算法
3. 风险分析算法
4. Eval 逻辑
5. Repair Loop

---

## 14. Phase 2 完成标准

Phase 2 只要求：

1. Requirement Dependency Map 已建立
2. Information Sufficiency 规则已结构化
3. Sufficiency Score 已实现
4. Information Gap 输出已实现
5. Unknown / Conflict 分类已实现
6. Phase 2 测试已运行

不包括：

1. 主动追问
2. 风险分析
3. Eval
4. Repair Loop
