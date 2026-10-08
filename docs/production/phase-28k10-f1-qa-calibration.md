# Phase 28.K.10-F1 — QA Timeout & Generation-Length Calibration

Date: 2026-09-27 · Owner 授权后实施（PART 4 提案原文执行）。

## 1. Executive Summary

- 实施了授权的最小校准：`generation.timeout_s 60→90`（单值+出处
  注记；其余零触碰）。同步了直接绑定该值的 B5.1 fixture
  （test_p28b51_calibration 预算断言——授权范围内）。
- **回归全绿**：backend **787+2 零失败**（含 B4/B6/GOV/M3/M4/HD-2/
  consumer 全量）· web **221+2** · tsc clean。质量门零放宽
  （citation/evidence/grounding/fail-closed 原样）。
- **Reliability 判定：FAIL（如实）**——复验窗口 llm_unavailable 仍
  1/3（同一"续保"问题·第 3 次顺序 QA 调用）。
- **但根因被复验彻底重新归位**（本阶段最重要的产出）：
  ①该问题**裸生成仅 16.1s 且引用门通过**；②**全新进程单独跑同一
  问题=58.4s·citation_gate_rejected**（生成正常——是引用合规 P2）；
  ③两窗口的 ~200s llm_unavailable 均发生在**窗口内第 3 次顺序 QA
  调用**=突发序列下的供应商瞬态，**与 timeout 预算无关**（60s 与
  90s 预算下同样失败）。
- 结论：预算失配假设**被证伪**；残余不可靠性归属 F2（网关 call_log
  可观测性——无法看到真实错误类）+F3（供应商侧突发降级）+F4
  （引用合规/D-04）。
- 90s 保留或回退=Owner 裁决（两读法见 §13；数据上无观察到 60-90s
  带样本，但回归无害且覆盖未采样漂移带）。

## 2. Current Configuration（实施后）

```text
generation.timeout_s = 90.0（单旋钮：同值驱动 gateway 钳制与适配器
看门狗——build_gateway 读同一 rules）· max_tokens=1024（不变）·
gateway_max_retries=1（不变）· max_regenerations=1（不变）·
最坏有界墙钟 90×2×2=360s → 诚实 llm_unavailable（保持）
```

## 3. K.9.1 Failure Evidence（对照基线）

见 phase-28k9.1：B-qa×3 = citation_gate 49.6s / insufficient 4.3s /
**llm_unavailable 177.3s**；C-long 30.6/34.8/56.2s（=旧预算 94%）。

## 4. Root Cause（复验后修正）

```text
原假设：QA 长生成 23-56s 方差 vs 60s 看门狗 → 耗尽。
复验证伪：
  · 问题定向诊断：同问题+同证据 裸 provider 调用=16.1s·引用门 PASS
  · 序列隔离诊断：全新进程首个调用=58.4s·citation_gate（生成正常）
  · 90s 预算下窗口第 3 次 QA 调用仍 ~200s 失败（与 60s 时同签名）
修正结论：llm_unavailable = 短突发序列（窗口内连续多次调用）下的
供应商瞬态降级；具体错误类 UNKNOWN（call_log=unavailable——F2 缺口
使精确归因不可能）。预算失配非根因（60→90 无效果符合此结论）。
```

## 5. Proposed→6. Authorization→7. Implementation

```text
提案=PART 4 原案；Owner 逐项授权（timeout 60→90·其余保持·质量门/
S-1/S-2/Provider/Prompt 零触碰）；实施：
  M config/qa-grounding-rules.yaml（timeout_s 90.0+F1 出处注记）
  M tests/runtime/test_p28b51_calibration.py（直接绑定 fixture：
    ==90.0·>56.2·总预算 ≤190；B6 基线无需同步——纯运行时行为，
    B6 套件回归证实）
```

## 8. Regression

```text
backend 全量 **787 passed + 2 skipped（零失败）**（含 B4 7/7·B6
10/10·GOV 11/11·M3 7/7·M4 9/9·HD-2·E-6/B-02/K.7/consumer 契约）
web **221 passed + 2 skipped** · tsc clean
未运行项：无（全量执行）
```

## 9. Stability Recheck（K.9.1 同方法·12 请求·tmp/k10-window.json）

```text
A-short×6：全 normal（2.1-3.1s）
B-qa×3：citation_gate 49.9s（ret=1·attempts=2）·insufficient 4.4s
        （ret=0）·**llm_unavailable 199.7s（P3·同第 3 调用位置）**
C-long×3：全 normal（51.0/24.5/41.6s）
定向诊断×2：裸生成 16.1s·gate PASS；隔离治理调用 58.4s·
        citation_gate
```

## 10-12. Safety / Citation / S-1 / S-2 Verification

```text
Safety=PASS（回归全绿+复验零不安全交付：全部失败方向=诚实拒答）
Citation Gate=PASS 未绕过（复验 2 例 citation_gate 拒绝=门在工作；
  未为通过率动门）
S-1=PASS（K.7 套件 16/16 含于 787）·S-2=PASS（B6/M3/规划基线全绿）
Negative=PASS（insufficient→fail-closed 复验在案：B-qa#2 4.4s）
```

## 13. Before/After Metrics

```text
                  60s（K.9.1）      90s（K.10）
llm_unavailable   1/3 QA            1/3 QA（同问题·同调用位置）→ 无改善
timeout 直接观测  0                 0
citation_gate     1                 1（+隔离诊断 1）
语料缺口拒答      1                 1
短请求            6/6·2.0-3.8s      6/6·2.1-3.1s
长生成            30.6/34.8/56.2s   51.0/24.5/41.6s（同量级）
最坏失败等待      ≤240s             ≤360s（变长——未见受益样本）
```

## 14. Remaining Risks / 15. Follow-ups

```text
F2 网关 call_log 持久化（本阶段两次诊断均因 call_log=unavailable
   无法看到真实错误类——归因瓶颈的根源）
F3 供应商侧突发降级核查（套餐/并发/时段——administrative）
F4 引用合规轨道（D-04：隔离诊断显示该问题生成正常但不过门）
风险：90s 使罕见全耗尽路径的用户等待变长（≤360s 有界+诚实失败）；
   60-90s 受益带无实测样本（保留属预防性）
```

## 16. Batch-1 Recommendation

```text
Provider=YELLOW 维持（瞬态未消除但已精确定性：突发序列触发·
非预算·非持续）→ **Batch-1=OWNER_DECISION** 维持：
  A 接受风险 GO（QA 突发窗口偶见诚实"稍后再试"；规划链健康）
  B 先 F2（可观测性）→ 精确归因 → 再裁
  C 90s 保留/回退的配置裁决（数据支持两读；回退更严格）
```

```text
Phase 28.K.10-F1 Status: COMPLETE
QA Reliability: FAIL（预算校准未改善——根因重新归位 F2/F3/F4）
Safety: PASS · Citation Gate: PASS · S-1: PASS · S-2: PASS
Provider: YELLOW
Batch-1: OWNER_DECISION
REAL_USER: 0 · Keys Distributed: 0 · Pilot Runtime: NOT STARTED
Code Changes: 2（qa-grounding-rules.yaml·test_p28b51_calibration.py）
Commit: NONE
```
