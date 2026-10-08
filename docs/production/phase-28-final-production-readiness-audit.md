# Phase 28 Final Production Readiness Audit

Date: 2026-09-26 · 性质：**READ-ONLY AUDIT**（零产品代码/架构/配置/
运行时/前端/后端改动；git 实证 tracked-modified 22 项全部为 28 系列
既有未提交 span，本审计新增仅本报告）。方法：代码实搜 + 新鲜全量
回归 + 本会话全部运行证据（M5/E 系列实测）交叉。

## 1. Executive Summary

- **Verified**：架构闭环（单 Runtime/确定性 Router/Registry/三 Agent
  全经统一脊柱）；Grounding fail-closed 在全部灰度实测中零不安全
  交付；Consumer Surface（E-1..E-7）三重边界+零前端泄漏+零伪行为；
  内部端点角色门 fail-closed；回滚三度演练；B4 等价门 17/17。
- **Unverified**：真实用户（全程 REAL_USER=0，探针/测试从不冒充）。
- **Blocked**：生产知识链（HD-2：当前环境 knowledge=mock）；多用户
  数据隔离（无所有权模型，id 寻址+消费者端点免鉴权 → 无法证明跨
  用户隔离）；数据治理（ADR-024 retention/access/deletion 未决）。
- **Pending Owner Decision**：消费者鉴权模型、HD-2 配置、REAL_USER
  授权、提示词证据记号校准、深链/导出契约、永久 Full Authority、
  数据保留策略、commit 授权、M5 清理。
- **结论分类：INTERNAL BETA**（依据 §23 Gate 矩阵推导，见 §24）。

## 2. Current System State

```text
代码：HEAD 9407a84 + 未提交 span（28.A..E-7 全部迁移+消费者面代码）
测试：backend **734/734（本审计新鲜复跑）** · web **207+2（新鲜）** ·
      tsc **clean（新鲜）**
运行实例：:8000 已停止（harness 内存压力回收 full 灰度任务——非错误，
      未自行恢复）；:5173 Owner vite 存活；隔离实例已清理
默认状态：ROUTER_AUTHORITY 代码默认=slices（router_authority.py:53-54
      空缺省→slices，本审计复核）· slice flags 默认 QA=ON(D4)/
      PRODUCT=OFF/PLAN=OFF · mock 知识（.env 仅 LLM_* 变量）
```

## 3. Architecture Reality Audit（Documentation ≠ Reality → 以代码为准）

**ONE_RUNTIME = PASS**。证据：`create_app` 唯一（runtime/server.py:1031）
· orchestrator 唯一引用（server.py:52，worker "invoke the EXISTING
orchestrator exactly like demo"，:339/:516-521 单一 `_agent_worker`
线程脊柱）· 无第二 engine/orchestrator/dispatcher 类（全仓 grep）·
结构级证明=B4 E1 字节等价（legacy vs candidate 同脊柱产物逐位一致，
17/17）。调用链实测（E-7 六旅程 + shadow 记录）：

```text
Message→Conversation(POST /api/chats/{id}/messages)→Intent(rule,schema)
→Router(authority)→Registry(config)→QA/ProductQA/Planning Agent
→既有 8 阶段脊柱→Grounding→Result→Artifact→Consumer Delivery ✓
```
残留并行路径（受控、非生产消费者路径）：demo 模式=Developer 控制台
专属（POST /api/runs + 前端 mapPromptToCase——B6/E-1 双重守卫测试
锁定其不得进入消费者 ChatLayout）。

## 4. Intent / Router Audit

**PASS**。Intent≠Prompt：`schema/intent-*.json`（draft-07 闭合）+
IntentResult 无 agent/workflow/tool/skill 键（schema 断言）+
intent_classified 事件 + Router 消费（server 脊柱实测 authority 触发）
+ shadow 全量记录（resolver/latency/mismatch）。LLM candidate=
env-gated OFF、advisory-only、forbidden-key 拒绝（28.A-2 测试）。
Router deterministic：decision_source 无 llm 值（契约测试）；authority
resolver 单读取者（git grep 断言）+ 非法值 fail-closed（ typo 不可
授权）。默认=slices 未变（§2）。无前端/Agent/prompt 选 Agent（E-6
API 源扫描 + B6 守卫）。

