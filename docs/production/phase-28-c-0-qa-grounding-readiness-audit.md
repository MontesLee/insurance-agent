# Phase 28.C-0 · QA Agent + Grounding Readiness Audit（再审计）

Date: 2026-09-28 · 只读·15 分钟时限·零改动。

## Status

**28.C-0 READY_WITH_BLOCKERS**（QA 执行路径已建成且生产在跑——历史
28.C-0/C-1/C-2 已完成；进入"产品可用"的真实阻塞=G-1 双因子，属语料+
校准轨道，非架构缺失）。

## 1. Current QA Execution Path（本会话反复实证）

```text
user msg → POST /api/chats/{id}/messages（server.py:1574）
→ intent 层（rules-only·intent_classified 0-16ms）
→ 切片判定（server.py:796-851）：insurance_qa/product_qa/规划/legacy
→ QA 路径 run_qa_turn（runtime/qa_agent/agent.py）
   ①输入契约校验（intent+clarify）
   ②KnowledgeService.build_evidence（knowledge/service.py:361）
     → WeKnoraLiveProvider.search（127.0.0.1:8080·~4.3s/次）
     → 治理（govern_search_result·K002 只放行受治命中）
   ③冲突→确定性双陈；否则
   ④generate_grounded（grounding/loop.py）→ LLMGateway.generate_stream
     （治理链+句级引用门流式[K.26]·attempts≤1+max_regen=1）
   ⑤citation gate 终判（grounding/gate.py check）
→ qa_answered 事件 + _finish_run 单写 transcript（K.27-S1）
→ 前端：K.20 流式气泡+K.29-A 输出盒；无 QA 专属卡片
```

## 2. QA Agent Boundary

**不存在独立 QA Agent runtime——存在的是 ADR-021 registry 中的一个
first-class 切片**（insurance-qa-agent）经 Intent Router 裁决派发
（ruling D4），与规划/legacy 共享同一 runtime/gateway/事件总线。
这是设计使然（One Runtime 原则），非遗留债务。

## 3. QA Artifact / Card Current State

- 无 QA artifact schema/卡片。QA 终态=普通 chat 消息（K.20 气泡+transcript）
- run_dir 落 `qa-answer-context.json`（审计文件·非 registry artifact·前端不消费）
- artifact registry 仅服务规划链（9 类产物）
- **判断（A）**：按 Product Vision（Chat is the Product Surface），
  知识 QA 的正确契约=chat answer；QA artifact/card **非必需→Deferred**
  （仅当需要"可下载回答记录"时再立项，避免重复 schema）
- **判断（C）**：若未来需要，最小契约=answer+grounding_status+
  evidence_refs[]+provenance——恰好是 qa-answer-context.json 已有字段，
  无需新 schema 设计

## 4. Grounding / Citation Gate（代码实证）

gate.check（gate.py:82）：逐句判定——`is_fact_sentence`（:76）= 句含
**~40 个保险域 fact_markers 之一**（医疗/重疾/免赔/续保/等待期/保额/…）
即视为事实句，必须句内含 `\[E\d+\]`；违例词表 4 类；max_regenerations=1。
门本身按 ADR-022 fail-closed 正确实现（测试 6/6 绿）。

## 5. G-1 Root Cause（多因子·代码+运行证据）

K.28/K.31-A/K.34 实测存在**两种不同签名**，历史统称 G-1：

- **A 型（零命中）**：主流概念题（如"医疗险和重疾险区别"）→ WeKnora
  vector_search 0 命中 → insufficient_evidence 快拒（4.3s·无 LLM）。
  根因=**语料覆盖**（HD-2 KB 仅 10 部真实法规；概念对比类内容缺位）
  [MEASURED×3 场景]
