# Phase 28.J — Final Production Re-Audit

Date: 2026-09-26 · 性质：**AUDIT-ONLY / ZERO CODE CHANGE / ZERO RUNTIME
CHANGE**（本审计零产品/前端/Router/Intent/Grounding/WeKnora/Identity/
Governance/Artifact/Event 改动，零 commit；git 实证 117 status 项全部
为 28 系既有未提交 span + 本报告）。方法：当前代码实搜（行号在案）+
**本审计新鲜全量回归** + HD-2 live-env 复证 + 只读基础设施探测；
不以旧报告覆盖新证据（时间优先级：代码+测试 > 最新报告 > 旧报告）。

## Executive Summary

- **四个 Critical Blocker 全部 RESOLVED 且今日复证成立**：B-03→28.F ·
  B-02→28.G · B-01→28.H · B-04→28.I；本次逐一以当前代码行号 + 新鲜
  测试 + live 探测重证，无 REGRESSED。
- **新鲜质量门全绿**：backend **766 passed + 2 skipped** · HD-2
  live-env **8/8（含 2 live 门）** · web **219 passed + 2 skipped** ·
  tsc **clean**；专项门 B4 7/7 · B6 10/10 · B5.1 校准 15/15 · M4 9/9 ·
  M3 7/7 · E-6 5/5 · B-02 15/15 · GOV 11/11 · QA 16/16 · Product-QA
  15/15（全部本审计复跑，非引用旧数）。
- **Release Classification 重算：CONTROLLED PILOT READY**（原 INTERNAL
  BETA 的四个阻塞门 G5/G6/G7/G11 全部转 PASS；G10 Real User 仍 NOT
  VERIFIED——由定义在试点前不可验证，正是下一阶段目的）。
- **REAL_USER_READY = YES**（技术条件）；**不能据此直接开启**——需
  Owner D-03 授权后进入 isolated REAL_USER gray。
- **PERMANENT_FULL_AUTHORITY = DEFERRED**（代码支持+灰度证据齐；缺
  真实用户样本；D-07 未决）。
- 已知残留如实在案：citation model-fit（fail-closed，unsafe delivery
  =0）与 110/304 无嵌入为 **PRODUCTION_RISK**（影响可用性/覆盖率，
  不影响安全）；无 RELEASE BLOCKER。

## Current Release Classification

**CONTROLLED PILOT READY**（由 §Quality Gate Results 矩阵重算推导；
不沿用 INTERNAL BETA 旧结论，也不按"未来应该怎样"拔高）。

依据：G0-G4/G7/G8/G9/G11/G12 全 PASS（含原 CONDITIONAL 的 G5/G6 与
原 BLOCKED 的 G7、原 PENDING 的 G11 转正）；G10 Real User = NOT
VERIFIED（REAL_USER=0 全程如实）——CONTROLLED PILOT 的定义即"在
Owner 授权的隔离灰度中引入真实用户"；PRODUCTION READY 不成立
（真实用户证据=0、生产部署 :8000 未执行、永久 Authority 未决、
citation 合规率部分、持久层为内存 V0.1）。

## B-01 Status

```text
B-01 = RESOLVED（今日复证，无回归）
Evidence:
  code    server.py:976-1023  strict 启动知识预检（controlled_pilot/
          production ⇒ KnowledgeService 必须构造成功且 WeKnora 可达；
          PRODUCTION_KNOWLEDGE_REQUIRED / WEKNORA_UNREACHABLE 拒启动）
          knowledge/service.py:94-147  strict: json registry FORBIDDEN、
          registry 文件 override FORBIDDEN、PG registry 必需、provider
          选择 fail-closed（ProviderConfigError）
          knowledge/provider/weknora.py:11 mock 禁为证据源；:128 无
          伪造空成功；:208-221 SEARCH_METHOD 部署旋钮
          mode.py:38-40 STRICT_MODES=(controlled_pilot, production)
  corpus  insurance-pilot-2 KB（10 份真实监管文档 · 304 chunks ·
          A/S 级源）+ agent PG registry 治理链（28.H 在案，未变）
  probe   WeKnora-app :8080 → HTTP 401-alive；agent-postgres :5433 →
          TCP OPEN（本审计只读探测）
  tests   HD-2 套件 live-env 复跑 **8/8**（含 live H-R2 治理检索 +
          H-R4 语义近邻答案层 fail-closed；秘密经 gitignored tmp/
          注入，零打印）——生产知识链今日活体复证
  gates   双轨仍成立：Product-QA Catalog 锚点+WeKnora 知识边界
          （product_qa 15/15）；QA 引用闭包门 fail-closed
          （B5.1 校准 15/15：全角拒/ASCII 收/缺据拒）
  no-fallback 断网零 mock 回退（H-N1 自动化，含于 8/8）；
          mock 强制=构造即拒（H-N5）；缺据=诚实拒答（H-N2）
```

