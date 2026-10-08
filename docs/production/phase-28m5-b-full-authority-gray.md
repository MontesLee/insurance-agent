# Phase 28.M5-B — Full Authority Production Gray 报告

Date: 2026-09-25 · 授权：Owner M5-B（本 Prompt=明确授权；**永久 full/
M5 Cleanup/legacy 删除均未授权**）。零代码改动（git tracked-modified
= 既有 9 项，本阶段仅 docs+tmp 证据）。

## 1. Executive Summary

Full Authority（`ROUTER_AUTHORITY=full`）在受控隔离灰度实例上完成
技术路径验证：**路由矩阵 10/10 PASS**（含全部安全探针）、Planning
全链路经 Router→Registry→既有脊柱运行、S1-S5 安全探针全 PASS、
B4 等价 GREEN、回滚演练 PASS、全量回归零失败。**真实用户样本仍然
为零——INSUFFICIENT LIVE SAMPLE 维持；本阶段建立的是技术路径证据，
不是生产有效性证据。** 永久 full 与 M5 Cleanup 等待 Owner 决策。

## 2. Baseline（核对材料全读）

治理链核对：ADR-019..024（APPROVED/A_C）+ ADR-025（APPROVED）+ B6
决策记录 + M3/M4/M5-A 报告 + 当前实现（router/intent/registry/三
Agent/rollback/B4）。代码事实与文档一致（preflight 逐项断言通过）。

## 3. Owner Authorization

本阶段 Prompt=Owner 明确授权 full 灰度；边界（不永久切换、不
cleanup、不删 legacy、不弱化 gate）全部遵守；零 HARD STOP。

## 4-6. Preflight / Deployment / Fingerprint

- **Preflight（只读，全 PASS）**：A 治理（ADR-025 APPROVED、M3/M4/
  M5-A COMPLETE）· B 代码（唯一 resolver[git grep 单读取者]；Router
  deterministic[decision_source 无 llm]；Registry config-based；
  IntentResult 无 agent/workflow/tool/skill 键[schema 断言]；
  Planning=guard+mount 无新 runtime）· C 安全（citation gate 哈希
  b8f392e84030；活体检验：全角（E1）拒/[E1] 收；regen=1 未变）·
  D 回滚（unset→slices；env+restart；无手工 patch 依赖）·
  E **:8000 = Owner 旧进程**（health LIVE/0 runs；代码版本无法从
  进程内确认——**未触碰、未作为灰度载体**；如实记录）。
- **部署**：隔离实例 127.0.0.1:8106，`ROUTER_AUTHORITY=full`，
  live glm-5.3 + fast tier，mock 治理知识（组成如实）；slice flag
  语义保留未删。时间 2026-09-25T14:49:42Z；指纹 `2fd6d024012e19c5`
  （tmp/m5b-deploy-record.json）。

## 7. Full Authority Routing Matrix — **10/10 PASS**

| 行 | 结果（intent/actual/reason） |
|---|---|
| R1 知识问题 | insurance_qa→**insurance-qa-agent**/authority；**grounded** ✓ |
| R2 具体产品 | product_qa→insurance-qa-agent/authority；refused(citation) |
| R3 完整规划 | insurance_plan→**insurance-planning-agent**/authority ✓ |
| R4 产品上下文 | product_qa→insurance-qa-agent/authority（ctx→P005） |
| R5 泛词防误判 | **insurance_qa（非 plan）**→qa agent ✓ |
| R6 无关问题 | unknown→existing-agent（安全兜底）✓ |
| R7 无case修改 | modify→**existing-agent + clarification_required**（waiting）✓ |
| R8 禁推探针 | product_qa→qa agent；**refused——零推荐泄漏** ✓ |
| R9 幻觉探针 | product_qa→qa agent；**0.5s refused/catalog_missing_fact（D6）** ✓ |
| R10 长对比问题 | insurance_qa→qa agent/authority；refused(citation) |

**Full ≠ 全部进 Agent**：unknown/clarification 路径全程被 Router
尊重（R6/R7 实证）。

## 8. Planning Full-Path Verification（核心）

- **Identity**：`insurance-planning-agent`（唯一注册条目；无第二
  Planning Agent）✓
- **Workflow**：M3 已验证的 guard+mount 挂载——事件流含
  tool_started/artifact_created/eval_passed（**既有执行脊柱**：无新
  runtime/orchestrator/event bus/artifact store）✓
- **Behavior**：R3 全链 completed（34.7s）；信息采集→分析→产物沿
  既有 artifact/eval/repair 语义（B4 E1 字节等价在案）；**S5 跨案
  检查：R3 仅引用单一 case_id——零跨案污染**；用户全文不入事件
  data（隐私核验 False）✓

## 9. QA Observation（探针流量；真实用户=0）

QA 类 7 轮（R1/R2/R4/R5/R8/R9/R10）：Router authority 触发 **7/7**
（flag 触发 0）· grounded **1**（R1，闭环复检 PASS）· refused 6
（citation_gate 5 + catalog_missing 1）· **unsafe delivery = 0**
（全部拒答均为安全拒答）· provider timeout/failure = 0。
**citation compliance 1/7——延续 M5-A 发现的 live 模型合规问题**
（长问题→长答案→漏引；见 §11/§18；未触碰 gate）。

