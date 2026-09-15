# Step 2：Evidence + Product Recommendation

> 目标：让 Agent 能基于需求、风险、保障缺口与解决策略，**检索有来源的知识证据**，
> 从**真实 Catalog** 生成受约束的产品候选，并做出**可解释、可追溯**的产品推荐。

```text
Solution ──► Evidence Request ──► Knowledge Search ──► KnowledgeEvidence
                                                              │
Client ──► CoverageGap ──► Product Catalog ──► ProductCandidateProvider
                                                              │
                                                              ▼
                                                    ProductRecommendation
```

---

## 1. 审计结论（先审计，再编码）

| 规格要求 | 审计前真实状态 |
|---|---|
| A. Knowledge Evidence Contract | ✅ 已存在 `contracts/knowledge-evidence.schema.json` |
| B. Evidence Provider | ✅ 已存在 `evidence/`（`request` / `provider` / `loop`） |
| C. Product Candidate Provider | ❌ **不存在**（只有策略→候选的 translator） |
| D. Product Catalog | ❌ **不存在**（全仓库 grep `catalog` 零命中） |
| E. Recommendation 消费真实候选 | ❌ 消费的是策略级占位，无产品/保费/资格 |
| F. Step 2 E2E | ❌ 不存在 |

另外发现一个**真实缺陷**：

> `adapters/knowledge_search_adapter.to_canonical` 把 `provenance` 写成 `[]`，
> 且**丢弃了 `chunk_id` / `document_id`** —— 规格 §二十二 要求的
> `Recommendation → Evidence → Document → Chunk` 追溯链实际上是**断的**。

---

## 2. 新增：Product Catalog（V0.1 DEMO）

`catalog/product-catalog.v0.1.json` —— 12 个结构化产品，覆盖医疗 / 重疾 / 寿险 / 意外 / 储蓄。

```json
{
  "product_id": "P001",
  "product_name": "demo-百万医疗险A（标准版）",
  "product_type": "medical",
  "company": "demo-insurer-A",
  "is_demo": true,
  "features": [...],
  "eligible_age": { "min": 0, "max": 65 },
  "eligibility_rules": [{"rule": "age", "min": 0, "max": 65}],
  "coverage_directions": ["医疗","住院","大额","社保目录外","免赔额"],
  "constraints": [...],
  "required_evidence_domains": ["medical"],
  "evidence_refs": ["01_medical_insurance.md"],
  "premium": { "annual": 400, "basis": "demo_reference" },
  "term": { "years": 1 },
  "liquidity_impact": "low"
}
```

**全部 `is_demo = true`，保费是 `demo_reference` 参考量级，公司名是 `demo-insurer-*`**。
不得当作真实可投保产品，不得当作真实报价。

两个刻意设计的负向样本：

| 产品 | 用途 |
|---|---|
| **P011** 老年医疗（限 60–80 岁） | 验证 30 岁客户必须判 `ELIGIBILITY_INELIGIBLE` |
| **P008** 增额终身寿（`life` 类型，方向是储蓄/传承） | 验证寿险策略下必须判 `COVERAGE_DIRECTION_MISMATCH` |

---

## 3. 新增：Product Candidate Provider

`.trae/skills/product-candidate-provider/`（SKILL / CONTRACT / schemas / references /
resources config / scripts / evals）

**四类确定性判定**（全部规则外置到 `candidate-provider.rules.json`）：

| 判定 | 取值 |
|---|---|
| `product_type_match` | 类型不匹配者**根本不进入候选** |
| `coverage_direction_match` | `MATCH / MISMATCH / UNKNOWN` |
| `eligibility.status` | `ELIGIBLE / INELIGIBLE / UNKNOWN` |
| `evidence.status` | `AVAILABLE / MISSING` |

`UNKNOWN` 是**独立第三态**，绝不与 `ELIGIBLE`/`MATCH` 合并。

**输出被拒候选而非静默丢弃**（`admissible=false` + `reject_reason_codes`）——
这样"为什么没推荐 P008"是可回答、可审计的。

### 职责切分（强制）

| 关注点 | Candidate Provider | Recommendation |
|---|---|---|
| 产品是否真实存在 / 类型 / 方向 / 资格 / 证据 | ✅ 判定 | 消费判定 |
| 排序、选主推、生成理由 | ❌ | ✅ |

---

## 4. 修改：Recommendation（不推倒重写）

按规格 §十四，通过 **adapter** 接入，核心引擎 `recommendation_engine.py` 不改评分逻辑：

- 新增 `scripts/product_candidates_to_candidate_solutions.py`
  —— 把 ProductCandidates 投影为 legacy engine 认识的 candidate 形状
- 新增 `resources/config/product-candidate-to-solution.rules.json`（纯投影映射）
- `schemas/product-recommendation-input.schema.json` 增加**可选** `product_candidates`
- `invoke-product-recommendation.py`：有 `product_candidates` → 用真实候选；
  没有 → 回退 `solution_plan`（legacy 行为**完全不变**）
