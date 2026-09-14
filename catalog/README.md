# Product Catalog（V0.1 — DEMO）

## ⚠️ 这是演示数据

`product-catalog.v0.1.json` 中的 **12 个产品全部是虚构的**：

- 每个条目的 `is_demo` 都是 `true`
- 公司名为 `demo-insurer-A/B/C`，产品名以 `demo-` 前缀
- `premium.annual` 的 `basis` 是 `demo_reference` —— **参考量级，不是真实报价**
- `term.years = 999` 表示终身（`term_whole_life_years` 在 catalog 顶层声明）

**用途**：让 `Candidate → Recommendation` 链路可被确定性测试。
**禁止**：把这些产品当作真实可投保产品呈现给客户，或把保费当作真实价格引用。

## 结构

```
catalog/
├── README.md
└── product-catalog.v0.1.json      # 12 个 demo 产品
```

Schema：`.trae/skills/product-candidate-provider/schemas/product-catalog.schema.json`

## 险种覆盖

| product_type | 产品 |
|---|---|
| `medical` | P001 百万医疗A、P002 长期保证续保、P003 中端0免赔、**P011 老年医疗（限60-80岁）** |
| `critical_illness` | P004 定期至70、P005 终身、P006 多次赔付 |
| `life` | P007 定期寿险、**P008 增额终身寿（储蓄/传承方向）** |
| `accident` | P009 综合意外、P010 高危职业 |
| `savings` | P012 年金险 |

加粗的两个是刻意设计的负向样本：

- **P011**：年龄区间 60–80，用于验证 30 岁客户必须被判 `ELIGIBILITY_INELIGIBLE`
- **P008**：`life` 类型但保障方向是储蓄/传承，用于验证寿险策略下必须判
  `COVERAGE_DIRECTION_MISMATCH`（同类型但方向错，不得成为主推荐）

## 校验

```bash
python .trae/skills/product-candidate-provider/scripts/invoke-product-candidate-provider.py \
    --validate-catalog

python .trae/skills/product-candidate-provider/scripts/invoke-product-candidate-provider.py \
    --lookup P001
```

## 换成真实数据

把 `catalog/product-catalog.v0.1.json` 替换为真实产品库即可，
`candidate-provider.rules.json` 的 `catalog_path` 指向新文件。
届时 `is_demo` 应改为 `false`，且**必须同时保留 `evidence_refs` 的真实来源**，
否则候选会因 `EVIDENCE_MISSING` 全部被拒。
