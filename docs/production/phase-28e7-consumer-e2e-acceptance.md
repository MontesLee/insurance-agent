# Phase 28.E-7 — Consumer End-to-End Acceptance 报告

Date: 2026-09-26 · E-4..E-7 连续授权收官验收。E-7 自身改动：1 处
消费者文案最小修复（Journey F 发现的缺陷）+1 测试。

## Status

```text
E-7 STATUS: PASS
（E-4 PASS · E-5 PASS · E-6 PASS · E-7 PASS → Consumer Surface
Completion — PASS）
```

## Objective

证明消费者可完整使用产品而不接触内部 Runtime：六旅程实测 +
全 DOM 泄漏扫描 + 全量回归。不为验收重构。

## Consumer Journeys（live 实测，全部经真实浏览器）

| Journey | 探针/路径 | 结果 |
|---|---|---|
| A 知识 QA | 「百万医疗险的免赔额是什么意思？」→ :8000 Owner 灰度 | **PASS**：✓已理解→●正在为你分析→terminal 已完成；本轮为 citation 诚实拒答（已知 model-fit）——无伪报告、无内部码 |
| B 产品 QA | 「P001 的等待期是多久？」 | **PASS**：grounded——目录无等待期字段→不做条款断言[E1]+类别通识 30 天[E2]（明示非条款值）+建议以条款为准；前端层泄漏 0 |
| C 规划 | 完整家庭信息 → planning | **PASS**：进入管线（已了解家庭基本情况）后转入澄清（专业 5 问：社保/已有保单/预算/健康/收入比例） |
| D 澄清→续答 | 同 chat 续答 5 问 | **PASS**：已分析保障需求→已识别家庭风险→已分析保障缺口→已设计保障方案→**分析报告已生成**→已完成 + **真实报告卡→Modal 真实内容→下载可用**（Modal 泄漏 0） |
| E 拒答 | 「长生不老保XYZ…值得买吗？」 | **PASS**：「知识库暂无可靠依据，暂时无法回答…换个说法再问」（目录缺失 fail-closed；本轮零卡） |
| F 错误 | 隔离 :8121（NO_DOTENV 无 LLM）+ 临时 vite :5273 | **发现缺陷→最小修复→PASS**：原 503 横幅透传后端原始 detail（LLM_PROVIDER/API_KEY/Demo Mode 等内部词）→ 固定消费者文案「暂时无法回答：智能服务暂时不可用，请稍后再试。」（live 复证 + 单测） |

## 全 DOM 泄漏扫描（§39 清单 × 各旅程快照）

```text
前端层（chrome/组件/属性/aria）：run_id/case_id/artifact_id/eval_id/
approval_id/agent id/router/registry/knowledge-search/stage id/
KnowledgeService/WeKnora/LLMGateway/provider/model/prompt/QA_REFUSED/
WAITING_USER/slice/authority/trace/debug/evaluation/approval/runtime = 0
```

**记录两类非前端层发现（未修改，Owner 校准项）**：
1. **答案内容记号**（Journey B）：governed 答案文本含证据分级/元数据
   记号（"authority: B"、"catalog version 0.1, product_version 1.0"）
   ——提示词（product-qa-answer-v3）措辞所致；前端不得改写已交付
   事实文本；属提示词校准轨道（同 B5.1，Owner 决策）。
2. **遗留持久化数据**：E-2 前旧会话的侧栏虚构报告预览仍可见
   （用户数据未动；新轮零产生）。

## Space / Capability Acceptance Matrix

| Capability | Consumer | Operator | Developer |
|---|---|---|---|
| Chat | PASS | — | — |
| Activity | PASS（DTO 语义） | internal | internal |
| Answer | PASS | PASS | PASS |
| Artifact | PASS（真实事件门控+Modal+下载） | PASS | PASS |
| Review/Approval | hidden | PASS | PASS |
| Trace/Eval/Debug/Inspector | hidden | limited | PASS |
| Runtime IDs/Raw Events/Agent IDs | hidden | allowed | allowed |

路由边界（#/chat 消费者 fail-safe 默认；#/operator/* · #/developer/*
内部直达可用——E-1 测试 13 项维持绿）；API 边界（E-6 端点角色门
734 内含 5 项 + 前端源扫描 2 项）。

## Regression（最终矩阵）

```text
backend: 734/734（E-6 后基线；E-7 仅 web 改动，battery 复跑确认）
web:     207 passed + 2 skipped（E-6 基线 206+2 +1 banner 测试）
tsc:     PASS clean
B4/M4/M3: 含于 734 全绿
E-2/E-3/E-4/E-5/E-6 套件: 全绿（含于 207）
Architecture invariants（§45 清单 30 项）: 30/30
```

## Files Changed（E-7）

```text
M web/src/components/chat/ChatLayout.tsx（503 横幅消费者文案——不透传 detail）
A web/src/components/chat/agentUnavailable.test.tsx（+1）
```

## Performance / Accessibility 检查

无重复轮询/重连风暴（SSE 单流+游标；Modal 取回一次）· 新增
aria-label 全消费者文案（下载报告/关闭报告/Modal 标题）· 无 id 入
aria（测试断言）。

## Deferred

消费者鉴权模型（Owner）· artifact 深链（opaque 寻址需授权）·
HTML/PDF 导出（后端契约）· 答案内容记号校准（提示词轨道）·
会话持久化后端 · REAL_USER（未开放，需独立授权）。

## Owner Decision Required

① 消费者鉴权模型（公开 chat vs CONSUMER 角色）② 答案证据记号
consumer 化的提示词校准授权 ③ artifact 深链/导出后端契约 ④
REAL_USER（独立授权）⑤ 既有队列（HD-2/citation/M5 遗留）。

## Final Gate

```text
E-7 STATUS: PASS
Consumer Surface Completion — PASS
```