## 5. Agent / Workflow Audit

**PASS**。Registry=config-based（config/agent-registry.json +
runtime/agent_registry.py 加载器；无动态注册）。QA/Product QA/
Planning 全经 registry_lookup→统一脊柱（M4 路由矩阵 10/10 + E-7
旅程实测；shadow reason=authority 全程可查）。职责边界：QA 类=
证据转述（禁推荐——R8 禁推探针零泄漏；D6 目录缺失 0.5s 拒答）；
Planning=既有 8 阶段脊柱（M3 guard+mount，无第二 planning runtime，
零跨案）。E1 提示词冻结 sha 持续 tripwire。

## 6. Grounding / Evidence Audit

**PASS（fail-closed 实证）**。citation 闭包门（sha b8f392e84030
活体：全角拒/ASCII 收；regen=1 有界）；AnswerContext 闭合 schema
（grounded/partial/refused + 9 值 failure_reason）；D6 双缺→拒答；
证据链 provenance（retrieved_at/content_hash/governance）。全部灰度
窗口 unsafe delivery=0；幻觉探针（R9）结构级拦截。**Owner
Calibration 待决项现状**（§15 of E-7）：governed 答案文本含
"authority: B"、"catalog version 0.1/product_version 1.0"——定性=
**prompt wording**（product-qa-answer-v3 的证据归因措辞；非 evidence
metadata 必需、非 consumer presentation 层——前端不改写已交付事实
文本）。未修改，列 D-04。

## 7. Artifact Audit

**事实**：view=PASS（ReportModal 真实 rendered_report，运行时原产物）
· download=PASS（Markdown Blob，零新后端契约）· deep link=DEFERRED
（寻址=run_id，消费者 URL 必泄内部 id；opaque 寻址=新契约）。
**Deep link 是否 Production blocker？——判定：非 blocker**：当前
UX（对话内卡片→查看→下载）已覆盖用户旅程（E-7 Journey D 实测完整
走通）；深链增益=分享/收藏场景，属产品增强；安全上 opaque 寻址需
后端契约+所有权模型（依赖 D-01/D-05）。分类：DEFERRED（Enhancement）。
Completion≠Artifact 维持（投毒测试：hasArtifact=true 于 refused/
failed 强制 false）。

## 8. Consumer Surface Audit

**PASS**（E-0..E-7 链条）：Space（hash 路由 fail-safe 消费者默认）
· Information（consumerView allowlist，零 spread）· Semantic
（activity DTO，未知值全隐藏）· Artifact（§7）· Terminal（五态
确定性优先级）· Auth（§10）· E2E（六旅程）。前端层泄漏=0（§39
清单 DOM 扫描 ×旅程）；伪进度/伪完成/伪产物/伪成功=0。

## 9. Operator / Developer Boundary Audit

**PASS**。Operator（Review/Approval/Workspace/Feedback）与
Developer（Dashboard/运行控制台/Inspector/Trace/Debug/Demo）全部
保留且仅存于内部路由；未被 Consumer 依赖（E-6 源扫描）。Human
Review=escalation 语义未变（needs_review 仅质量门触发，非全量必经）。

## 10. Auth / Security Audit

**CONDITIONAL（多用户维度 BLOCKED）**。已验证：runtime/auth.py 三
角色秩级（OWNER⊇REVIEWER⊇OPERATOR）+ `_identity_dep` keys 模式
401 fail-closed + production 无 key 拒启动 + 8 内部数据端点角色门
（E-6 测试 5 项）+ CORS 白名单机制。**SECURITY RISK（不可证明
安全，未修）**：
1. **IDOR 类**：chat/runs/events/artifacts/stream 以 chat_id/run_id
   寻址且无所有权/会话概念（`get_chat(chat_id)` 等无 ident 依赖）—
   任何持有 id 者可读对话与产物（run_id 含 8 hex 熵，非枚举安全
   论证）。单租户 loopback=可接受现状；多用户=**BLOCKER（B-02）**。
