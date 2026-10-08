# Phase 28.M5-A — No-Plan Production Gray Observation 报告

Date: 2026-09-25 · 授权：Owner M5-A（**仅 no-plan**；full/Planning 经权威/
M5 cutover/legacy 清理均未授权）。**Full Authority NOT ENABLED。**

## 1. Authorization Scope（如上复述，逐条遵守）

未触碰：full · Planning 经权威 · M5 cutover · legacy 路由删除 · 切片
flag 删除 · Intent/Router/Registry/工作流所有权 · grounding gate ·
artifact/approval/event 契约 · 执行脊柱。零 HARD STOP。

## 2. Configuration（部署记录）

- **Preflight**（只读核验全过）：resolver 三档就绪；flag 默认 QA=ON
  （D4）/product=OFF/plan=OFF；**任何环境无持久 authority 设置**
  （.env 无 ROUTER_AUTHORITY 条目）；rollback 机制在位；:8000 为
  Owner 旧进程（**未触碰**——切换该进程属 Owner 动作，如实记录）。
- **部署**：隔离实例 127.0.0.1:8106，`ROUTER_AUTHORITY=no-plan`，
  live glm-5.3（.env；fast glm-5.3-flash）+ **mock 治理知识组合**（进程
  环境无 weknora 变量——组成如实记录）。部署时间 2026-09-25T14:30:15Z；
  配置指纹 `083fc0145387befb`（tmp/m5a-deploy-record.json）。回滚
  = env 清除+重启（已演练，见 §12）。未向用户暴露任何内部 ID。

## 3. Traffic Volume

```text
LIVE SAMPLE: 0（真实用户流量：零——本机无真实用户接入）
Probe 注入流量: 10 轮（P1-P10，含 1 条上下文种子轮；全部终态，
  run_id 清单 tmp/m5a-probes.json，与真实流量可区分——诚实分离）
>>> INSUFFICIENT LIVE SAMPLE: YES（维持显式声明）
```

## 4. QA Observations（P1/P2 + 权威路由轮）

- 路由：intent→**Router Authority**→qa registry→QA Agent→既有脊柱 ✓
  （reason=authority，非 flag）。
- grounding_status：**0/2 grounded，2/2 citation_gate_rejected**（live
  模型两轮均未过引用闭环门，各 2 次尝试后诚实拒答）。**零无据交付**。
- 与 B5.1（3/4）相比合规率显著走低——**如实上报为 live 模型合规方差/
  退化观察**，非 staging 缺陷（门 fail-closed 正常工作）；候选归因：
  本轮问题更长（对比型问题）→答案更长→漏引概率升高。低频事件不隐藏。

## 5. Product QA Observations（P3/P4/P5/P9/P10）

- 目录锚点：P005/P009/P001 解析正确（product_ref 在案；P5 缺失产品=
  None 如实）；KB 证据：合格证据参与（P10 上下文→P001 链接文档）。
- grounding：**1/5 grounded**（P10，证据闭环复检 PASS）；refused 4
  （citation_gate 3 + insufficient 1）。P9 禁推试探→citation_gate
  拒答（**无推荐泄漏交付**）✓。Provider 故障：0（llm_unavailable 0；
  最长 135.8s 有界内）。

## 6. Planning Isolation

P6 规划 / P7 修改：**全部 existing-agent、flag_off**——**ISOLATED，
零泄漏**（no-plan 权威集不含 planning，实证）。P7 修改由 legacy 承接
并追问（ADR-019 M1 澄清路径保持；遥测 reason=flag_off 描述切片未因
flag 触发，M1 语义在意图层已强制）。

## 7. Routing Correctness

intent 分布（10 轮）：knowledge_qa 2 · product_qa 5 · insurance_plan 1 ·
modify 1 · unknown 1。**authority 触发 7 / flag 触发 0**（QA 类全部经
权威，符合 no-plan）· **意外路由 0**（unknown→legacy 兜底，绝不业务
Agent）· 澄清率（modify）：1/1 legacy 追问。

## 8. Safety

**PASS**：幻觉证据 0（闭环门拒一切无据输出）· 无支撑保险事实交付 0 ·
推荐泄漏 0（P9 拒答）· 非法 Agent 选择 0 · 意外 artifacts 0（QA 轮零
artifact，D1）· 意外 risk signals 0（零 approval/eval_failed）。
悬挂引用 0（evidence_refs⊆map 复检）。

## 9. Grounding

- 证据闭环复检（对 grounded 轮重跑 gate）：**1/1 PASS**。
- 拒答全部带机器可读 failure_reason ∈ 枚举；refused 轮 evidence_refs
  均为空 ✓。**Grounding violations: 0**。

## 10. Latency（QA 类 7 轮，live 模型主导）

min 0.5s（快速拒答）· p50 63.5s · max 135.8s（≤240s 预算，零超时）。
分类延迟 0-16ms（可忽略）。

## 11. Regression（全绿）

```text
Backend: 729 passed / 0 failed（B4 17/17 GREEN + M4 9/9 + 安全/路由/
  QA/Product-QA/Planning 隔离测试全在内）
Web:     148 passed / 2 skipped · tsc clean
分类: 零失败——无需分类（1-5 类均未出现）
```

## 12. Rollback

**PASS**：no-plan→unset+重启（既有 env+重启机制，未即兴新机制）——
回滚后 QA 回到 D4 默认 flag 触发（reason=fired）/ planning 保持
legacy（flag_off）✓；流量窗口（10 轮 run_id 清单）与遥测全部保留
（shadow.jsonl + run_dir AnswerContext 增量审计不删）。

## 13. Known Issues

1. live 模型引用合规率波动（本轮 1/7 vs B5.1 3/4）——门无据不交付，
   但拒答率伤体验；建议 Owner 考虑模型档位实验或免责句豁免裁决
   （后者=gate 语义变更，需显式批准）。
2. 知识组合为 mock 治理语料（非 WeKnora 生产语料）——真实生产观测
   需 Owner 配 weknora env（HD-2 数据侧仍未决）。
3. :8000 Owner 旧进程未切换——真实流量观测前提是 Owner 将生产进程
   升级到当前代码并设 no-plan。

## 14. Statistical Limitations

```text
INSUFFICIENT LIVE SAMPLE: YES
样本 = 10 轮脚本注入探针（单一问题集、单次会话、单实例）；无真实
用户流量、无真实流量分布、无时长效应。所有比例为点估计，无置信区间。
不得据此得出生产结论。
```

## 15. Recommendation / Next Gate（事实性）

- Staging 机制（权威路由/隔离/遥测/回滚/安全）在受控流量下全部正确
  工作；本轮未出现任何 staging 侧缺陷。
- 真正的 gray 观测需：(a) Owner 将生产进程升级到当前代码并设
  `ROUTER_AUTHORITY=no-plan`；(b) weknora env（或接受 mock 语料）；
  (c) 真实用户接入。届时重跑本报告的指标采集。
- live 模型引用合规是需要 Owner 关注的第一运营问题（拒答率）。

```text
NEXT GATE:
Owner authorization required for Router Authority = full
（不得由绿灯/低错误率/灰度成功/ADR-025 已批/无事故推断授权）
```
