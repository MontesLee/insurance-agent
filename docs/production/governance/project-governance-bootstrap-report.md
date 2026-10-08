# Project Governance Bootstrap Report — North Star & Architecture Guardrails

Date: 2026-09-24 · Phase 28.1（治理引导）。本任务零业务代码改动。

## 1. Created files

| 文件 | 性质 | 作用 |
|---|---|---|
| `docs/PROJECT_VISION.md` | 新建·产品契约 | 一句话定位、目标用户（普通保险消费者）、核心体验五步、第一阶段 Agent 边界（QA+Planning）、Anti Goals（禁演变为通用 chatbot/workflow 展示/dashboard 产品/eval 平台） |
| `docs/ARCHITECTURE_PRINCIPLES.md` | 新建·架构契约 | 六原则：Chat-first / Intent before Agent / Router owns routing only / Agent owns workflow / Insurance knowledge grounding / User-Developer Space separation |
| `docs/DEVELOPMENT_CHECKLIST.md` | 新建·流程 | 每阶段 Step 0 产品对齐（四问，答不上来不开工）→ Step 1 架构检查（复用运行时/孤立系统/ADR/四哨兵）→ Step 2 实施 → Step 3 验证 |
| `docs/production/governance/product-direction-audit.md` | 新建·基线审计 | 产品身份判定、真实用户旅程（存在 vs 设计）、五类漂移 P0×3/P1×9/P2×4 清单 |
| `.claude/commands/product-audit.md` | 新建·命令 | `/product-audit`：对照 Vision/Principles 审仓库（代码优先于文档），四哨兵漂移检测，与基线 diff，输出 P0/P1/P2 报告到 docs/production/governance/product-audit-YYYY-MM-DD.md，只读 |
| `docs/production/governance/project-governance-bootstrap-report.md` | 新建·本报告 | — |
| `CLAUDE.md` | 修改·追加 | 新增 "Project Identity & Architecture Guardrails" 节：项目身份、Before Any Implementation 四问（不确定即 STOP）、Before Large Feature 必读清单；既有会话协议全部保留 |

## 2. Existing architecture understanding（判断依据）

基于本会话五次只读审计（27.7.7 workspace IA → 27.7.8 review 架构 →
27.8 review center → 27.9 chat-first → 28.0 迁移计划）的 file:line 证据，
本次仅补读 AGENTS.md/CLAUDE.md/docs 结构复核：

- **真实系统**= 治理优先的确定性保险规划管线（8 阶段 9 技能 YAML 单图 +
  eval 唯一门 + repair 环 + Review Card/审批闭环）+ 一个真实单 Agent
  对话前端（默认 chatMode=agent，live glm 已配置，意图枚举在 prompt 内，
  每轮新 case）+ 一套未接生产路径的 4 专家多 Agent 层（仅 demo/benchmark/
  审批恢复）。三条执行路径已共享 `orch._execute_stage` 内核——割裂在
  身份层（Intent/Router/Registry）与生命周期层，不在执行层。
- **知识层**：KnowledgeService（provider→governance→evidence，fail-closed）
  已生产形态；WeKnora live 纯检索 + R1-R9 治理 + PG 注册表；**但证据从不
  进入 LLM 上下文、答案文本零代码门禁**（28.0 §7 结构性缺陷）；Product
  Catalog 仅 12 个 demo 产品，等待期/免责/健康告知数据与 schema 双缺。
- **UI**：默认入口 Chat ✅；但产物交付不完整、review 不回链 chat、无 URL
  路由、按 case 发起 run 的唯一 UI 在 Developer Mode、dev 标记泄漏用户面。
- **治理存量**：ADR-008..018 生效（004 确定性评估 / 017 治理分离 / 018
  反馈=证据）；ADR-019..024 已提案未批准（28.0）。AGENTS.md 管 Skill 层。

## 3. Identified risks（基线漂移清单，详见 product-direction-audit.md §3）

- **P0×3**：①多 Agent 层不在生产路径（双/三世界割裂）②LLM 无证据输出
  保险知识（结构性：证据不进上下文+答案零门禁）③产品事实问答结构性
  不可答（目录数据+schema 双缺）。
