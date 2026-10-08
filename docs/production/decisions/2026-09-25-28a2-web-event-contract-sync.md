# Decision Record — intent_classified web 事件契约同步（28.A-2 期内 BLOCKED_FOR_IMPLEMENTATION）

Date: 2026-09-25 · Phase: 28.A-2 · 机制：28.A-2 spec "Automatic Decision
Handling"（发现范围/归属冲突 → 记录 → 标记 BLOCKED_FOR_IMPLEMENTATION →
继续安全任务）。

## 发现（What）

ADR-019 验证门与 implementation boundary 要求 `intent_classified` 事件
词汇**双端同步**（后端 EVENT_TYPES **与** web 事件契约，"缺一即红"；
28.0.1 隐耦 #3：只加后端不加 web 契约 → 前端 runReducer 对表外事件
设计性静默忽略，无告警漂移）。现状：后端词汇已含
`intent_classified`（runtime/events.py:67，28.A-1 落地）；web 侧契约
未加（28.A-1 已知限制 #4，按 spec"未来展示"显式缓议）。

## 冲突（Why blocked）

28.A-2 spec 的 git 允许清单为 `runtime/intent/* · runtime/router.py ·
tests · docs`——**web/** 不在允许路径内。补齐 web 契约属前端改动，
本阶段无授权。

## 影响评估（Impact）

- 低：shadow 阶段 intent_classified 仅用于审计/调试，前端不消费该类型
  即无用户可见损失；静默忽略是设计行为（不是数据损坏）。
- 风险敞口：若长期不同步，28.B/28.C 切权威后 UI 将继续吞并意图事件
  （无报错）——必须在切权威前闭合。

## 处置（Decision）

**BLOCKED_FOR_IMPLEMENTATION（限本阶段）**。解锁条件（任一）：

1. 后续阶段授权含 web/** 改动（28.G 空间分离或专门的事件契约同步小改）；
2. 28.B（router 权威化）开工时作为其前置项一并处理。

届时动作：web 事件契约加 `intent_classified` 类型 + timeline 渲染策略
（建议 L4 折叠/开发者可见层级）+ 双端契约测试（表内类型枚举同步断言）。

## 关联

- ADR-019 implementation boundary（双端同步条款）
- phase-28-implementation-gates.md ADR-019 验证门（"缺一即红"）
- 28.A-1 报告已知限制 #4 · 28.0.1 隐耦 #3
