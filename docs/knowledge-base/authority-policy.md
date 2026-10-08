# KB v1.0 Authority Boundary Policy

**核心原则:General knowledge cannot automatically upgrade to product fact.**

## 不可跨层升级

```
L1/L2/L3/L4/L5 不能自动跨层升级证据权威。

General Insurance Knowledge      ≠ Product Fact
Product Type Knowledge           ≠ Specific Product Fact
Planning Methodology             ≠ Regulatory Requirement
FAQ                              ≠ Contractual Evidence
```

## 禁止的推理示例

| 错误推理 | 为什么错 |
|---|---|
| 「重疾险通常包含重大疾病责任」→「所以某产品一定包含 XXX 疾病」 | 险种通识 → 产品事实(需产品条款证据) |
| 「家庭经济支柱需要较高寿险保障」→「因此客户应该购买 500 万寿险」 | 方法论 → 个性化结论(Planning 域) |
| 「医疗险通常有免赔额」→「因此该产品免赔额为 1 万」 | 险种通识 → 产品数字(REQUIRE_KB) |

## 与运行时契约的对应

- Claim Support:DOMAIN-FACT 必须 cited∧SUPPORTED(封印语义不变)
- C2 资格:QualifiedEvidence 是唯一证据入口
- Authority(Phase-16 cohort):scope 仅 FACTUAL_PARAPHRASE
- R3 产品事实:无 QualifiedEvidence → REFUSE(任何层知识不可替代)
