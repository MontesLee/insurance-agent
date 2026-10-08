# S2 Batch-2 UAT Start — STAGED（窗口维持 OPEN-UNSTARTED）

Date: 2026-09-30 · Owner 决定：**暂不分发**（本轮零分发零窗口起算·
不伪造起点）· 状态：**S2 STAGED / 48H WINDOW NOT OPEN**

## 1-2. Batch-2 用户与分发状态

| 用户 | key 状态 | whoami 验证 |
|---|---|---|
| pilot-user-03 | `distribute/03.key`（token-only）staged | ✓ CONSUMER authenticated |
| pilot-user-04 | `distribute/04.key` staged | ✓ |
| pilot-user-05 | `distribute/05.key` staged | ✓ |

**物理分发：未执行**（Owner 选择暂不分发）。分发材料：
`tmp/pilot-keys/distribute/{03,04,05}.key` +
`HANDOFF-s2-batch2.md`（入口 http://localhost:5273）。

## 3. S2 起始时间

**DISTRIBUTION_COMPLETED_AT = 未发生**——48h 窗口**未起算**
（S2 = OPEN-UNSTARTED 维持）。任务规则遵守：未以 readiness/prompt/
服务启动时间充当起点。起算程序：Owner 分发完成→回报实际时刻→
记录于 REGISTRY+观察台账→窗口开表。

## 4-7. 当前 Production/Runtime 状态（实测）

| 项 | 值 |
|---|---|
| commit | **e1aba0e**（D-08 intent span RESEALED） |
| :8123 | PID 31740 ·health 200·灰度 `CLAIM_SUPPORT_ENABLED=1`（P2-1+FIX2+OBS-1 全载入） |
| :5273 / WeKnora / PG | 200 / 401-alive / :5433 Up |
| Claim Support | FROZEN·S1 CURRENT_GRAY·Authority NOT GRANTED |
| Intent / LLM | SEALED @ e1aba0e·`INSURANCE_AGENT_INTENT_LLM`=OFF·Det=AUTHORITY |
| Planning Claim Support | NOT ENABLED |

## 8. Observation Protocol（就绪·沿 OD-12 冻结）

Gate A/B/C 周期记录（`tmp/obs/k28ii_s2_observation.jsonl`·会话内
cron 3h 周期+跨会话回放协议）·UX 观察项（拒答理解/处理中理解/
断线困惑/taxonomy 不匹配）+P2-1 前端断线提示+P2-2 PG 告警面=
记录不修改。

## 9. Rollback Mechanism（沿 OD-12 Gate A 六步）

任一 A1-A6 → `CLAIM_SUPPORT_ENABLED=0`→restart→OFF 签名→旧路径
验证→incident evidence→STOP。

## 10-11. Initial Health & Safety Baseline

Health 全绿（§4 表）·安全基线=OD12_BASELINE 沿封（FP=5·Escape=0·
FR=0/6·P/R 0.80·865+2·RV4-A 0/RV4-B refused）+Pre-UAT 全零横切
（Final Gap Test）。

## 12. 声明

```
S2 = STAGED（三 key 就绪·未分发）
48H WINDOW = NOT OPEN（待 Owner 物理分发完成时刻）
PRODUCTION AUTHORITY = NOT GRANTED
S3 = NOT AUTOMATIC
```

**Owner 后续动作**：任意时刻完成三把 key 物理分发→回报实际完成
时刻（精确到分钟）→窗口起算（新会话或本会话均可执行记录）。
