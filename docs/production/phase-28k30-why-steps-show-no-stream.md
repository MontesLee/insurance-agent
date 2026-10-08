# 28.K.30 — 为什么很多步骤的文本框没有任何输出

> 只读取证 → 最小修复。本文回答两个用户提问，并给出可复现的实测命令。
> 结论：**每个步骤都调用了 LLM**；文本框空/只有一句话是**模型在该档位下真实的输出量**，
> 而不是前端丢包；另外发现并修复了一个自动滚动缺陷。

## 1. 用户的两个问题

1. 很多「正在思考…」的文本框没有任何输出，该步骤就完成了 —— 这些步骤是不是没调 LLM？
   如果没调 LLM，就不该显示「正在思考…」。
2. 一些步骤的文本框只有一句话就不再刷新 —— 应该高频刷新 / 自动滚动，展示最新实时信息。

## 2. 结论（三条独立事实，均有实测支撑）

### F1 · 每个步骤都调用了 LLM，而且 LLM 就是整步耗时的全部

真实运行 `run_b79ab1a7b7e34fc2`（2026-09-28 14:27，pilot `:8123`）的逐步对账
（数据源：`tmp/obs/run-profiles/<run_id>.json`，由既有 Run Profiler 记录）：

| 步骤 | 流式增量 | 整步 | 其中 LLM 生成 | 其中工具/阶段执行 | 该步动作 |
|---|---|---|---|---|---|
| 1 | **72** | 9.56 s | 9.51 s | 0.05 s | record_client_profile |
| 2 | 0 | 13.18 s | 13.15 s | 0.04 s | record_client_profile |
| 3 | 0 | 9.15 s | 9.11 s | 0.04 s | record_risk_assessment |
| 4 | 0 | 4.41 s | 4.41 s | — | coverage_gap_analysis（前置缺失，失败） |
| 5 | **45** | 8.70 s | 8.66 s | 0.05 s | record_requirement_analysis |
| 6 | 0 | 4.60 s | 4.53 s | 0.06 s | coverage_gap_analysis |
| 7 | 0 | 4.37 s | 4.29 s | 0.08 s | solution |
| 8 | 0 | 9.15 s | 4.40 s | **4.68 s** | product_candidate_provider + knowledge-search |
| 9 | 0 | 4.31 s | 4.19 s | 0.12 s | recommendation |
| 10 | 0 | 4.38 s | 4.23 s | 0.15 s | report_generation |
| 11 | 0 | **17.73 s** | 17.56 s | — | agent_decide（收尾） |

- **LLM 生成占整步 96–100%**。用户猜测的「这些步骤没调用 LLM」不成立。
- 但真正"干活"的**工具/阶段执行是纯确定性 Python，零 LLM 调用**：`orch._execute_stage`
  → `_invoke_python_stage` → `adapters/*`（`grep -n provider|llm adapters/*.py` 无任何命中），
  只花 **35–151 ms**。唯一例外是步骤 8 的 `knowledge-search`（WeKnora 检索，4.68 s，仍非 LLM 生成）。

### F2 · 整次运行 117 条增量**全是 reasoning，content 为 0**

`content` 通道在 9 阶段链路上从未被使用：模型把结论放在 **tool_call 的参数**里
（`agent_decide` 的 `message` / 各工具的 JSON 入参），而 `stream_generate` 只
yield `reasoning_content` 与 `content` 两种 delta，**工具调用参数的分片被静默累积、不流式**。
所以文本框天生只能显示推理，且收尾步骤（17.6 s）必然全程无输出。

### F3 · 文本量少是**推理预算**造成的，不是前端丢包

用**真实 system prompt + 真实 11 个工具定义**直接调用 provider 实测
（`tmp/_probe_delta_volume.py` / `_probe_tiers2.py` / `_probe_continuation.py`）：

