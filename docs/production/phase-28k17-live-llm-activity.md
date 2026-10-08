# Phase 28.K.17 — Consumer Live LLM Activity Implementation（Option A）

Date: 2026-09-27 · 纯前端实现（授权范围逐字遵守：仅 3 源文件+测试）。

## 1. Status

```text
COMPLETE
```

## 2. Files Changed

```text
web/src/state/runReducer.ts（RunUiState.lastDeltaAt:number|null[epoch
  ms]；agent_stream_delta 分支首行 Date.now() 打点——内容语义字节级
  不变）
web/src/components/chat/AgentActivity.tsx（DELTA_FRESH_MS=2000 常量·
  GENERATION_COPY="正在生成回答"·useDeltaFresh[到达后恰好一次过期
  重渲·无进度模拟]·Case A-D 组合）
测试：runReducer.test.ts(+2)·AgentActivity.test.tsx(+7 含 beforeAll
  scrollTo stub[jsdom 缺失])
```

## 3-6. Architecture / Delta→lastDeltaAt / Heartbeat 交互 / 优先级

```text
架构：零 backend/EventBus/SSE/事件词汇/schema 改动；E-3 单一事件
  映射未动（generation 行非事件映射=到达元数据派生，与心跳同类）；
  E-5 终态优先级原样（live=false 即整体关闭）。
Case A：live && now-lastDeltaAt<2000 → 「● 正在生成回答」（真实
  delta 到达驱动·data-testid=activity-generation）
Case B：events.length 变化 → 既有活动（心跳计时重置·既有）
Case C：无新事件且无新鲜 delta 且 ≥12s → K.13 心跳（原文案）
Case D：任何终态 → generation 行与心跳均不显示
计时器仅用于新鲜度判定（到期一次重渲）——无 setInterval 轮播/
无伪造进度（T1-T3 锁定）。
```

## 7. Security Verification

```text
reasoning=0 渲染（T6：reasoning delta→仅安全活动行·原文不入 DOM·
  无 stream-panel）·content 渲染字节级不变（T7/T8+既有套件）·
  raw delta/prompt/provider/model/tool/id=0（consumerDom FORBIDDEN 族
  +T6 断言）·未知事件 fail-closed 维持（E-3 既有）
```

## 8. Tests

```text
T1 delta 激活活性行（精确文案）✓ T2 新鲜 delta 压制心跳 ✓
T3 2s 过期→13s 真静默→原心跳 ✓ T4 新事件=既有活动+静默重置 ✓
T5 终态×4（completed/failed/needs_review/waiting）两行皆无 ✓
T6 reasoning 仅安全行·零文本 ✓ T7 content 面板+活性行 ✓
T8 混合流：reasoning 隐/content 显/行在 ✓
T9/T10=既有套件（unknown fail-closed·FORBIDDEN 扫描）全绿 ✓
runReducer：lastDeltaAt 初始 null·打点·刷新·不入 events[]·内容
  缓冲不变（+2）✓
```

## 9. Regression

```text
web **236 passed + 2 skipped**（=227+9）· TypeScript clean
backend 零改动（未运行——无后端 delta；沿用 794+2 基线）
```

## 10. Manual Verification（jsdom 等价·无 REAL_USER/无 synthetic）

```text
Scenario A 短答：已理解→（content delta 短暂活性行）→完成 ✓（T1/T7）
Scenario B 长生成：已理解→●正在生成回答（delta 驱动）→content 流
  面板→完成 ✓（T2/T7/T8）
Scenario C 静默：>2s 无 delta→活性行消失；≥12s 无事件→原心跳 ✓（T3）
```

## 11. Before / After UX

```text
Before:  已理解你的问题
         ● 正在为你分析        ←（40s 静止·仅事件驱动）
After:   已理解你的问题
         ● 正在生成回答        ←（真实 agent_stream_delta 到达驱动·<2s
                                 新鲜度；真静默 12s 才回落心跳；终态即灭）
```

## 12. Known Limitations

```text
①freshness=2s 窗口：delta 间隔 >2s 的慢流派会在行与心跳间闪烁
  （可后续调参；保守取值）
②agent-loop 之外的路径（QA 切片生成）无 agent_stream_delta——该路径
  仍只有 K.13 心跳（K.16 已记录；QA 切片流式=后端改动·未授权）
③elapsed「已用时」显示未实施（spec 列为可选）
```