- `recommendation_engine.py` 增加**产品校验硬阻断**：
  候选带 `_product_validation` 且未通过 → 硬拒（legacy 候选无此字段 → 零影响）

### 输出变化

`primary_recommendation` 新增 `product` 块：

```json
"product": {
  "product_id": "P007",
  "product_name": "demo-定期寿险A（定额）",
  "product_type": "life",
  "is_demo": true,
  "solution_id": "SOL-001",
  "related_gap_ids": ["GAP-001"],
  "eligibility": "ELIGIBLE",
  "evidence_status": "AVAILABLE"
}
```

`not_recommended[].reason` 对产品校验失败输出
`product validation failed: product_ineligible` 等具体原因。

### 状态语义

| 场景 | 状态 |
|---|---|
| 正常 | `COMPLETE` |
| 候选存在但无证据 | `INCOMPLETE_EVIDENCE`（规格 §十九 `INSUFFICIENT_EVIDENCE` 的既有等价态） |
| 无合格候选 / 全部不合格 | `NO_CANDIDATES` |
| 缺输入 | `INSUFFICIENT_INPUT` |

---

## 5. Evidence 可追溯性修复

`adapters/knowledge_search_adapter.to_canonical` 现在为每条证据补全：

```json
{
  "evidence_id": "…", "content": "…", "source": "…", "source_type": "…",
  "document_id": "…", "document_name": "01_medical_insurance.md",
  "chunk_id": "…", "section": "…", "source_level": "…",
  "retrieval_method": "sparse_rrf|hybrid_rrf|unknown",
  "provenance": [
    {"source_type": "DOCUMENT", "source_id": "…"},
    {"source_type": "CHUNK",    "source_id": "…"}
  ]
}
```

契约 `contracts/knowledge-evidence.schema.json` 同步显式声明（改生成源
`contracts/build_contracts.py` 后重新生成，避免手改被覆盖）。

新增契约测试 `tests/contracts/test_knowledge_evidence_traceability.py`：
真实检索 + 断言每条证据的 Document / Chunk 两跳都可解析。

---

## 6. 测试与结果

| 套件 | 结果 |
|---|---|
| 契约测试（9 → **10**） | **10/10** |
| Candidate Provider 不变量 + 负向 | **19/19** |
| Step 2 E2E（4 案例） | **61/61** |
| Step 1 core-analysis E2E | 41/41 |
| 其余既有 18 套件 | 全绿 |

### Step 2 E2E 案例

| 案例 | 结果 |
|---|---|
| `case-001-happy-path` | `COMPLETE`，主推 **P007**；P008 方向不符被拒 |
| `case-002-no-evidence` | `INCOMPLETE_EVIDENCE`，无主推 |
| `case-003-no-candidate` | `NO_CANDIDATES` + `next_information_needed` |
| `case-004-ineligible-product` | 全部 `product_ineligible`，无主推 |

**Evidence / Candidate / Recommendation 三段真实执行**（语料：
`domain/insurance/references`），只有 Requirement/Risk/Gap/Solution 用 fixture。

### 负向测试（规格 §二十）

1. `FAKE-001` → `PRODUCT_NOT_IN_CATALOG`，不进入候选
2. 85 岁客户 → 全部 `ELIGIBILITY_INELIGIBLE`
3. 寿险策略下的 P008 → `COVERAGE_DIRECTION_MISMATCH`
4. 无证据 → 全部 `EVIDENCE_MISSING`
5. 虚构产品名 `不存在的万能险X` → `NOT_FOUND`

外加**反向探针**：篡改险种映射后候选集必须改变 —— 证明守卫真的读了规则文件。

---

## 7. 本次踩到并修掉的真实缺陷

1. **空类型列表 = 全量候选**：`if ptypes and product_type not in ptypes: continue`
   在 `ptypes=[]` 时短路，导致整个 Catalog 12 个产品都成了候选（case-003 本应 0 候选）。
   已改为"空类型列表 → 零候选"。
2. **测试的假通过**：E2E runner 把 manifest 的 `entry` 当成 `expect` 传，
   导致 `provider_status` / `max_evidence` / `expect_rejected` 等 **8 类断言根本没执行**。
   已修 + 增加守卫：manifest 出现 runner 未实现的期望键 → **直接 FAIL**。
3. **Evidence 断链**：见第 5 节。

---

## 8. 技术债 / 留给 Step 3

- `ProductCandidates` **未**升级为 Canonical 契约（仅 Skill 级 schema）。
  升级需要改动全部 9 份 canonical schema 的 `artifact_type` 枚举，收益不抵风险，留 Step 3。
- Catalog 是 demo 数据（12 个）。真实产品库需保留 `evidence_refs` 的真实来源，
  否则候选会因 `EVIDENCE_MISSING` 全部被拒。
- Step 2 E2E 上游（Requirement / Risk / Gap / Solution）仍为 fixture。
  本机执行 `.ps1` 后可把产出注入变成真端到端。
- 未实现 Orchestrator / CaseState / Long-running Harness（规格 §二十六 明确禁止）。
- `eligibility` 目前只校验 `age` 与 `occupation_class`；健康告知、地区未纳入。
