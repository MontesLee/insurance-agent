# 面试作品 Demo 脚本（5–10 分钟）

> 🌐 语言：🇨🇳 中文 · 🇺🇸 [English](portfolio-demo.md)

以下全部是真实运行时输出 —— 每一行状态都来自真实 harness 产出的
持久事件/artifact/checkpoint。没有假活动、没有预写死的"AI 思考"。

## 准备（一个终端，约 30 秒）

```bash
python -m demos.demo_four_agent        # 金样本：4 Agent、并行、报告
```

## 第一幕 —— 正常路径（2 分钟）

运行 `python -m demos.demo_basic`。随着转录滚动讲解职责分离：

1. **Planner = 做什么** —— 经过校验的任务图（10 项检查的校验器）。
2. **Harness = 何时** —— 任务生命周期、依赖屏障、checkpoint。
3. **Agent = 怎么做** —— 带受控工具集的专家；他们绝不自评 PASS。
4. **Eval = 质量** —— 每个 artifact 都过门禁；repair ≤ 2；artifact =
   带血缘的持久事实。
指着 RUN SUMMARY 讲：任务、agent、artifact、评估、风险级别、终态。

## 第二幕 —— 失败是诚实的（2 分钟）

`python -m demos.demo_replan`。方案任务失败（agent 拒绝编造）。观察：
agent_failed → 下游 BLOCKED → 确定性重规划触发 → Planner → 校验器 →
图 v2 → diff → 接受 → 报告完成。说出定义这个项目的那句话：

> 没有任何环节伪造成功。失败被保留，图在同一套校验下被修订，已完成
> 的工作从未重跑。

## 第三幕 —— 人类的两种参与方式（3 分钟）

- `python -m demos.demo_hitl` —— 高影响重规划停在 WAITING_HUMAN；
  批准；只有 Harness 恢复执行。**Human-in-the-loop：一个决策门。**
- `python -m demos.demo_hotl` —— 运行时遇到问题，monitor 抬升风险，
  策略在安全屏障暂停；恢复。**Human-on-the-loop：DAG 之上的监督者，
  而不是 DAG 里的节点。**

## 第四幕 —— 并行，可证明地安全（1 分钟）

`python -m demos.demo_parallel`。独立分支并发执行；scheduler 是唯一
写者；artifact 编号保持顺序且确定。补一句：max_concurrency=1 结果
相同（benchmark B007 已验证）。

## 证据包（留着运行或打印）

```bash
python -m evals.benchmark.runner          # 11/11 用例，硬门全 0
pytest tests/runtime -q                   # 300+ 测试
```

`docs/benchmark-report.md` —— 故障注入（18 个场景）、false-pass 计数
0、确定性（3 次完全一致）、崩溃恢复。面试一句话：

> "我做的是 LLM 周边的执行工程：规划经过校验、agent 永不自评、失败
> fail closed、人类在 DAG 之外监督 —— 而且这一切我都能确定性地证明。"
