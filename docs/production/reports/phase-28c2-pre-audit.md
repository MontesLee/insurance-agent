# Phase 28.C-2 Pre-Audit — Product QA Agent 最小生产闭环（开工前置，只读）

Date: 2026-09-25 · 性质：READ-ONLY（本文件先于一切代码）。依据：PRODUCT_VISION/
ARCHITECTURE_PRINCIPLES（FROZEN）· ADR-019..024 · 28.C-1 as-built · spec
（28.C-2 + 28.B readiness）。

## 1. QA Agent 结构可复用性（检查 #1）

28.C-1 的 `runtime/qa_agent/` 分层：gate（引用闭环门）/ context
（AnswerContext 构建+校验）/ agent（轮次循环+网关适配）。Product QA 需要
**同一** 门、同一 AnswerContext 契约、同一网关接线、同一拒绝模板——重复度
估算 **>60%**（触发 spec 的 30% 共享阈值）。处置：新建 `runtime/grounding/`
承载共享能力（citation gate / evidence validation / answer context
builder / generation loop + gateway adapter）；`runtime/qa_agent/gate.py`
与 `context.py` 降为**兼容 shim**（原 import 路径全部保持——C-1 的 16
测试不改不红）；`qa_agent/agent.py` 改为调用共享 loop。**行为等价重构**
（代码逐字搬移），非大规模重构。

## 2. KnowledgeService 产品事实支持（检查 #2）

- `build_evidence(query)` 为通用检索（无产品意识）——**不修改 knowledge/**
  （禁改承诺）。产品作用域过滤（只保留与已解析产品相关的证据）在 Product
  QA Agent 层做（确定性字符串规则）。
- 关键发现：**目录自带产品→知识链接**——每产品 `evidence_refs` 指向 KB
  文档（P001→01_medical_insurance.md…P012→00-product-taxonomy.md）。链接
  文档是产品作用域证据的合法判定依据（目录声明的证据域，非随意补位）。

## 3. Catalog 当前能力（检查 #3）

实证（catalog/product-catalog.v0.1.json，catalog_version 0.1，demo 模式）：

- **12 个产品**，命名 `demo-XXX`（P001 demo-百万医疗险A（标准版）…
  P012 demo-年金险A）。**spec 例名"健康满分"不存在于目录**——场景 A 以
  真实产品（demo-百万医疗险A / P001）同形问题实现，报告如实说明。
- **已有事实字段**：premium（P001 年缴 400）/ term / eligible_age /
  constraints（P001 deductible 10000元、P002 保证续保20年）/ features /
  coverage_directions / company / 双版本键（product_version+目录
  effective 窗口）——确定性查表有真材实料。
- **三缺依旧**：waiting_period / exclusions / health_declaration 数据与
  schema 双缺（B3 未决，D6 裁决 fail-closed 不阻塞）。
- 入口选择：`runtime/catalog_governance.py::load_catalog`（mode 感知 +
  validate_catalog 治理校验）——治理路径，非裸 eval_engine 读文件。

## 4. WeKnora 数据覆盖（检查 #4）

- fixtures KB（6 篇）为**品类级知识**（"百万医疗险常见等待期为 30 天"
  01_medical_insurance.md:15；重疾 90 天 02:15），显式标注 TEST DATA；
  **无任何具体产品条款文档**（grep 零命中产品名）。
- 推论（诚实边界设计）：产品参数问题的证据判定必须区分（a）目录链接文档
  中的**品类级表述**（可用，答案须以"常见/一般"框定并明示目录无专项值）
  与（b）**无中生有的产品专项值**（禁止）。判定规则确定性可编码：已解析
  产品 + 参数词命中 → 目录字段或链接证据内容含该词则答，否则
  `catalog_missing_fact` 拒答（D6）。P012 的 evidence_refs（00-product-
  taxonomy.md）不在 fixtures KB → 其参数问题将 fail-closed（正确行为）。
- 生产 WeKnora 需上传**产品条款文档**（KB 运营项，HD-2 相邻）才有专项
  参数可答——数据工程不阻塞今晚代码。

## 5. Schema 扩展需求（检查 #5）

`qa-answer-context.schema.json` 需**最小增量**（additive optional，向后
兼容 C-1 全部记录/测试）：

1. evidence anchor 增可选 `source_type`（"catalog" | 治理证据类型）——
   区分目录锚点与 WeKnora 证据。
2. 顶层增可选 `product_ref`（resolved/product_id/product_name/matched_by）
   ——产品解析结果入档（未解析产品问题不填）。

## 6. 发现的一个前置缺口（必须在 C-2 内修复）

**意图规则不认识目录产品名**："demo-百万医疗险A的等待期多久" 现分类为
insurance_qa（等待期∈qa signals；branch 1 只认 这款/那款/P0xx 标记）——
spec 流程要求 intent=product_qa。处置：classifier 增**确定性目录名信号**
（缓存目录；产品全名/去括号基础名/P0xx 命中 → specific-product 分支；
目录不可读→无信号→行为退化如旧，fail-closed）。影响面：意图规则行为演进
（外置数据源+确定性+语料回归 22/22 守护——A-1/A-2 同模式）；非 STOP 项。

## 7. 架构冲突检查（STOP 规则核验）

| STOP 条件 | 触发？ |
|---|---|
| 修改 ADR | 否——ADR-022 §1 表 WeKnora 拥有 条款文本；"链接证据+品类框定+双缺拒答"是表内边界的实现解释，记录于本审计与 decisions |
| 修改 PRODUCT_VISION | 否 |
| 切换 Router authority | 否——product_qa 切片 flag 默认 OFF；全局权威不动 |
| 修改 orchestrator 核心 | 否 |
| 修改 artifact contract | 否——schema/ 增量 optional 字段（run 记录契约自身演化，非 contracts/ 九类） |
| 修改 approval 状态机 | 否 |
| 修改 WeKnora 核心 | 否（knowledge/ 零改动） |

**判定：GO**（一处意图规则演进 + schema additive 扩展，均有回归守护；
其余全部为新增面）。

## 8. 实施计划

```
A runtime/grounding/（gate/context 逐字搬移 + loop 抽取：网关适配/
  build_gateway/证据块/生成-再生成-拒答梯度/冲突模板）；qa_agent shim 化
  → C-1 16 测试原样全绿（行为等价门）
B schema 增量（anchor.source_type + 顶层 product_ref，optional）
C config/product-qa-rules.yaml（参数词表/上下文扫描窗口/目录字段渲染）
D classifier 目录名信号 + 回归（corpus 22/22 + 新用例）
E runtime/product_qa_agent/（resolution + 证据组装 + 共享 loop）
F server 切片：INSURANCE_AGENT_PRODUCT_QA_SLICE 默认 OFF（与 QA slice
  同缝接线，actual_execution=insurance-qa-agent，qa_answered 增 slice 标识）
G tests（A-F 六场景 + 真数据 catalog_missing_fact + shim 等价 + 切片 e2e）
H 全量回归（before 662 → after 预期 662+新增）
I 28.B readiness audit（只读）+ phase 报告 + 记账
```
