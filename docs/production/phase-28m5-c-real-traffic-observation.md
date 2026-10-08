# Phase 28.M5-C — Real-Traffic Full Authority Observation 报告

Date: 2026-09-25 · 观测窗口 15:22–15:35Z（约 13 分钟，真实生产端口）。
零代码改动（git tracked-modified = 既有 9 项；仅 docs+tmp 证据）。

## 1. Executive Summary

生产实例 :8000（**旧进程**，2026-09-24 21:31 启动、28.A-1 时代代码）
按 Owner 本阶段授权以仓库标准方式重启为**当前代码 +
`ROUTER_AUTHORITY=full`**（运行级 env；代码默认 slices 未变）。真实
生产端口上完成受控观测：路由/规划全链/安全/grounding/引用/延迟/
回滚全部按 M5-B 基线工作；**真实用户到达 = 0**（web UI 未运行 + 实例
bus 计数证实仅探针流量）——**INSUFFICIENT LIVE SAMPLE 维持**。观测后
执行回滚演练（PASS）并**恢复 Owner 授权的 full 灰度配置**继续暴露。

## 2. Authorization

Owner M5-C Prompt=授权真实流量受控观测 + :8000 标准重启。未授权：
cleanup / 永久 full / 流量扩大 / gate 修改——全部遵守；零 HARD STOP。

## 3. Preflight（只读，全 PASS）

治理（ADR-025 APPROVED、M5-A/B COMPLETE）· 代码（单 resolver git
grep；默认=slices；citation gate sha b8f392e84030 未变+活体检验）·
**WeKnora 前置**：.env **无任何 WEKNORA 变量**——生产知识链路=
治理 mock 组合（**既有环境状态，非本阶段切换**；真实生产知识链路需
Owner 配置 weknora env+语料——HD-2 未决，如实记录为限制）· LLM=live
glm-5.3（.env）。

## 4-5. Production Instance / Fingerprint

- **旧进程确认**：PID 10204，`python -m runtime.server --port 8000`，
  启动 2026-09-24 21:31:42（早于全部 M 系列工作）→ 报告
  **PRODUCTION INSTANCE NOT YET UPDATED** → 按授权标准重启
  （idle 0 runs，无活动连接，安全窗口）。
- 新实例：当前工作树代码（HEAD 9407a84 + 未提交跨度
  27.7.6-D..F..28.M5-B），`ROUTER_AUTHORITY=full`（运行级），
  15:22:13Z 上线；指纹 `f1df4bd64d543b2b`（tmp/m5c-deploy-record.json）。

## 6. Deployment Scope

单一生产实例 :8000（无比例灰度能力——未自建流量分配系统）；观测窗口
15:22–15:35Z；流量人口=该实例可达的一切调用方（实际：仅本阶段探针；
web UI 5173 **未运行**——真实用户无 UI 入口，如实记录）。

## 7. Real-Traffic Sample（严格五分类）

```text
REAL_USER:      0（实例 bus runs=6=全部探针；shadow 甄别 109 条
                 非探针记录=并行回归测试的进程内流量[chat_sse/cfg_*/
                 chat_gray_* 等测试 chat id]→ SYSTEM_TEST）
DEVELOPER:      0 · SYNTHETIC: 0
SCRIPTED_PROBE: 6（chat_m5c_* 前缀，run_id 清单 tmp/m5c-probes.json）
SYSTEM_TEST:    109（in-process battery，不冒充任何真实流量）
>>> INSUFFICIENT LIVE SAMPLE = YES（真实用户证据不被探针替代）
```

## 8-9. Intent Distribution / Router Authority（探针口径）

intent：insurance_qa 1 · product_qa 2 · insurance_plan 1 · unknown 1 ·
modify 1。**authority 触发 4/4（QA 类+规划）· flag 触发 0 · 意外路由
0 · wrong-agent 0 · router error 0 · LLM/frontend 选 Agent：0**（结构
保证+实测）。

## 10. QA Observation（C1/C6）

total 2 · Router authority 2 · grounded 0 · refused 2
（citation_gate_rejected ×2——C6 禁推探针被拒=安全正确）·
unsafe delivery **0**（全部拒答均为安全拒答）· provider failure/
timeout 0 · 延迟 37.8s / 168.1s（有界内）。

## 11. Product QA Observation（C2）

total 1 · authority 1 · **grounded 1**（目录锚点 P001；证据闭环复检
PASS；合规交付）· 目录缺失/推荐泄漏/无支撑产品事实：0 · 61.9s。

## 12. Planning Observation（C3）

total 1 · Router authority 1 · 身份=**insurance-planning-agent** ✓ ·
completed（38.7s）· 既有脊柱事件（tool/artifact/eval）· repair/
artifact 失败 0 · 无支撑产品事实 0 · 意外推荐 0 · **跨案污染 0** ·
执行错误 0。**无第二 Planning Runtime**（结构+事件流双重确认）。