## B-02 Status

```text
B-02 = RESOLVED（今日复证，无回归）
Evidence:
  code    auth.py:34-37 CONSUMER(1)<OPERATOR(2)<REVIEWER(3)<OWNER(4)
          consumer_access.py resolve_subject/read_allowed（主体≠角色≠
          所有权；internal 值班读 O-7 不变）/ArtifactRefRegistry（ref
          ≠授权，解析后复检所有权）/RateLimiter 240/60s（仅 keys 模式）
          chats.py:24-33 owner 服务端创建时绑定（客户端不可声明）·
          Run owner 继承 · server.py:1087-1091 重启后无主 run fail-closed
          server.py:1056-1084 _consumer_read_guard：429→401→统一 404
          （缺失 vs 他人对象同状态同 detail）——覆盖 chats get/messages、
          runs get/events/stream/artifacts(/type)、artifact-refs、
          consumer/artifacts/{ref}（:1222-:1453 全部实点）
          server.py:1199-1203 POST /api/runs=OPERATOR 门
  tests   test_g_b02_isolation **15/15**（T1-T10 + 矩阵 + spoof 忽略 +
          枚举 429 + 前端身份/深链）；E-6 边界 5/5；含于全量 766
  残留(非blocker) 身份/所有权=内存 V0.1 层（重启→对象无主→404
          fail-closed，安全默认；持久化随 PERSISTENCE 立项）；无登录
          产品（Owner 已排除现阶段选型——受邀 key=内部 beta 形态）
```

## B-03 Status

```text
B-03 = RESOLVED（今日复证，无回归）
Evidence:
  code    chatState.ts:85-93 loadChats() 三条回退（无存储/版本不符/
          损坏）全部 return [] —— 永不 seedChats；:59 seedChats 导出
          保留=Developer/Demo 能力（不在消费者路径）
  tests   seedRegression 5 用例（新消费者零种子/真实会话保留/demo 能力
          隔离/刷新不生史/重开不生史）+ chatState 契约——含于 web 219
          新鲜全绿；消费者 DOM 泄漏套件同步绿（零虚构历史/卡片/进度）
  边界    demo 能力（DEMO_CASES/mapPromptToCase）仅内部面可达：消费面
          Composer mode="agent"（ChatLayout.tsx:228——演示 case 选择器
          不渲染）；消费者发送路径=postChatMessage(text) 纯文本
          （ChatLayout.tsx:119，客户端映射结果绝不进服务端请求）；
          服务端 demo 入口 POST /api/runs=OPERATOR 门
```

## B-04 Status

```text
B-04 = RESOLVED（今日复证，无回归）
Evidence:
  code    governance.py:36-41 五数据类（BUSINESS/TRACE/EVAL/AUDIT/
          META）· :86 deletion_eligible 纯函数（now 注入=确定性时钟；
          legal_hold 阻断；consumer_requested 任意时刻可删）· :118-136
          legal-hold registry · :138-162 tombstone 仅 identity 字段 ·
          :164-192 audit 构造裁剪（元数据 only）
          config/data-governance-policy.json per-class 保留（部署可改；
          INSURANCE_AGENT_RETENTION_POLICY 整体换档）
          server.py:1292 DELETE /api/consumer/chats/{id} 级联（authn→
          ownership→审计→policy→chat 物理删+每 run 目录 rmtree+
          _runs/_active 摘除+EventBus.purge(event_bus.py:61)+refs
          revoke_for_run+tombstone）；:1369 /api/governance/audit=
          OPERATOR；:1076-1084 operator 读消费者数据入审计
  tests   test_gov_lifecycle **11/11**（GOV-T1-T12：级联全 404/跨用户
          隔离/删后 artifact+深链死/bus purge/eval golden 哈希不变/
          developer fail-closed/审计元数据/消费者不可读审计/legal
          hold/tombstone 零内容/保留解析+env 换档）——新鲜复跑
```

