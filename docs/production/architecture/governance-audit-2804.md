# Governance Audit — Phase 28.0.4 Freeze Report

Date: 2026-09-25 · 零代码改动（runtime/web/backend/schema/agent/ADR 内容
均未触碰；ADR 六份 PROPOSED 文件原样）。

## 1. 新增文件

| 文件 | 内容 |
|---|---|
| `docs/production/architecture/PRODUCT_VISION.md` | **权威产品基线 v1.0（FROZEN）**：Product Identity（不是：后台系统/Dashboard/人工审核工具/通用 chatbot；是：Chat-first Insurance Agent Platform）+ 唯一业务入口链（Message→Conversation→Intent→Router→Agent→Workflow→Evidence-grounded Result→Artifact Delivery）+ 三空间边界（User：Chat 唯一入口/四类业务/输出/禁见清单；Operator：Review Center+Approval+Feedback=升级处理非入口；Developer：Dashboard/Dev Mode/Eval/Trace/inspection）+ Anti-Goals |
| `docs/production/architecture/ARCHITECTURE_PRINCIPLES.md` | **权威架构基线 v1.0（FROZEN）六原则**：①Chat is the Product Surface ②Intent ≠ Prompt（schema+rules+runtime event；prompt 仅辅助）③Router is Deterministic（lookup/validate/dispatch；禁 LLM 选 Agent、禁 Agent 私联 Agent；Router 决定交给谁/Agent 决定怎么做）④Insurance Fact Requires Evidence（条款/责任/等待期/免责/保额←Catalog 或 WeKnora；禁模型补全）⑤One Runtime（禁平行 workflow engine/artifact storage/agent 执行模型；复用 orchestrator+event+artifact）⑥Human Review is Escalation（人不是默认审核者） |
| `docs/templates/feature-proposal-template.md` | 新功能提案模板（Feature/User Problem/Space/Chat Entry/Agent/Intent/Router/Workflow/Artifact/Evidence Source/ADR Impact/Risk 十二行，含填写守则） |

## 2. 修改文件

| 文件 | 修改 |
|---|---|
| `CLAUDE.md` | Guardrails 节升级 v2：**Product Alignment Check**（四问：是否服务 Chat UI/属于哪个 Space/是否新增 Agent·Router·Workflow·Artifact→查 ADR/漂移）+ **Architecture Drift Detection**（改码前查 git diff；orchestrator/agent execution/artifact lifecycle 被改→必须报 "Architecture Impact Detected" 并回查 ADR）+ **Forbidden Actions**（六禁：新 Agent Runtime/新 Workflow Engine/绕 Router 调 Agent/prompt 当业务规则源/无证据造保险事实/Developer UI 暴露给 User）+ 链接改指权威文档 + 模板要求。既有会话协议全部保留 |
| `.claude/commands/product-audit.md` | 命令升 v2：输出契约固化为 **PASS/FAIL 六节 + Changed ADR files + Final GREEN/WARNING/BLOCKED**（判级规则成文：FORBIDDEN 模式确认或 P0 回归=BLOCKED；已知路线内缺口=WARNING；全绿=GREEN）；保留基线 diff 机制；读单改指权威文档 |
| `docs/PROJECT_VISION.md` | **降为导航桩**（指向权威版；保留路径仅为兼容既有引用；28.1 有效内容已全部并入权威版） |
| `docs/ARCHITECTURE_PRINCIPLES.md` | 同上（28.1 六原则全部并入：分工条款→权威版 P3，空间分离→PRODUCT_VISION §Space Boundary） |

## 3. 规则冲突检查（含既有的 CLAUDE.md / AGENTS.md）

1. **与 Phase 28.1 的重复（本阶段最大冲突，已解决）**：28.1 曾创建
   `docs/PROJECT_VISION.md` + `docs/ARCHITECTURE_PRINCIPLES.md`；本阶段
   规格要求在 `docs/production/architecture/` 建同类文件——若两处并存
   全文即双源真理（恰是本治理要防的漂移）。**解法：新路径=唯一权威
   （FROZEN v1.0），旧路径=导航桩**；CLAUDE.md/命令/Checklist 引用已
   改指权威版。28.1 内容零丢失（全部并入）。
2. **`.commands/` 路径解释**：规格写 `.commands/product-audit.md`；
   Claude Code 命令的功能目录是 **`.claude/commands/`**（28.1 已有
   命令在册并在本会话技能列表生效）。按功能意图落笔：升级
   `.claude/commands/product-audit.md` 至 v2，**未**新建根目录
   `.commands/`（避免死文件）。如所有者确需根目录副本，一句话即可补。
3. **与 AGENTS.md**：无冲突、零重复——AGENTS.md 管 Skill 层（命名/
   分层/确定性/eval 纪律/禁造事实），本基线管产品与架构层；唯一交叠
   点"禁止创造事实"为刻意同源（Principle 4 上承 AGENTS.md §9 与
   ADR-005）。
4. **与既有 ADR**：无冲突。Principle 3/4/5/6 分别上承 ADR-019..024
   （PROPOSED）、ADR-005/022 裁决、28.0 §11 canonical 核、ADR-017 +
   27.7.8 升级方向。注意：**原则先于 ADR 批准生效**——若 019..024
   最终被裁剪，需回看 Principle 2/3 的实现措辞（原则本身仍成立，
   因其描述的是目标态而非具体实现）。
5. **与 CLAUDE.md 既有内容**：会话协议/检查点协议未动；28.1 的四问
   被新四问**吸收**（原第 2/4 问并入新问 3/4 与 Forbidden Actions，
   无语义丢失）。

## 4. 后续开发如何使用

1. **每个任务开始**：CLAUDE.md §Product Alignment Check 四问（答不上
   来→STOP 澄清）；新功能先填 `docs/templates/feature-proposal-template.md`。
2. **每次改码前**：§Architecture Drift Detection——git diff 触及
   orchestrator/agent execution/artifact lifecycle → 主动报
   "Architecture Impact Detected" 并回查 ADR。
3. **每阶段**：`docs/DEVELOPMENT_CHECKLIST.md` Step 0-3（阶段视角）与
   模板（功能视角）配合。
4. **周期/大合并后**：`/product-audit`——输出六节 PASS/FAIL + Final
   GREEN/WARNING/BLOCKED，报告落 `docs/production/governance/
   product-audit-YYYY-MM-DD.md`；BLOCKED=立即停下升级给所有者。
5. **裁决顺序**：PRODUCT_VISION（为什么）> ARCHITECTURE_PRINCIPLES
   （怎么建）> ADR（具体决策）> 阶段文档。两份 FROZEN 基线的修改
   需所有者明确决策。
6. **禁止行为清单**（六禁）由 CLAUDE.md 常驻——任何会话违反即架构
   事故，不因"局部合理"豁免；豁免只能走 ADR。

## 5. 残留事项

- HD-1..8（Phase 28.0.3 人类决策）仍待所有者裁定——治理冻结不改变
  该队列，反而强化之（Principle 2/3/4 的实现细节系于 019..024 批准）。
- `docs/DEVELOPMENT_CHECKLIST.md` 与 bootstrap report 中的旧路径引用
  仍指向 28.1 文件——导航桩保证不断链，后续顺手更新即可（非必须）。
- 根目录 `.commands/` 未建（见 §3.2），如需请示。

**STOP — 未修改任何代码与 ADR 内容。等待下一阶段授权。**