## 13-14. Grounding / Citation Compliance

- Grounding（证据闭合）：grounded 轮复检 **PASS**；安全维度 unsafe
  factual delivery = **0**。
- Citation（契约合规）：grounded 1/1（本轮！）；拒答 2 为长答案漏引
  （C6 168.1s=两轮再生成仍不合规→诚实拒答）。与 M5-A/B 的 1/7 相比
  本轮小样本 1/1+2 拒——**样本过小无统计意义**；延续记录为
  MODEL-FIT/UX 问题（非 Router 缺陷；gate 零改动）。
- 分类报告（按 §18 拆分）：Safety=PASS（零不安全交付）·
  Grounding=PASS（闭合复检）· Citation=波动（小样本）·
  Usability=拒答率仍为主要成本。

## 15-16. Safety / Cross-Case — **PASS**

S 系列等效检查：幻觉交付 0（gate 拒）· 推荐泄漏 0（C6 拒答）·
wrong-agent 0 · 跨案 0（每探针独立 chat/case；planning 单 case_id）·
内部 ID 用户暴露 0（事件遥测检查；用户面仅自然语言状态）。

## 17. Latency（vs M5-B 基线）

Router/Intent 开销 p50 **0ms**（=M5-B 0ms ✓ 可忽略）。总延迟 p50
38.7s / max 168.1s（M5-B：QA p50 73.1/p95 134/max 134——本轮同量级，
live 模型主导；168.1s≤240s 预算，零超时；归因=生成长度，非 router/
retrieval——分类延迟 0-16ms）。

## 18. Artifact Delivery

Planning C3 产物沿既有 artifact spine（类型/schema/版本=contracts
既有；**零新类型/schema**）；交付=既有 chat/事件机制；渲染/深链/
导出=既有路径（未新增行为）。Artifact failure 0。

## 19. Human Escalation

窗口内 needs_review 触发 0；既有语义（escalation 而非默认审核）未被
触碰——Full Authority 未被解读为"全自动通过"。

## 20. Model-Fit Findings（观察记录，未修改变量）

| 项 | 值 |
|---|---|
| symptom | 长答案漏引→citation gate 拒答（C1/C6） |
| frequency | 本窗口 2/3 QA 类拒答（M5-A/B：6/7、5/7） |
| traffic type | SCRIPTED_PROBE（长/价值判断问题） |
| model / prompt | glm-5.3 / qa-answer-v3 · product-qa-answer-v3 |
| grounding/safety | 零不安全交付；闭合全 PASS |
| user-visible impact | 拒答文案（诚实但高拒答率） |
| safety impact | 无（fail-closed） |

## 21. Incidents — **NONE**

P0 清单零触发；无回滚触发条件出现；无 Owner 升级事项。

## 22. Rollback — **PASS**

full→unset+重启（生产端口实证）：QA→D4 flag（fired）· Product QA→
legacy（flag_off）· Planning→legacy（flag_off）· unknown 不变 ✓。
遥测全保留。演练后实例**恢复 Owner 授权的 full 灰度配置**继续暴露
（15:36Z 起，:8000 LIVE）。

## 23. Regression — **PASS（零失败）**

backend **729/0**（B4 17/17+M4 9/9+M3 7/7+安全全含）· web **148+2** ·
tsc clean。

## 24. Statistical Limitations

**INSUFFICIENT LIVE SAMPLE = YES**：真实用户 0；探针 6（单一问题集/
单窗口/单实例）；并行测试流量已按 chat 前缀与实例 bus 计数双重甄别，
绝不计入。Synthetic/scripted probes **不能替代** real-user evidence。
不得据此宣称 production validated。

## 25-26. Cleanup Deferred / Permanent Authority

M5 Cleanup **DEFERRED**（候选清单沿用 M5-B §19，未动）。Permanent
Full Authority **NOT DECIDED**（代码默认=slices；当前生产实例持
Owner 授权的运行级 full 灰度，可随 Owner 指令 unset 回滚）。

## 27. Next Gate

```text
Owner decisions:
  ① 真实用户流量引入（启动 web UI 并接入真实用户；或直接 API 暴露）
     ——届时重跑本报告指标采集；
  ② weknora env + KB 语料配置（HD-2）——真实生产知识链路前提；
  ③ citation-compliance 缓解决策（模型档位/免责句豁免=gate 语义变更）；
  ④ M5 Cleanup 授权（独立阶段）；⑤ Permanent Full Authority 决策。
```

## 28. 四层级结论（按 §35）

```text
Technical Path:        PASS（生产端口全链验证=B4/M5-B 基线一致）
Production Operation:  PASS（:8000 当前代码+full 运行中；回滚演练过）
Real User Evidence:    INSUFFICIENT（0 真实用户；UI 未运行）
Safety:                PASS（零不安全交付；零跨案；零泄漏）
```