## Quality Gate Results（本审计新鲜执行，非引用）

```text
backend 全量        python -m pytest tests/runtime tests/contract -q
                    → 766 passed + 2 skipped（393.9s，exit 0）
HD-2 live-env       +注入 tmp/ 秘密复跑 → 8/8（2 live 门实跑）
B4 Router 等价      test_p28b4_gate 7/7
B6 preflight        10/10（E1 提示词冻结 tripwire 含）
M4 authority        test_p28m4_staging 9/9
M3 planning         test_p28d_m3_slice 7/7
E2/E3/E5 consumer   含于 web 全量（consumerView/activity/terminal 套件）
E4 artifact         含于 web 全量（artifactDelivery）
E6 consumer auth    test_e6_space_api_boundary 5/5
E7 journeys         六旅程为 28.E-7 live 实测记录（本审计不重开浏览器；
                    其锁定契约=web 219 内 DOM/终态/交付套件全绿）
B-02 T1-T10         test_g_b02_isolation 15/15
GOV-T1-T12          test_gov_lifecycle 11/11
web 全量            vitest → 219 passed + 2 skipped（18.3s，exit 0）
TypeScript          tsc --noEmit → clean（exit 0）
零失败；两处 skip=HD-2 live 门（默认无 env）+web e2e live（同性质）
——live 版已单独实跑补证（8/8）。
```

## Architecture Invariants

```text
Runtime   PASS — 单一执行脊柱：orchestrator 唯一模块引用
          （server.py:54），runtime/ 全目录无第二 Orchestrator/
          WorkflowEngine/Dispatcher 类（本审计 grep 实证）；
          B4 等价门 7/7 + B6 10/10 持续锁定 legacy≡candidate。
          链路：Message→Conversation→Intent→Router→Agent→Workflow→
          Evidence→Result→Artifact Delivery（E-7 六旅程实测在案）。
Intent    PASS — Intent≠Prompt：schema/intent-*.json 契约 + IntentResult
          无 agent/workflow 键 + LLM candidate env-gated advisory-only；
          Router 不由 LLM 决定（decision_source 无 llm 值，契约测试含
          于全量）；Intent 不选 Agent/Workflow（registry lookup）；
          modify-without-active-case fail-closed（契约含）。
Router    PASS — deterministic（router_authority.py；:31 默认 slices；
          :57 非法值 fail-closed——typo 不可授权）；无私有路由；
          prompt 无路由权威（B6 守卫 + E-6 API 源扫描）。
Grounding PASS — 事实=Catalog+WeKnora 治理证据（双轨 15/15+16/16）；
          缺据 fail-closed（H-N2）；引用闭包门权威且模型不可绕过
          （B5.1 15/15）；全部窗口 unsafe delivery=0。
Consumer  PASS — #/chat 默认产品面（未知路由 fail-safe 消费者，shell
          测试锁定）；无 Developer Mode/Operator UI/raw run_id/case_id/
          agent_id/provider/model/raw event/reason code/chain-of-
          thought/伪产物/伪完成（web 219 内 DOM 泄漏套件 + 未知值
          fail-closed 断言全绿；URL 零内部 id——深链为不透明 ref）。
```

## Consumer Surface

E-1..E-7 成果全部在位且被本审计新鲜回归锁定：三空间 shell（hash 路由，
fail-safe 消费者默认，legacy webui:mode 失效有负测锁）· consumerView
allowlist（无 spread/透传）· activity DTO fold（未知隐藏、去重、
started≠completed）· Completion≠Artifact（投毒→false）· 五态终态优先级
（refusal 经 result_status）· Markdown 下载 + 不透明深链 #/report/{ref} ·
503 消费者文案（后端细节不渲染，ChatLayout.tsx:126-130 注释在案）·
身份门（401→IdentityGate；按主体分域存储）。

