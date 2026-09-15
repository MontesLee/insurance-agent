> 🌐 **Language:** 🇺🇸 [English](ADR-007-checkpoint-resume.md) · 🇨🇳 中文

<a id="adr-007-checkpoint-resume"></a>
# ADR-007 · 检查点 / 恢复

<a id="context"></a>
## 背景

一个运行长链路的智能体（9 个步骤 + 可能多次修复）会被打断：等待客户补充数据、等待人工复核、进程被杀死。每次中断都从头重跑，既浪费工作成果，又会重复副作用（例如重复的检索）。

<a id="decision"></a>
## 决策

- **检查点（Checkpoint）**：在每个阶段以 OK/GATE/NEEDS_REVIEW 结束时，`run()` 进行持久化（`case_state.json` + 一条 `checkpoints[]` 记录）。
- **先验证再信任（Trust after validate）**：`load()` 执行 5 项检查（文件存在/可解析、`case_id` 匹配、schema 有效、注册表 fingerprint 一致、task→stage 引用完整）；**任何失败即为 `CHECKPOINT_INVALID` + 一份原因列表——绝不静默地从损坏状态恢复**。
- **恢复（Resume）**只重跑非 PASS 的任务，并**报告**任何被重跑的 PASS 任务（通常为空）。
- **门禁是真正的停止点**：门禁 `stop` → `PAUSED_NEEDS_REVIEW`；`next_runnable` 仍指向被门禁挡住的阶段，**重试无法绕过它**——必须显式调用 `approve()`。

<a id="alternatives"></a>
## 备选方案

- 不做持久化，仅用内存：进程一死，一切尽失。
- 持久化但不验证：从损坏状态静默恢复会产生难以察觉的错误结论。
- 把门禁当作“建议”：人工复核变得毫无意义。

<a id="why"></a>
## 理由

可恢复性要求“能恢复”与“恢复正确”两者兼备。验证是后者的前提；前提要求**生产者阶段处于 `COMPLETED`**（而非仅仅是产物存在）——否则一个停在 `NEEDS_REVIEW` 的阶段无法拦住下游。

<a id="trade-offs"></a>
## 取舍

- 每个检查点都持久化完整状态；对大型案例而言 IO 较重（当前规模下可接受）。
- 严格验证会在环境迁移时假阳性（false-positive）报出 `CHECKPOINT_INVALID`（例如绝对路径变化）；需要人工介入。
- 冻结 + 验证意味着“手动改状态再重跑”不被允许；调试必须走正规的修复路径。
