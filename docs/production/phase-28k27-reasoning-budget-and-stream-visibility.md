# 28.K.27 — 浏览器端「提问后看不到 streaming delta」根因与修复

日期：2026-09-28 · 分支：本地工作区（未提交） · 相关：28.K.17 / K.20 / K.21 / K.22 / K.24 / K.26

用户报告：**「浏览器端，向 agent 提问超过 30s 了，没有看到任何 streaming delta。」**

> 本文只记录取证与最小修复，不改动既有流式架构、事件 schema、Agent runtime 或 LLM gateway。

---

## 1. 现象与初步误判

浏览器 console 报出：

```
:5273/api/runs/run_86061c15417b403b        404
:5273/api/runs/run_86061c15417b403b/events 404
:5273/api/runs/run_86061c15417b403b/stream?after_event_id=evt_000016&key=… 404
```

用**浏览器同款 key** 直接复现（`?key=`／`Authorization: Bearer`）：

```
GET /api/consumer/whoami            → 200 {"subject":"consumer:pilot-user-02","role":"CONSUMER"}
GET /api/runs/run_86061c15417b403b  → 404 {"detail":"not found"}
```

鉴权通过而 run 返回 404 ⇒ **不是鉴权/代理问题**。这三个 404 属**既有设计**：
`runtime/server.py:1205 _run_owner()` 对「不在内存 registry 中的 run」取不到 owner，
`_consumer_read_guard()`（1174-1193）对 consumer 一律 **uniform 404**（D-API-1 防枚举）。
`/api/health` 当时 `bus.runs=2`，那个 09:30 的老 run 必然 404。
**它们不是本次故障的原因**，只是页面在恢复一个已过期会话。

---

## 2. 真实根因（两层，均有硬证据）

### 2.1 第一层：delta 一直在流，但流的全是 `reasoning`，前端按设计全部丢弃

挂到用户当轮的真实 run 的 SSE 流上**实测 90 秒**（只读，未产生任何 product 流量）：

```text
event_counts = {"run_started":1, "intent_classified":1, "agent_step_started":1,
                "agent_step_error":1, "agent_stream_delta":4418}
delta_kinds  = {"reasoning": 4418}          ← 4418 条，content = 0
```

- `web/src/state/runReducer.ts:206`：`if (e.data["kind"] === "reasoning") return;`
  —— 28.K.20 / E-2 安全规则：**reasoning（CoT）永不进入可展示缓冲**（正确，不应改）。
- `web/src/components/chat/AgentActivity.tsx:190,193`：
  `state.stepOutputs.filter((b) => b.text.trim().length > 0)` —— **空桶不渲染**。
  由于所有 delta 都是 reasoning，桶文本恒为空 ⇒ **连输出框都不渲染**。

结论：用户看到的不是「空盒子」，而是**什么都没有**。

### 2.2 第二层：glm-5.3 的无界 reasoning 撞穿 generation wall，该轮注定失败

该 run 的完整事件链只有 4 条：

```text
evt_000001 run_started        (03:52:20.199)
evt_000002 intent_classified  (03:52:20.205)  insurance_plan / registry_lookup
evt_000003 agent_step_started (03:52:20.209)  {"step": 1}
evt_000004 agent_step_error   (03:56:20.211)  {"attempt": 1, "error_type": "TimeoutError"}
```

`03:56:20.211 − 03:52:20.209 = 240.000s`，正是
`runtime/run_deadline.py` 的 `GENERATION_WALL_S` 默认值 **240s**
（`runtime/agent/agent.py:204 _generate_with_retry` 的 thread+join watchdog；**不是** httpx 超时）。

`LLM_RETRY = 2` ⇒ 3 次 × 240s = **720s**。上一轮 `run_ce793abf6c4f4d62` 实测
`03:33:30 → 03:45:30` = **正好 720s**，终态 `needs_review`，reason 为
`AGENT_ERROR_MESSAGE`（`runtime/agent/agent.py:196`「抱歉，这次我没能生成有效的分析步骤…」）。

**这是可复现的必败路径，不是偶发。**

### 2.3 用真实 prompt 复现（11 tools / system prompt 3633 chars）

```text
==== BEFORE (reasoning_effort 未设置) ====
 first delta @4.0s kind=reasoning
 ...6000 deltas @243.2s (r=6000 c=0)
 -> elapsed=250.0s finished=False  kinds={"reasoning":6443,"content":0}
```

250 秒内产出 6443 条 reasoning、**零 content、零 tool_call**，永不结束。

---

## 3. 关键实验：GLM 的 reasoning 可调档

| 请求 | 结果 |
|---|---|
| `thinking: {"type": "disabled"}` | HTTP 400 code 1210 |
| `reasoning_effort: "none"` | HTTP 400 code 1210 |
| `thinking: {"type": "enabled"}` | 200（≈ 默认行为，83 条 reasoning） |

400 报错原文：

```text
{"error":{"code":"1210","message":"该模型始终思考，不支持关闭思考；请使用 low、high 或 max。"}}
```

逐档实测（同一 prompt）：

| 档位 | 耗时 | reasoning delta | content delta |
|---|---|---|---|
| 默认（未设置） | 4.1s | 94 | 1 |
| **`reasoning_effort: "low"`** | **1.1s** | **0** | 1 |
| `reasoning_effort: "high"` | 1.6s | 12 | 1 |

⇒ **正确参数名是 `reasoning_effort`，取值 `low` / `high` / `max`**；`thinking.*` 不是有效旋钮。

由于本产品**本来就完全丢弃 reasoning**（E-2：不渲染、不持久化、不进事件），
对 reasoning 限流**不损失任何用户可见内容**，却把「必然失败的 720s」变成「8s 完成」。

