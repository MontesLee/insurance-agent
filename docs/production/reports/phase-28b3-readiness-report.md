# Phase 28.B3 Readiness Report — Router Authority Migration 前置条件审计

Date: 2026-09-25 · 性质：审计（本阶段零 runtime/零生产路径改动——
git 复核：仅 docs 四件 + 记账）。问题：当前系统是否满足 Router
authority migration（ADR-025 M2→M4）的前置条件？

## 1. 前置条件总表（按 ADR-025 阶段映射）

| # | 前置条件 | 状态 | 证据/缺口 |
|---|---|---|---|
| P-① | 权威归属成案（ADR-025） | 🟡 **本阶段立案，PROPOSED** | docs/adr/ADR-025-router-authority-migration.md（八项必含主题齐备+O-1 闭合声明）；**待所有者批准** |
| P-② | B4 行为等价门 | 🟡 设计就绪，未实现 | router-equivalence-gate-design.md（六维对比/双等价类/自等价自检/RED 纪律）；实现+基线采集=下阶段授权项 |
| P-③ | Golden case 清单 | 🟡 25 案入库，未采集 | docs/testing/router-golden-cases.md（5 意图全覆盖+负向锚+覆盖矩阵）；PENDING_CAPTURE |
| P-④ | web 事件契约同步 | ✅ | EventType union=52+2 reserved；双端守护测试两侧 battery 常绿（28.B prep） |
| P-⑤ | 意图/路由/注册契约 | ✅ | IntentResult/RouterDecision/agent-registry v1 冻结+契约测试；registry fail-closed 启动校验 |
| P-⑥ | QA 权威切片（M1） | ✅ | insurance_qa 真实路由（D4）；AnswerContext 审计+幻觉结构性为零（场景 E 常驻） |
| P-⑦ | product_qa 灰度就绪（M2） | ✅ 代码就绪 / ⬜ 未灰度 | flag 默认 OFF；开启+流量校准=运营动作 |
| P-⑧ | live shadow 一致性数据 | ⬜ | 样本薄；legacy annotate 覆盖率缺口（既有 live 记录 legacy_intent 全 None）；HD-1 阈值未裁定 |
| P-⑨ | planning 行为单元（M3/28.D） | ⬜ 未实施 | insurance_plan/modify 仍走 legacy chat agent；E1 字节级等价依赖它先行 |
| P-⑩ | 观测告警线 + 切换日观测包 | ⬜ | checklist O-7/O-8 待定线 |
| P-⑪ | demo 映射/chat 工具自选退役方案 | ⬜ | M4 内容；双路径测试覆盖要求已写入 ADR-025 §7 |

## 2. 分阶段就绪判定

| 阶段 | 判定 | 阻塞项 |
|---|---|---|
| M0 准备 | ✅ **完成**（本阶段+28.B prep：ADR 立案/B4 设计/黄金清单/契约同步/迁移清单） | 仅 ADR-025 批准动作 |
| M1 QA 权威 | ✅ 已达成（运行中） | — |
| M2 product 灰度 | 🟡 **可启动**（代码/契约/审计全就绪） | 建议：灰度开启与 P-⑧ 数据积累并行；回滚演练（checklist B-4）先行 |
| M3 planning 切片 | 🔴 **不可开工** | P-①批准 → P-②实现+基线（E1 前提）→ P-⑨ 实施；prompts planning 段冻结令生效 |
| M4 全量权威 | 🔴 不可开工 | M2+M3 全绿 + P-⑧阈值裁定 + P-⑩告警线 + 退役方案（P-⑪） |

## 3. STOP 规则核验（本阶段执行中）

- 需要**修改既有 ADR**？——否。ADR-025 为**新建**（spec 明令），PROPOSED
  状态待批；ADR-019..024 零改动。
- 需要**架构调整**？——否。四件交付物全部 docs；无代码、无 schema、
  无契约变更。
- 需要**改变生产路径**？——否。runtime/** 本阶段零触碰（git status
  复核）；所有 flag/权威状态与阶段起点完全一致。
- 其余禁项（orchestrator/workflow/artifact lifecycle/approval/权威切换）
  ——零触碰。

**结论：本阶段无 STOP 触发；STOP 面前移至 M3/M4 开工条件上（§2 红区）。**

## 4. 与 28.B readiness audit（前次）的差异对账

前次 NOT READY 五阻塞：B-1 web 契约（✅ 已解，28.B prep）；B-2 B4 门
（🟡 设计完成，实现待授权）；B-3 ADR-025（🟡 立案完成，批准待所有者）；
B-4 live 校准（⬜ 不变）；B-5 planning 目标（⬜ 不变）。**两项半解**，
进度与 checklist P-1..P-9 序列一致。

## 5. 建议下一步（按序）

1. **所有者裁决 ADR-025**（批准/修改；连同 M2 灰度授权）。
2. **实现 B4 门 + 采集 golden 基线**（E2 案可即刻采；E1 案待 M3 前
   prompts 冻结后采）。
3. **M2 灰度**：`INSURANCE_AGENT_PRODUCT_QA_SLICE=1` + 服务器重启 +
   回滚演练 + 校准节奏（checklist S-2/S-3、B-4、O-8）。
4. M3 前置齐后进入 28.D（planning 行为单元）。

**STOP — 准备基础完成（ADR/B4 设计/黄金清单/就绪审计四件套）；权威
未切换、生产路径未动；等待 ADR-025 批准与下一步授权。**