## Identity / Ownership / Authorization

```text
Authentication → Identity（服务端解析主体）→ Ownership（服务端记录
owner）→ Authorization（端点界 _consumer_read_guard）→ 治理 → 删除 →
审计 —— 链条闭合，无以下反模式（逐一排除）：
  localStorage=授权 ✗（key 仅认证秘密；whoami 决定主体）
  run_id=授权 ✗（所有权复检；ref 解析后仍复检）
  不透明 ref=授权 ✗（resolve≠grant）
  前端过滤=授权 ✗（全部服务端守卫）
  已删对象可读 ✗（GOV-T1/T2/T8 全 404，内部身份亦不可复活）
  父删后 artifact 可下载 ✗（refs revoke_for_run；GOV-T4/T5）
匿名+keys=401；无 key 本地开发 loopback=文档化冻结行为（ownerless）。
```

## Data Governance

§B-04 五类清单/保留策略/级联删除/legal hold/tombstone/审计独立存活/
eval 隔离（golden 哈希不变）全部成立（11/11 新鲜）。运行态注意：
当前删除审计/registry 为进程内存 V0.1（与 Chat/Run 同层）——随进程
存活；生产部署需按部署 checklist 落地（见 Production Configuration）。

## Knowledge / Grounding

生产链=治理真实 WeKnora（B-01 复证）。**三层区分（§9 专项裁定）**：

```text
retrieval correctness   = PASS（H-R1/R2/R3 live+A 级 stamps；今日 8/8）
evidence quality        = PASS（A/S 监管源 · provenance 全字段）
citation compliance     = PARTIAL（hermetic 校准 15/15 门行为正确；
                          live glm 生成偶发未过引用门→fail-closed 拒答；
                          28.H 三层诊断在案：检索成功/LLM 引用失败/
                          门正确拒绝）
unsafe delivery         = 0（全部窗口，无一例外）
→ citation failure ≠ unsafe delivery（系统已 fail-closed）；
  整体 Knowledge Chain 不因此 BLOCKED；按 §8 分类=PRODUCTION_RISK。
```

## Artifact Delivery

真实事件门控（hasRealArtifact）· ReportModal 渲染运行时原产物 ·
Markdown 下载 · 不透明 ref 深链（ar_+hex24；ref≠授权）· 父删即死
（GOV-T4/T5）。无伪造卡片/预览（B-03+E-2 投毒锁定）。

## Security

角色门 15 内部端点（10 OPERATOR + 5 REVIEWER，server.py 实点复核）·
消费者守卫 429/401/统一 404 · 高熵 hex16 id · 枚举限流（300 连发→429）
· spoof 全忽略 · CORS 白名单 · secrets 纪律（密钥仅存 gitignored tmp/，
本审计全程零打印——包括 live 复证注入）。残留（如实）：内存 V0.1
身份层（重启数据丢→fail-closed，安全但可用性受限）；无登录产品
（受邀 key 分发=运营动作）；单实例部署形态（未做多租户横向）。

## Observability

runtime/obs 四咽喉（http/knowledge/llm/persistence）+ health/ready/
metrics/diagnostics（角色门）+ intent shadow 全量 + run 目录事件留痕
（消费者不渲染）。已知 LOW：diagnostics llm_provider 读取时序
（obs/diagnostics.py:64 读时 env——注入式实例下可能显示 None vs
实际 live 调用；观测口径问题，非功能缺陷）。

## Rollback

三度演练在案（B5/B5.1/M5-C 生产端口实证）且本审计期零相关代码变更：
authority unset+restart · slice flags 独立回滚 · 前端回滚无状态迁移 ·
知识链回退=env 切换（strict 预检保证不会静默回 mock——拒启动）。
全部 documented+tested+reversible 维持。

## Technical Debt Classification（§8 逐项，五档硬分类）