---

## 4. 修复内容（最小增量）

### 4.1 `runtime/agent/model.py`

- `OpenAICompatProvider.__init__` 新增可选参数 `reasoning_effort: str = ""`。
- 抽出 `_payload_base(messages)`，由 `generate()` 与 `stream_generate()` 共用；
  **仅在非空时**注入 `payload["reasoning_effort"]`。
- 旧调用点（`tests/runtime/test_agent_model.py:79` 等）不受影响（参数可选，默认省略）。

### 4.2 `runtime/agent/config.py`

- `LLMConfig.reasoning_effort`，默认 **`"low"`**，注释内含完整证据与理由。
- 新增 `REASONING_EFFORT_ENV = "LLM_REASONING_EFFORT"`；`default|none|off` ⇒ 返回 `""`（省略参数 = 28.K.27 之前的行为）。
- 新增 `resolved_reasoning_effort` 属性；`to_provider()` 透传（main 与 fast 两档）。
- `describe()` 暴露 `reasoning_effort`（非密钥，便于 `/api/agent/config` 核验生效值）。

### 4.3 `web/src/components/chat/AgentActivity.tsx`

- 新增 `stepBoxes` 过滤：**空桶若属于当前步且 `lastDeltaAt !== null` 则渲染**。
  `lastDeltaAt` 由**任意 kind** 的 delta 打戳（在 reducer 的 reasoning 过滤**之前**），
  因此首个 reasoning delta 就会让输出框出现。
- 空且 active 的盒子渲染 `正在思考…`（`data-testid="step-output-thinking"`）+ 光标；
  **不存储、不渲染任何 reasoning 文本**。
- 刻意以 `lastDeltaAt !== null` 作为前提，以维持既有契约
  （`stepOutputE2E.test.tsx:133`：**完全没有任何 delta 时不得渲染输出框**，避免「模板化空盒」）。

### 4.4 测试

- `tests/runtime/test_agent_config.py` 新增 `test_reasoning_effort_budget`：
  默认值、`low/high/max` 归一化、`default/none/off` 省略、**payload 契约**（有配置才发送 / 省略时不出现 / 不动 model+messages / 不含密钥）。
- `web/src/components/chat/stepOutput.test.tsx` 新增 3 例：
  reasoning-only 时出现 thinking 盒且 **CoT 文本不外泄**；未开始流式时不渲染盒子；content 到达后占位消失。
- `.env.example` 增补 `LLM_REASONING_EFFORT` 的文档与证据注释。
- ⚠️ **同步更新了既有断言**：`test_agent_config.py` 对 `describe()` 的 key 集合使用
  **精确相等**，新增 `reasoning_effort` 后必须补入该键。这属于**契约变更**（新配置项），
  不是放宽断言。

---

## 5. 验证结果

| 检查 | 结果 |
|---|---|
| `tsc --noEmit` | **exit 0** |
| `vitest run`（全量） | **272 passed / 2 skipped（274）**，exit 0 —— 与修复前**完全一致** |
| `vitest run`（受影响 5 文件） | 5 files / **53 passed** |
| `tests/runtime/test_agent_config.py` | **55/55** ALL GREEN（原 39/39，+16 新检查） |
| `tests/runtime/test_agent_model.py` | **14/14** ALL GREEN |
| 真实 prompt 端到端（11 tools，3633 chars） | **BEFORE 250s 未完成（6443 reasoning / 0 content / 无 tool_call）→ AFTER 8.1s 完成，产出 `agent_decide`** |

---

## 6. 生效前提（重要）

- **前端**：vite HMR 自动生效，浏览器刷新即可。
- **后端**：Python 已 import 旧模块，**必须重启 `python -m runtime.server`（:8123）后代码才生效**。
  本轮**未擅自重启**（重启属 Owner 动作）。
- 覆盖方式（env 或 `.env`）：
  - `LLM_REASONING_EFFORT=high` / `max` —— 若判定 `low` 影响计划质量；
  - `LLM_REASONING_EFFORT=default`（或 `none`/`off`）—— 回到 28.K.27 之前的行为。

---

## 7. 未验证 / 剩余风险（如实计入）

1. **未做真实用户端到端手验**：需重启后端 + 消费者 key + 一次真实提问。
   本项目禁止 synthetic 流量，故本轮**不声称端到端已通过**；但 §2.3/§5 的真实 prompt 直连实验
   已在上游等价位证明「BEFORE 必失败 → AFTER 8s 完成且仍产出 tool_call」。
2. **`low` 对计划质量的影响未做业务级评估**：单次实验仅证明 `agent_decide` 仍被正确产出，
   未评估多轮分析与报告质量。若要保守，可切 `high` 或 `max`（仍远优于默认的无界）。
3. **`agent_step_error` 在 UI 上仍是 no-op**（`runReducer.ts:197`）：
   3 次 × 240s 重试期间用户依然看不到任何失败/重试提示。
   `low` 之后超时应显著减少，但该 UX 缺口**仍然存在**，属独立后续项。
4. **QA 切片路径**（无 `agent_step_started`）在 reasoning 阶段仍不渲染 step 盒，
   仅由既有 `正在生成回答` 活动行承担存活指示；本轮未改动该路径。

---

## 8. 边界声明

- 未改动：事件 schema / `agent_stream_delta` payload（仍严格为 `{kind, text}`）、
  Agent runtime 循环、LLM gateway、SSE 传输、`runReducer` 的 E-2 规则。
- **reasoning 文本在任何层都不落盘、不渲染、不进事件** —— 仅「是否有 token 在到达」这一事实
  被用于驱动 UI 存活指示。
- 改动均为**本地工作区未提交**状态，沿用本会话既有的「暂不提交」决定。
