# K.25-S1 Final Report — Artifact ID Content Hygiene

Date: 2026-09-27 · 独立 Consumer Content Security Bugfix。

## Result

```text
PASS（三层修复全落地·backend 815+2 零失败·web 258+2·tsc clean·
live pilot 复验：规划+QA 场景 ID 泄漏=NONE）
```

## Root Cause

```text
ART-009 产生：runtime/artifact_registry.py "ART-%03d"（规划 8 阶段
每阶段注册产物）→ 传播：agent.py _tool_content() 把 {artifact_id,
eval_id} 序列化进 LLM 工具消息 + state.py context_summary() 列出
artifact keys → glm 在生成答案时复述"（ART-009）"→ 交付：
outcome.message 经 chats.add_assistant_message 进入消费者聊天文本
（K.25-RV R2 实证）
```

## Source Hygiene

```text
PASS — agent.py _tool_content()：内部标识键（artifact_id/eval_id/
run_id/case_id/approval_id，递归）从 LLM 面投影整体剥离（模型看不到
→无法复述）；state.py context_summary()：artifact TYPES-only +
eval 计数（不再暴露 ART-/EVAL- 值）。内部状态（tool_history/事件/
registry）保留真实 ID（T1/T9 锁定）。
```

## Delivery Hygiene

```text
PASS — 新 runtime/consumer_hygiene.py 纯函数：
  · sanitize_consumer_text()：窄模式（\b(ART|EVAL)-suffix\b·
    run/chat/evt/appr/agentcase_+8 尾）——括号包裹塌缩·裸 ID→
    "相关结果/校验记录"（句子自然）；应用于 _finish_run 的
    chat_message（唯一聊天边界点——正常/QA/needs_review/deadline/
    崩溃五路全覆盖）
  · strip_internal_ids_for_llm()：源卫生递归剥离
```

## Streaming Hygiene

```text
PASS — 双层：
  · K.22 validated chunks：generate_grounded._emit_streamed 对
    【完整已验证答案】先 sanitize 再 48 字符切块——跨块分裂的 ID
    也不可能漏过（T3）；门判定在原文上已运行——sanitizer 仅改写
    消费者措辞，非门旁路（K.22 语义零变化）
  · agent-loop live stream（K.20）：前端渲染层（新
    web/src/state/contentHygiene.ts 同模式纯函数）作用于【累积
    缓冲】——分裂 chunk 在渲染时被捕获（per-chunk regex 做不到）；
    应用于 Conversation stream-message + MessageView assistant 文本
```

## Internal ID Detection

```text
Actual pattern: ART-%03d / EVAL-%03d（registry）·run_/chat_/evt_/
appr_/agentcase_ + ≥8 字符尾（server/events）——窄边界（\b+连字符+
后缀）：SMART-1/P001/日期/金额/条款编号结构性不匹配（T6）
```

## Before / After

```text
Before: "正式报告已更新生成（ART-009）。"（K.25-RV R2 实测）
After:  "正式报告已更新生成。"（括号塌缩）·裸 "见 ART-009" →
        "见 相关结果"（自然替换）——live 复验 final answer 零 ID
```

## Tests

```text
T1 源卫生（LLM 投影零 ID·原结构不动）✓ T2 交付（含括号塌缩·句子
  自然）✓ T3 流式（完整答案先 sanitize 再切块+K.22 grounded 链）✓
T4 多 ID ✓ T5 变体（ART-ABC/EVAL-007/run_/chat_）✓ T6 业务文本
  （P001/SMART-1/日期/金额/编号）零误伤 ✓ T7/T8=live pilot 复验
  （下）✓ T9 内部 linkage 不动 ✓ T10 _finish_run 聊天消息 sanitize ✓
前端 +3（util 变体·stream-message 渲染·MessageView 渲染）
```

## Regression

```text
K.17: PASS（套件含于全量）·K.20: PASS·K.22: PASS（6/6 含 T3 强化）·
K.24: PASS（8/8）·K.25: PASS（progressProjection 9/9——进度模型
  零触碰）
backend **815 passed + 2 skipped（零失败）**（=K.25 后 808+7 S1）
web **258 passed + 2 skipped**（=255+3）·TypeScript: PASS
```

## Security

```text
CoT: 0 · Reasoning: 0 · Internal ID: 0（live 规划+QA 双场景扫描
NONE）· Tool: 0 · Skill: 0 · Agent: 0 · Raw Event: 0 · Exception: 0
```

## Real Pilot

```text
Planning（原泄漏同类场景·两轮 289s+233s）：COMPLETED·9/9 VALID·
  report ref 交付 50.6KB·final answer 自然（"全流程各环节校验均
  通过"——模型不再看到 ID 故自然改写）·**ID 泄漏 NONE** ✓
QA（等待期·70s）：completed/QA_ANSWERED（首次 live 通过引用门！）·
  事件链 tool_started/completed 正常·答案带 [E1] 引用·ID 泄漏
  NONE ✓
```

## Artifact Integrity

```text
Create/Store/Retrieve/Authorization/Download/Linkage: 全 PASS——
sanitizer 只作用于 LLM 面投影与消费者文本；registry/事件/审计/ref
解析使用真实 ID 不变（T9 + live report ref 交付实证）
```

## Files Changed

```text
runtime/consumer_hygiene.py（新·纯函数双层）·runtime/agent/agent.py
（_tool_content 源卫生）·runtime/agent/state.py（context_summary
类型化）·runtime/server.py（_finish_run 交付 sanitize）·
runtime/grounding/loop.py（K.22 切块前 sanitize）·
web/src/state/contentHygiene.ts（新·渲染层）·Conversation.tsx/
Message.tsx（渲染接线）·测试：test_k25s1_hygiene.py（7）+
contentHygiene.test.tsx（3）
```

## Scope Check

```text
Router unchanged · Runtime unchanged · EventBus unchanged · SSE
unchanged · Event vocabulary unchanged · K.17 preserved · K.20
preserved（渲染层仅加 sanitize·流式语义零变化）· K.22 preserved
（门在原文运行·sanitize 仅改措辞）· K.24 preserved · K.25 progress
preserved（投影零触碰）
```

## Remaining Limitations

```text
①agent-loop 流式渲染层 sanitize 为最终兜底——极罕见情况（模型
  幻觉出非标准 ID 形态）不在窄模式内（如实：模式覆盖仓库真实
  ID 形态）
②源卫生使模型不再看到 eval/artifact 标识——如未来某内部计算
  确需 ID 传递，需重新评估该调用点（当前无此需求）
```

## Owner Decision

```text
无强制项。（可选）pilot 继续自然观察；ART-xxx 卫生已闭环。
```

STOP
