# 测试策略

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](testing.md)

本项目把测试当作"架构主张为真"的证据（fail-closed 的 eval、禁止自评
PASS、依赖屏障、确定性提交、恢复）。下面的数字是快照 —— 每一节都给出
可以复现它的命令。

## 1. 命令

```bash
pytest tests/runtime -q                             # pytest 套件（当前：227 passed）
PYTHONIOENCODING=utf-8 python tmp/run_regression.py # 全部独立套件（52 个）
python evals/agent-benchmark/run_agent_benchmark.py # 33 例 benchmark + 安全硬门
python evals/agent-benchmark/run_golden_cases.py    # golden 回归
cd web && npm test                                  # React UI 单测（vitest）
```

## 2. 两层评估纪律

| 层 | 位置 | 回答的问题 |
| --- | --- | --- |
| Skill 级 eval | `.trae/skills/<skill>/evals/` | 这个 skill 的行为是否符合自己的契约？ |
| 系统级 eval | `evals/` | 组装起来的 agent 系统端到端表现如何？ |

两层共用同一纪律：只认可机检断言；FAIL → repair → 重跑；负向自检
（一个不会失败的测试什么也证明不了）。

## 3. 测试类别（`tests/runtime/`，pytest + 双模式脚本）

每个套件既能在 pytest 下跑，也能作为脚本运行（`python
tests/runtime/test_*.py`），通过共享的 `Checks` 累加器 —— 这是早于
pytest 体系就存在的仓库约定。

| 类别 | 套件（示例） |
| --- | --- |
| 单元 / 契约 | `test_agent_tools`、`test_agent_model`、`test_agent_config`、`test_planner` |
| Harness 与状态机 | `test_harness`、`test_events`、`test_event_bus` |
| Agent 执行器 | `test_specialist_agent_executor`、`test_agent_loop`、`test_agent_intent` |
| **Eval 边界** | `test_eval_boundary`（工具不评估；harness 评估；repair 有界；禁止自评） |
| A2A / 消息驱动 | `test_agent_communication`、`test_message_handoff`、`test_message_driven_scheduler` |
| 恢复 | `test_cross_process_recovery`（新进程从磁盘续跑） |
| **并行调度器** | `test_parallel_scheduler`（T1–T21 + 禁止 worker 自评 + 探针"牙齿"） |
| **并行 4-Agent E2E** | `test_parallel_4_agent_e2e`（阻塞探针的重叠证明） |
| 串行 4-Agent E2E | `test_true_4_agent_e2e` |
| Web/UI server | `test_server`、`test_sse`、`test_concurrency` |

并行测试用**同步原语而非计时**证明核心主张：阻塞探针只在两个任务
同时处于执行内部时才放行（另有专门的"探针牙齿"测试证明探针会拒绝
串行交错 —— 实现错了测试就失败）。

## 4. 独立脚本套件（`tmp/run_regression.py`）

`tests/{contracts,e2e,eval,evidence,structure,workflow}` 是脚本式套件
（模块级 `sys.exit` —— 有意不在仓库根目录被 pytest 收集）。runner 执行
全部 52 个并汇报 `PASS / FAIL / INFRA_ERROR`。当前快照：**51 PASS、
0 FAIL、1 INFRA_ERROR**（见下，pre-existing）。

## 5. Benchmark 与 golden

`evals/agent-benchmark/` 以 agent 模式端到端跑 33 个用例并施加安全硬门
（无凭据结论、repair 有界），另有 9 个 golden 用例做前后门控。结果写
入 `results.json` / `golden_results.md`。注意：跑 benchmark 会改写
`results.json` 的 `generated_at` 时间戳 —— 若不想让 diff 里出现这类
噪音，用 `git checkout -- evals/agent-benchmark/results.json` 恢复。

## 6. 已知基础设施问题（pre-existing，干净树已复现）

- `step3-mutation` 在回归 runner 中报 INFRA_ERROR（其自身 traceback；
  与当前运行时代码无关 —— 把工作区完全 stash 后可复现）。
- cp936 控制台：runner 与部分套件会打印 GBK 无法编码的字符 —— 设置
  `PYTHONIOENCODING=utf-8`。
- 不要在仓库根目录裸跑 `pytest -q`：脚本式套件在 import 时抛
  `SystemExit` 会中断收集。请用 §1 的命令。

## 7. 新增 runtime 测试的约定

遵循仓库风格（见任一套件头）：双模式 section + `Checks`、`tmp/` 下的
临时 harness root、用 FakeLLMProvider 脚本获得确定性行为、`finally` 里
`cleanup()` 清理临时目录。测试必须在其声称的性质被破坏时失败 —— 避免
`try/except: pass`，避免基于 sleep 的并发证明。
