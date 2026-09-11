---
name: "requirement_analysis"
description: "保险需求分析。基于 client_intake 产出的客户画像进行信息充分性判断、需求识别、需求优先级分析与后续问题生成。"
---

# Requirement Analysis Skill

本文件是 `requirement_analysis` 的注册入口。

完整 Contract / 能力 / 测试真源：
- `02-requirement-analysis/CONTRACT.md`  — Input / Output / Status / Evidence / Boundary Contract
- `02-requirement-analysis/schemas/input.schema.json`  — 输入 JSON Schema
- `02-requirement-analysis/schemas/output.schema.json` — 输出 JSON Schema
- `02-requirement-analysis/INFORMATION_SUFFICIENCY.md` — 信息充分性引擎（加权打分 + Blocking Fields + Conflict Fields）
- `02-requirement-analysis/QUESTIONING.md`  — 主动追问优先级与多轮策略
- `02-requirement-analysis/ANALYSIS.md`    — Risk Map / Requirements / Coverage Gaps / Priorities / Evidence 生成
- `02-requirement-analysis/EVAL.md`        — 独立 Deterministic Eval（6 类 Issue Taxonomy + 5 维打分）
- `02-requirement-analysis/REPAIR.md`      — Targeted Repair Loop（MAX_RETRY=2，无法修复时进入 HUMAN_REVIEW_REQUIRED）
- `02-requirement-analysis/DATASET.md`     — 15 个 case、三类场景（analysis_only / multi_turn_update / mutated_eval）的回归集
- `02-requirement-analysis/tests/dataset/dataset-report.json` — 最近一次全量回归报告

当前实现状态：**Phase 0 ~ Phase 8 全部完成 + Production Ready 加固已落地**。
- Runner 侧所有子脚本调用均走 `scripts/lib/requirement-analysis-runtime.ps1`：显式 `powershell -ExecutionPolicy Bypass` 启动 + Output JSON 强校验（文件存在 / 大小阈值 / 合法 JSON / 顶层属性存在），杜绝生产沙箱 ExecutionPolicy 导致的静默失败。
- Dataset Pass Rate：**15/15（100%）**；5 维 Eval 均分 > 93；Phase1~Phase6 级测试脚本全量 PASS。

---

## Skill 定位

`requirement_analysis` 的目标是：

1. 读取 `client_intake` 已整理好的客户事实
2. 判断当前信息是否足以支撑需求分析
3. 输出结构化的需求分析结果
4. 严格区分：
   - 客户事实
   - 推理结论
   - 假设
   - 未知信息

---

## 严格边界

可以做：

- 分析客户保障需求
- 标记信息缺口
- 输出需求优先级
- 输出证据链

不可以做：

- 修改 `client_intake` 的任何文件、Prompt、Schema、测试或逻辑
- 输出具体保险产品
- 输出保险公司名称
- 输出销售话术
- 把未知信息当成事实

---

## 输入来源

优先输入来源：

1. `01-client-intake/clients/<客户目录>/CLIENT_PROFILE.md`
2. `client_intake` 的本轮执行结果 JSON（仅作为补充上下文，不作为长期真源）

若 `client_intake` 字段与本 Skill 不完全匹配，必须使用 Adapter 做字段映射，不得反向修改 `client_intake`。

---

## 当前阶段说明

Phase 0 ~ Phase 8 已全部完成，且 Production Ready 加固已落地（统一运行时安全调用 + Output JSON 强校验，Dataset 15/15 PASS）。

已锁定的 Contract：

1. Input Schema
2. Output Schema
3. Status Enum（5 态 analysis_status）
4. Requirement Type Enum
5. Evidence / Unknown / Assumption 边界
6. 与 `client_intake` 的接口关系

完整使用方式、PowerShell 调用模板、常见错误处理见 `02-requirement-analysis/USAGE_GUIDE.md`。
