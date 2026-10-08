# 28.K.28-II-DP-P2-1 · Product QA Deployment Fallback Hardening

Date: 2026-09-29 · Mode: **最小生产修复**（单 guard·复用既有机制）·
**K.28-II-DP-P2-1: PASS_WITH_FINDINGS**（目标根治+1 新 P2 记录不修）

## 1. Original Finding

DP 审计 P2-1：默认 `slices` 部署模式下 `product_qa` 切片 OFF
（28.C-2 规格默认）→ product_qa Intent 正确+Router 正确 → 落
**legacy agent 环**——无 C2/无引用门/无 Claim Support 的不受治理
产品回答。当前 pilot（full authority）不受影响；部署回退时暴露。

## 2. Reproduction Evidence（修复前·只读默认 env）

- `classify("P001的等待期是多少")` → **product_qa**；Router →
  insurance-qa-agent·registry_lookup ✓
- `authority_mode()`（默认 env）= **slices**；`governs(product_qa)`
  =False；`product_qa_slice_enabled()` 默认 **False** → `_pq_slice
  = False`
- server.py:798 注释自证 fallback：「an unexpected slice failure
  falls through to the existing agent path（fail-closed to the
  status quo）」——28.C-2 时代的 status quo=legacy 环为唯一路径，
  **属 intentional historical configuration default（Q2=配置默认+
  历史兼容行为），非 guard 缺失的意外**；DP 审计重新定性为治理缺口。
- Q3（同机制其他 intent）：**无**——insurance_qa 切片默认 ON
  （ruling D4）·planning M3 独立门·unknown 走 fallback 为设计。
  RELATED_FINDING=无新项。

## 3. Root Cause

切片门（server.py:716）：`_pq_slice = (authority_governs ∨ pq_flag)
∧ intent==product_qa ∧ …`。False 时不设防——dispatch 块仅在
`_qa_slice or _pq_slice` 时进入治理管线，否则隐式落穿到 legacy
agent worker。**缺一条「product 事实永不进非治理环」的反向守卫。**

## 4. Minimal Fix（单 guard·~30 行·server.py 切片 dispatch 前）

```python
if (intent == product_qa and not _pq_slice
        and router == insurance-qa-agent/registry_lookup
        and not clarification_required):
    self._finish_run(run_id, case_id, "run_failed", "failed",
        result_status="PRODUCT_QA_UNAVAILABLE",
        message=<内部诊断：deploy mode+flag off>,
        chat_message=<固定消费者文案：该功能暂时不可用…>,
        chat_kind="error")
    return
```

**全复用既有机制**：run-failed 终态=K.24 deadline supervisor 与
crash wrapper 同形（幂等 first-wins·单一 transcript 写入=K.27-S1
卫生边界）；固定消费者文案=K.1 惯例；result_status 为 run 级元数据
（同 RUN_DEADLINE_EXCEEDED/CRASHED 先例·非新协议）。**零新错误
协议**；guard 置于生成循环之前 → **无 regen/retry 面可绕**（P2-1-07）。

## 5. Behavior Before / After

| 场景 | 前 | 后 |
|---|---|---|
| product_qa + 切片 ON / full authority | 治理管线 | **不变**（P2-1-01/03） |
| product_qa + 切片 OFF（slices 默认） | legacy 环自由回答 | **FAIL CLOSED**（run_failed/PRODUCT_QA_UNAVAILABLE·固定文案·零 legacy delta） |
| insurance_qa + 切片 OFF | legacy | **不变**（P2-1-04·非本范围） |
| planning / unknown / invalid | 各既行为 | **不变**（P2-1-05/06） |
| legacy-valid 消息 | legacy 环 | **不变**（smoke-3 completed） |

## 6. Test Matrix（新 `tests/runtime/test_k28ii_dp_p2_1.py`·23/23）

P2-1-01 切片 ON 治理链执行 ✓·02 OFF→guard 触发+fail closed ✓·
03 pilot full-authority 不变 ✓·04 qa+OFF 不变 ✓·05 planning 不变 ✓·
06 invalid→conversation-agent 不变 ✓·07 无 retry 绕行面（guard 先于
生成·幂等终态）✓·08 治理路径矛盾主张拒答 ✓·09 支持主张交付 ✓·
10 固定文案零内部件+无 delta ✓·S1-S5 安全（普通/塞引用/免引用要求/
retry/流式——guard 恒触发或先于 segmenter）✓·legacy-valid ×2 不受
影响 ✓。

**既有契约更新（1 处·如实记录）**：`test_p28b4_gate.py::
test_gray_flag_off_records_fallback_reason` 原断言「OFF→existing-
agent/completed」——即本修复被 Owner 指令移除的行为本身；按新契约
更新（failed/PRODUCT_QA_UNAVAILABLE/**legacy provider 零输出**/
shadow flag_off 观测保留）。B4 观测契约（slice_decision 记录）不变。

## 7. Security Verification

- Runtime smoke（in-process harness·B4 模式）：pq+OFF → failed/
  PRODUCT_QA_UNAVAILABLE·**legacy-leak=False**·固定文案；
  qa+OFF → completed（保留）；generic → completed（legacy 合法路径）。
- 消费者文案正则扫描（E\d/claim/support/run_/slice/agent/intent）
  零命中（P2-1-10）；fail-closed 先于 segmenter → 无
  agent_stream_delta 可发。

## 8. Regression

- **E2E 16/16 + FI 6/6 = 22/22 PASS**（`decision_path_e2e_audit.py`
  复跑）——P2-1 修复后决策链整体不回归。
- 密封套件：Intent 12/12·C2 8/8·K.26 6/6·Claim Support 48 检查
  （26 pytest 收集项+standalone）·B4 7/7 全绿。
- **全电池 865 passed + 2 skipped**（基线保持）。

## 9. Rollback

单 guard 块还原（server.py 一处）+B4 测试期望还原——无数据迁移/
无配置变更。当前 pilot :8123（PID 25928·24082d5+FIX1）**未重启/
未载入本修复**（健康 200·未动）；载入=Owner 重启+P2-1 Reverify。

## 10. Scope Audit

Intent/C1/C2/Claim Support/K.26/Router 架构/Registry/Planning/LLM/
D-08/OD-12/baseline/shadow corpus 修改=**0**（frozen 文件 mtime
未动）；S2 **OPEN-UNSTARTED 保持**（未分发/未起算）；新 rollout
framework=0·percentage routing=0。改动=server.py 单 guard +
test_p28b4_gate.py 契约更新 + 新测试文件 + 本报告。

## 11. Remaining P2/P3（不修·记录）

- **P2-3（新发现·本阶段测试暴露）**：Claim Support 数值匹配为
  子串匹配——「免赔额为0元」被目录记录 `constraints:"10000元"` 的
  子串 `"0元"` 误判 SUPPORTED（SUBSTRING_FP）。方向=潜在 false
  support（非逃逸面：需证据恰含同尾子串）。Claim Support 冻结
  （24082d5）→ 按 §1 禁改，记录待 Owner（与 P2-2 词法天花板同族，
  修法=数值边界匹配·属独立 K.28-II-FIX2 候选）。
- P2-2 词法天花板（沿 DP）·P3-1..4（沿 DP）。