2. 消费者鉴权模型未决（D-01）：当前匿名=设计现状而非决定。
3. 409 冲突响应回带 case 级运行信息（内部面语义；消费者 chat 路径
   文案已消费者化）。
Secrets：.env 本地未提交；密钥永不打印（会话纪律）；无硬编码凭据。

## 11. WeKnora / HD-2 Audit

**CONFIG BLOCKED（代码 READY）**。code readiness=完整（provider
选择 env 驱动；strict 禁 mock HG-24-03；启动期校验 RV-P2-01；
knowledge/provider/weknora.py live provider Phase 18/24）。configuration
readiness=**缺失**（.env 无 INSURANCE_AGENT_WEKNORA_{URL,API_KEY,
KNOWLEDGE_BASE_ID}）。credential readiness=Owner 持有（Phase-24
docker 栈仍运行：WeKnora-app :8080 401-alive + agent-postgres :5433）。
operational readiness=RUNBOOK 在案（KB stall/scoped key/tenant
header 要点）。当前实例 knowledge_provider=mock（自报）。分类：
HD-2=CONFIG_ONLY（凭据动作=Owner）。

## 12. REAL_USER Readiness

**NOT VERIFIED（REAL_USER=0 全程，如实）**。Checklist：

| 项 | 状态 |
|---|---|
| Consumer Auth | PENDING（D-01；B-02 关联） |
| Data isolation | **FAIL（无法证明——无所有权模型）** |
| Knowledge provider | **FAIL（mock；HD-2）** |
| Monitoring/Observability | PASS |
| Rollback | PASS（三度演练） |
| Error handling | PASS（消费者文案+fail-closed） |
| Privacy | PARTIAL（用户全文不入事件遥测 ✓；保留/删除未决 D-06） |
| Rate limit | **FAIL（无消费者级限流）** |
| Production configuration | FAIL（runtime_mode=demo/非 strict/json 后端） |
| Support/review path | PASS（escalation+Operator 面在位） |
| 新用户首屏 | **FAIL（B-03 seed 虚构对话，见 §19）** |

→ **Synthetic / scripted validation complete. Real-user validation
pending.（不得表述为"生产验证完成"）**

## 13. Router Authority Readiness

Evidence currently available：路由矩阵 10/10（含 unknown/clarification
尊重）· S1-S5 安全全过 · B4 E1/E2 等价 17/17 · 权威≡flag 等价 9/9 ·
回滚生产端口演练 ✓ · E-7 消费者旅程经 full 灰度全通 · 零 wrong-agent/
意外路由（全部窗口）。Remaining evidence：**真实用户样本（=0）**；
HD-2 后真实知识链上的复验。Decision required：D-07（永久 Full
Authority）。代码默认保持 slices（未动）。

## 14. Observability / Rollback

Observability **PASS**：runtime/obs 四咽喉（http/knowledge/llm/
persistence）+ /api/health|ready|metrics|diagnostics（角色门）+
intent shadow（resolver/latency/slice_decision）+ run 目录事件全量
（内部可用 run_id/case_id 定位；消费者不渲染）。已知小项：
diagnostics llm_provider=None 与实际 live 调用不一致（读取时序，
LOW）。Rollback **PASS**：authority unset+restart（生产端口实证）·
slice flags 独立回滚 · Consumer 变更=前端回滚（无状态迁移）· 全部
documented+tested+reversible。

## 15. Data Governance

**PENDING（ADR-024 constraints）**：feedback 绑定 run_id+version 已
裁决；**数据政策（retention/access/deletion）未定义→ 28.0.5 起
BLOCKED 未解**。现状事实：会话=浏览器 localStorage+服务端 chat 对象
（无用户维度）；run/artifact=文件系统持久（json 后端）；shadow.jsonl
累积；无删除路径。→ D-06。标记 **Governance Pending**（未自行决定
任何 retention policy）。

## 16. Test Coverage（本审计新鲜复跑）