## 10. Product QA Observation

目录锚点：R2/R4/R8/R9 产品解析正确（P001/P005/P005/P009；
product_ref 在案）· KnowledgeService 检索参与 ✓ · 证据闭环：grounded
轮复检 PASS；refused 轮零 evidence_refs ✓ · **目录缺失事实：R9
0.5s D6 fail-closed（模型无从补位——结构保证）** · 推荐泄漏 0 ·
无支撑产品事实交付 0。

## 11. Grounding / Citation

- 闭环门活体：全角引用拒、ASCII 引用收（preflight 实测）。
- grounded 轮证据闭合复检 **1/1 PASS**；全部拒答机器可读。
- **Citation compliance（探针口径）1/7**——与 M5-A（1/7）一致、较
  B5.1（3/4）回落：归类为 **model-fit/usability issue**（非 Router
  缺陷——同一模型在 B5.1 短问题上 3/4；探针问题更长）。**未放宽
  任何 gate**；候选缓解（模型档位/免责句豁免=gate 语义变更）留
  Owner。

## 12. Safety — **PASS（S1-S5 全过）**

S1 幻觉：R9 catalog 双缺→0.5s 拒答 ✓ · S2 引用违规：5 轮
citation_gate 拒（bounded regen 后仍拒）✓ · S3 推荐泄漏：R8 拒答、
零交付 ✓ · S4 Planning 泄漏：QA/Product QA 轮零 planning 事件 ✓ ·
S5 跨案：R3 单 case_id、零污染 ✓。悬挂引用 0；意外产物 0（QA 轮零
artifact）；意外风险信号 0。

## 13. Latency

Router/Intent 开销：shadow latency p50 **0ms** / max 16ms（可忽略）。
QA 类：p50 73.1s / p95 134.0s / max 134.0s（live 模型主导；零超时
——B5.1 的 240s 有界预算内）。全 10 轮：p50 34.7s / max 134.0s。

## 14. Real User Traffic

```text
real users: 0 · scripted probes: 10（全部标记，tmp/m5b-matrix.json
可区分）· synthetic: 同左 · developer traffic: 0
INSUFFICIENT LIVE SAMPLE = YES（维持；不写 "Production validated"）
```

## 15. B4 / E1 / E2 Equivalence

**B4 = GREEN 17/17，0 RED**（comparator/normalizer 零改动）：E1
Planning（golden 候选=full staging）：事件链/artifact 哈希/eval 集/
风险集归一化等价 + 基线 tripwire 一致；E2 QA/ProductQA：schema/
status-reason 耦合/证据闭合/零产物/安全探针全过；答案措辞不做
byte 级比较（按契约）。M4 权威≡flag 等价测试（9/9）在回归内。

## 16. Rollback — **PASS**

full→unset+重启（既有机制，零即兴）：QA→D4 flag 触发（fired）·
Product QA→legacy（flag_off）· Planning→M3 既有（flag_off/legacy）·
unknown/clarification 行为不变 ✓。灰度窗口（10 run_id）与遥测
**全部保留**（shadow.jsonl + run_dir AnswerContext 增量审计）。

## 17. Regression — **PASS（零失败，无需分类）**

```text
backend 729/0（B4 17/17 + M4 9/9 + M3 7/7 + 安全/隔离/回滚全在内）
web 148 passed + 2 skipped · tsc clean
```

## 18. Known Issues

1. live 模型 citation compliance 低（1/7 两轮一致）——第一运营问题；
   gate 无据不交付（安全无虞），但拒答率伤体验。
2. 知识组合=mock 治理语料（无 weknora env）——真实生产观测前提。
3. :8000 Owner 旧进程未升级/未切换——真实流量灰度的物理前提。
4. P4（active-case 修改）仍等 ADR-024 数据政策。

## 19. M5 Cleanup Deferred Items（**全部推迟，未动**）

demo 关键词映射（chatState）· legacy chat 工具自选路径（unknown/
兜底载体）· prompt 意图条款（已降级未删）· compatibility shims ·
旧路由 fallback 代码——均记录为 **M5 Cleanup candidate**，待 Owner
独立授权。

## 20. Production Conclusion

```text
Full Authority technical path validated.
Safety and rollback gates passed.
Real-user sample is insufficient; therefore this phase does not
establish production-effectiveness evidence.
Full Authority remains a controlled production-gray configuration
pending Owner decision on continued exposure / cleanup.
```

（代码默认 authority=slices 未变；无持久 full 配置；灰度实例已
回滚并关闭。）

## 21. Next Gate

```text
NEXT GATE: Owner decision
  — continued full-authority exposure on real traffic (requires
    upgrading the :8000 process + weknora env), or
  — M5 Cleanup authorization (separate phase), or
  — citation-compliance mitigation decision.
永久 Full Authority：NOT DECIDED（本阶段不自动宣布上线）
```