- **P1×9**：业务发起入口错位于 Developer Mode、产物交付不完整、review
  不回链 chat、工具边界不一致（chat 全局 vs 专家裁剪）、7 个运行追踪
  存储、意图+工作流混在同一 prompt、workflow 归属悬空、LLMGateway
  未接线、空间无门禁+dev 标记泄漏。
- **P2×4**：URL 路由缺失、demo/agent 双模并存认知、lexical 重排丢语义
  质量、GAP 注记上脸。
- 全部 P0 均在 28.0 路线图（28.B/28.C）覆盖内；本治理机制的作用是把
  它们变成**周期复查、只收敛不增长**的基线。

## 4. New governance rules（生效方式）

1. **CLAUDE.md**（每会话必读）现在携带项目身份 + 实现前四问（不确定即
   STOP）+ 大功能必读清单 → 对所有未来 Claude Code 会话默认生效。
2. **六原则**是硬约束：违反需显式 ADR 豁免，不允许默许；与 ADR-004/
   017/018、AGENTS.md 叠加生效、互不重复。
3. **/product-audit**（`.claude/commands/product-audit.md`）= 周期对齐
   审计：代码优先于文档、四哨兵（developer 功能变用户流 / 重复运行时 /
   LLM 无证据 / workflow 泄漏）、与基线 diff、P0/P1/P2 报告落盘、只读。
4. **DEVELOPMENT_CHECKLIST** = 每阶段 Step 0-3 关卡；Step 0 四问答不上
   来不开工。

## 5. How future Claude Code sessions should use them

- **会话开始**：CLAUDE.md（含新 guardrails）→ .agent/current-task.md →
  checkpoint.md → 阶段文档；大功能先读 Vision/Principles/相关 ADR。
- **实现前**：过 CLAUDE.md 四问 + DEVELOPMENT_CHECKLIST Step 0/1（四哨兵
  自查）；触碰 ADR-019..024 主题（运行时统一/意图层/Registry/grounding/
  目录边界/血缘）时先确认对应 ADR 已批准。
- **阶段收尾**：DEVELOPMENT_CHECKLIST Step 3 + 更新漂移基线状态列；
  方向存疑或大合并后运行 `/product-audit` 并归档报告。
- **争议裁决**：Vision（为什么）> Principles（怎么建）> ADR（具体决策）
  > 阶段文档；改 Vision/Principles 本身需要明确产品决策，不得顺手改。

## 6. Remaining questions（待产品负责人决策）

1. **ADR-019..024 批准**：治理文档已把 28.0 提案当作"设计不是许可"，
   批准/裁剪仍待决策（决定 P0 修复的开工顺序）。
2. **P0-③ 目录数据工程**：schema 补字段（waiting_period/exclusions/
   health_declaration）+ 真实产品数据来源——是数据/商务问题，工程侧
   只能 fail-closed 等料。
3. **KB 语料运营**：pilot 仅 10 份监管文本；QA Agent 上线前的语料覆盖
   目标与责任人。
4. **QA 答案的审核策略**：qa-answer 是否入 Review/抽检面（当前 Review
   面向规划产物；建议抽检不入审批，待确认）。
5. **dense 检索决策**：保 lexical 确定性 or 启 dense（影响 WeKnora 语义
   质量利用率）。
6. **本任务产物纳入版本控制**：CLAUDE.md/docs/**/.claude/** 与既有未提交
   树（27.7.6-D..F→28.0）一起等待 commit 授权。

## 7. Phase 7 验证声明

`git status`/`git diff` 复核：本任务改动 = `CLAUDE.md`（追加节）+
`docs/**`（4 新文件+本报告）+ `.claude/**`（1 命令）——全部在允许清单
内。工作树中其余修改（runtime/server.py、tests/、web/、start-human-
session.bat 等）为 27.7.6-D..F 与 27.7.7 的**既有未提交工作**，本任务
零触碰。另按 CLAUDE.md 会话协议更新 `.agent/`（会话簿记，非业务代码）。
