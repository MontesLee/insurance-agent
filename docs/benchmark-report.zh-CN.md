# Phase 11 Benchmark 报告

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](benchmark-report.md)

复现命令：`python -m evals.benchmark.runner`（确定性；无 LLM）。

## 1. 测试环境

Windows 11 · Python 3.11 · 单进程、ThreadPoolExecutor 有界并行、JSON
文件持久化。全程没有 Redis/Postgres/Kafka/K8s。

## 2. Benchmark 用例（evals/benchmark/cases，schema 校验）

| 用例 | 类别 | 场景 | 结果 |
| --- | --- | --- | --- |
| B001 | happy path | 完整咨询链、4 Agent、artifact+血缘+checkpoint | **PASS**（completed） |
| B002 | 信息缺失 | 建档 agent 拒绝编造客户档案 | **PASS**（needs_review，无 client-profile） |
| B003 | 知识失败 | 空知识 → 不编造证据，下游阻塞 | **PASS**（needs_review） |
| B004 | 产品失败 | 无候选 → 重规划丢弃产品任务，诚实降级 | **PASS**（completed，无 product-candidates） |
| B005 | repair 耗尽 | 非法 product_id ×N → 恰好 3 次 eval / 2 次 repair | **PASS** |
| B006 | 重规划 | 阻塞路径 → v1→v2，前一修订不可变 | **PASS** |
| B007 | 并行 | 真并行 DAG，artifact 编号确定、观察到 task_scheduled | **PASS** |
| B008 | HITL | 高影响重规划 → WAITING_HUMAN → 批准 → 恢复 → completed | **PASS** |
| B009 | HOTL 通知 | 失败 → 信号 → NOTIFY → 自主继续 | **PASS** |
| B010 | HOTL 暂停 | 预算耗尽 → HIGH → 屏障暂停 → RESUME → 终态 | **PASS** |
| B011 | golden | 四 Agent 并行金样本，完整审计轨迹 | **PASS** |

**benchmark_pass_rate = 1.0（11/11）**

## 3. 故障注入（矩阵 F01–F18，全部 PASS）

Planner 非法 JSON/图 → 有界重试 ≤ 2（F01/F02）· agent 工具失败 → 无编造
artifact（F03）· 知识为空 → fail closed（F04）· 非法产品 → 目录不变量
FAIL（F05）· repair 耗尽 → 恰好 2 次（F06）· 任务阻塞 → BLOCKED/重规划
（F07）· 重规划无变化 → 停止（F08）· 重规划耗尽 → NEEDS_REVIEW（F09）·
审批拒绝 → fail closed、v1 保持（F10）· HOTL 安全屏障暂停、无中途杀死
（F11）· PAUSE 中崩溃 → 幂等恢复、只应用一次（F12）· RESUME 中崩溃 →
恢复并完成（F13）· 重复命令 → 幂等 no-op（F14）· 越权 actor → 白名单
拒绝（F15）· 非法 A2A 目标 → AGENT_MISMATCH（F16）· 非法 artifact 引用
→ ARTIFACT_NOT_FOUND（F17）· 伪造 worker OK → 无自评 PASS（F18）。

## 4. False-pass 测试 —— `false_pass_count = 0`

坏的/空 artifact、被产品污染的分析、指纹被篡改的注册表条目、非法
product_id、未知 task_type、重复 task_id、依赖环、已删依赖引用、
错误/未知 agent、策略禁止的 A2A 目标、未知消息类型、越权命令、
对未知/已通过任务的重试、伪造 worker OK —— **全部被拒绝**
（`tests/runtime/test_false_pass.py`）。

## 5. 并行一致性 —— 通过率 1.0

B007 与 B011 在 `max_concurrency=1` 与 `2` 下：任务终态一致、artifact
类型**与顺序编号**一致、图修订一致、每个 artifact 类型的 eval 结论
一致。（串行模式对 stage-tool artifact 合法地多记一行 eval —— harness
的 eval 加 stage runner 内部的那个；并行 worker 会丢弃副本上的 ——
结论一致，Phase 7 已记录的不对称。）

## 6. 重规划

B004/B006：修订 2 被接受且带 diff；修订 1 快照不可变；被移除任务绝不
伪造成功；被保留的 terminal-ok 任务绝不重跑；artifact 跨越换图存活
（registry verify PASS）。

## 7. HITL

B008 完整生命周期（请求 → 等待 → 批准 → Harness 恢复 → completed）；
F10 拒绝路径（fail closed，不生成替代图，该项目重规划停止）。

## 8. HOTL

B009 通知之下自主继续（人不是 workflow 阻塞点）；B010 监督者在安全
屏障暂停 + 恢复；重试经过校验且绝不重复已完成工作（Phase 10 套件
T21/T22）。

## 9. 崩溃恢复

暂停中崩溃 → 重启后不执行直到 RESUME；PAUSE/RESUME/REPLAN 命令中
崩溃 → 幂等恢复、各自恰好应用一次（F12/F13 + Phase 10 套件 T28–T31）。

## 10. 溯源

所有用例 `artifact_lineage_errors = 0`、`provenance_errors = 0`：
注册表指纹校验通过、血缘可解析、每个 artifact 带生产者与溯源；
human-input artifact 带 `source_type=human`。

## 11. 确定性

金样本 B011 运行 3 次：任务状态一致、artifact 编号一致（确定性提交
顺序）、eval 结论一致、修订一致。明确区分：**语义确定性**（已验证）
与**运行时元数据差异**（时间戳、事件 uuid、线程顺序 —— 不比较）。

## 12. 真实 LLM smoke

确定性验收从不调用 LLM。真实 GLM 行为由既有套件覆盖
（`evals/agent-benchmark` 33 例、`python -m runtime.agent.smoke_test`），
并刻意排除在确定性契约之外 —— LLM 措辞差异不得改变确定性预期。

## 13. 已知限制

Benchmark 脚本是声明式 fixture（确定性 provider 脚本），不是自由格式
自然语言；四 Agent 金样本的 happy path 没有 A2A 消息（handoff 覆盖在
Phase 6 套件）；`SIGNAL_LONG_RUNNING` 读取墙上时钟；无 token 核算
（预算是任务/重规划/修复计数）；无外部通知渠道（飞书是未来适配器）。

## 14. 最终验收

```
Benchmark 用例：11/11 PASS     故障注入：18/18 PASS
False-pass：     计数 0        并行一致性：1.0
重规划：PASS                   HITL：PASS        HOTL：PASS
崩溃恢复：PASS                 溯源：0 错误      确定性：PASS
硬门：全部为 0
```
