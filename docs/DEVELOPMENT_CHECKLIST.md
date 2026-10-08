# DEVELOPMENT_CHECKLIST — 每阶段开工四步

> 每个实现 Phase 开始前按序走完 Step 0/1；跳步是方向漂移的主要来源。
> 配套：docs/PROJECT_VISION.md · docs/ARCHITECTURE_PRINCIPLES.md ·
> CLAUDE.md（Project Identity & Architecture Guardrails）·
> docs/production/governance/product-direction-audit.md（漂移基线）。

## Step 0 — Product Alignment（先答问题，再写代码）

必须能用一两句话回答（写进阶段文档开头）：

- **用户价值是什么？**（普通保险消费者得到了什么）
- **是否增强 Chat experience？**（业务能力是否从 Chat 可用；若暂不可
  用，本阶段是否明确为其铺路且不设置新障碍）
- **是否属于 User Space？**（若纯属内部能力：它服务于哪条用户价值链，
  何时可见）
- **是否符合 Agent ownership？**（能力挂在哪个 Agent 名下；不挂 Agent
  的"游离能力"需要显式豁免理由）

**任一问答不上来 → 停下来澄清，不开工。** 明确的反例（直接否决）：
只为演示跑通的 Agent、只在 Developer 页出现的业务功能、与 Chat 无关的
新看板。

## Step 1 — Architecture Check

- **复用已有 Runtime？**——执行走 canonical 核（orchestrator 脊柱），
  产物走唯一 artifact 写入路径，事件走 EventBus/SSE，知识走
  KnowledgeService。新建平行系统 = 违反 Principle 4，需 ADR 豁免。
- **是否产生新的孤立系统？**——新的运行追踪存储/产物目录/检索协议/
  渲染器都要过问：能否挂到既有 7 类存储与唯一渲染器策略上（收敛，
  不再增殖）。
- **是否违反 ADR？**——ADR-004（确定性评估唯一门，LLM 不入 eval）、
  ADR-017（治理无控制耦合，审批冻结）、ADR-018（反馈=证据）；涉及
  运行时统一/意图层/Registry/grounding/目录边界/血缘的改动对齐
  ADR-019..024（未批准前是设计不是许可）。
- **漂移哨兵自查**——本改动是否触碰四哨兵：developer 功能变用户流？
  重复运行时？LLM 无证据？workflow 泄漏到 router/会话层？触碰即在本
  阶段文档记录缓解措施。

## Step 2 — Implementation

- 遵循 AGENTS.md（命名/Skill 分层/确定性优先/eval 纪律/禁止创造事实）。
- 新对外契约（schema/API/事件类型）先写契约再写实现，并补契约测试。
- 行为等价优先：重构路径必须有前后等价回归门（参照 28.0 §19）。

## Step 3 — Validation

- 相关测试/eval 全绿（基线：backend tests/runtime 599/0；web vitest
  144 + tsc clean；knowledge 离线 50+28；business HG 门；agent
  benchmark）。
- 负向自检：注入故障必须报红，清理后复绿（AGENTS.md §6）。
- 回看 Step 0 的答案：交付物是否兑现了声称的用户价值；漂移基线中
  对应项是否收敛（必要时更新 product-direction-audit.md 的状态列）。
- 更新阶段文档 + .agent/ 记录；重大方向变化触发 /product-audit。
