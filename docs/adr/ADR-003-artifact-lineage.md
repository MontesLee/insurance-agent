# ADR-003 · Artifact lineage

## Context
推荐一个产品后，必须能回答「为什么是它」：它覆盖了哪条需求？针对哪个风险？缺口的判断依据是什么？客户事实从哪来？
如果层间只传自由文本，这条链就断了。

## Decision
每个产出物注册为**带血缘的 Artifact**：`artifact_id` / `produced_by`（哪个 stage）/ `input_artifacts`（来自哪些 ART）/ `fingerprint`（sha256）/ `evidence_refs`。
注册表**只存元数据，不复制内容**（内容在 `state["artifacts"]`）。冻结机制保证已发布 artifact 不可改。

## Alternatives
- 只存最终报告：中间推理不可回溯。
- 把血缘写进 artifact 内部：契约污染，且跨 artifact 引用困难。
- 全量快照每个中间态：存储爆炸且难以看出「谁依赖谁」。

## Why
血缘把「结论」变成「可审计的推导链」。它同时支撑三件事：
(1) Eval 的 `cross_artifact` 检查（如缺口必须引用真实存在的 `risk_id`）；
(2) 报告里的 Provenance（Recommendation → Product → Evidence → Document → Chunk）；
(3) 篡改检测（fingerprint 变了即 `ARTIFACT_MUTATION`）。

## Trade-offs
- 每次读写都要维护注册表，代码量增加。
- fingerprint 与内容强绑定，任何无害的格式变动都会触发不一致 —— 需要严格的「只写一次」纪律。
- 血缘链在跨 Case 复用时需要额外设计（当前一个客户 = 一个 CaseState）。
