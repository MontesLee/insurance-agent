# 03 — 状态与枚举（Status & Enums）

> 来源：原 CONTRACT.md §5（Analysis Status）、§6（Requirement Types）、§7（Priority）。
> 本文件锁定所有枚举，是 Output Schema 的强制约束来源。

---

## 1. Analysis Status（分析状态，5 态）

- `COMPLETE`：信息足够，分析可作为正式需求结论输出
- `PRELIMINARY`：可以给出初步分析，但存在明确不确定性
- `NEED_MORE_INFORMATION`：信息不足，必须先补关键资料
- `CONFLICTING_INFORMATION`：存在关键冲突信息，不能直接给出稳定结论
- `FAILED`：分析失败，通常用于结构错误、运行错误或 Eval 拒收

## 2. Requirement Type（需求类型，当前 5 类，可扩展）

- `medical`
- `critical_illness`
- `accident`
- `life`
- `savings`

说明：当前先锁定这 5 类，后续允许扩展；输入和输出都必须使用统一 enum。

## 3. Priority（优先级，4 级）

- `P0_CRITICAL`：若不先处理，该需求会显著影响家庭核心风险承受能力或后续分析可靠性
- `P1_HIGH`：风险明显，应优先纳入近期保障规划
- `P2_MEDIUM`：有必要处理，但优先级低于当前核心缺口
- `P3_LOW`：可后置观察或在后续补充信息后再判断

## 4. 状态间约束（与 Eval 联动）

- 当 `analysis_status = NEED_MORE_INFORMATION / CONFLICTING_INFORMATION` 时，不得输出正式 `requirement`（Eval 失败类型 `INSUFFICIENT_INFORMATION`）。
- `risk_map.priority` 与 `requirements.priority` 必须一致（Eval 失败类型 `LOGICAL_INCONSISTENCY`）。
- `analysis_status` 必须与输出内容自洽。

## 5. 输出 Schema

完整字段定义见 `schemas/output.schema.json`。
