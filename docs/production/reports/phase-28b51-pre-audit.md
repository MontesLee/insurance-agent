# Phase 28.B5.1 Pre-Audit — 模型适配校准（只读 + live trace 复现）

Date: 2026-09-25 · 性质：Phase 0 只读审计 + **真实调用链复现**（probe：
live glm-5.3-flash 经真实 gateway/证据组装，原始输出+门判定落
tmp/b5/probe-pre.json）。禁止猜测——以下每条均有代码行号或 trace 支撑。

## 1. Citation 链路（代码+trace 实证）

链路：`SYSTEM_PROMPT（qa_agent/agent.py、product_qa_agent/agent.py 内联
常量）→ 证据块（loop.py evidence_block：[E1] source:… 内容）→ live 模型
生成 → gate.check（grounding/gate.py：分句→事实句（38 词表）须**句内**
含 \[E(\d+)\] → 违规即拒（一次再生成）`。

### 复现结果（B5 两失败，原始输出已捕获）

| 场景 | 墙钟 | 门判定 | **真实失败模式（原始输出可证）** |
|---|---|---|---|
| B 具体产品 | 19.0s | 5 句中 4 句 fact_sentence:no_citation | 模型输出**要点式分析、全部事实句零 [E#] 标注**，且出现违规桥接："按品类通用规则**推测**约为 30 天"——证据在上下文（目录 E1+链接 E2）而模型**摘要化转述而非逐句引用** |
| F 知识问答 | 11.6s | 5 句全部 no_citation | 模型用了**全角括号（E1）（E2）**而非 ASCII 方括号 [E1][E2]——gate 正则 `\[E([0-9]+)\]` 只认方括号；内容本身与证据一致 |

**归因（taxonomy）**：B=missing citation placement + unsupported
speculation framing；F=format mismatch（全角括号）。**均非 evidence
availability 问题**（两案证据均充足且内容被模型正确转述）。均非 gate
缺陷（gate 正确拒了不合规输出——fail-closed 工作正常）。

### 修复方向（Phase 2）
Prompt 侧最小校准：显式 `[E1]` ASCII 格式契约（禁 （E1）/【E1】）、
逐句引用的 VALID/INVALID 示例（含要点式反例）、禁"推测"桥接、无据必
拒答。**不动 gate**。

## 2. Timeout 链路（代码实证）

```
rules generation.timeout_s=30（config/qa-grounding-rules.yaml）
  → build_gateway（grounding/loop.py）LLMGateway(timeout_s=30, max_retries=1)
  → gateway.generate：request.timeout_s=min(30,30)=30 ……
  → 【断点】_GatewayProviderAdapter.generate **忽略 request.timeout_s**，
    直调 inner.generate（runtime/agent/model.py OpenAICompatProvider
    构造器 httpx timeout=60s——与 gateway 预算无关联）
  → httpx 60s 为 per-read 超时：慢滴流响应可远超 60s 总墙钟
  → 重试：gateway max_retries=1 → 2 次尝试，**无总预算上限**
  → 耗尽 → LLMError → llm_unavailable 拒答（fail-closed ✓，B5 E 案
    AnswerContext/无 artifact 均已验证正常）
```

**E 案 174.6s 算术**：2 次尝试 × ~87s/次（慢滴流不触发 per-read 60s）
≈ 174.6s ✓——**timeout 设置过大 + 适配层未执行 gateway 预算 + 无总
上限** 三因叠加；非"单次 provider latency"单一原因。

### 修复方向（Phase 3）
① 适配器**执行** request.timeout_s（线程看门狗 → llm.types.TimeoutError
 (retryable)，gateway 既有重试策略自然接管）——这是让**既有外置规则
 真正可执行**的最小接线修复（llm_candidate 已用同款看门狗模式）；
② 外置参数校准：timeout_s 30→**60**（证据：D 案合法成功生成 ~50s，
 30s 会误杀；60s 不是"用更长 timeout 掩盖失败"——是容纳已实证的
 合法慢成功上限）+ max_retries 保持 1 → **总预算有界 ≈120s+开销**
 （修复前无界）。

## 3. 现有 prompt/rules 外置状态

两 SYSTEM_PROMPT 目前为**代码内联常量**（qa_agent/agent.py /
product_qa_agent/agent.py）——**无外置 prompt 文件**。按 spec"优先外置
文件"原则：将 prompt 文本移入**既有规则文件**（qa-grounding-rules.yaml
/ product-qa-rules.yaml 的 generation 段，prompt_version 同步升 v2），
agent 改为从规则加载（仅此一处代码接触，不碰 Router/Orchestrator/
Registry/Artifact/Event/Spine）。

## 4. B4 / B5 复测面

- B4 golden 用**脚本化答案**（MockLLM/FakeLLM）——prompt 变更不影响
  脚本输出与门判定；适配器看门狗对 mock（即时返回）无影响。预期
  GREEN（重跑验证，绝不改 comparator/normalizer）。
- B5 重测：同 provider/model/场景/夹具/环境/请求形态（独立实例
  8106、flag=1、live glm + mock 治理知识）。沿用 INSUFFICIENT LIVE
  SAMPLE 纪律（脚本注入流量）。

## 5. STOP 边界核验

所需改动=两规则文件 + 两 agent 模块的 prompt 装载 + 适配器看门狗
（runtime/grounding/loop.py）——**均不在禁改清单**（不碰 ADR/权威/
M3/Router ownership/Registry/Orchestrator/Spine/artifact/approval/
gate 语义/事件词汇；不删 fail-closed；不放宽门）。若实施中超出此
范围即 HARD STOP。**判定：GO。**
