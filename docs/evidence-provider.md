# 共享 Evidence Provider（V2 Phase 4）

> 落实用户 Phase 1 评审的**修改 3**：
> Knowledge Search 不是 workflow 里写死的第 6 步，而是**任何 Skill 在任何时刻都能请求的共享 Evidence Provider**。

---

## 1. 为什么要有这一层

把 Knowledge Search 写死成线性流程的一步，会锁死架构：

```text
solution → knowledge-search → product-recommendation     # 写死
```

真实的决策过程需要的是**回环**：

```text
                   ┌→ Knowledge Search
                   │
Risk ─→ Gap ─→ Solution
                   │
                   └→ Knowledge Search
                            ↓
                    Product Recommendation

Product Recommendation
        ↓  "我缺少某个产品责任的证据"
Knowledge Search → Evidence → 继续 Recommendation
```

因此 Workflow 必须支持的原子操作是：

```text
Skill → Evidence Request → Knowledge Search → Skill
```

而不是 `Step 6`。

---

## 2. 结构

```text
evidence/
├── __init__.py
├── request.py        # 请求侧：把任意 Skill 的需要 → 规范 KnowledgeQuery
├── provider.py       # 供给侧：KnowledgeQuery → knowledge-search 引擎 → 规范 KnowledgeEvidence
├── loop.py           # 受控回环：一次完整的 request → retrieve → return
└── resources/config/evidence-request.rules.json   # 查询模板外置
```

一次回环：

```python
from evidence import request_evidence

round = request_evidence(solution_entry, source_kind="solution")
round["request"]    # 规范 KnowledgeQuery  （已过契约校验）
round["evidence"]   # 规范 KnowledgeEvidence（已过契约校验）
round["source_unchanged"]   # True —— 请求方 Artifact 未被修改
```

`source_kind` 取值：`solution` / `gap` / `risk` / `text`。

---

## 3. 请求侧：查询是模板生成的，不接受自由文本

```python
query = f"{domain_query_template[domain]} {purpose_query_suffix[purpose]}"
```

| domain | 模板 |
| --- | --- |
| `life` | 定期寿险 保障期限 保额 家庭责任 |
| `medical` | 百万医疗险 保障范围 免赔额 社保目录外 |
| `critical_illness` | 重疾险 确诊给付 保额 收入补偿 |
| `accident` | 意外险 伤残分级 意外医疗 |
| `savings` | 年金险 储蓄 现金流 确定给付 |
| `general` | 保险 保障 责任 |

`purpose` ∈ `SOLUTION_VALIDATION / PRODUCT_VALIDATION / POLICY_FACT / MEDICAL_FACT / REGULATORY_FACT / COMPARISON / OTHER`。

**为什么不接受调用方自由文本？**

1. 查询是检索质量的唯一入口，交给调用方自由拼接等于把检索可控性让渡出去。
2. 自由文本是幻觉与注入的入口。模板化后，查询是 `(domain, purpose)` 的纯函数——
   同域同目的必得同一查询（单测断言）。
3. 需要的**具体性由 domain + purpose 提供**，需要的**可追溯性由 `related_artifact_ids` 提供**，
   二者分离，各自可测。

调用方 Artifact 的 id（`SOL-001` / `GAP-R1-001`）进入 `related_artifact_ids`，
**不进入 query**。

---

## 4. 硬边界

| # | 边界 | 强制方式 |
| --- | --- | --- |
| B1 | **Evidence ≠ Recommendation**：证据产物不得携带决策字段（`recommendation` / `candidate_id` / `fit` / `priority` / `severity` / `gap_level`…） | 不变量单测「禁止属性存在」 |
| B2 | **诚实弃权**：`insufficient_evidence` 必须对应**空** evidence 列表，绝不补一条 | 不变量单测 + 负向探针 |
| B3 | **只读回环**：绝不修改请求方 Artifact | deepcopy 前后比对，写入 `source_unchanged` |
| B4 | **冲突透传**：引擎 `conflict=true` 时原样透传，保留双方证据，不自动合并 | 数据集 case-05 + 逐条断言 |
| B5 | **不重造检索**：直接调用 knowledge-search 引擎，不复制检索逻辑、不改其业务 | 代码结构（`provider.build_engine` 加载其入口） |
| B6 | **双向契约校验**：请求与证据都过 `contracts/*.schema.json` | `provider.validate` 内建 |

---

## 5. 验证结论

| 套件 | 结果 |
| --- | --- |
| 契约测试（9） | **ALL GREEN**（knowledge-query / knowledge-evidence 已改为跑真实 provider） |
| `tests/evidence` 数据集（5 例） | **ALL GREEN** |
| 架构不变量单测 | **ALL GREEN** |
| 负向探针（反橡皮图章） | **GUARDS LIVE** |

负向探针三项均真实触发：

- 注入"弃权但仍返回证据"的引擎 → 弃权诚实性检查**捕获**
- 篡改 `domain_query_template` → 查询随之改变（证明规则驱动，非硬编码）
- 在 payload 中植入 `priority` → 决策字段检测器**捕获**
- 基线：0 命中

5 个既有/新建 Skill 数据集回归全绿；**`knowledge-search` Skill 0 文件被修改**。

---

## 6. 运行

```bash
python tests/evidence/run_evidence_dataset.py
python tests/evidence/test_evidence_invariants.py
```

---

## 7. 与决策链的关系

Evidence Provider 是**横切能力**，不属于任何单一 Skill：

```text
ClientProfile → Requirement → Risk → CoverageGap → Solution → Product → Report
                                         ↑            ↑          ↑
                                         └──── Knowledge Search ──┘
                                              （按需，非固定步骤）
```

下游 `product-recommendation`（Phase 5）将通过同一回环请求 `PRODUCT_VALIDATION` 证据，
无需新增任何检索代码。