| 档位 | 场景 | 完成 | 墙钟 | TTFT | 增量数 | reasoning 字符 | content 字符 |
|---|---|---|---|---|---|---|---|
| `low` | 首轮 / main | ✅ | 16.3 s | 6.2 s | 56 | 265 | 0 |
| `low` | 首轮 / main（复采样） | ✅ | 7.8 s | 4.2 s | 16 | 72 | 0 |
| `low` | 首轮 / main（复采样） | ✅ | 6.1 s | 1.7 s | 31 | 143 | 0 |
| **`high`** | 首轮 / main | ✅ | 11.9 s | 1.6 s | **228** | **1088** | 0 |
| **`high`** | 首轮 / main（复采样） | ✅ | 11.8 s | 3.7 s | **107** | **499** | 0 |
| **`high`** | 首轮 / main（复采样） | ✅ | 30.4 s | 15.9 s | **242** | **1146** | 0 |
| `max` | 首轮 / main | ❌ **>90 s 不返回** | — | 4.1 s | 2456 | 10241 | 0 |
| `low` | 续跑（有工具结果）/ main | ✅ | 5.7 s | — | **0** | **0** | 0 |
| `high` | 续跑 / main | ✅ | 14.9 s | 2.0 s | 80 | 374 | 0 |
| `low` | 续跑 / fast | ✅ | 9.4 s | 4.7 s | 18 | 87 | 0 |
| `high` | 续跑 / fast | ✅ | 11.1 s | 4.5 s | 214 | 193 | **288** |

关键读数：

- **`low` 档可以完整跑到结束、一条增量都不发**（续跑 / main：0 条 / 5.7 s）。
  这正是「文本框一直空着、然后步骤就完成了」的直接来源。
- **`high` 档一律产出 80–242 条增量、374–1146 字符**，且首轮场景**比 `low` 更快**
  （11.8–11.9 s vs 6.1–16.3 s）；续跑场景比 `low` 慢约 5 s。
- **`max` 档必须排除**：90 s 仍未返回，会撞 `GENERATION_WALL_S=240` × `LLM_RETRY=2`（=720 s）看门狗。

> 复盘：上一轮把 `reasoning_effort` 定为 `low`，依据是"默认档 90 s 不产出 content/tool_calls"。
> 当时**没有测 `high` 这个中间档**。本轮的重复采样显示 `high` 既不失控、文本量又是 `low` 的 4–8 倍。

## 3. 本次已修：自动滚动缺陷（真 bug）

`AgentActivity.tsx` 的 `StepOutputBox` 用"距离底部是否 < 24px"决定要不要跟随，
但该判断是在内容**已经增长之后**执行的（`useEffect` 在 DOM 更新后运行）。后果：
单次增量把内容推高超过 24px（本字号约 2 行）——或者盒子刚填满——条件立即变 false，
而 `userScrolled` 仍为 false，于是 **该步剩下的时间里再也不跟随**，视图冻结在旧的
一屏上；文本还在到达，但用户看到"写了一句就不动了"。

修法：跟随只被**一件事**打断 —— 用户主动上滑（`onScroll` 中 `diff >= 24` 才置位）；
滚回底部即恢复跟随。

```
- const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 24;
- if (!userScrolled.current && (atBottom || prevLen.current === 0)) el.scrollTop = el.scrollHeight;
+ if (!el || !active || userScrolled.current) return;
+ el.scrollTop = el.scrollHeight;
```

新增 3 条断言（`stepOutput.test.tsx` → 18 条）：① 大增量后仍跟到底部；
② 用户上滑后不再被抢走视图、滚回底部后恢复跟随；③ 已结束的步骤不会被滚动。
**已用反向验证确认**：把实现回退到旧逻辑后，前 2 条会失败（`expected +0 to be 200` / `to be 400`）。

> 注：第一次"回退验证"曾假通过 —— 我用普通对象代替 `useRef` 伪造旧逻辑，
> 每次渲染都会重置为 0，等于把守卫短路了。改成真正的 `useRef` 后测试才具备判别力。
> 教训：负例验证必须逐字复刻旧实现，任何"等价改写"都可能把断言变成空断言。

这一步在 `reasoning_effort=low` 下不会改变观感（文本不溢出 160px 上限），
但一旦采纳 `high`（499–1146 字符），跟随就是必需的。

