# Phase 28.I — Data Governance & Lifecycle 报告

Date: 2026-09-26 · 目标：B-04 从 Owner Decision/BLOCKED →
**policy + 可执行边界 + 自动化证据**。Owner 原则 D-GOV-1..6 全部落地。

## Status

```text
28.I STATUS: PASS（B-04 = RESOLVED——G-GOV-1..12 全 PASS）
```

## B-04

```text
B-04 = RESOLVED（数据治理核心：分类/保留策略/消费者删除级联/
        trace·eval 治理/访问审计/legal hold/tombstone——全部自动化证明）
```

## Data Inventory（机器可验证：config/data-governance-policy.json +
runtime/governance.py 分类常量）

| 数据类 | 对象 | owner | 含用户内容 | 消费者可见 | Operator | Developer | 删除关系 | 保留策略（可配置默认） |
|---|---|---|---|---|---|---|---|---|
| D1 business_content | Conversation/Message/Run/AnswerContext/Artifact | consumer subject | **是** | 自己的 | 审计后职责访问 | 审计后职责访问（无默认内容权） | 消费者可随时发起→级联硬删 | 180d（部署可改） |
| D2 operational_trace | 运行事件/诊断（含 prompt/答案载荷） | 随父 run | **是** | 进度语义（非原始） | 职责 | 职责 | **随父删除**（bus.purge+目录） | 30d≤业务（D-GOV-5） |
| D3 evaluation_data | eval 用例/输出/golden | 项目 | 显式选定才含 | 否 | REVIEWER | 职责 | 目的绑定；生产对话**零自动复制**（GOV-T7 哈希证明） | 90d 最小必要 |
| D4 security_audit | 访问/删除/hold 审计 | 系统 | **否**（仅元数据，构造保证） | 否 | OPERATOR 审计视图 | 不可 | **独立**——业务删除不级联（D-GOV-1） | 365d 独立治理 |
| D5 system_metadata | 配置/健康/指标 | 系统 | 否 | — | — | — | 业务范围外 | 运营周期 |

## Deletion（生命周期证明，GOV-T1/T2/T4/T5/T6 全绿）

```text
DELETE /api/consumer/chats/{id}
  authenticate → subject → ownership（统一 404）→ 审计(deletion_request)
  → policy（legal_hold 阻断→409；消费者请求=D-GOV-3 任意时刻可删）
  → cascade：chat 记录物理删除（含 messages 全文）
      → 每 run：run 目录 rmtree（events/qa-answer-context/artifacts）
        + _runs/_active 摘除 + EventBus.purge（trace 含用户内容→D-GOV-5）
        + 不透明 artifact refs 全量撤销（deep link 死亡，D-GOV-4）
        + run tombstone
  → conversation tombstone（仅 identity/ts/reason/actor——零内容 GOV-T11）
  → 审计 deletion_executed（审计独立存活）
删后全路径 fail-closed：chat/run/events/stream/artifacts/深链=404；
内部身份也无法复活（GOV-6）。
```

## Access（边界证明）

```text
Consumer：仅自己的业务数据（B-02 所有权不变；删除同样过所有权门）
Operator：职责访问保持（O-7 权限零变动）但**每次读消费者数据入审计**
          （who/when/object/action/purpose 元数据，GOV-9/GOV-7）
Developer：同内部职责通道——无独立绕过面；已删对象 404；一切访问留痕
（D-GOV-6 满足=最小权限+目的+审计；权限模型未扩大未缩小→无 STOP-3）
```

## Trace / Eval

```text
Trace：D2 独立类，保留期短于业务（30d）；随父级联物理清除（bus purge
       + 目录删除）——不留孤儿 prompt/答案/证据。
Eval ：生产对话→eval/golden **无任何自动复制路径**（GOV-T7：运行真实
       chat 后 golden 目录逐字节不变）。显式选定+目的绑定=未来显式流程。
Audit：元数据构造保证（字段裁剪）——不含消息/产物正文/secret（GOV-T7 级
       断言+审计内容负测）。
```

