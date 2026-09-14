# Product Candidate Provider — CONTRACT

## 1. 在链路中的位置

```text
Solution ──► Evidence ──► Candidate ──► Recommendation
                            ▲
                     （本 Skill）
```

```text
SolutionPlan + CoverageGapAnalysis + ClientProfile + KnowledgeEvidence + ProductCatalog
        ↓
   ProductCandidates（真实 Catalog 产品，确定性筛选）
        ↓
   product-recommendation（排序、选主推、给理由）
```

## 2. 为什么必须有这一层

Step 2 之前，链路上是：

```text
SolutionPlan → solution_to_candidates → candidate_solutions → recommendation
```

那是把**策略**伪装成**候选**：策略没有产品、保费、期限、投保资格，也没有证据。
`recommendation` 实际上在对一组不可能存在于任何产品库的对象排序。

本 Skill 用真实 Catalog 闭合这个洞。

## 3. 与 recommendation 的职责切分（强制）

| 关注点 | Product Candidate Provider | product-recommendation |
|---|---|---|
| 产品是否真实存在 | ✅ | 断言（不得出现） |
| 类型 / 方向 / 资格 / 证据 | ✅ 判定并打标 | 消费判定结果 |
| 排序与选主推 | ❌ | ✅ |
| 生成 decision reasons | ❌ | ✅ |
| 输出 primary / alternatives | ❌ | ✅ |

**禁止**让同一个环节"想产品 → 生成产品 → 推荐产品"。

## 4. 判定输出契约

每个 candidate 必须携带：

| 字段 | 取值 | 含义 |
|---|---|---|
| `product_type_match` | `MATCH` | 类型不匹配者根本不进入候选 |
| `coverage_direction_match` | `MATCH / MISMATCH / UNKNOWN` | 保障方向关键词命中 |
| `eligibility.status` | `ELIGIBLE / INELIGIBLE / UNKNOWN` | 年龄、职业 |
| `evidence.status` | `AVAILABLE / MISSING` | 是否有对应领域证据 |
| `admissible` | bool | 以上全部通过 |
| `reject_reason_codes` | 数组 | 失败原因 |

`UNKNOWN` 是**独立第三态**，绝不与 `ELIGIBLE` 合并。

## 5. 失败语义

| 场景 | 输出 |
|---|---|
| Catalog 无对应险种 | `status=NO_CANDIDATES` + `next_information_needed` |
| 候选存在但无证据 | 候选 `EVIDENCE_MISSING`，`admissible=false` |
| 请求了不存在的产品 | `rejected[].reason_codes=[PRODUCT_NOT_IN_CATALOG]` |
| 缺 solution_plan | `status=INSUFFICIENT_INPUT` |

## 6. 不变量（机检）

1. 候选 `product_id` ⊆ Catalog `product_id`
2. 所有候选 `is_demo = true`
3. `INELIGIBLE` 候选绝不进入 `admissible_candidate_ids`
4. 年龄未知 → `UNKNOWN`，永不 `ELIGIBLE`
5. 空保障方向 → `UNKNOWN`，永不 `MATCH`

## 7. 上游依赖（只读）

`SolutionPlan` / `CoverageGapAnalysis` / `ClientProfile` / `KnowledgeEvidence` / `ProductCatalog`
—— 本 Skill 一律只读，不写回。