| # | 项 | 分类 | Evidence | Impact | 判定依据 | Required Action |
|---|---|---|---|---|---|---|
| 1 | citation model-fit | **PRODUCTION_RISK** | 28.H 三层诊断+校准 15/15+live 拒答实证；unsafe delivery=0 | 真实用户 QA 拒答率上升 | fail-closed 已保证安全；影响质量/可用性非安全 | D-04 校准轨道（试点前/中）；不阻塞授权 |
| 2 | 110/304 chunks 无嵌入 | **PRODUCTION_RISK** | 28.H Remaining①（3 份核心法规各半） | 该部分语料向量检索不可达→缺据拒答 | 安全 fail-closed；纯覆盖率问题 | WeKnora 侧 re-embed（运维动作） |
| 3 | CJK keyword 检索 | **TECHNICAL_DEBT** | 该构建无 CJK 分词；vector_search 旋钮已启用（weknora.py:208） | 仅影响未来 keyword/hybrid 模式 | 现役路径已绕开 | WeKnora 升级/分词器（后置） |
| 4 | registry/WeKnora 切分不一致（200 vs 304） | **TECHNICAL_DEBT** | 28.H Remaining③ | provenance stamps 仍绑定；一致性维护成本 | 非正确性缺陷 | re-anchor 对齐（后置） |
| 5 | :8000 生产部署 | **OWNER_DECISION** | :8000 停止（本审计探测 000）；strict env 配方在 tmp/hd2.env 模板 | 部署=运营授权动作 | 技术就绪已证（:8123 隔离实证） | 随 D-03 试点授权一并执行 |
| 6 | Permanent Full Authority | **OWNER_DECISION**（DEFERRED） | §Permanent Full Authority Status | 权威常置 | 缺真实用户证据 | D-07 |
| 7 | governance UI | **FUTURE_ENHANCEMENT** | API 级治理完备（GOV 11/11） | 消费者删除按钮/Operator 审计界面缺=运营用 API/命令 | 治理本体不缺 | 前端小项（后置） |
| 8 | retention scheduler | **TECHNICAL_DEBT** | eligibility 纯函数+policy 就绪；无自动到期执行器 | 到期数据暂不自动清（消费者删除可用） | 功能缺口有界 | adapter 后接 |
| 9 | old demo 残件 | **TECHNICAL_DEBT** | DEMO_CASES/mapPromptToCase/Composer 默认 mode="demo" | 消费面 UI 隐藏（mode="agent"）+发送纯文本+服务端 OPERATOR 门+守卫测试 | 三重防线在位 | D-09 清理时移除 |
| 10 | webui:mode | **TECHNICAL_DEBT**（已退役残迹） | route.ts 注释+shell 负测锁（键无效） | 旧设备死键惰性 | 代码权威已移除 | 无需动作（D-09 顺带清缓存键） |
| 11 | runtime_mode=demo 默认 | **PRODUCTION_RISK** | server.py:981 默认 demo；strict 需显式 INSURANCE_AGENT_MODE | 部署漏设 env→以 demo 默认启动（mock 知识/鉴权可选） | 严格校验仅在 strict 生效——部署错误面 | 部署 checklist 钉死 strict env（随 #5） |
| 12 | diagnostics 时序 | **TECHNICAL_DEBT** | obs/diagnostics.py:64 读时 env | 观测口径偶不一致（LOW） | 非功能缺陷 | 观测小修（后置） |

## REAL_USER Readiness

```text
REAL_USER_READY = YES（技术条件全部具备；见逐项）
  B-01 RESOLVED（今日 live 复证）· B-02 RESOLVED（15/15）·
  B-03 RESOLVED（code+回归）· B-04 RESOLVED（11/11）·
  Consumer Surface 完整（E-1..E-7，219+2）· Auth（CONSUMER 身份+
  401 fail-closed+strict 拒无钥启动）· Ownership（服务端绑定+继承）·
  Governance（删除/审计/保留）· Knowledge（治理 WeKnora live）·
  Grounding（fail-closed，unsafe delivery=0）· Artifact（真实事件+
  不透明引用）· Rollback（三度演练）· Observability（四咽喉+shadow）·
  Regression（766+2 / 219+2 / tsc clean 全新鲜）

=YES 不等于开启。运营前置（非代码阻塞，随 D-03 执行）：
  部署 strict env（mode/keys/data-key/WeKnora/retention）· 受邀 key
  分发流程 · 预期管理（QA 拒答率=citation 合规现状）· 重启丢会话
  （内存 V0.1）告知 · 治理操作走 API（无 UI）
```

