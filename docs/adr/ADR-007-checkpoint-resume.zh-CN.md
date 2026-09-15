> 🌐 **Language:** 🇺🇸 [English](ADR-007-checkpoint-resume.md) · 🇨🇳 中文

# ADR-007 · Checkpoint / Resume

## Context
Agent 跑一条长链（9 步 + 可能多次 repair）会中断：等待客户补资料、等待人工审核、进程被杀。
若每次中断都从零重跑，既浪费又会重复施加副作用（如重复检索）。

## Decision
- **Checkpoint**：每阶段 OK/GATE/NEEDS_REVIEW 后由 `run()` 落盘（`case_state.json` + `checkpoints[]` 条目）。
- **Validate 后信任**：`load()` 做 5 项校验（文件存在/可解析、`case_id` 匹配、schema 合法、registry fingerprint 一致、task→stage 引用完整）；
  **任一失败即 `CHECKPOINT_INVALID` + 原因列表，绝不从损坏状态静默续跑**。
- **Resume** 只重跑未 PASS 的 task，并**报告**被重跑的 PASSed task（正常应为空）。
- **闸门是真实停点**：gate `stop` → `PAUSED_NEEDS_REVIEW`，`next_runnable` 仍指向被闸 stage，**重试不可绕过**，必须显式 `approve()`。

## Alternatives
- 不落盘，全靠内存：进程一死全丢。
- 落盘但不校验：损坏状态静默续跑会产出错误结论且难以发现。
- 闸门做成「建议」：人工审核形同虚设。

## Why
可恢复性同时要求「能续」和「续得对」。校验是「续得对」的前提；
前置条件要求**生产者 stage 已 `COMPLETED`**（而非 artifact 存在），否则停在 `NEEDS_REVIEW` 的 stage 挡不住下游。

## Trade-offs
- 每次 checkpoint 全量落盘，Case 大时 IO 偏高（当前规模可接受）。
- 严格校验会在环境迁移（如绝对路径变化）时误报 `CHECKPOINT_INVALID`，需人工介入。
- 冻结 + 校验意味着「手动修一下 state 再跑」不被允许，调试需要走正规 repair 路径。