- **B 型（门败拒答）**：检索有命中→生成流式（句级门多数过）→**终判
  fact_sentence:no_citation**（含 marker 词但缺 [E#] 的句子）→ 重生成
  仍败→citation_gate_rejected。根因=**模型引用纪律×门严格度的校准**
  ——marker 词表宽（"保险/医疗"级泛词也触发事实句判定），flash 模型
  在过渡/总结句上常漏引 [CODE-EVIDENCE: gate.py:76 fact_markers +
  K.28 B 3/3、K.31-A 4/4 同签名]
- 结论勾选：**多因素**（语料覆盖 + 引用校准）；非 gate bug、非
  extraction bug、非 schema 问题
- **G-1 阻塞 28.C？**：阻塞"产品可用性"（用户在主流问题上得到拒答）
  ——是 28.C 剩余工作的核心；不阻塞架构（链路完整正确）

## 6. Product Catalog Dependency

| 项 | 现状 | QA 是否依赖 | 阻塞 28.C | 最小解决 |
|---|---|---|---|---|
| Product Catalog | **机制在库**（28.C-2：catalog E1 锚+D6 守卫+attribute-grounding 规则），切片 DEFAULT OFF；数据=demo 目录 | 仅 product_qa 切片依赖；**知识 QA 零依赖** | 否 | Owner 决策开启+灰度（B4 式） |

产品推荐能力属规划链（product_candidate_provider·已运行）；**不混入
普通知识 QA**（边界正确·无泄漏：K.28-K.36 无跨链路由证据）。

## 7. HD-2 KB Dependency

已解决（28.H）：真实 WeKnora KB insurance-pilot-2（10 部真实法规）+
PG registry + 启动预检。QA 依赖其**内容覆盖**（A 型根因）——是数据
轨道非工程阻塞。

## 8. QA vs Planning Boundary

意图层确定性路由（insurance_qa vs insurance_plan）+ authority 全量灰度
（full）下实测边界干净：本会话 40+ 真实 run 无 QA↔planning 泄漏；
规划链内 knowledge-search 工具走同一 KnowledgeService（治理一致）。
QA 不消费产品推荐数据 ✓。

## 9. Provenance.model Debt

位置：`grounding/loop.py` `gctx.refused(...)` 两处（llm_unavailable /
citation_gate_rejected 路径硬编码 `"model": ""`；28.C-1 起预存；
grounded 路径正常携带 resp.model）。1 行 housekeeping，非 28.C 耦合。

```text
DEFERRED: provenance.model refused-path fill（K.32-B 已列·Stage 1 期顺手）
```

## 10. Minimal Phase 28.C Implementation Plan（剩余·非重建）

历史 28.C-0/C-1/C-2 已交付。剩余最小三段：

**28.C-3 · G-1 语料覆盖（A 型）**——目标：主流概念题命中率。
范围：WeKnora KB 内容补充（概念对比/区别类文档）+ 命中率回归探针。
非 production code（数据+探针脚本）。验收：A/B 类问题 grounded 率>0。
不做：不改检索算法/不改门。

**28.C-4 · 引用校准（B 型）**——目标：门败拒答率下降。先测量后决策：
落违规分布观测（哪类 marker 句失败）→ 再在 {prompt 引导强化·marker
泛词收窄（gate 规则=政策决策）·QA 模型档位（flashx 纪律未测）} 中选。
范围：测量=纯观察 1 处；修改=Owner 裁决后。验收：同题 grounded 率
提升且无无引文事实句漏网。不做：不放宽 ADR-022 fail-closed。

**28.C-5 · product_qa 切片启用决策**——Owner 决策+灰度方案（机制已备）。

## 11. Blockers

- B-G1（数据）：KB 概念类语料缺位（A 型）——28.C-3
- B-G1'（校准）：引用纪律×门校准（B 型）——28.C-4·含政策决策点
- B-DEC：product_qa 启用（Owner）——28.C-5

## 12. Deferred Work

QA artifact/card（chat 契约足够）·provenance.model 1 行·QA llm.call
model 字段（同族 1 行）·C 早澄清产品决策（K.31-A 起）。

## 13. Evidence

本会话实测链：K.28（B 型 3/3+token 佐证）·K.31-A（QA 探针 2/2 同签名·
5.7-9.2s vs flash 12-18s）·K.34（B 型执行级归因）·K.36（零 drift）；
代码：gate.py:76/82·loop.py refused 路径·qa_agent/agent.py·
product_qa SLICE_ENV；测试：test_k22_qa_streaming **6 passed**（0.4s）。

## 14. Final Recommendation

28.C 剩余工作=**数据与校准，不是工程重建**。顺序：28.C-3（语料·直接
消 A 型）→ 28.C-4（先观测违规分布再裁决校准手段）→ 28.C-5（product_qa
启用决策）。QA artifact 维持 chat 契约（Deferred）。