## Permanent Full Authority Status

```text
PERMANENT_FULL_AUTHORITY = DEFERRED
  code support        = YES（slices/no-plan/full；非法值 fail-closed）
  isolated gray       = PASS（B5/M5 系列矩阵+S1-S5）
  equivalence         = PASS（B4 7/7 + B6 10/10 今日新鲜；权威≡flag 等价）
  real-user evidence  = 0（不可在试点前获得）
  authorization       = D-07 未决；代码默认保持 slices（未动）
```

## Remaining Owner Decisions（仅真正未决；已决不重复上报）

```text
D-03 REAL_USER authorization（本审计 REAL_USER_READY=YES 为其输入）
D-04 citation 校准/模型适配缓解轨道（PRODUCTION_RISK #1 的处置）
D-07 Permanent Full Authority（DEFERRED，缺真实用户样本）
D-08 commit/发布授权（未提交 span 117 status 项——28 系全部工作）
D-09 M5/demo 清理授权（独立阶段；覆盖 #9/#10 残件）
D-10 HTML/PDF 导出与 vision 措辞对齐（产品决策时顺带）
已决并实现（不再上报）：消费者身份模型/所有权/统一 404/不透明引用/
artifact 所有权/数据治理原则/删除生命周期/operator 审计/developer
访问限制（D-01′/D-API-1/2/D-05′/D-GOV-1..6）及 D-02（HD-2）。
```

## Remaining Release Blockers

```text
RELEASE BLOCKER = 无（B-01..B-04 寄存器清空且今日复证无回归）
PRODUCTION_RISK（非阻塞，试点窗口管理）：citation 合规率 · 嵌入覆盖
  110/304 · 部署 mode 默认 demo（须 checklist 钉 strict）· 内存 V0.1
  持久层（重启丢会话）· 受邀 key 分发（运营）· 治理无 UI（API 操作）
TECHNICAL_DEBT：#3/#4/#8/#9/#10/#12（见分类表）
FUTURE_ENHANCEMENT：#7 治理 UI
```

## Recommended Next Phase

```text
Owner 决策 D-03 → isolated REAL_USER gray（controlled_pilot 部署：
strict env + 受邀消费者 keys + 治理配置上线 + 观察窗口）→ 观察/
评估（含 citation 拒答率实测分布 → 反哺 D-04）→ D-07/D-08 按证据
推进。本审计到此 STOP——不开启 REAL_USER、不动 Full Authority、
不修任何债务项。
```

## Evidence Index（本审计新鲜产生）

```text
backend 766+2（393.9s）· HD-2 live-env 8/8 · web 219+2（18.3s）·
tsc clean · B4 7/7 · B6 10/10 · B5.1 15/15 · M4 9/9 · M3 7/7 ·
E-6 5/5 · B-02 15/15 · GOV 11/11 · QA 16/16 · Product-QA 15/15
探测：WeKnora :8080=401-alive · PG :5433=OPEN · :8000=停止 ·
:5173=存活 · .env 变量名单（仅 LLM_*）
代码实搜行号：server.py:976/1048/1056/1087/1199/1292/1369 ·
consumer_access.py · auth.py:34 · chats.py:24/66 · event_bus.py:61 ·
governance.py:36-192 · router_authority.py:31/57 · mode.py:38 ·
provider/__init__.py:28 · weknora.py:208 · chatState.ts:59/85 ·
ChatLayout.tsx:119/228 · Composer.tsx · obs/diagnostics.py:64
历史证据引用：E-7 六旅程 · 回滚三度演练 · 28.F/G/H/I 报告 ·
ADR-019..025（025 APPROVED 2026-09-25）
```

---

```text
Phase 28.J Final Production Re-Audit

Audit Status: COMPLETE（零代码/零运行时/零 commit 改动）
B-01 = RESOLVED · B-02 = RESOLVED · B-03 = RESOLVED · B-04 = RESOLVED
Release Classification: CONTROLLED PILOT READY（重算，非沿用）
REAL_USER_READY = YES（技术条件；开启仍需 Owner D-03）
PERMANENT_FULL_AUTHORITY = DEFERRED（D-07）
Release Blockers: NONE
```