```text
backend: 734/734（本审计新鲜复跑，含 B4 17/17 · M4 9/9 · M3 7/7 ·
         E-6 边界 5/5）
web:     207 passed + 2 skipped（新鲜）
tsc:     clean（新鲜）
```

**这些数字代表什么**（§18 要求）：确定性单元/契约/集成层面——
Intent 契约 10、shadow/calibration、三 slice 行为、B4 双跑等价 17、
M4 权威 9、M3 7、planning 基线 tripwire、安全/隔离/回滚、E-6 边界 5、
消费者面 46（壳/路由/视图/DTO/终态/产物/API 源扫描/DOM 泄漏/503）。
金字塔：Unit≈590 · Contract≈24（含双端事件词汇）· Integration≈90
（TestClient 全链/slice/hermetic 双跑）· E2E（env-gated 真后端）1
（skip）+ 浏览器 live 旅程（本会话 11 探针，人工执行非 CI）· Live
Gray=全部 M5 窗口（脚本探针）· **Real User=0**。

## 17. Test Blind Spots（green 之外的坦白）

| 项 | 覆盖 |
|---|---|
| 跨用户数据泄漏 | **Not Covered**（无多用户模型可测） |
| 真实 WeKnora 行为 | **Not Covered**（mock；代码级集成测试在，凭据级未跑） |
| 真实生产流量/分布漂移 | **Not Covered**（0 真实用户；live glm 观测= Partial） |
| Prompt injection 对抗 | Partial（GC-PQ-07 负向锚；无系统性对抗套件） |
| 长对话/多轮上下文 | Partial（D 旅程 2 轮实测；无长历史压力） |
| 并发运行 | Partial（409 case 冲突+电池并发；无满载矩阵） |
| SSE 重连/刷新 | Covered（cursor 单测+live reload 行为） |
| 网络中断/慢速/部分失败 | Partial（错误文案+watchdog 240s+provider
  crash→needs_review 实证；无 chaos） |
| 重复提交 | Partial（409+busy 态） |
| 陈旧产物/遗留会话 | Partial（stale 文案+404-retry 诚实；遗留数据=§19） |
| 权限变更/会话过期 | Not Covered / N/A（无会话） |
| 大产物/移动视口/完整 a11y | Not / Partial / Partial |

## 18. Documentation Drift

1. PRODUCT_VISION v1.0 输出措辞「HTML 在线查看/PDF 打印导出」vs
   ADR-023 ruling「v1=Markdown」vs 现状（Markdown Modal+.md 下载）—
   **LOW DOC DRIFT**（ADR ruling 与实现一致；vision 措辞待 Owner
   下次产品决策时对齐）。
2. M5-C「UI 未运行」辅助论据已被 M5-C.1 更正（vite [::1] 漏检）—
   历史报告保留，更正在案。
3. diagnostics llm_provider=None vs live glm（LOW，观测读取时序）。
4. 其余：phase 报告/ADR/AGENTS/CLAUDE 与代码一致（本会话逐阶段
   核对+本审计抽查）。

## 19. Architecture Debt Register（Severity/可延迟）

| 项 | 严重度 | 可延迟 |
|---|---|---|
| **B-03 新用户 seed 虚构对话**（loadChats→seedChats，chatState.ts:67-77：任何新浏览器注入 3 条预置"历史"含罐头建议与 📄 预览） | **HIGH（真实用户 blocker 级）** | 至 REAL_USER 前（一行级修复，本审计未动） |
| 遗留设备本地虚构卡预览（E-2 前持久化 chat） | LOW | 是（设备本地） |
| demo 关键词映射/DEMO_CASES/演示模式残件（M5-B §19 清单） | MEDIUM | 是（Developer 面专属+双守卫锁定） |
| webui:mode legacy 键（已弃用未清） | LOW | 是 |
| finalize 演示分支 + finalAssistantText 内部措辞 | LOW | 是 |
| runtime_mode=demo/非 strict/json 后端（生产化配置差距） | MEDIUM | 至生产部署前（strict 将强制 weknora） |
| .env.example 无 weknora 模板段 | LOW | 是 |
| 诊断 llm 读取时序 | LOW | 是 |
| 未提交 span（28.A..E-7 全部代码） | **流程 HIGH** | 至 commit 授权（D-08） |

