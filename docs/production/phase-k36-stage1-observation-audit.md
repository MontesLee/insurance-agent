# K.36 Stage 1 Observation Audit

## Status

**STAGE1_OBSERVATION_CLEAN**

## Production Config（只读 /api/agent/config 实测）

model: glm-5.3 · fast: glm-5.3-flashx · qa: glm-5.3-flash（与 K.35
切换目标一致·零 drift）

## Backend

:8123: **LIVE**（health=200）

## Rollback Artifact

path: `tmp/env.rollback.k35`
status: **VALID**（2083 bytes 可读；内容=切换前状态
LLM_FAST_MODEL=glm-5.3-flash · LLM_QA_MODEL 未设置 ✓；未恢复未修改）

## Post-K.35 Natural Traffic

runs: **NONE**（K.35 smoke 后 0 条新增 glm agent.llm_call 记录 ·
0 个新 run-profile——正常结果，不伪造 observation）

## Routing Observation

Step1: 无新 run → 以 K.35 smoke 为最新证据（1/1=glm-5.3 ✓）
Step2+: 同上（9/9=glm-5.3-flashx · 零 flash 泄漏 ✓）
QA: 无新 QA run → NOT EXERCISED（K.34 执行级证据承接）

无 routing anomaly（无发现泄漏的任何新数据点）。

## Reliability Observation

agent_step_error: 0（K.35 smoke·无新增）
schema rejection: 0 · invalid continuation: 0 · repair: 0 ·
needs_review: 0 · terminal failure: 0

**RELIABILITY = NO_OBSERVED_ANOMALY**

## Known Debt（维持 observation/debt·未动）

- G-1 citation_gate_rejected：known baseline
- QA refused path provenance.model=""：known debt（1 行补齐待 Stage 1 期）
- C early clarification：Product decision required

## Performance

OBSERVATION ONLY（未做任何 P50/P95/对比——按规则）

## Conclusion

Stage 1 配置零 drift ·服务健康 ·回滚工件有效 ·无新流量故无新
anomaly 观察面 ·已知债务三项维持。**一切如 K.35 预期。**

STOP
