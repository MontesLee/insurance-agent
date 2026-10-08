# Phase 28.K.24 — Run Deadline & Agent Execution Watchdog

Date: 2026-09-27 · L1（run-level deadline）+ L2（agent 环墙钟看门狗）
+ retry budget 实施（授权范围内：Run lifecycle·agent loop·timeout→
terminal 传播·测试·config）。

## 1. Status

```text
COMPLETE（K.24 测试 8/8 · backend 全量 **808 passed + 2 skipped
零失败**；前端零改动——K.17/K.20/K.22 套件含于全量）
```

## 2-3. Pre-Implementation Audit / Topology

沿用 K.23 图谱：WeKnora 15s·QA 90s×2×2≈360s 有界·agent 环
httpx per-read（无墙钟）·**run deadline ABSENT**·前端无兜底。
生命周期入口/出口实证：_agent_worker（server.py）try→正常终态/
except→run_failed[CRASHED]+finally 清理；无独立 deadline。

## 4. Run Deadline Design（L1）

```text
语义：run_started 起 ABSOLUTE monotonic deadline（time.monotonic，
抗时钟漂移）·全阶段共享·重试不复位。
Enforcement（runtime enforcement，非仅配置）：每 run 一个
deadline supervisor daemon 线程——run_done Event 等待剩余时间；
到期→_finish_run(run_failed·RUN_DEADLINE_EXCEEDED)+消费者安全
文案「处理时间过长，已停止本次分析。你可以重新发送再试。」
（零内部信息）。**Run lifecycle 拥有终态，不依赖 worker 线程结束**
（K.23 风险消除）。worker finally 先 run_done.set()——正常完成时
supervisor 静默退出（T1/T14 不误杀）。
```

## 5. Agent Wall-clock Watchdog（L2）

```text
_generate_with_retry：每次 provider 调用（generate/stream_generate）
经 thread+join(budget) 看门狗——与 QA 适配器同模式（28.B5.1 复用，
非新机制·无 asyncio 重写·无 sleep 轮询）。慢滴流（每 0.4s 一 chunk
的对抗样本）在 budget 内未完成→llm TimeoutError→有界重试→
needs_review fail-closed（T3 实证 <10s 终结）。
```

## 6. Retry Budget

```text
generation_budget = min(GENERATION_WALL_S, deadline_at - now)——
run 剩 20s 时生成只获 20s（T15 实证：配置 300s/实际 deadline 2s→
总耗时 <20s）。重试启动前检查 remaining ≥ MIN_RETRY_BUDGET_S（5s）：
不足则不启动注定超限的调用（T4 实证：floor 3600s→立即拒启 <5s）。
```

## 7. Terminal Closure

```text
_finish_run：**幂等终态闭合**（_closed 集合+锁；首个终态胜出，
后续为 no-op）——正常路径/QA 切片/agent 终态/崩溃处理器/deadline
supervisor 五路全部路由经此（server.py 五个调用点）。保证每 run
恰一个 terminal 事件，无论哪路先触发（test_finish_run_idempotent
实证 first-wins）。run_failed 后 agent_stream_delta 发射门控
（closed 集合检查）——terminal 后零增量流（T13）。
```

## 8. Cancellation Semantics

```text
看门狗超时后底层 provider 线程为 daemon——不可可靠取消（诚实记录：
不假装已解决）。但 run 先进 terminal（supervisor 独立闭合）+delta
门控停止输出——资源占用随进程生命周期回收，无 Run 无限 running。
```

## 9. QA Compatibility

```text
QA 90s 看门狗/网关重试/regen 零触碰（K.22 套件 6/6 含于全量）；
run deadline 为外层 ceiling（QA 最坏 360s << 900s 默认值）。
```

## 10. K.22 Compatibility

```text
门后 buffered streaming 语义原样（证据门/引用门/零 delta-on-fail
测试全绿）；deadline 期间触发→无验证答案→零 delta（构造保证）。
```

## 11. Test Matrix（8/8）

```text
T2 run deadline→run_failed/RUN_DEADLINE_EXCEEDED+消费者文案 ✓
T3 慢滴流墙钟看门狗（<10s 终结 needs_review）✓
T4 低于最小预算不启动重试 ✓ T5 重试耗尽→needs_review（T3 内含）✓
T13 closed run 零 delta ✓ T14 快生成不误杀 ✓
T15 deadline 钳制生成预算 ✓ T1 正常完成不受影响 ✓
+ _finish_run 幂等（first-wins）✓
（T6-T12=既有套件覆盖[工具/QA/引用/K.22/流式]·T16=全量 808+2 ✓）
```

## 12-13. Safety / Observability

```text
安全五零维持（全量含 consumerDom/B-02/E-6/泄漏套件）；timeout
分类可观测：RUN_DEADLINE_EXCEEDED（run 数据字段+server 日志）/
agent 看门狗超时经 agent_step_error{error_type}事件+F2 llm.call
TimeoutError 分类（零新观测系统）。
```

## 14. Performance / Metrics

```text
configured run timeout=900s（推导：QA 360s 最坏+规划链实测 300-600s
+修复余量）·generation wall=240s/次·retry floor=5s·
最坏理论 runtime=900s（有界）·terminal guarantee=每 run 恰一终态
Before：run timeout ABSENT·agent 无墙钟 → After：900s deadline+
240s 看门狗+预算钳制+幂等闭合
```

## 15. Rollback

```text
4 文件还原（run_deadline.py 删除·agent.py _generate_with_retry
还原·server.py 五终态点还原直接 _emit/_set+移除 supervisor/_closed）
→回到 K.23 状态（无 deadline）。env 旋钮可将 deadline 调大（如
86400）近似禁用而不回滚代码。
```

## 16. Real User Verification

```text
PENDING（不 synthetic；pilot :8123 仍运行 K.24 前码——生效需
Owner 授权重启）
```

## 17. Known Limitations

```text
①底层 provider 线程超时后不可取消（daemon 随进程回收——run 终态
  不受影响，如实记录）
②900s/240s 默认值为工程推导（env 可调；生产调优=Owner）
③demo _worker（POST /api/runs 内部面）未接 supervisor（其崩溃闭合
  在案+内部面 OPERATOR 门——边界如实记录）
④前端兜底（K.23 L3）未实施（本阶段禁改前端——backend 正确终态
  下 K.17/K.20 现有 UI 负责结束 loading，全量测试证实）
```

## 18. STOP

```text
零 Intent/Router/QA 语义/引用门/证据门/SSE/EventBus/前端改动·
零 synthetic·未重启 pilot
```
