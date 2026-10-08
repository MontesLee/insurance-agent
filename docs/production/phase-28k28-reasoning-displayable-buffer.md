# Phase 28.K.28 — reasoning（CoT）进入可展示缓冲（分段渲染）

> **本文件取代 28.E-2 / 28.K.20 的「reasoning 思维链文本永不渲染」决策**（Owner 决定，
> 2026-09-28）。被取代的原始记录保留在
> `phase-28e2-consumer-rendering-view-boundary.md` §8，未改动，仅附加修正说明。

## 1. 动机

`glm-5.3` 是**始终思考**的模型：实测单轮 90 秒内到达 **4418 条 `reasoning` delta、0 条 `content`**
（`tmp/_sse_out.txt`）。而 `runReducer` 在此之前对 `kind === "reasoning"` 直接 `return`，
于是 step 输出桶**永远为空**，用户在整个推理阶段看不到任何过程内容。

28.K.27 曾以「空桶显示 `正在思考…` 占位」缓解，但用户仍看不到**任何实际进展**。
本次按 Owner 要求放开准入：reasoning 允许进入 step 可展示缓冲。

## 2. 改动（最小增量，未提交）

| 文件 | 改动 | 原因 |
|---|---|---|
| `web/src/state/runReducer.ts` | `stepOutputs` 由 `{key, text}` 改为 `{key, segments:[{kind,text}]}`；新增 `StepSegment` / `StepOutputBucket` / `bucketText()` / `appendSegment()` / `MAX_BUCKET_CHARS=4000`；delta 处理移除 reasoning 早退，改为**按 kind 入桶**；答案气泡仍 `content-only` | reasoning 必须可展示，但必须与 content **可分辨** |
| `web/src/components/chat/AgentActivity.tsx` | `StepOutputBox` 由收 `text:string` 改为收 `segments`；按 kind 分段渲染：`content` 正常，`reasoning` 弱化（`italic text-slate-400`）+「思考」chip；`stepBoxes` 过滤改用 `bucketText()` | 让 CoT 与答案正文在视觉上不混淆 |
| `web/src/state/stepStreaming.test.ts` | 7 → 11 条；改写 E-2 条为「28.K.28 reasoning 以独立 segment 入桶」 | 契约变更 |
| `web/src/components/chat/stepOutput.test.tsx` | 8 → 9 条；改写「reasoning 永不渲染」两条 | 契约变更 |
| `web/src/components/chat/streamMessage.test.tsx` | 改写 T2/T3/T6、T11：**断言主体从「整个 DOM」收窄到「答案气泡」**，并新增「reasoning 只出现在 step 盒」 | 该文件渲染 `<Conversation>`，而 Conversation 含 activity 卡 → 会渲染 step 盒 |
| `web/src/components/chat/AgentActivity.test.tsx` | 改写 T6、T7/T8：activity **行列表**仍不含流文本，文本只进 step 盒 | 同上 |

**同 kind 相邻段合并**：`R,C,R,C` → 3 段（非 4 段）；`R,R,C,C` → 2 段。
**4000 字符上限跨段生效**，从**最旧**文本开始丢弃。

## 3. 明确保住的边界（未改动）

1. **答案气泡 `stream` 仍为 `content-only`** —— CoT 绝不进入最终 Assistant 回答。
   （`streamMessage.test.tsx` T2b/T4/T5 仍绿。）
2. **AgentActivity 的 activity DTO / 进度文案不含 reasoning** ——
   `progressProjection.test.ts:130-144`（断言 `内部R` 不出现）仍原样通过。
3. **渲染期 `sanitizeConsumerText` 对每个 segment 生效** —— reasoning 段同样经过
   `ART-`/`EVAL-`/`run_` 标识改写（新增测试覆盖）。

## 4. 残余风险（**未解决，需知悉**）

`sanitizeConsumerText` 只改写 `ART-/EVAL-/run_/chat_/evt_/appr_/agentcase_` 一类**内部标识**，
**不拦截 system prompt 复述**。`glm-5.3` 的 reasoning 经常复述任务约束与提示片段，
这些内容现在**会直接呈现给终端用户**。若要收敛，需在 runtime 层引入 reasoning 的白/黑名单或
摘要化 —— **本次未实现**。

## 5. 验证（本机实测）

| 检查 | 结果 |
|---|---|
| `tsc --noEmit` | **exit 0** |
| 受影响 6 个测试文件 | **50 passed / 50** |
| 全量 web 套件 | **280 passed / 2 skipped（282）· 33 files passed / 2 skipped（35）· exit 0** |
| 对比修复前 | 272 passed / 2 skipped（274）→ 净增 8 条断言，**0 失败** |

## 6. 未验证

- **live 浏览器肉眼验证：未执行**。需要真实提问 + 真实 LLM 流；本项目禁止 synthetic 流量，
  且我已无授权窗口代发提问。因此**不声称端到端已通过**。
- 前端由 vite HMR 自动生效；**后端无需重启**（本次改动纯前端）。
