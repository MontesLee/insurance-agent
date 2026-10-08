# Phase 28.G — Consumer Identity & Ownership Implementation 报告

Date: 2026-09-26 · 目标：**B-02 从设计 → Implementation + Automated
Evidence + PASS**。Owner 已决项（D-01′ 认证消费者 / D-API-1 统一 404 /
D-API-2 高熵+限流 / D-05′ 不透明引用）全部落地；三概念分离
（Identity ≠ Role ≠ Ownership）贯穿。

## 1. Status

```text
28.G STATUS: PASS（B-02 RESOLVED — 见 §2/§7/§8 回归数字）
```

## 2. B-02 Resolution

**B-02 = PASS**：认证主体 + 对象所有权 + 端点授权 + 统一 404 + 高熵
id + 限流 + 不透明引用全部实现，并以 15 项自动化隔离测试
（T1-T10 + 矩阵 + 不变量 + 兼容 + 枚举防护）证明。残留边界（如实）：
身份/所有权为**内存 V0.1 层**（与 ChatManager 同层——服务重启后对象
无主 → fail-closed 404；持久化属既有 PERSISTENCE 立项）；无登录产品
（Owner 已排除选择具体登录方案——CONSUMER key 机制为内部 beta 受邀
形态，符合"authenticated subject abstraction"最小实现）。

## 3. Identity

复用既有 auth 运行时（零第二 auth 平台）：`runtime/auth.py` 增
CONSUMER 角色（秩级 CONSUMER(1)<OPERATOR(2)<REVIEWER(3)<OWNER(4)，
既有包含关系不变）。主体=服务端从凭据解析：`consumer:<user>` /
`rbac:<user>`（`runtime/consumer_access.py` `resolve_subject`）。
前端存储的 key=**仅认证秘密**；whoami 决定主体（绝不信任客户端
owner 字段）。前端身份门（keys 模式 401 → 最小密钥门；退出清除当前
主体本地转录；local-dev 模式无门=冻结行为）。

## 4. Ownership

`Conversation.owner`（ChatManager 创建时绑定主体）→ `Run.owner`
（chat 路径继承 chat owner；demo 路径=创建者 rbac 主体）→
Artifact 经 Run 父链推导（run 端点 + 引用解析双路同查）。确定性
判定 `read_allowed(ident, owner)`：internal（≥OPERATOR 值班读全量，
O-7 不变）> 主体==owner > 其余 404；匿名+keys=401；无 key dev=
冻结全放行（ownerless）。id 熵：chat/run 新 id hex16（内部 run_id
保留为运行时身份；消费者面经不透明引用）。

## 5. API Boundary（保护清单 + 404 语义）

```text
守卫端点（限流+401+所有权+统一404"not found"）：
GET /api/chats/{id} · POST /api/chats/{id}/messages[/stream]（防注入：
  未知 id 绑定请求者主体而非写入他人）· GET /api/runs/{id} ·
  /events · /stream · /artifacts · /artifacts/{type}
新增（additive）：GET /api/consumer/whoami ·
  GET /api/runs/{id}/artifact-refs/{type}（发行不透明引用）·
  GET /api/consumer/artifacts/{ref}（解析+所有权复检）
补门：POST /api/runs=OPERATOR（E-6 漏项，demo=内部面）
不变：review-card=REVIEWER · approvals/supervisor/…=E-6 门 ·
  health/agent-config 开放
```
404 语义：缺失 vs 他人对象**同状态同 detail**（T1 实证连 detail 都
一致——修复了首版 detail 差异的存在性 oracle）。内部用户经守卫后
仍获内部语义 detail。

## 6. Security Tests（全部 PASS，15/15）

```text
T1 跨用户对话读=404（对称+与缺失全等） ✓   T2 跨用户 Run=404 ✓
T3 跨用户 events=404 ✓                    T4 跨用户 stream=拒于流前 ✓
T5 artifact 全路径（run 键/发行/解析/未知 ref）=404 ✓
T6 枚举：无存在性 oracle + 300 连发触发 429 ✓
T7 客户端 owner 提示全忽略（query/body）+ 注入零效果 ✓
T8 id 变更不改所有权 ✓                     T9 父链无旁路 ✓
T10 匿名（keys 模式）全守卫端点 401 ✓
矩阵 A/B/anonymous × chat/run/events/stream/artifact ✓
内部兼容 O-7：OPERATOR 读消费者对象 200；CONSUMER 过不了任何内部门；
  REVIEWER 门不变 ✓   dev loopback 全放行（冻结行为）✓
限流单元 + read_allowed 真值表 ✓
前端：401→身份门；有效凭据→进入；存储按主体分域（切换零残留）；
  local-dev 无门；深链 #/report/{opaque} 渲染+拒绝路径；URL 零 run_id ✓
```

