# Artifact、血缘与溯源

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](artifacts-and-provenance.md)

事实来源：`runtime/artifact_registry.py`、
`runtime/state/case_state.py`（`put_artifact`）、
`runtime/state/transitions.py`、`contracts/`。

## 1. Artifact = 持久输出边界

每个 stage 恰好产出一个规范 artifact 类型，按 `contracts/` 中的 JSON
Schema 校验（client-profile、requirement-analysis、risk-assessment、
coverage-gap-analysis、solution-plan、knowledge-evidence、
product-candidates、product-recommendation、insurance-report）。内容存
在 `state["artifacts"]`（磁盘上每个 artifact 另有一个可检视文件）；
注册表只存**元数据 + 血缘** —— 绝不存第二份内容。

## 2. Artifact 注册表

每条注册记录包含：

```text
artifact_id        ART-001、ART-002…… 顺序、确定性
artifact_type      规范类型
producer_skill / producer_stage
input_artifacts    声明消费的上游 artifact id（血缘边）
status             VALID
content_ref        磁盘上的 artifacts/<type>.json
fingerprint        规范 JSON 的 sha256 —— 冻结守卫
evidence_refs      payload 内声明的证据/文档 id
```

- **确定性编号**：按注册顺序 `ART-%03d`。并行模式下 scheduler 通过
  规范路径重新注册合并的 artifact，编号只由图序决定、与线程时序无关
  （用"多次运行 id 映射完全一致"来测试）。
- **血缘**：`lineage()` 沿 `input_artifacts` 回溯到客户事实 ——
  "这条推荐从哪来"不需要重跑任何东西就能回答。
- **冻结**：完成后 `put_artifact` 拒绝改变 artifact
  （`guard_immutable`，指纹比对）；加载时 `verify()` 复查每个指纹 ——
  被篡改的 artifact 会变成响亮的 `CHECKPOINT_INVALID`，而不是静默损坏。

## 3. 重复与冲突处理（fail-closed）

- 同类型重新注册是**幂等**替换（同一个 id）。
- 同类型但**内容不同**的重新注册被拒绝（并行合并中的
  `MERGE_REJECTED` / `ARTIFACT_COLLISION`）。没有覆盖、忽略或
  last-write-wins 路径。
- 重复 *id* 在构造上就不可能（单写者顺序注册）；并行测试在并发执行
  后断言唯一性。

## 4. Artifact 与 Message 的区别

```text
Artifact = 持久事实（经过校验、冻结、带血缘、进 checkpoint）
Message  = 协调信号（只有 id、经过校验、会被 ACK —— 永不是事实）
```

Agent 之间通过引用 artifact id 通信；任何需要内容的消费者都经注册表
读取 artifact。消息绝不携带 payload 副本，永远不可能成为第二事实
来源。

## 5. 领域层的溯源

注册表血缘之外，领域 artifact 自带溯源 payload：知识证据声明文档/
分块 id 与置信度；推荐 artifact 引用的证据必须可解析（eval 的
provenance 检查）；报告生成只从既有 artifact 综合。见
[insurance-domain](insurance-domain.zh-CN.md) 与 ADR-003 / ADR-005。
