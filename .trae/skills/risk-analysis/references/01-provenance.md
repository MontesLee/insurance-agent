# 01 · Provenance（证据溯源与 status 语义）

> 本文件描述**已实现**的溯源规则。真源：`schemas/*.schema.json` + `scripts/invoke-*.ps1`。
> 上层约定（五态、上游不可变、INFERRED 仅消费方自推）见仓库根 `AGENTS.md` §3。

---

## 1. 为什么要有溯源层

风险分析的每一句结论都必须能被**追回到一个事实**。追不回去的结论不得写进 `conclusion`——
宁可留在 `unknowns` + `next_information_needed`。

`UNKNOWN > fabricated certainty` 是本 Skill 的最高优先级，溯源层是它在工程上的落地方式。

---

## 2. FactValue 四元组

ClientState 每个字段都是 FactValue：

```jsonc
{
  "value": 1500000,          // UNKNOWN 时为 null
  "status": "KNOWN",         // KNOWN|UNKNOWN|ESTIMATED|ASSUMED|INFERRED
  "source": { "layer": "client_state",
              "origin": { "skill": "client-intake", "field": "mortgage_balance" } },
  "confidence": 0.9,
  "note": "ESTIMATED / ASSUMED / INFERRED 必填"
}
```

| 状态 | 含义 | 谁可以置位 |
|---|---|---|
| `KNOWN` | 上游明确给出 | 上游透传 |
| `UNKNOWN` | 上游没有 / 明确未知 | 上游透传，或本 Skill 在字段缺失时补槽位 |
| `ESTIMATED` | 有量级但不确定（"约 25 万"） | 上游透传，或数值解析命中模糊词 |
| `ASSUMED` | 无事实支撑的假设 | 上游透传 |
| `INFERRED` | **仅**由本 Skill 自己推导 | 本 Skill（必须带 `note` 写推导依据） |

**`note` 必填规则**：`ESTIMATED` / `ASSUMED` / `INFERRED` 缺 `note` → Eval 5 `unknown_integrity` 判 `UNKNOWN_AS_KNOWN`（BLOCKING）。

---

## 3. EvidenceEntry（风险级证据）

```jsonc
{
  "evidence_id": "E001",
  "fact": "家庭年收入约 120 万",
  "source": {
    "layer": "client_state",        // client_state | requirement_analysis | unknown
    "field": "financial_profile.household_income",
    "origin": { "skill": "client-intake", "field": "household_income" },
    "status": "ESTIMATED"
  }
}
```

不可溯源时必须写成完整四件套，**禁止**把 unknown 伪装成 KNOWN：

```jsonc
{ "layer": "unknown", "field": "unknown",
  "origin": { "skill": "unknown", "field": "unknown" }, "status": "UNVERIFIED" }
```

---

## 4. provenance_index

`RiskAnalysisInput.provenance_index` 是 ClientState `source` 的**扁平索引**：

```jsonc
{ "client_state_field": "financial_profile.annual_income",
  "origin_skill": "client-intake", "origin_field": "annual_income", "status": "KNOWN" }
```

用途：Eval 2 `evidence_grounding` 做 O(1) 校验——每条 evidence 的 `source.field` 必须能在索引里找到且 `status` 一致。
索引与实际 `source` 不一致，等于给了 Eval 一张假地图。

---

## 5. 字段定位（profile 顺序）

引擎按 `risk-sufficiency.rules.json#profile_names` 的顺序把 ClientState 展平成 `field -> {field, profile, value, status, ...}`：

```
family_profile → financial_profile → responsibility_profile
→ existing_protection → health_profile → employment_profile
```

- **同名字段取先出现的 profile**（`if ($fieldMap.ContainsKey($fname)) { continue }`）
- **单一真源**：三个引擎（sufficiency / discovery / analysis）都从同一份 `profile_names` 读取；
  引擎内不得再自带一份列表（Phase 9 修复：此前三份硬编码 + 一份未消费的 `field_profile_index`）
- 不在词表里的上游字段：保留到最接近的 profile，`note` 标 `unmapped_original_field=<原名>`

---

## 6. 数值解析与否定识别

规则外置：`risk-discovery.rules.json` / `risk-scoring.rules.json`。

| 能力 | 配置项 | 说明 |
|---|---|---|
| 中文单位 | `number_units` | 万 / 亿 / 千 / w / k |
| 模糊词 | ——（引擎识别"约 / 大概 / 左右 / 估计"） | 命中即 `status=ESTIMATED` 且下调 confidence |
| 整值否定 | `negative_tokens` | "无"、"没有"、"none"、0 |
| 前缀否定 | `negative_prefixes` | "无房贷"、"没买" |
| **整句否定** | `negative_substrings` | "父母有退休金，无需固定赡养"、"不承担赡养"（Phase 8 缺陷 D1 补齐） |

**判定语义**：命中否定 = **已知不存在**，不是"未知"。
这一条决定了 `NOT_IDENTIFIED` 能不能判出来——把"无房贷"读成"不知道有没有房贷"，R4 就会永远停在 `UNDETERMINED`。

---

## 7. 派生字段

`family_responsibility`、`liabilities` 等由引擎从其它字段推导 → `status=INFERRED` + `note` 写明推导依据。
上游透传字段**不得**标 `INFERRED`（AGENTS.md §3）。

---

## 8. 机检落点

| 检查 | 位置 | 不变量 |
|---|---|---|
| 结论有证据 | Eval 2 `evidence_grounding` | 每个 `risk_exists=true` 的 risk 至少 1 条非 unknown 证据；`reasoning_evidence_refs` 不得悬空 |
| UNKNOWN 未被滥用 | Eval 5 `unknown_integrity` | ESTIMATED/ASSUMED/INFERRED 必须有 note；不可溯源不得标 KNOWN |
| 修复不发明事实 | Repair 红线 | 修复前后 `evidence[]` 集合与 `impact_estimate.amount` 必须逐字一致（契约 §9 断言） |