## 20. Blocker Register

```text
B-01 生产知识链缺失（HD-2 CONFIG_ONLY；当前 knowledge=mock）
    Severity: CRITICAL（对 REAL_USER/生产）
    Evidence: /api/diagnostics 自报；.env 变量名单；M5-C.2/C.1
    Impact: 一切"生产知识验证"不成立；mock 事实不可冒充生产
    Trigger: REAL_USER 开放/生产部署
    Workaround: 无（纪律禁止 mock promotion）
    Required: D-02；Phase: HD-2 配置
B-02 消费者数据隔离无法证明（无所有权模型；id 寻址+免鉴权读取）
    Severity: CRITICAL（多用户）
    Evidence: get_chat/runs 读端点无 ident 依赖（server.py:1215-1237
    等）；无用户概念
    Impact: 持 id 者可读他人对话/产物（IDOR 类）
    Trigger: 多用户/公网暴露
    Workaround: 单租户 loopback 部署
    Required: D-01（+D-05 关联）；Phase: 鉴权实现
B-03 新用户虚构对话种子（seedChats）
    Severity: HIGH（消费者信任/产品正确性）
    Evidence: chatState.ts:67-77
    Impact: 每个新用户首屏出现伪造"我的对话"
    Trigger: 任何真实用户首次访问
    Workaround: 无
    Required: Owner 决定移除/替换（属消费者产品决策；实现一行级）
B-04 数据治理未决（retention/access/deletion；ADR-024 BLOCKED 项）
    Severity: HIGH（合规/隐私，随真实用户数据出现而生效）
    Evidence: 28.0.5 决策冻结记录；无删除路径代码事实
    Required: D-06
```

## 21. Technical Debt Register（非 blocker）

§19 表列（demo 残件/legacy 键/演示分支/示例缺口/时序/未提交 span
流程项）；**严格区分**：仅 B-01..B-04 与未提交流程项影响发布门，
其余为可延迟债务。

## 22. Owner Decision Queue（重新验证后）

已解决移除：~~User-Space 面缺失~~（E 系列）~~虚构报告卡~~（E-2）
~~内部端点未设防~~（E-6）~~tripwire 日期~~（M5-C.2）。

```text
D-01 Consumer Authentication（A 匿名单租户 / B 认证消费者 / C CONSUMER
    角色）——因 B-02，多用户前必须决策
D-02 HD-2 WeKnora 生产配置（env 三变量+KB+strict 决策）——解 B-01
D-03 REAL_USER 授权（依赖 B-01..B-04 清障）
D-04 答案证据记号 consumer 化（提示词校准轨道；解 "authority: B"
    /catalog version 措辞）
D-05 Artifact 深链 opaque 寻址（可选增强；涉新契约+所有权）
D-06 数据保留/访问/删除政策（ADR-024 未决项）——解 B-04
D-07 永久 Full Authority（证据见 §13；缺真实用户样本）
D-08 commit/发布授权（未提交 span 22 tracked+新增文件）
D-09 M5 清理授权（独立阶段）
D-10 HTML/PDF 导出与 vision 措辞对齐（产品决策时顺带）
```

## 23. Release Gate Matrix

```text
G0  Architecture        PASS     单 Runtime/Registry/spine（B4 结构证明）
G1  Intent/Router       PASS     契约+确定性+fail-closed+权威实测
G2  Grounding           PASS     闭包门+D6+零不安全交付（全窗口）
G3  Artifact            PASS     view/download 实测；深链=DEFERRED 非门
G4  Consumer            PASS     E-1..E-7；泄漏 0/伪行为 0
G5  Security            CONDITIONAL（单租户可证；多用户 BLOCKED=B-02）
G6  Auth                CONDITIONAL（内部门 PASS；消费者模型未决 D-01）
G7  Knowledge Provider  BLOCKED  （HD-2；mock 不得冒充）
G8  Observability       PASS
G9  Rollback            PASS
G10 Real User           NOT YET VERIFIED（REAL_USER=0）
G11 Data Governance     PENDING （D-06/B-04）
G12 Test Coverage       PASS（含已文档化盲区清单 §17）
```