## Acceptance Gates

```text
G-GOV-1  数据清单完整（5 类×9 属性表+代码化分类） PASS
G-GOV-2  保留策略定义（per-class·文件驱动·env 可换） PASS
G-GOV-3  消费者删除可用（authn+ownership+policy→级联） PASS
G-GOV-4  级联删除（chat→run→dir→trace→refs，全 404 证明） PASS
G-GOV-5  Artifact 生命周期（ref 随父撤销；全下载路径死亡） PASS
G-GOV-6  Trace 生命周期（D2 短保留+随父清除） PASS
G-GOV-7  Eval 隔离（golden 哈希不变） PASS
G-GOV-8  Developer 边界（职责通道+已删 fail-closed+留痕） PASS
G-GOV-9  Operator 访问审计（consumer_data_read 全记录） PASS
G-GOV-10 Legal hold（最小通用 registry；阻断→409） PASS
G-GOV-11 审计零敏感内容（构造裁剪+负测） PASS
G-GOV-12 策略可配置非魔数（INSURANCE_AGENT_RETENTION_POLICY 换档证明） PASS
```

## Tests（11/11 全绿）

```text
GOV-T1 消费者删除 ✓ T2 级联 ✓ T3 跨用户隔离（GOV-1）✓
T4 删后 artifact 404 ✓ T5 删后深链 404 ✓ T6 trace 级联（bus purge）✓
T7 eval 隔离（哈希）+ 审计内容负测 ✓ T8 developer 已删 fail-closed ✓
T9 operator 审计+消费者不可读审计 ✓ T10 legal hold ✓
T11 tombstone 零内容 ✓ T12 保留解析（deterministic clock）✓
+ 消费者请求优先于保留窗（D-GOV-3）✓ + env 换档策略 ✓
```

## Regression

```text
backend: **766 passed + 2 skipped**（=28.H 755 + GOV 11；全套内一处
         跨套件干扰已修——GOV 与 B-02 共享 subject 触发 28.G 模块级
         探测限流器 429 → GOV 改独立 subject+limiter 重置夹具后全绿；
         零生产代码改动）
web: 219+2（未触碰）· tsc clean（未触碰）
B4/M4/M3/E2-E7/B-02 T1-T10/HD-2：含于全量
未变：Intent/Router/Authority/Grounding/WeKnora/Consumer 身份与所有权
（git 审计：仅 governance 新模块+删除端点+bus.purge+refs 撤销+chats.delete）
```

## Git Scope

```text
A runtime/governance.py · config/data-governance-policy.json ·
  tests/runtime/test_gov_lifecycle.py（11）
M runtime/server.py（删除端点+审计视图+operator 读审计钩子）
M runtime/agent/chats.py（delete）· runtime/event_bus.py（purge）·
  runtime/consumer_access.py（revoke_for_run）
零触碰：intent/router/grounding/qa·product-qa·planning workflow/
WeKnora/catalog/consumer 身份/UI/event 词汇/artifact 生成语义
```

## Production State

```text
REAL_USER = OFF · WeKnora unchanged（HD-2 配置原样）· Router Authority
unchanged（默认 slices；:8000 保持停止）· 消费者身份/所有权 unchanged
```

## Remaining Issues（不属于 B-04，独立工作项）

```text
citation model-fit · 110/304 embedding 债 · CJK keyword 检索债 ·
registry/WeKnora 切分不一致 · :8000 生产部署（含治理配置上线）·
Permanent Full Authority · 治理 UI（消费者删除按钮/Operator 审计界面
=前端后续小项；本阶段按禁令未动 Consumer UI）· 定时到期清理 scheduler
（当前=纯 eligibility+即时消费者删除；到期自动执行=可替换 adapter 后接）
```

## FINAL

```text
不进入 REAL_USER。下一步（Owner）：Final Production Re-Audit →
D-03 REAL_USER authorization → isolated REAL_USER gray → observation。
```
