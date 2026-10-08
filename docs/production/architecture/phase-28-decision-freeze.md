# Architecture Decision Freeze — Phase 28.0.5

Date: 2026-09-25 · 所有者最终裁决（依据：PRODUCT_VISION.md ·
ARCHITECTURE_PRINCIPLES.md · adr-approval-review-2803.md ·
phase-28-implementation-plan.md）。本文件是 ADR-019..024 的**裁决记录
与实施解锁凭据**；ADR 正文以 docs/adr/ 为准。

# Approved ADR

| ADR | Status | 裁决要点 |
|---|---|---|
| **ADR-019 Intent Layer** | **APPROVED**（M1 已落笔） | 意图输入 = message + recent conversation context + active case context；上下文不可得 → modify 意图 → clarification；**prompt 永不作为 intent source** |
| **ADR-020 Router Contract** | **APPROVED**（原文） | Router deterministic；三层约束 = schema contract + import boundary + CI tests |
| **ADR-021 Agent Registry** | **APPROVED**（原文） | Registry v1 = **configuration based**；禁止 runtime dynamic registry |
| **ADR-022 Knowledge Grounding** | **APPROVED**（原文） | Insurance fact grounding required：product fact / coverage / waiting period / exclusion / policy term 必须 Catalog 或 WeKnora evidence；**缺失 fail closed** |
| **ADR-023 Chat Artifact Experience** | **APPROVED**（原文） | **v1 = Markdown default；HTML / PDF = future**（渲染器唯一性与 L1 层级规则 v1 即生效） |
| **ADR-024 Conversation Case Lifecycle** | **APPROVED_WITH_CONSTRAINTS** | 补充①反馈锚定 = run_id + artifact_version（防未来反馈污染/串版本）②数据政策三定义（retention / access boundary / deletion strategy）未定前 **BLOCKED implementation** |

# Remaining blocked

- **conversation persistence implementation**（ADR-024 §6：retention /
  access boundary / deletion strategy 三项未定义）
- **data retention implementation**（同上）
- **catalog ownership**（目录数据工程归属与来源未定——阻塞真实产品
  问答价值，不阻塞代码）

# Implementation unlocked

- **28.A**（Intent Layer + Router + Registry 契约；影子模式 + 行为等价
  基线采集；详见 phase-28-implementation-plan §5.1 / implementation-
  gates ADR-019/020/021 栏）

# Implementation blocked

- **28.C** until: **KB dataset decision**（语料覆盖目标与投入裁定）
- **28.E** until: **ADR-024 implementation boundary**（§6 三项数据政策
  定义完成，解除 APPROVED_WITH_CONSTRAINTS 的 BLOCKED 项）
- 另见 phase-28-implementation-gates.md：28.B/D 另需 O-1 裁决
  （ADR-025 于 28.B 开工前成文）+ 行为等价门就绪；28.F 需 ADR-023
  future 部分解锁（HTML/PDF 时点）。

---

## 备注（裁决完整性）

- 28.0.3 的 HD-1（置信度阈值）与 HD-2（qa-answer 卡面政策）未在本轮
  裁决中给出：**28.A 影子期以观测数据回填 HD-1；HD-2 在 28.C 开工前
  必须裁定**（不阻塞 28.A）。
- O-1（ADR-025 Unified Runtime）：维持 28.0.3 建议——28.B 开工前成文。
- 本冻结后，ADR-019..024 的任何正文修改回到标准 ADR 流程（修订需
  显式记录，不得静默）。

**STOP — 等待 28.A 授权。**

---

## 2026-09-25 追加 — ADR-025 批准记录（Phase 28.B6）

Owner 批准 **ADR-025 Router Authority Migration**（PROPOSED →
APPROVED）。批准范围=治理框架与阶段准入方式；**各阶段（M2/M3/M4/M5）
仍须独立授权**；Router Authority 保持 OFF 直至 M4；M3 另设 preflight
门。批准时点前置状态：B4 GREEN 14/14 · backend 703/0 · web 148+2 ·
tsc clean · M2 机制经灰度+回滚演练验证 · model-fit 校准完成 · 治理
一致性审计 PASS。回滚契约（§6）为一切阶段切换的硬前提。完整记录见
docs/adr/ADR-025-router-authority-migration.md Status 节。
