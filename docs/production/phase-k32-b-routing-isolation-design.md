# K.32-B · FlashX Routing Isolation Implementation Design Audit

## 1. Status

**DESIGN_READY**（最小方案明确可实施；遗留项为 rollout 政策类非设计阻塞）。

## 2. Current Routing（代码实证·零 drift）

```text
config.py:121 to_provider(fast) ── server.py:528 构建 fast_provider
  ├─ agent.py:77   step==1→provider(glm-5.3)；step2+→fast_provider   [C1/C2]
  ├─ server.py:813 QA 切片 provider=fast_provider or provider         [C3/C4]
  └─ server.py:644 intent 候选 make_candidate(fast_provider or …)     [C5·关闭]
qa_agent/agent.py:162 build_gateway(provider) → C3 首试与 C4 重生成共用
同一 gateway/同一模型（generate_grounded 内 attempts 循环）。
```

## 3. C2/C3/C4 Separation Point

| Class | Entry Point | 现行模型 | 可区分 |
|---|---|---|---|
| C1 | agent.py:77 step==1 分支 | glm-5.3 | YES |
| C2 | agent.py:77 else 分支 | glm-5.3-flash | YES |
| C3 | server.py:813 → gateway.generate_stream | glm-5.3-flash | YES（单一调用点） |
| C4 | 同 C3 gateway 内 attempt 循环 | 同 C3 | YES（随 C3） |

**区分点=server.py:813 一处调用点**——无需任何 classifier/新抽象。

## 4. Minimal Isolation Design

在**既有 configuration boundary** 加第三个模型槽（Option A·env-based）：

```text
LLM_MODEL      → C1（不变）
LLM_FAST_MODEL → C2（不变机制）
LLM_QA_MODEL   → C3/C4（新增；默认空）
```

- `config.py`：LLMConfig 增 `qa_model` 字段 + `pick("LLM_QA_MODEL")` +
  `to_provider(qa=True)`（model 解析链 `qa_model or fast_model or model`）
  + `describe()` 暴露 qa_model（/api/agent/config 契约缝复用）。
- `server.py`：`_agent_worker` 构建 `qa_provider`（仅当 cfg.qa_model 与
  fast 不同）并在 :813 改为 `provider=qa_provider or fast_provider or
  provider`。C5（intent 候选）不接 qa 槽，维持 fast——行为不变。

## 5. Fallback / Retry Impact

Step2+ flashx 失败：**B（同模型有界重试）**→耗尽 needs_review fail-closed
（agent.py 现行；K.28-K.31 实测 0 触发）。QA flash 失败：gateway 同模型
重试（max_retries=1）→ llm_unavailable 诚实拒答。**跨模型 fallback 不
存在（NOT CURRENTLY AVAILABLE），本设计不新增。** C4 重生成随同一
gateway 自动留在 QA 槽 → **NO SEMANTIC CHANGE EXPECTED**（seam 只改
"哪个 provider 对象被构造"，gateway/重试/门内部零触碰）。

## 6. Observability Impact

C2 路径 `agent.llm_call` 带 model 字段 → flashx/flash 直接可区分
[EXISTING]。已知小缺口：QA 路径 obs `llm.call` 的 model 字段为空
（K.31-A 记录）——实施时可选 1 行（generate_grounded 的 LLMRequest 填
model）补齐 QA 归因；不补则以 /api/agent/config 契约承担归因。
**不做任何 observability architecture change。**

## 7. Default / Rollback Safety

默认（不设 LLM_QA_MODEL）：qa 解析链回落 fast → **行为与现在逐字节
一致**。Rollout 配置：`LLM_FAST_MODEL=glm-5.3-flashx` +
`LLM_QA_MODEL=glm-5.3-flash`（两者须同显式设置；缺失 QA env 时 QA 随
fast=flashx——即 K.32 已记录的"同行"行为，非意外新模型）。启动安全：
env 缺失回落 .env（K.31-A 实证）。

**Rollback**：撤 `LLM_FAST_MODEL` 覆盖+重启 → step2+=flash·QA=flash
（QA env 同时失效无害）。Rollback scope=fast 槽（step2+）；
requires code deploy：NO（seam 发布后）；env/config change：YES。
K.31-A 已实操演练同型回退（分钟级）。

## 8. Minimal Diff

```text
Files likely to change:
1. runtime/agent/config.py（~12 行：字段+pick+to_provider(qa)+describe）
2. runtime/server.py（~5 行：qa_provider 构建+:813 传参）
3. tests/runtime/test_agent_config.py（+3-4 契约测试）

Files that MUST NOT change: agent loop / gateway / grounding loop /
provider 实现 / frontend / SSE / WeKnora / prompt / retry / schema。
```

Option A（上述 env 缝）vs Option B（结构化 routing abstraction）：
B 改动面/测试负担/架构影响全面更大且引入新抽象，违反 frozen
architecture 最小 diff 约束——**Option A 符合**。

## 9. Implementation Scope

IN：qa_model 配置槽 + :813 选择 + 契约/回滚/默认测试 +（可选）QA
llm.call model 字段 1 行。OUT：FlashX 生产 rollout·percentage canary·
QA FlashX 切换·prompt/retry/provider/frontend 改动。

## 10. Test Plan（设计·不实施）

- T1 默认配置保持现行行为（qa→fast 回落）[test_agent_config 扩展]
- T2 fast 槽变更仅影响 step2+（:77 分支回归）[EXISTING：K.30 obs 测试]
- T3 设 LLM_QA_MODEL 后 QA 走独立模型 [新契约测试]
- T4 撤 env 恢复 flash（回滚）[新契约测试]
- T5 agent.llm_call 记录真实 model [EXISTING：K.30 测试]

## 11. Open Decisions（非设计阻塞）

① env 命名定稿（LLM_QA_MODEL 建议）②QA llm.call model 字段是否随
seam 一并补 ③seam 发布与 Stage 1 金丝雀的先后（K.32 §8 既存决策）。

## 12. STOP

**PRODUCTION CODE CHANGE: NONE · DESIGN READY · STOP（时限内）。**

---

## K.32-C Implementation Result

Status: COMPLETE

Changed:
- runtime/agent/config.py（qa_model 字段+resolved_qa_model 属性+to_provider(qa=)+describe()+pick；本阶段净增 ~20 行）
- runtime/server.py（QA 调用点 _qa_provider 缝 ~15 行：qa_model 设置时 to_provider(qa=True)，否则原 fast 回落；fail-quiet）
- tests/runtime/test_agent_config.py（T1-T4 契约 + describe 键集契约更新；12 passed）

Routing（Case A/B/C 实测验收）:
Default（.env 现行）:      Step1→glm-5.3 · Step2+→glm-5.3-flash · QA→glm-5.3-flash ✓
FlashX candidate（env）:   Step1→glm-5.3 · Step2+→glm-5.3-flashx · QA→glm-5.3-flash ✓
Rollback（env）:           Step2+→flash · QA→flash ✓

agent.py/provider/retry/QA logic/citation gate/observability：零改动。
（server.py/config.py 的 git diff 大数字=未提交的 K.25-K.32 累计 span，
本阶段净增量如上。）

Tests: pytest tests/runtime/test_agent_config.py → **12 passed**（14.6s）

Production rollout: NOT PERFORMED
Production default: UNCHANGED（.env 未触碰；LLM_QA_MODEL 未设）

PRODUCTION CODE CHANGE:
Implementation exists, but production configuration/default behavior unchanged.

STOP