Verified 8 · Conditional 2 · Blocked 1 · Not Yet Verified 1 ·
Pending 1（G12 计 PASS 附盲区披露）。

## 24. Release Classification

**INTERNAL BETA**。Basis：Gate 矩阵（G0-G4/G8/G9/G12 PASS =
架构闭环+可验证+可演示+消费者面完整）∩（G7 BLOCKED+G10 NOT
VERIFIED+G5/G6 多用户条件+G11 PENDING = 不满足 RC/PRODUCTION 的
预置门槛）。DEMO 不成立（治理/等价/边界/消费者交付远超演示形态）；
RELEASE CANDIDATIVE 不成立（RC 定义需真实用户证据+生产知识链+数据
治理就绪）；PRODUCTION READY 不成立（上述全部+鉴权）。

## 25. Final Recommendation-Free Conclusion

```text
The following gates are verified: G0,G1,G2,G3,G4,G8,G9,G12
The following gates remain unresolved: G5/G6(conditional, D-01),
G7(blocked, D-02), G10(not verified, REAL_USER=0), G11(pending, D-06)
Therefore the current release state is: INTERNAL BETA.
Synthetic/scripted validation PASS（含 live LLM 全链）；
Real-user validation NOT VERIFIED；
TEST GREEN BUT PRODUCTION READINESS UNVERIFIED（知识链/隔离/治理）。
```

**View A — Engineering**：架构闭环 ✓ · Runtime 唯一 ✓ · Router
正确（确定性+权威+回滚）✓ · Grounding 安全（fail-closed 实证）✓ ·
Artifact 正确（真实事件门控）✓ · Consumer 隔离（三重边界）✓ ·
Tests 可靠（确定性层次厚实；盲区已披露）✓。

**View B — Product/Release**：可用=对话问答（知识/产品/规划/澄清/
拒答/报告查看下载）全链真实可用（live LLM；消费者面）· 依赖
Mock=**全部保险知识内容**（governed mock——形态真实、事实非生产）·
依赖 Owner 配置=生产知识链（HD-2）、鉴权、限流、strict 生产模式 ·
尚未验证=真实用户一切行为 · 阻止真实用户=B-01/B-02/B-03/B-04。

## 26. Evidence Index

```text
治理：PRODUCT_VISION/ARCHITECTURE_PRINCIPLES(28.0.4) · 决策链
  28.0.3/28.0.5 · ADR-019..025（docs/adr/）
Intent/Router：28.A-0/A-1/A-2 报告 + schema/ + shadow 实测（本会话）
Slice/等价：28.C-1/C-2 · B4(17/17) · B6(基线+tripwire) · D(M3) ·
  M4(9/9) 报告 + tests/runtime/test_p28*
灰度/实测：B5/B5.1 · M5-A/B/C/C.1/C.2 报告 + tmp/ 探针记录
消费者：E-0..E-7 报告 + web/src（route/shell/consumerView/activity/
  测试）+ tmp/e7-journey*
安全：runtime/auth.py + tests/runtime/test_e6_space_api_boundary.py
  （5）+ test_p0_r06.py + 消费者 DOM 泄漏测试
本审计新鲜验证：backend battery（BATTERY_FINAL 见 §2 复跑）· web
  207+2 · tsc · git（零新改动）· :8000 停止事实 · router_authority
  默认复核 · seedChats 代码事实
```

---

```text
Phase 28 Final Production Readiness Audit

Audit Status: CONDITIONAL（审计本身完成=PASS；被审计对象含
             BLOCKED 门 → 系统状态 CONDITIONAL）
Code Changes: NONE · Architecture Changes: NONE
Verified Gates: 8 · Conditional: 2 · Blocked: 1 · Not Yet Verified: 1
               · Pending: 1
Critical Blockers: B-01 知识链(mock/HD-2) · B-02 数据隔离 ·
               B-03 新用户虚构种子 · B-04 数据治理
Current Release Classification: INTERNAL BETA
```
