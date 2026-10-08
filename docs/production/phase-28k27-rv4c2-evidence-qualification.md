# K.27-RV4-C2 · QA Evidence Relevance Qualification（P1-B Phase 1）

Date: 2026-09-29（续 2026-09-28 被截断会话）· Status: **PASS
（offline 全绿）· LIVE_VERIFICATION_PENDING_OWNER_RESTART**

## 0. Session Continuity Note

本阶段为**续作**：上一会话在实施中途被截断（代码/配置/测试已落盘，
无报告/无 ADR 附裁决/无簿记）。本会话经 Owner 两项裁决（判定法=
词项重叠；ADR 附裁决两处都写）后续作完成：新鲜验证 + ADR 附裁决
+ 本报告 + 簿记。落盘代码经全量重验（见 §5），非盲信。

## 1. Step 0 — Product Alignment

- **用户价值**：消费者的 QA 回答不再出现「无关法规被系统标为
  权威依据」（RV4-A 实例：家庭规划补充问题 → 农业保险条例成为
  [E1] 唯一依据）。错答变为诚实拒答（insufficient_evidence）。
- **Chat experience**：直接增强——QA 切片是 Chat 面核心回答路径。
- **Space**：User Space。
- **Agent ownership**：knowledge-qa 切片（ADR-021 registry slice，
  非 Agent runtime）。

## 2. Step 1 — Architecture Check

- 复用既有 Runtime：过滤器位于既有 QA 切片证据组装层内部（
  qa_agent/agent.py），零新系统、零新 schema（evidence_refs 仅
  数量可减、结构不变）、零新事件类型。
- ADR 对齐：本阶段写入的 **ADR-022 附裁决 B** 正是本修复的授权
  依据（RetrievedEvidence≠QualifiedEvidence）；ADR-019 附裁决 A
  同时追认已上线的 C1。fail-closed 方向（少答优于错答）。
- 漂移哨兵：零触碰（不涉 developer 功能/重复运行时/无证据 LLM/
  workflow 泄漏）。
- 架构影响检查：qa_agent 为 registry 切片（ADR-021），非
  orchestrator/agent 执行/router/artifact 生命周期——无
  Architecture Impact。

## 3. What Was Built（设计=RV4-B §6 P1-B·逐条兑现）

| 件 | 内容 |
|---|---|
| `runtime/qa_agent/agent.py` | `_bigrams()`（CJK-only bigram·数字/拉丁/标点剔除）+ `_qualified_evidence()`（query↔证据内容+source 文本 bigram 交集 ≥ 阈值，去通用停用表）+ 组装前接线（**溯源记录之后**——retrieval.allowed_hits 保留治理语义） |
| `config/qa-grounding-rules.yaml` | `retrieval.qualification`：`min_query_bigram_overlap: 2` + `generic_bigrams` 停用表（保险/个人/公司/业务/我们/可以/以下/相关）——Owner 可调 |
| `tests/runtime/test_k27rv4c2_evidence_qualification.py` | 8 节 19 检查（§5）·证据全部取自**真实治理试点语料** knowledge/pilot/documents/ |
| `docs/adr/ADR-019` 附裁决 A | conversation continuation 语义（追认 C1·topic-switch 边界·歧义 fail-closed·V0.1 内存边界） |
| `docs/adr/ADR-022` 附裁决 B | Retrieved≠Qualified + presence≠support + user-fact 免引 + product_qa 同类边界记录 |

**语义关键点**：
- 全落选 → 复用**既有** insufficient_evidence 拒答（零新拒答路径、
  零新文案）。
- 过滤发生在重试/重生成**之前**——两次 attempt 收到同一已过滤集合，
  不可经重试重扩张回原始检索（R5 实证）。
- 阈值 0 / 退化 query（仅通用词）= 直通——回滚旋钮 + 防过度过滤。
- gate.py / grounding/loop.py / router / planning / WeKnora / 治理
  R1-R9 / web：**零触碰**（设计 §7 NOT 清单全遵守）。

## 4. Calibration（阈值=2 的实证基础）

- RV4-A 真实案例（规划补充文本 × 农业保险条例 chunk）：非通用
  bigram 交集 < 2 → 被滤（R1/bigram 单元契约双重断言）。
- 真实相关案例（「重疾险的等待期是什么」× 健康保险管理办法等待期
  chunk）：≥ 2 → 通过（R2·grounded 路径保持）。
- 混合检索仅保留相关项（R3）。阈值外置可调——后续真实流量若现
  过度过滤，Owner 调参即可（无需改码）。

## 5. Validation（本会话新鲜运行）

- 专项：`test_k27rv4c2_evidence_qualification.py` standalone
  **19/19 ALL GREEN**。
  - R1 RV4 案例拒答（gateway 零调用·零 E1）· R2 相关通过 ·
    R3 混合仅留相关 · R4 零检索不变 · R5 重试不可绕过（两 attempt
    证据集逐字节相同）· R6 拒答文案零 [E · 阈值 0=回滚直通 ·
    bigram 单元契约（数字/拉丁/标点剔除实证）。
- 全电池：`python -m pytest tests/runtime tests/contract -q` →
  **865 passed + 2 skipped**（447s；C1 基线 857+2 → +8=C2 新增；
  K.26 流式 / K.27-S1 单写 / 既有 QA / planning / intent golden /
  安全九零全含且绿——零回归）。
- DoD 对照（RV4-B §8 Evidence 节）：无关→拒 ✓·相关→qualified ✓·
  user-fact 不强贴 ✓·retry attack ✓；citation-only attack=
  Phase 1 显式不拦（附裁决 B 裁定 2·Phase 2 影子先行）。

## 6. Boundaries & Known Gaps（如实）

1. **product_qa 同类边界**：product_qa_agent 未解析产品路径
   （match is None → items 直通 [E#]）为同类组装且无本过滤。该切片
   DEFAULT OFF（28.C-0）；启用决策（28.C-5）须同步套用（ADR-022
   附裁决 B 已记录）。
2. **claim-support 语义未做**（Phase 2）：引用门仍是存在性门——
   资格下限消除了「无关证据进场」面，未建立「引用句确被证据支持」。
3. **词项重叠的语义盲区**：同义改写（query「重疾」vs 证据「重大
  疾病」）可能被滤 → 诚实拒答（fail-closed 方向·可接受·真实流量
  观察后调参或升级判定法）。
4. **LIVE 未生效**：pilot :8123 跑 C1 代码；C2 生效需 Owner 授权
  重启，随后以 RV4 原两轮复放验证（预期 T2 走 planning——C1 已证；
  若再落 QA 则农业条例场景应拒答而非 grounded）。

## 7. Rollback

`min_query_bigram_overlap: 0`（或删 qualification 块）→ items 直通
= C2 前行为（R6' 旋钮测试锁定）。无需回滚代码。

## 8. Next（Owner）

①授权 :8123 重启 + RV4 两轮真实复放（live 复证）②观察期真实
  QA 流量的拒答率变化（G-1 语料线叠加观察·过度过滤信号=阈值调参）
  ③28.C-3R 仍被 JWT env 阻塞（如已取得请以该 env 重启会话）
  ④D-08 commit span 继续扩大（34+ modified·134+ untracked）。
