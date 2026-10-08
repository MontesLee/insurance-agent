# Phase 28.K.20 — Consumer LLM Streaming

Date: 2026-09-27 · 前端展示层实现（授权文件范围内：runReducer ·
components/chat/* · 测试；activity.ts 最终零改动）。

## 1. Status

```text
COMPLETE（web 246+2 · tsc clean；REAL_USER verification=PENDING——
无自然长回答样本，不伪造）
```

## 2. Existing Streaming Path（审计实证）

```text
LLM provider(stream_generate：reasoning_content 先流·content 后流)
→ agent.py 每 delta emit("agent_stream_delta",{kind,text})
→ bus.publish_transient（不入事件史）→ SSE 实时转发（无 id 行）
→ useRunStream → runReducer：缓冲进 s.stream（原语义=同 kind 才
  累积，reasoning 会**重置**缓冲）→ 仅 AgentActivity 卡内 StreamPanel
  渲染 content
schema 实证：data={kind:"reasoning"|"content", text}；无 sequence/
run_id/其他字段（server.py:804-810）
既有 fixture 证明三者关系：E-2 套件"reasoning 不渲染/answer 只取
  content"+run_50389328 真实流（reasoning 先·content 后）
```

## 3. Root Cause（"一次性出现完整答案"）

```text
①E-2 旧缓冲语义：reasoning delta 会重置 stream 缓冲——混合流中
  content 被打断丢弃
②渲染位置：content 流只在活动卡内的小面板（StreamPanel），不在
  聊天消息位；终态后由 finalize 一次性写入正式消息——用户感知=
  "长时间静态→整段出现"
③glm 特性：窗口大半为 reasoning 流（被安全丢弃）——仅有尾部
  content 可显（K.16 已证）
```

## 4. Consumer Streaming Design（最小增量·复用既有状态）

```text
runReducer（唯一流状态，未新增第二套）：
  · reasoning delta：**完全不触碰展示缓冲**（E-2 强化——既不渲染
    也不复位）+照常打 lastDeltaAt
  · content delta：跨 reasoning 间歇累积（T3）·尾 4000 截断
Conversation：消息位新增 stream-message 气泡（assistant 样式+
    光标）——仅 content·非空·无 terminalEvent 时显示
AgentActivity：移除 StreamPanel（单一展示位·避免重复）——
    K.17 活性行/心跳原样
ChatLayout finalize（T5）：failed 且无服务端回复时——保留已安全
    流出的 content +「这次回答没有完整生成，请稍后重试。」
    （run_failed 不清缓冲=构造保证）；needs_review 维持 K.1 固定
    文案（契约优先·如实注记）
收敛模型：terminalEvent 置位→气泡即隐→finalize 写入正式消息=
    流式消息收敛为 assistant message（无重复·T4）
渲染批处理：SSE 传输层已按事件分帧（非逐 token 事件）——维持
    每 delta 渲染（无新增 rAF/批层·无人工延迟）
```

## 5. Reasoning Safety Boundary

```text
reasoning delta → 不进缓冲·不进 DOM·不进任何 metadata（除到达
时间戳）。E-2/E-3/consumerDom 全套泄漏断言 + 新 T2/T3/T6/T11。
```

## 6. Test Results（新增 streamMessage 9 + runReducer 2 + 更新 2 旧期望）

```text
T1 A→AB→ABC ✓ · T2/T3/T6 混合流只累计 content·reasoning 零渲染 ✓
T2b 纯 reasoning 无气泡 ✓ · T4 终态收敛无重复 ✓ · T5 失败保留
  partial+失败文案·零 raw error ✓ · T7 快完成无残留 ✓ ·
T10 四终态清理 ✓ · T11 泄漏全零 ✓ · T8/T9 K.17 兼容（AgentActivity
  套件 16/16）✓ · T12 全量回归 **246+2** ✓
旧期望更新（2）：reasoning 不再入缓冲（强化）·跨 reasoning 累积
  （T3 要求的语义变化——非掩盖，是本阶段授权行为变更）
```

## 7. Leakage Verification

```text
reasoning/prompt/system/developer/provider/model/tool/skill/agent/
run_id/artifact_id/raw event = 0（T11+consumerDom FORBIDDEN 族+
E-2 套件全绿）
```

## 8. K.17 Compatibility

```text
有 content delta：消息位流式气泡 + 「● 正在生成回答」并存 ✓
（fresh<2s）；真静默≥12s：心跳 ✓；终态：全部消失 ✓——AgentActivity
套件 16/16 原样通过
```

## 9. Real User Verification

```text
PENDING（本轮无自然长回答真实样本；不发送 synthetic——K.20 纪律）
```

## 10. Files Changed

```text
web/src/state/runReducer.ts（delta 缓冲语义：reasoning 零接触+
  content 跨歇累积）
web/src/components/chat/Conversation.tsx（stream-message 气泡）
web/src/components/chat/AgentActivity.tsx（移除 StreamPanel·清理
  useRef）
web/src/components/chat/ChatLayout.tsx（failed 保留 partial+固定
  失败文案）
测试：streamMessage.test.tsx(新·9) · runReducer.test.ts(+2/更新2) ·
  AgentActivity.test.tsx（更新 2 处至新展示位契约）
```

## 11. Known Limitations

```text
①QA 切片生成路径后端无 delta（K.16 已记）——QA 回答仍非流式
  （后端改动未授权）
②needs_review 中途流内容不保留（K.1 固定文案契约优先——设计取舍
  如实注记）
③缓冲尾 4000 截断沿袭（超长答案的流式头部截断；finalize 用服务端
  全文·正确性不受影响）
④真实渲染节流未加（SSE 已分帧；如实测抖动可后续 rAF 批层）
```

## 12. STOP

```text
零 backend/EventBus/SSE/事件词汇/Router/Agent/WeKnora/auth 改动·
无新 SSE/轮询/websocket·零 synthetic·零重启（pilot :5273 vite
HMR 自动生效）
```
