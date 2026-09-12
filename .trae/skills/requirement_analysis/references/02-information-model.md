# 02 — 信息模型（Information Model）

> 来源：原 CONTRACT.md §3（Input Contract）、§8（Evidence/Reasoning/Conclusion）、§9（KNOWN/UNKNOWN/ESTIMATED/ASSUMED）。
> 本文件定义输入对象结构与「事实 / 推理 / 假设 / 未知」四象限的严格分离。

---

## 1. Input 顶层结构

Input 不是直接复制 `CLIENT_PROFILE.md` 的 Markdown 文本，而是一个适配后的结构化输入对象，必须能表达：来源是谁、分析范围是什么、当前有哪些客户事实、哪些事实是确认的/推断的、哪些信息仍待补充、是否存在冲突。

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
  "analysis_scope": ["medical", "critical_illness"],
  "client_profile": {
    "facts": [],
    "inferred_notes": [],
    "follow_up_items": [],
    "handoff_notes": ""
  },
  "conflicts": [],
  "constraints": [],
  "metadata": { "client_id": "C009", "client_alias": "张先生三口之家" }
}
```

### 1.1 Fact

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

### 1.2 Conflict

```json
{
  "field": "annual_income",
  "values": ["去年收入80万", "去年实际60万"],
  "reason": "前后说法不一致",
  "resolution_status": "UNRESOLVED"
}
```

### 1.3 Constraint

```json
{
  "type": "customer_preference",
  "description": "客户更关注重疾/失能风险，不希望身故保障过高",
  "source": "CLIENT_PROFILE handoff / inferred"
}
```

## 2. KNOWN / UNKNOWN / ESTIMATED / ASSUMED

四种状态必须严格区分：

- `KNOWN`：客户明确说过，或可直接追溯到上游事实
- `UNKNOWN`：没有提供，且不能可靠推导
- `ESTIMATED`：只能给出区间或近似值，必须明确说明依据
- `ASSUMED`：为了继续分析暂时采用的假设，必须显式标出，后续可被推翻

规则：

1. `UNKNOWN` 不能伪装成 `KNOWN`
2. `ESTIMATED` 必须写依据
3. `ASSUMED` 必须写假设原因
4. Eval 必须能识别这四种状态混淆（见 `evals/eval-policy.md`）

禁止自动补全：未知就是未知，不做自动补全；冲突信息不合并为单一事实，必须显式进入冲突列表。

## 3. Evidence / Reasoning / Conclusion 契约

每个重要结论必须至少能追溯到一条证据链：

```json
{
  "evidence_id": "EV001",
  "fact_refs": ["annual_income", "mortgage_balance", "children_info"],
  "value_status": "KNOWN",
  "reasoning": "家庭主要收入来源承担房贷与子女抚养责任，收入中断将直接影响家庭现金流。",
  "conclusion": "life 需求优先级至少为 P1_HIGH"
}
```

硬约束：

1. 没有证据支持的结论，不得进入正式 `requirements`
2. 推理必须引用事实，不能只写抽象判断
3. `reasoning` 不能替代 `evidence`

## 4. 输入 Schema

结构化定义见 `schemas/input.schema.json`。生产调用前先跑 Schema Test 校验输入合法性。
