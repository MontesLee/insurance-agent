# Step Streaming Live E2E 不生效 — 定位与修复

Date: 2026-09-28 · 性质：前端-only 修复（零后端改动）。

## 1. Root Cause

```text
真实链路断在：CHECKPOINT 8（stepOutputs 不变化——QA 路径
currentStepKey 恒 null→delta 全走全局气泡→step 盒永不出现）
```

## 2. Evidence

```text
Backend:    agent_stream_delta emitted = YES（live 探针 3044 deltas·
            T_first=3.7s·agent_step_started 事件在案）
SSE:        agent_stream_delta transmitted = YES（transient 通道正常）
Frontend:   singular-dispatch E2E 模拟 = PASS（reducer/组件链路正确）
根因:       Owner 测试的是 QA 类问题 → QA 切片路径无 agent_step
            事件 → currentStepKey 恒 null → delta 全进全局 K.20
            消息气泡 → step 盒零渲染 → 「前端没有任何可见变化」
```

## 3. Fix

```text
file: web/src/state/runReducer.ts
change: QA-slice turn（sawAgentStep=false）首个 content delta 到达时
        自动开 "qa-composing" 桶（delta 同时进 step 盒+全局气泡——
        step 盒=执行透明度·气泡=最终答案位置·两视图并存不重复）；
        agent-loop 边界间隙（sawAgentStep=true 但 key 短暂 null）只进
        全局气泡（避免误归属+下一 agent_step_started 开正式桶）；
        agent-loop 步内 delta 仅进桶（不镜像全局气泡——防双显）
新增:   sawAgentStep 布尔标志（区分 QA 轮与 agent-loop 边界间隙）
reason: Owner 从前端测试发现零可见变化——QA 问题（最常见消费者
        问法）走 QA 切片路径无 step 事件——step 盒设计遗漏了这一
        主路径
```

## 4. Live Verification

```text
single step (agent-loop): PASS（E2E 模拟 singular dispatch：
  T1 无盒→T2 首delta开盒→T3 增长→T4 新步新盒+旧步保留→T5 终态冻结）
multi step: PASS（step2 不入 step1——隔离断言）
QA turn (auto-open fix): PASS（首个 content delta→qa-composing 桶
  渲染 + K.20 气泡并存）
step isolation: PASS
real streaming: PASS（live 探针 3044 deltas·T_first 3.7s ≪ T_final
  128s——后端链路实证；前端 singular-dispatch 模拟同步过）
reasoning protection: PASS（reasoning 永不入桶——E-2 维持）
final answer: PASS（transcript finalize 不受影响）
浏览器肉眼验证: PENDING（需 Owner 在 :5173/:5273 发起真实问题——
  vite HMR 已自动加载修复代码）
```

## 5. Performance

```text
first step started:   T+0s（agent_step_started 即刻）
first stream delta:   T+3.7s（live 实测·glm 流式）
first visible box:    T+3.7s（首个 content delta 渲染）
final response:       T+128s（本探针轮为澄清·生成 116s）
```

## 6. Tests

```text
before: web 270 passed + 2 skipped · tsc clean（原版 step streaming）
after:  web **272 passed + 2 skipped**（+2 E2E singular-dispatch 模拟）
        tsc clean（修两处未用变量后）
新增/更新：stepStreaming 7（QA 断言更新为 auto-open）·stepOutput
组件 5（QA 断言更新）·stepOutputE2E 2（新·singular dispatch 路径）
```
