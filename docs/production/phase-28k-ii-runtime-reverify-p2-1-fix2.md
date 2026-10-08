# 28.K.28-II-RUNTIME-REVERIFY · P2-1 + FIX2 运行时载入复验

Date: 2026-09-30 · Mode: **RESTART + REVERIFY**（Owner 任务书=重启
授权；零代码改动）· **RUNTIME-REVERIFY: PASS**

## 1. Restart 前状态

HEAD=24082d5·staging=0·:8123 **DOWN**（第十次回收沿袭）·S2=
OPEN-UNSTARTED·Batch-2 未分发·:5273/WeKnora(401)/PG 健康。
盘上待载代码：`claim_support.py` sha `242be576`（FIX2·mtime 09-30
18:37）+ `server.py` sha `b843d582`（P2-1 guard·mtime 09-29 17:43）。

## 2. Restart 后

**PID 33072**·start **2026-09-30 19:16:42**·health 200（~3s）。
载入证明：两文件 mtime 均 < 进程启动 + §3/§4 行为签名（下）。
启动配置：`CLAIM_SUPPORT_ENABLED=1`·LLM Claim Judge OFF（无
authority 路径）·Planning NOT ENABLED·authority=full（pilot 沿袭）。

## 3. FIX2 Runtime Evidence（F2-R1..R4·与运行进程同 env 组合）

| Case | claim×evidence | 结果 | 判定 |
|---|---|---|---|
| F2-R1 | 免赔额0元 × 目录记录形（10000元·标签远数字） | **refused**（citation_gate_rejected） | ✅ 无假支持 |
| F2-R2 | 等待期90天 × 真实正例 | **grounded** | ✅ 正例不误伤 |
| F2-R3 | 免赔额0元 × 免赔额0元 | **grounded** | ✅ |
| F2-R4 | 免赔额1000元 × 10000元 | **refused** | ✅ |
| RV4-B | 健康法规×「重疾等待期90天」 | **refused** | ✅ |

（首版探针 F2-R2/R3 invalid_input=探针问题措辞触发 product_qa
分类——修正问法后全过；非运行时缺陷，如实注记。）
证据：`tmp/obs/k28ii_reverify_fix2.json`（5/5）。

## 4. P2-1 Runtime Evidence

- **PQ-R1（live API·真实服务器进程）**：P001 产品问→completed·
  走受治理 Product QA 路径（本次因引用校准诚实拒答=治理链正常
  工作形态；非 legacy 输出）✅
- **PQ-R2（slice OFF fail-closed）**：本实例 env=full 无法在不改
  运行配置下演练 OFF 态——以**同载入代码的测试 harness**验证：
  `test_p28b4_gate` 7/7（OFF→run_failed/PRODUCT_QA_UNAVAILABLE·
  legacy provider 零输出·shadow 观测保留）+ `test_k28ii_dp_p2_1`
  **23/23**（S1-S5 安全/legacy-valid 不误伤/无 retry 面）✅
  K.24 幂等/K.27-S1 单写/K.1 固定文案由上述套件锁定。
- **PQ-R3（合法非产品路径）**：legacy-valid ×2 completed（23/23 内）✅

## 5. RV4 Runtime Recheck

- **RV4-A（live·真实 WeKnora+真实 C2）**：RV4 原文 query→检索 1
  （农业保险条例）→**C2 qualified=0**——不进 claim support ✅
- **RV4-B**：见 §3——refused·零 grounded·零 citation-only 旁路·
  零尾泄漏（refused 路径 deltas=0 沿密封契约·E2E-16 复证）✅

## 6. Streaming / Security

拒答/失败文案扫描（本次 live 拒答文案+P2-1 fail-closed 文案）：
claim_id/evidence_refs/support_*/UNSUPPORTED/CONTRADICTED/tool/
agent/run_/slice/gate → **零命中**。T_first<T_final 与未支持段
零外流沿 E2E-15/16（22/22 内）复证。retry/regeneration 无门旁路
（E2E-07+P2-1-07）。

## 7. Decision Path Reverify

**E2E 16/16 + FI 6/6 = 22/22 PASS**（`decision_path_e2e_audit.py`
在载入代码上复跑；product_qa OFF fail-closed 与 short⊂long
false-support=0 均含其内）。

## 8. Full Regression

Claim Support **65/65**·P2-1 **23/23**·B4 7/7·E2E+FI 22/22·
**全电池 865 passed + 2 skipped**（pg_cred.txt 环境恢复后·本轮流
程中未再出现该环境问题）。零新失败。

## 9. Frozen-Component Integrity

HEAD=24082d5 未动·staging=0·Intent/C1/C2/K.26/D-08/OD-12 零触碰
（本轮零代码改动——仅重启+验证）。Planning OFF·LLM Judge OFF·
Production Authority NOT GRANTED。

## 10. S2 状态

**OPEN-UNSTARTED 保持**——Batch-2 未分发·48h 窗口未起算·S1→S2
过渡仍待 Owner 决策（本报告即其输入之一）。

## 11. Final State

```
RUNTIME-REVERIFY: PASS
:8123 = PID 33072 · HEAD 24082d5 + P2-1 + FIX2 已载入（行为证明）
S2 = OPEN-UNSTARTED · Production Authority NOT GRANTED
Next = Owner 决定 Batch-2 distribution（S2 窗口起算）
```