## 4. 已采纳的两项决策（本轮实施）

### 4.1 推理预算 → `high`（**仅本机 `.env` 试点**）

`.env`（gitignored）追加 `LLM_REASONING_EFFORT=high`，实测解析结果：
`resolved_reasoning_effort = 'high'`，主档与 fast 档的 provider 都拿到 `high`。

- **不改进 `runtime/agent/config.py` 的默认值**，因此 `test_agent_config.py` 的 5 条
  「documented default is 'low'」断言保持原样、后端零改动。
- 回退只需删掉 `.env` 里那行。试点确认观感后再决定是否固化为全局默认
  （那时需同步改 config.py 的证据注释与那 5 条断言 —— 属契约修订，须单独记录）。

### 4.2 「正在思考…」只在真的有模型在生成时显示

新增纯函数 `stepsAwaitingModel(events)`（`web/src/state/stepAnchors.ts`）：
一个步骤只要出现过 `tool_started` / `tool_failed` / `tool_completed` / `agent_decision`
（都带 `data.step`），就说明**模型已经返回**，该步骤不再处于「等待模型」状态。

`AgentActivity` 的空盒渲染条件因此收紧为「**当前步骤 且 模型仍在生成**」；
模型返回后，那个空文本框**整个不再挂载**，后续静默由里程碑行自身表达，
不再被误标为「思考」。

- 为什么用事件而不是定时器：这些事件只可能产生于一次生成**完成之后**，
  是硬边界，不需要猜、也不需要等超时。
- QA 桶（`qa-composing`）**不需要例外**：`runReducer` 是在 delta 处理器内部、
  过了 `text.length === 0` 早退之后才创建它，所以它**永远不可能是空的**，
  根本走不到空盒分支（这是读代码可证的，不是假设）。
- 这条改动**修订了 28.K.27 的"未流式步骤不渲染文本框"语义**：现在多了一个前提
  ——不只是"还没流"，还要求"模型仍在生成"。既有断言本身未改（它构造的是
  `lastDeltaAt === null` 的状态，仍然不渲染），但语义边界已更新，故在此明示。

## 5. 验证

- `web/`：`tsc --noEmit` exit 0；全量套件 **35 files / 314 passed · 2 skipped（316）· exit 0**
  （本轮改动前 300 passed；净增 14 = 3 滚动 + 8 等待态纯函数 + 3 占位边界，0 失败）。
  未删除任何既有测试。
- **两次反向验证**（逐字回退到旧实现后确认断言会红）：
  1. 自动跟随：回退后 `expected +0 to be 200` / `to be 400` 失败；
  2. 占位边界：回退后 `expected <span…> to be null` 失败。
- 后端零改动（`.env` 不入库），无需重跑后端套件。

## 6. 未做 / 残余

1. **浏览器端到端未执行**（`:8123` 后端当前未运行）。本文所有前端结论来自组件测试 + 反向验证，
   不声称真机通过。`high` 档的真实观感也需要在浏览器上肉眼确认。
2. `content` 通道为 0 的根因（工具调用参数不流式）**未修**：收尾步骤 17.6 s 的静默仍在。
   修它需要在流式层增量解析 tool_call 的 `arguments`，只对 `agent_decide.message` 这类
   面向用户的字段放行 —— 属于独立的契约层改动，本次未动。
   （`high` 档下 fast 档续跑实测出现过 288 字符的 content 增量，说明该通道并非不可能被用到。）
3. `max` 档已实测不可用，**不要**把它当作"文本更多"的选项：90 s 不返回。
4. 本轮所有实测脚本在 `tmp/`（gitignored），未入库。复现：
   `python tmp/_probe_delta_volume.py`、`python tmp/_probe_tiers2.py 60 main low high`、
   `python tmp/_probe_continuation.py 60 fast low high`、
   `python tmp/_analyze_step_deltas.py tmp/obs/run-profiles/<run_id>.json`。
5. 代码改动**未提交**（沿用既有的「暂不提交」决定）。
