# ADR-023 — Chat Artifact Experience

## Status

**APPROVED (2026-09-25, Phase 28.0.5 owner ruling — 保持原文，无修改）**.
裁定范围：**Artifact v1 = Markdown default**；**HTML / PDF = future**
（v1 不含 HTML 模板交付——本文 Decision §2 的 HTML/PDF 条目自 v1 起视为
future scope，按 Migration strategy 逐步解锁；渲染器唯一性与 L1 层级
规则自 v1 即生效）。弱依赖 ADR-021（已 APPROVED）；深链依赖 URL 路由
（28.G）。

## Context

现状（代码实证）：9 类 artifact 全 JSON 规范信封；仅 insurance-report
带 rendered_report（Markdown 模板渲染，无 LLM）。交付碎片化：同一
报告在 **4 处重复取数渲染**（chat ArtifactCard 弹窗 / Conversation.
ReportBlock / Developer ArtifactInspector / ReviewWorkspace）；chat 只露
最终报告一张卡；**无 HTML**（仅 tmp 一次性脚本）、**无 PDF**（全库零）、
**无导出端点**（无 Content-Disposition 路由）、**无 artifact 深链**；
ArtifactCard 首屏泄漏 `artifactType · run {id}`（27.8 漂移清单）。

## Problem

"答案+报告"是产品核心交付（PROJECT_VISION Core Experience 第 5 步），
但今天报告出不了 Chat 的弹窗、出不了系统、带不走；且四套渲染器已经开始
漂移（同一 rendered_report 各处自行取数解析）。

## Decision

**用户面输出 = Text + Artifact**：

1. **统一渲染**：每类 artifact 恰一个 human-readable renderer（统一
   ArtifactViewer 收编 4 处重复）；raw JSON 查看器仅 Developer Space。
   同一 artifact 不允许存在多套互相漂移的 renderer（漂移哨兵：以
   渲染器唯一性断言执行）。
2. **格式矩阵**：markdown（现有 rendered_report）✅ 保留；**HTML** =
   确定性模板渲染（复用 report 引擎模板体系，后端或前端皆可，产物必须
   字节可回归）；**PDF** = 浏览器打印样式优先（print stylesheet +
   打印按钮），服务端 PDF 生成（weasyprint 等）需引入重依赖——**另案
   决策，默认不做**；JSON = Developer Space raw 视图；text = chat 回答。
3. **导出**：`GET /api/runs/{id}/artifacts/{type}?format=md|html`
   （Content-Disposition 下载；PDF 经浏览器打印实现，不发文件）。
4. **深链**：artifact 可寻址 URL（依赖 URL 路由）；分享=链接。
5. **信息层级**：技术 ID 不作为用户主内容（L1 无内部标识；id/枚举/
   payload 折入 L4 或 Developer Space——沿 27.8 标准）。

## Alternatives considered

- **A. 维持 4 处渲染（现状）**——否决：漂移已发生（各自取数解析）；
  每改报告结构要改四处。
- **B. 服务端 PDF 立即引入（weasyprint/wkhtmltopdf）**——否决：重
  依赖+运维面扩大，当前无真实需求信号；浏览器打印满足"带得走"。
- **C. 只做 markdown、不做 HTML/导出**——否决：报告交付是核心体验
  （Vision），markdown 弹窗不构成"交付"。

## Consequences

- 正：报告可看/可带走/可分享；渲染唯一性可测试；dev/user 空间边界
  在交付层落地。
- 负：渲染器收敛是一次跨 4 组件重构（回归面大）；HTML 模板进入
  字节回归基线（成本）；深链被 URL 路由阻塞（顺序约束）。
- 合规：不动 artifact store/registry/契约；不动 ADR-017。

## Implementation boundary

- 修改：web 渲染收敛（1+N：1 个 human renderer + 1 个 raw viewer）；
   新增导出端点（**增量**，不动既有 artifact 读取契约）。
- 冻结：artifact 信封/注册表/血缘；contracts/*.schema.json；Review
  Workspace 的 L4 raw 能力（保留不删）。
- 顺序约束：深链依赖 URL 路由（28.G/27.8-A）；主体收敛可在 28.B 后
  任意点实施（28.F）。

## Migration strategy

先收敛渲染器（纯前端，行为等价：渲染输出快照对比）→ 导出端点 →
HTML 模板 → 打印样式 → 深链（随 URL 路由）。每步独立可回退。

## Validation criteria

- 渲染器唯一性断言（同一 artifact 全站仅一个 human 渲染实现）。
- 导出契约测试（Content-Type/Disposition/格式正确性）。
- L1 层级断言（用户面首屏无 artifactType/run id 等内部标识）。
- 渲染快照回归（报告结构变更时四旧表面→一新表面的等价验证）。
- 全部既有前端基线（vitest 144 + tsc）绿。
