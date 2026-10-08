# Phase 28.F-2 — B-02 Consumer Data Isolation Design Audit

Date: 2026-09-26 · 性质：**DESIGN ONLY（零实现）**。依 Final Audit
B-02 与 28.F 授权（"F-2 只做 Design/Audit"）。不替 Owner 选择鉴权
模型；不实现任何 Gate。

## 1. Current State

消费者身份=**匿名**（无登录/会话/cookie；唯一"归属"线索=浏览器
localStorage 里的 chat_id 列表——**localStorage 中的 ID ≠
authorization**）。内部面有 API-key 角色（OWNER/REVIEWER/OPERATOR），
但消费者面（chats/runs 读/SSE/artifacts）**无 ident 依赖**（E-6 设计
决定：消费者鉴权模型=DEFERRED OWNER DECISION）。

## 2. Current Data Model（代码实读）

```text
Conversation（ChatManager, runtime/agent/chats.py）
  · in-memory V0.1（重启即失）；chat_id=uuid hex[:8]（≈32 bit）
  · {"chat_id","created_at","messages[]","runs[]"} — 无 owner/tenant 字段
  └─ Message（含 role/content/kind/run_id——用户全文在服务端内存对象中）
  └─ Run（引用；run 拥有执行）
Run（RunManager；run_id=hex[:8]）
  ├─ Events（bus + run 目录 jsonl）
  ├─ Artifacts（run 目录 artifacts/*.json；artifact_type 寻址）
  ├─ AnswerContext（run 目录 qa-answer-context.json）
  └─ Eval/Review refs（case_id/project 目录：approvals/review-card）
前端 Conversation 列表=localStorage webui:chats:v1（设备本地）。
```

## 3. Current Read APIs（逐项 authentication/authorization/ownership/enumeration）

