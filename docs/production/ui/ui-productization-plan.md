# UI Productization Plan — Insurance Agent UI V0.1 (Phase 27.5-1 design, not implemented)

## Information Architecture (V0.1)

```
Home(默认:Case Dashboard)
 |
 +-- Cases(试点主入口:case 列表 + 状态[待审/已批/已驳/草稿] + Run 状态)
 |    |
 |    +-- Case Detail = Review Workspace(主文档布局,单页纵向)
 |         ├── Header:客户画像摘要 + 审核状态徽章 + 计时器
 |         ├── 1 Requirement(需求清单)
 |         ├── 2 Risk(风险×已有保障×缺口金额)
 |         ├── 3 Coverage Gap
 |         ├── 4 Solution
 |         ├── 5 Recommendation(primary/not-recommended/uncertainty,
 |         │      业务状态如实呈现:INCOMPLETE_EVIDENCE ≠ 错误)
 |         ├── 6 Evidence(逐推荐:结论→证据引用→原文预览;链条断点
 |         │      高亮"NEEDS_REVIEW")
 |         ├── 7 Report(渲染视图 + 导出)
 |         └── 8 Review Bar(底部常驻:8 节快速判定 + 批准/驳回
 |                + 必填意见 + 自动 review_start/end 时间戳)
 |
 +-- Review Queue(待审优先列表:来自 /api/projects/{id}/approvals,
 |      只读呈现后端状态;审批动作回写后端)
 |
 +-- Pilot Dashboard(只读:健康、待审/已批/已驳计数、审查完成度
 |      n/12;不做成本/队列——等后端 API 化)
 |
 +-- Chat(现有 chat-first 模式保留为顾问对话入口)
 |
 +-- Developer Console(现有 Developer Mode 降级为调试视图,
        保留 Pipeline/Eval/Trace/Artifact Inspector)
```

复用原则:不新建框架,沿用现有 React/Vite/Tailwind 风格、
client.ts 模式、SSE hook 与 reducer;新增页面均为后端数据的
只读投影 + 两个回写动作(approve/reject 走既有端点)。

## Implementation order(下一阶段最小路径,5 步)

1. **Review Queue 页**(纯只读):消费现有 approvals 端点 → 列
   表 + 状态徽章。无后端改动。
2. **Review Workspace(Case Detail)**:拼装现有 cases/runs/
   artifacts 端点为主文档视图(含 Evidence 拼装:recommendation
   provenance refs → knowledge-evidence 原文)。无后端改动。
3. **Review Bar + Approval 操作**:8 节判定 + approve/reject(
   走既有端点,意见必填;后端若无意见字段则最小补齐——需另授
   权的 API 小改)+ 自动计时。
4. **反馈落盘**:审查表单导出 JSON/文件到 pilot evidence 目录
   (与 Runtime 状态隔离);若要入库需新增只读资源端点(单独
   授权评估)。
5. **Pilot Dashboard**:cases/approvals 前端聚合只读计数。

每步独立可验收;1–2 步零后端改动即可显著解除 B1/B2 阻塞。

## 验收口径(下一阶段)

Owner 能全程在 UI 完成:打开待审 Case → 一屏读完八节分析 →
点开任一推荐结论的证据原文 → 点批准/驳回并留意见 → 系统
自动记录审查用时 → Dashboard 看到审查进度 n/12。全程不接触
markdown 表单、不使用 curl。
