# 样例会话（Examples）

本目录存放**已填写的完整 / 半成品客户档案**，作为 Skill 采集逻辑的演示样例，仅供人工阅读参考，**不参与 eval 自动校验**（eval 只处理 `../evals/clients/` 下的 `CASE_*-Regression` 夹具）。

> 与以下两者区分：
> - `../evals/clients/` —— 冻结的回归测试夹具（由 `evals/executions/*.json` 经 `scripts/apply-execution.ps1` 生成），供 `run-eval.ps1` 校验。
> - `client-intake-data/clients/`（项目根下，运行时创建）—— 真实客户会话的写入目录，Skill 在运行时自动维护。

## C009-张先生三口之家
- 状态：✅ Intake 完成（R4，H1-H6 全部满足）
- 要点：补 Confirmed 城市=北京、家庭年支出约 35 万 → P0 阻塞全部清空；新增 Inferred I007 保费占收入 2.5%（保额有上浮空间）、I008 北京一线城市效应（教育/医疗成本上浮）；Pending P001 下次正式提醒 R5；Handoff Notes 已交接，可直接交 Needs Analysis。

## C010-李女士单亲妈妈
- 状态：❌ 未完成（R0，仅初始化）
- 说明：单亲妈妈家庭结构样例，用于演示家庭支柱责任与子女教育维度的采集。
