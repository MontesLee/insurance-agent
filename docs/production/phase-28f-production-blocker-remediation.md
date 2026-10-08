# Phase 28.F Production Blocker Remediation 报告

Date: 2026-09-26 · F-0 基线审计 → F-1 B-03 修复（实现+验证）→ F-2
B-02 设计审计（零实现）→ STOP。

## 1. Baseline（F-0 PASS）

```text
git：22 tracked-modified（28 系列 span）+ 既有 untracked —— 与
     Final Audit 基线逐项一致（无误认）
Backend: 734/734（BATTERY_F0，本阶段新鲜复跑，与审计树一致）
Web: 207+2（新鲜）· TS: clean
B4 17/17 · M4 9/9 · M3 7/7 · E-2..E-7 套件全绿（含于上述）
B-01..B-04 复核：全部仍然成立（.env 仅 LLM_*；chats.py 无 owner；
seedChats 在案；ADR-024 未决）
```

## 2. F-1 B-03 Root Cause

**A（UI seed）**：`web/src/state/chatState.ts` `loadChats()` 于
存储缺失/版本不符/损坏三条回退路径一律 `seedChats()` → 每个新浏览器
被注入 3 条预置"历史"（含罐头回复与 📄 预览）。路径：Browser →
loadChats（localStorage 空）→ seedChats → reducer 初态 → 渲染为
"我的对话"。不涉及后端。

## 3. F-1 B-03 Fix（minimal frontend change）

`loadChats()` 三条回退全部改为 `[]`（新用户=空态；空画布=ChatLayout
既有一个空"新对话"→ WelcomeScreen，非历史）。`seedChats` **导出保留**
（Developer/Demo 能力不删；消费者路径源级断言永不调用）。零
runtime/契约/后端改动。

## 4. F-1 Validation（新契约测试）

```text
chatState.test：新用户=[] ✓ 损坏存储=[]（无 demo 回退）✓
  seedChats 能力保留+loadChats 源级不引用 ✓ 版本信封往返 ✓
  （旧两断言"首载/损坏即种子"=缺陷契约，按整改要求更新）
seedRegression.test（新增 5）：
  Case A 新消费者零种子/零删除钮/零罐头文案 ✓
  Case B 真实会话保留 ✓ Case C demo 能力存活且隔离 ✓
  Case D 刷新不凭空生史 ✓ Case E 重开同 ✓
Consumer DOM leakage（既有套件）维持 ✓ → fake conversation/artifact/
progress/completion/success = 0
```

## 5. F-1 Regression

```text
Web: 213 passed + 2 skipped（207 基线 → +6 净增）· TS: clean
Backend: 734/734（BATTERY_F0；F-1 零后端文件改动，见 §Git）
Git diff 审计：本阶段改动= chatState.ts + chatState.test.ts +
新增 seedRegression.test.tsx —— 仅 B-03 文件；runtime/router/
intent/grounding/artifact contract/ADR/Vision 零触碰 ✓
```

## 6. F-2 B-02 Current State（详见独立设计文档）

消费者=**匿名**（无身份/会话；localStorage id≠authorization）；
chats=内存 V0.1 无 owner 字段（runtime/agent/chats.py 实读）；全部
消费者读端点（chat/run/events/artifacts/stream）**无
authn/authz/ownership**；id=hex8（小空间，无 rate limit）。

## 7. Ownership Model（现状 vs 目标）

现状：无 Identity 层——对象仅凭"知道 id"可达（chat→run→artifact 有
结构包含，无授权主体）。目标三层分离：
Authentication（D-01′ 选型）→ Object Ownership（对象加 owner 字段，
**数据模型变更=STOP-6，需 Owner 授权**）→ Authorization（中心化
`_require_owner` 沿 chat→run→artifact 链）。

## 8. IDOR Threat Model（T1-T6）

跨主体读对话全文/挂流/事件/读下载报告/注入消息/hex8 枚举——单租户
loopback 下不成立为越权（唯一主体）；**多用户/公网全部成立**。详见
设计文档 §5。

## 9. Consumer Auth Options（不替 Owner 选择）

A 匿名+服务端 opaque 会话令牌（最低成本达 G-B02-1..7；需 owner 字段
授权）· B 认证消费者（最强；产品级）· C CONSUMER 角色（内部 beta 受邀
适用）。附响应语义（401/403/404）与 id 空间/限流子决策（D-API-1/2）。

## 10. Artifact Security

下载入口=GET /runs/{id}/artifacts/{type}，与读同源 → 修复在端点授权
层；AnswerContext 随 run 事件链覆盖。opaque artifact reference 可与
深链（D-05）一体化（token=owner 绑定+可撤销+不可枚举）——仅设计。

## 11. Deep Link Relationship

D-05 与 B-02 共享 opaque-reference 构建块；建议顺序：授权主干先行、
深链为其上封装（不实现）。

## 12. B-01 Status（本阶段仅确认）

```text
B-01 = BLOCKED（不变）：knowledge_provider=mock（Final Audit 事实
复核成立）。code READY / config 缺三变量 / credentials=Owner /
corpus=Phase-24 栈在位 / strict 决策待 Owner（HD-2=CONFIG_ONLY）。
未连接 WeKnora。
```

## 13. B-04 Status（决策隔离，不制定政策）

```text
D-GOV-1 retention · D-GOV-2 access · D-GOV-3 deletion ·
D-GOV-4 artifact deletion · D-GOV-5 trace/eval 遥测保留 ·
D-GOV-6 operator 访问边界 —— 全部 Owner Decision。
依赖方向：B-04 依赖 B-02 的 owner 锚点（非反向）。
```

## 14. Owner Decisions（本阶段汇总）

```text
D-01′ 消费者身份选型（A/B/C，设计文档 §6）
D-API-1 无权响应语义统一 · D-API-2 id 空间升级+限流
D-05′ opaque artifact reference 是否随授权主干立项
D-GOV-1..6（B-04）· D-02 HD-2 · D-03 REAL_USER（需 B-01..04 清障）
D-07 永久 Full Authority · D-08 commit · D-09 M5 清理（既有队列）
```

## 15. Required Next Phase（建议边界，不自动执行）

```text
F-3（若授权）：B-02 implementation —— 依 D-01′ 选型实现 identity +
owner 字段迁移 + _require_owner + G-B02-1..10 测试矩阵；
HD-2 配置（依 D-02）；REAL_USER（依 D-03，最后）。
```

## 16. Evidence Index

```text
F-0：git status/diff（22 项一致）· BATTERY_F0 输出 · web/tsc 新鲜运行
F-1：chatState.ts diff · seedRegression.test.tsx · chatState.test.ts
     更新块 · web 213+2 · tsc clean
F-2：runtime/agent/chats.py（实读）· server.py 端点签名（本会话）·
     docs/production/phase-28f-b02-consumer-data-isolation-design.md
全局：phase-28-final-production-readiness-audit.md（B-01..04 证据）
状态：REAL_USER=NOT ENABLED · Authority=UNCHANGED（默认 slices；
:8000 保持停止）· WeKnora=NOT CONNECTED
```
