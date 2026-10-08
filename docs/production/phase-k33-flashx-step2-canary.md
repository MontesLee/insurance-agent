# K.33 · FlashX Step2+ Canary Validation

## 1. Status

**CANARY_PASS_WITH_OBSERVATIONS**（routing 隔离在真实 Agent Run 中完全
生效；QA 路径本轮未被触发——NOT EXERCISED，非失败）。

## 2. Canary Scope

C ×1·D ×1·E ×1（真实 GLM/WeKnora/Agent Runtime·K.31-A 原场景输入·
15 分钟时限内）。Canary 配置=进程 env
`LLM_FAST_MODEL=glm-5.3-flashx + LLM_QA_MODEL=glm-5.3-flash`（`.env`
零触碰）；启动前 `/api/agent/config` 实测
`model=glm-5.3 fast=flashx qa=flash effort=high`（K.32-C 契约面）。

## 3. Routing Results（agent.llm_call 逐调用实测）

| Scenario | run | Step1 | Step2+（N 次） | QA |
|---|---|---|---|---|
| C | run_1c3d6082 | glm-5.3 [MEASURED] | **glm-5.3-flashx ×9** ✓ | NOT EXERCISED |
| D | run_5278902f | glm-5.3 [MEASURED] | **glm-5.3-flashx ×9** ✓ | NOT EXERCISED |
| E | run_ef2a054e | glm-5.3 [MEASURED] | **glm-5.3-flashx ×5** ✓ | NOT EXERCISED |

**G1 ✓（3/3 step1=glm-5.3）·G2/G5 ✓（23/23 step2+ 调用=flashx·零 flash
泄漏）·G3/G4：QA NOT EXERCISED（三轮均走规划/agent-loop 路径，
qa_answered=0）——按规则记 NOT EXERCISED，不伪造通过。**

## 4. Observability

现有 `agent.llm_call` 完整承担：run_id+model+step+duration+status 逐
调用可区分（flashx/flash/主模型）；/api/agent/config 契约面含 qa_model。
零新增 tracing。已知缺口沿用 K.32-B 记录：QA 路径 gateway llm.call 的
model 字段空缺（本轮未触发故无影响）。

## 5. Reliability

3 轮：agent_step_error=0·schema 拒绝 0·invalid continuation 0·repair 0·
terminal failure 0·needs_review 0；终态 C/D/E 全 COMPLETED。
无 FlashX 特有异常迹象 [MEASURED n=3]。

## 6. Latency Observation（OBSERVATION ONLY·n=1 不作统计结论）

C E2E 57.5s（首内容 17.4s·COMPLETED）·D 44.9s（首内容 25.1s）·
E 44.0s。K.31-A 历史证据：flashx 臂 D med 89.0s·E 22.5s（n=3）。
本轮单次值与 K.31-A 区间相容；不据此更新任何性能结论。

## 7. Known Behavior Differences

C 本轮 normal completion（无早澄清）；K.31-A precedent: YES（flashx 臂
2/3 曾 WAITING_USER）——单次不构成方向证据。维持：
**Product decision required**（早澄清行为优劣未裁决）。

## 8. Rollback Verification

配置层 [VERIFIED]：resolver 实测
`LLM_FAST_MODEL=flash + LLM_QA_MODEL=flash` → step2+=flash·QA=flash
（K.32-C Case C 契约复证）；未启动第二轮真实 run 验证回滚（按规则）。

## 9. Production Configuration Safety

`.env` mtime 14:49 全程未变 [MEASURED]；canary 进程已终止并恢复生产
配置后端（/api/agent/config 复证 fast=glm-5.3-flash）；LLM_FAST_MODEL
未永久改动；LLM_QA_MODEL 生产未设置（resolver 回落 fast=现行为）。

## 10. Open Issues

①QA 路由（G3/G4）真实运行未覆盖——待 QA 类场景的金丝雀补充或
Stage 1 期观测 ②C 早澄清产品决策未决 ③QA llm.call model 字段空缺
（K.32-B 可选 1 行）④flashx billing 未核实（K.32 B3）。

## 11. Next Phase

Owner 决策：进入 Stage 1 持续金丝雀（pilot 实例常驻 env 覆盖 +
probe-alpha 合成流量 + 真实用户小样本 1-3 天·观测清单复用
agent.llm_call·回滚阈值按 K.32 §7）或暂缓。

## 12. STOP

**PRODUCTION DEFAULT UNCHANGED · CANARY COMPLETE · STOP（时限内）。**
