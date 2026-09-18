# 保险领域（示范负载）

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](insurance-domain.md)

保险是用于示范 Agent Runtime 架构的**参考领域** —— 不是贴上去的例子。
这个领域的硬问题（什么是事实、什么可以影响推荐、证据从哪来）恰恰
塑造了运行时的边界（污染检查、溯源门禁、目录不变量）。

## 1. 分析流水线

实现为 `runtime/insurance-analysis.yaml`（9 个 stage + 1 个共享服务）；
每个 stage 对应 `.trae/skills/` 里的一个 Skill，各自带契约与 eval：

```text
FACT          client-intake            client-profile          （对话/provided）
   ↓
REQUIREMENT   requirement-analysis     requirement-analysis     （对话/provided）
   ↓
RISK          risk-analysis            risk-assessment          （对话/provided）
   ↓
GAP           coverage-gap-analysis    coverage-gap-analysis    （确定性引擎）
   ↓
SOLUTION      solution                 solution-plan            （确定性引擎）
   ↓
EVIDENCE      knowledge-search         knowledge-evidence       （共享 RAG 服务）
PRODUCT       product-candidate-provider  product-candidates    （确定性引擎）
   ↓
RECOMMEND     product-recommendation   product-recommendation   （确定性引擎）
   ↓
REPORT        report-generation        insurance-report         （确定性引擎）
```

各环节一句话职责：**FACT** 以四元组（值/状态/来源/置信度）收集客户
事实，不做判断；**REQUIREMENT** 把事实变成有优先级的需求（与产品
无关）；**RISK** 识别并排序风险敞口；**GAP** 量化未保额；**SOLUTION**
设计策略层方案（契约规定与产品无关）；**EVIDENCE** 检索有出处的知识；
**PRODUCT** 从目录筛候选；**RECOMMEND** 把方案方向映射到具体产品；
**REPORT** 综合生成最终分析报告。

## 2. 方案与产品推荐的刻意分离

`solution-plan` 与 `product-recommendation` 是两个独立 artifact、两个
独立 skill、两道独立 eval 门（ADR-006）。分析层（需求/风险/缺口/方案）
受**污染检查**：一旦出现具体产品、公司或产品 id，eval 直接失败。只有
目录支撑层可以点名产品。这保证"分析"保持诚实，推荐可回溯到目录条目
而非 LLM 编造。

## 3. 产品目录安全

`catalog/product-catalog.v0.1.json` 是**演示目录**，并且在结构上就说
清楚了：

- 目录与产品级都有 `is_demo: true`；保险公司名是虚构的
  （`demo-insurer-A`……）；`notice` 字段声明演示基准。
- 有版本：`catalog_version`、每个产品的 `product_version`、
  `effective_from`/`effective_to` 生效日期、声明的保费基准。
- 候选提供器只提出目录内条目；eval 不变量（`catalog_exists`、
  `catalog_has_primary_product`）使任何不在目录中的产品 id 失败，
  repair 动作 `DROP_INVALID_PRODUCTS` 在重跑前从输入侧剔除。

> 本仓库**不包含**真实保险产品数据。所有产品都是显式版本化的虚构
> 演示条目。

## 4. 知识 / RAG（fail-closed）

```text
查询 → 归一化 → 检索 → RRF 融合 → 过度检索 → 重排 → 证据
```

- 引擎（`knowledge/rag/engine.py`）不硬编码任何判断：打分权重、来源
  质量映射、阈值与冲突键全部来自 knowledge-search skill 内的规则
  JSON。
- **共享 Evidence Provider**（`knowledge/evidence/provider.py`）是任何
  skill 获取证据的唯一接缝；请求与响应都过契约校验
  （`knowledge-query` / `knowledge-evidence` schema）。
- **Fail-closed**：检索弃权（证据不足）时空结果原样传播 —— 不编造、
  下游停止而不是消费虚构知识，eval 门 `required_non_empty` 让空证据
  artifact 失败。
- 语料是**小型本地演示知识库**
  （`.trae/skills/knowledge-search/evals/fixtures/kb`）。未连接任何外部
  或真实保险数据库；溯源字段指向这份本地语料。

## 5. 领域规则与运行时机制的对应

| 领域规则 | 运行时机制 |
| --- | --- |
| 分析层不得点名产品 | `contamination` eval 检查 |
| 推荐必须有目录支撑 | `invariant` eval 检查 + repair |
| 证据必须有出处 | `provenance` eval 检查 + 证据契约 |
| 事实来自客户而非 LLM | 对话适配器 + 四元组溯源 |
| 报告必须可追溯 | artifact 血缘（报告 → … → 客户事实） |
| 客户事实缺失/冲突则停 | 客户信息门 → `WAITING_FOR_USER` |
