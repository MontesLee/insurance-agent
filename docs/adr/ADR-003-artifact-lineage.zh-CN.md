> 🌐 **Language:** 🇺🇸 [English](ADR-003-artifact-lineage.md) · 🇨🇳 中文

<a id="adr-003-artifact-lineage"></a>
# ADR-003 · 产物血缘

<a id="context"></a>
## 背景

在推荐某款产品之后，系统必须回答“为什么是这款”：它覆盖了哪项需求、针对哪种风险、保障缺口判断基于什么、客户事实又从何而来。如果各层之间只传递自由文本，这条链路就断了。

<a id="decision"></a>
## 决策

每一个输出都登记为一个**带血缘的产物（Artifact with lineage）**：`artifact_id` / `produced_by`（由哪个阶段产出）/ `input_artifacts`（源自哪些产物 ARTs）/ `fingerprint`（sha256）/ `evidence_refs`。注册表**只存元数据、绝不复制内容**（内容存在于 `state["artifacts"]`）。冻结机制使已发布的产物不可变。

<a id="alternatives"></a>
## 备选方案

- 只存最终报告：中间推理无法回溯。
- 把血缘写进产物内部：污染契约，并使跨产物引用变得别扭。
- 对每个中间状态做全量快照：存储爆炸，且“谁依赖谁”变得不可见。

<a id="why"></a>
## 理由

血缘将“结论”转化为“可审计的推导链”。它同时支撑三件事：
(1) 评估（Eval）的 `cross_artifact` 检查（例如保障缺口必须引用真实存在的 `risk_id`）；
(2) 报告中的溯源（推荐 → 产品 → 证据 → 文档 → 片段（Chunk））；
(3) 篡改检测（任何 fingerprint 变动即为 `ARTIFACT_MUTATION`）。

<a id="trade-offs"></a>
## 取舍

- 注册表必须在每次读写时维护；代码更多。
- fingerprint 与内容紧密绑定——任何无害的格式变更都会触发不一致；需要严格的“只写一次”纪律。
- 跨案例（Cases）复用血缘需要额外设计（目前一个客户 = 一个 CaseState）。