## 7. Acceptance Gates

```text
G-B02-1 PASS（whoami+401 fail-closed）    G-B02-6 PASS（artifact=run 所有权）
G-B02-2 PASS（chat 所有权）               G-B02-7 PASS（统一 404）
G-B02-3 PASS（run 所有权）                G-B02-8 PASS（spoof 不可能）
G-B02-4 PASS（events 所有权）             G-B02-9 PASS（429 枚举防护）
G-B02-5 PASS（stream 所有权）             G-B02-10 PASS（消费者不达内部资源）
```

## 8. Regression

```text
G-0 baseline：backend 734/734 · web 213+2 · tsc clean（实现前新鲜）
G-8 full：backend **749/749**（=734 基线+15 隔离；三处实现中缺陷
  已修：①模块级限流器误伤 dev 模式轮询（首跑 35 败——改为仅 keys
  模式限流后全绿）②get_chat/get_run 缺失分支 detail 差异=存在性
  oracle（统一 not found）③E-6 旧"消费者面免钥"断言被 D-01′ 取代
  （更新为 keys 模式 401+CONSUMER 201 新契约））·
  web **219 passed + 2 skipped**（213→+6 身份/深链）·
  tsc **clean** · B4/M4/M3 含于 battery 全绿 · E-2..E-7 套件全绿（含于 219）
architecture invariants（§21 清单）：Router Authority UNCHANGED ·
  REAL_USER OFF · WeKnora/knowledge_provider UNCHANGED · Grounding/
  Intent/Agent spine UNCHANGED（git 范围审计：零 router/intent/
  grounding/agent-workflow 文件）
```

## 9. Git Delta（仅身份/所有权范畴）

```text
M runtime/auth.py（CONSUMER 角色） · runtime/consumer_access.py（新）
M runtime/agent/chats.py（owner+hex16） · runtime/server.py（owner/
  守卫/新端点/POST-runs 门/id 熵） · web/src/api/client.ts（鉴权头+
  401 事件+whoami/refs） · web/src/state/chatState.ts（按主体分域）
M web/src/App.tsx · app/route.ts（/report/{ref}） · ConsumerShell（门）
A IdentityGate.tsx · RefReport.tsx · identity.test.tsx ·
  tests/runtime/test_g_b02_isolation.py
测试接线更新：consumerApiBoundary（允许表+3）/consumerDom/
  seedRegression/shell（whoami mock+v2 键+异步）
```

## 10. Production State

```text
REAL_USER=OFF · WeKnora UNCHANGED（NOT CONNECTED）· knowledge_provider
UNCHANGED（mock） · Router Authority UNCHANGED（默认 slices）·
生产流量未触碰（:8000 保持停止） · 无隔离实例残留
```

## 11. Remaining Blockers（更新后）

```text
B-01 生产知识链（HD-2）——不变 BLOCKED
B-02 ——已解决（本阶段）；残留增强项=身份/所有权持久化层（随
  PERSISTENCE 立项；重启 fail-closed 已是安全默认）
B-03 ——已解决（28.F）
B-04 数据治理——不变 Owner Decision（D-GOV-1..6；所有权锚点现已就绪）
新增小项：邀请制 key 分发流程（运营动作）；身份层换真登录=未来产品
决策（现抽象可直接替换）
```

## 12. Owner Decisions Required

```text
D-02 HD-2 weknora 配置（解 B-01）
D-03 REAL_USER 授权（B-01/B-04 清障后）
D-04 提示词证据记号校准 · D-06 retention/deletion（B-04）
D-07 永久 Full Authority · D-08 commit/发布 · D-09 M5 清理
（D-01′/D-API-1/2/D-05′ 已由 Owner 决定并于本阶段实现）
```

## 13. 不进入 28.H；STOP