| Endpoint | Authn | Authz | Ownership | 枚举风险 |
|---|---|---|---|---|
| GET /api/chats/{chat_id} | 无 | 无 | 无（知道 id 即全读，含用户全文） | id 空间 hex8（小，理论可猜） |
| POST /api/chats（创建） | 无 | 无 | — | 无害 |
| POST /api/chats/{id}/messages[/stream] | 无 | 无 | 无（可向任意已知 chat 注入） | 同上 |
| GET /api/runs/{run_id} | 无 | 无 | 无 | hex8 |
| GET /api/runs/{id}/events[/stream] | 无 | 无 | 无（SSE 无凭据可挂任意 run） | 同上 |
| GET /api/runs/{id}/artifacts[/{type}]（含下载源） | 无 | 无 | 无（**跨读入口**） | 同上 |
| GET /api/runs/{id}/review-card | REVIEWER 门（E-6） | ✓ | 内部 | — |
| /api/projects/*（approvals/supervisor/…） | REVIEWER/OPERATOR 门（E-6） | ✓ | 内部 | — |
| /api/health/agent-config | 无（只读状态） | — | — | 无害 |

## 4. Ownership Graph（目标语义 vs 现状）

```text
目标：Consumer Identity ─ owns → Conversation ─ owns → Run ─ owns →
      {Events, Artifacts, AnswerContext}
现状：无 Identity 层；所有对象仅由"知识 of id"连接（实线缺失）。
```
chat→run 有 link（chats["runs"]），run→artifact 有目录包含；但**无任何
一层有授权主体**。

## 5. IDOR Threat Model（Broken Object Level Authorization）

```text
攻击面：B（匿名/低权）持 A 的 chat_id/run_id（泄露渠道：日志、分享
        截图、侧信道、小 id 空间枚举）
  T1 读 A 对话全文（GET /api/chats/{A}）        → 200（无拦）
  T2 挂 A 运行流（GET /runs/{A}/stream SSE）     → 200
  T3 读 A 事件链（含澄清问答内容）               → 200
  T4 读/下载 A 报告（GET /runs/{A}/artifacts/insurance-report）→ 200
  T5 向 A 对话注入消息（POST messages）          → 200（完整性攻击）
  T6 枚举：hex8 空间 ≈4×10^9；无速率限制 → 理论可行扫描
缓解现状：loopback 绑定 + 单租户部署惯例（非代码保证）；无 rate limit。
```
单租户单用户下 T1-T6 不构成跨主体越权（只有一个主体）；**多用户/公网
即全部成立**。

## 6. Consumer Identity Options（不替 Owner 选择）

| Option | 机制要点 | 安全性质 | 代价/影响 |
|---|---|---|---|
| A. 匿名+服务端会话令牌 | 首次进入发 opaque session token（cookie/header），chat/run 创建时绑定 token | 无身份但**有主体**；可做对象级授权+可撤销；不防自愿分享 | 需 Conversation 增加 owner 字段（数据模型变更=STOP-6 需授权）；最低成本达到 G-B02-1..7 |
| B. 认证消费者（登录/OTP/账户） | 真实身份 → 全链 ownership+审计 | 最强；支持跨设备/恢复/合规 | 产品级变更（Vision 相邻）；运营成本 |
| C. CONSUMER 角色（API-key 体系扩展） | 复用 runtime/auth.py 加第四角色 | 与内部体系统一；key 分发=产品门槛（每个消费者一把 key 不现实） | 适合内部 beta 受邀用户，不适合公开 |
共同前提（任一 Option）：对象模型加 owner 字段 + 授权检查 + 401/403/404
语义决策（**建议**：存在性隐藏→404 对未知/无权统一——仅记录建议）。

## 7. Authorization Options（对象级）

1. **中心化 ownership 检查**：单一 `_require_owner(resource, identity)`
   装饰/依赖，chat→run→artifact 沿链校验（防绕过：所有读端点必经）。
2. 能力 URL（opaque capability token 替代 run_id 寻址）——与 D-05
   深链同构（见 §9）。
3. 每对象 ACL——过度设计（无共享场景）。
推荐边界（仅记录）：Option 1 为主干；2 作为 artifact/深链增强。

## 8. Artifact Access Analysis

E-4 下载链=前端以 run_id+artifact_type 调 GET /runs/{id}/artifacts/
{type} → **与 T4 同入口**。修复必须在**端点授权**层（前端无参与）；
下载属读操作→与读同门。AnswerContext（含问题/证据/结论）同为 run
目录对象，须纳入同链（当前无独立端点暴露——随 run events 可见部分
内容，events 修复即覆盖）。

## 9. Deep Link Relationship（D-05 联动）

若未来引入 **opaque artifact reference**（服务端签发、绑定 owner、
不可枚举、可撤销），可同时满足：深链（可分享 URL）+ ownership（token
校验）+ authorization（scoped 只读）。即：D-05 与 B-02 共享同一构建
块；实现顺序建议（仅记录）：B-02 授权主干先行，深链作为其上的
token 化封装。不实现。

## 10. Data Governance Dependency（B-04 关联）

ownership 模型一旦建立，retention/deletion（D-GOV-1..6）将获得执行
锚点（按 owner 清算）；反之 retention 政策不影响授权主干设计。依赖
方向：B-04 依赖 B-02 的 owner 字段，而非相反。AnswerContext/事件/
shadow 遥测按 D-GOV-5 一并裁决。

## 11. Required Owner Decisions

```text
D-01′（细化）：Consumer Identity 选型 A/B/C（§6）
D-API-1：无权/未知 id 的响应语义（401 vs 403 vs 404 统一策略）
D-API-2：hex8 id 空间是否升级（更长/不可枚举 id）与 rate limit 引入
D-05′：opaque artifact reference 是否随授权主干一并立项
D-GOV-*（B-04 六项，见 F 报告 §13）
STOP 边界：Conversation/Run 数据模型加 owner 字段=STOP-6（需 Owner
授权后方可实现）。
```

## 12. Recommended Implementation Boundary（未来阶段，不实现）

```text
1) identity 层（依 D-01′）→ 2) ChatManager/RunManager 对象加 owner
（迁移：存量无主对象标记 legacy-owner）→ 3) `_require_owner` 接入
§3 表全部无门端点 → 4) 响应语义统一（D-API-1）→ 5) id 空间+限流
（D-API-2）→ 6) opaque artifact token（可选，D-05′）。
约束：不改 Event/Artifact 契约内容（owner 为访问元数据，不入事件
data）；Chat 内存 V0.1 → 持久化属既有 PERSISTENCE 缺口（另立项）。
```

## 13. Tests Required Before REAL_USER（定义，不实现）

G-B02-1..10 对应测试矩阵：双主体 A/B 夹具（各自 identity+chat+run+
artifact）× 交叉读/注入/下载/挂流（期望 401/403/404 依 D-API-1）×
前端不可绕过（直接 API 打）× 内部资源对消费者身份不可达 × 未知 id
fail-closed × 重启后 ownership 持久一致。

## 14. Hard Security Gates（G-B02-1..10）

```text
G-B02-1  跨用户 Conversation 读取阻断        G-B02-6  Run→Artifact 授权
G-B02-2  跨用户 Run 读取阻断                 G-B02-7  未知/非法 id fail-closed
G-B02-3  跨用户 Artifact 读取阻断            G-B02-8  前端不可绕过授权
G-B02-4  跨用户 Artifact 下载阻断            G-B02-9  直连 API 不可绕过
G-B02-5  Conversation→Run 授权链             G-B02-10 消费者身份不可达内部资源
（本阶段仅定义；实现=Owner 批准后的 B-02 implementation phase）
```
