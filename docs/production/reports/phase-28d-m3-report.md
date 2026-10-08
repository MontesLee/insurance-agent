# Phase 28.D (M3) — Planning Slice Implementation 报告

Date: 2026-09-25 · 授权：Owner M3 IMPLEMENTATION AUTHORIZATION（2026-
09-25；要求全绿后才进灰度观察——已依序执行）。契约：
docs/production/phase-28d-planning-slice-contract.md。

## 1. Status

```text
PHASE STATUS: COMPLETE（candidate implementation → E1 dual-run 等价 →
rollback verification → full regression → 灰度观察+回滚演练）
Router Authority: OFF（未提升——HARD STOP 边界未触碰）
```

## 2. Implementation（换入口不换脊柱）

- **NEW `runtime/planning_agent/`**：`planning_slice_enabled()`（
  `INSURANCE_AGENT_PLAN_SLICE` **默认 OFF**）· `guard_ok()`（契约守卫：
  已验证 IntentResult ∈ {insurance_plan, modify_existing_plan} 且无待
  澄清；失败→None→legacy 回退，绝不猜）· `run_planning_turn(intent,
  execute)`（守卫 + **挂载执行**：v1 行为=chat 工具栈挂上 planning
  registry 条目——迁移计划 §11/28.B 原文语义；脊柱异常原样传播=
  legacy 崩溃语义逐字节一致）。
- **server.py 三处增量**：切片条件（同 QA 缝；modify 带 clarification
  永不触发——M1）· slice_decision 扩到 plan 域（flag_off/fired/
  clarification_required/not_registry_lookup；actual_execution=
  insurance-planning-agent 如实）· run_agent_turn 调用点 guard 包装
  （守卫失败→legacy 回退+`slice_error=planning_guard_fallback` 标注；
  执行期异常→既有 run_failed/needs_review 语义不变）。**零新事件
  词汇、零产物类型、零 orchestrator/artifact/approval 改动**。

## 3. E1 Equivalence（真实双跑，非平凡）

golden planning 案候选侧开启 PLAN_SLICE：**B4 = GREEN 17/17，0 RED**
（docs/production/reports/router-equivalence-report.md）。**触发真实性
实证**（防平凡通过）：GC-PL-G01/G02 候选侧 `actual_execution=
insurance-planning-agent`、slice_decision fired ✓；GC-MD-G01 候选侧
不触发（clarification_required）→ legacy ✓。基线 tripwire（
planning-baseline.json 指纹）跨进程保持一致 ✓。平凡注释"no
candidate path yet"已按现实移除（测试反向断言其不存在）。

## 4. Rollback Verification

- **Flag OFF = legacy 逐字节**（E1 门 legacy 侧 + tripwire + M3 测试
  `test_slice_on_identity_and_equivalence_shape`：同输入两态结果/
  消息/事件类型完全一致）✓
- **Guard 失败回退**：monkeypatch 守卫拒绝→legacy 完成轮 +
  slice_error 标注 ✓（测试在案）
- **崩溃语义等价**：provider 崩溃两态产生相同 needs_review 降级
  （agent 环既定 fail-closed；无双跑）✓
- **回滚演练（真实服务器）**：PLAN=1 侧记录 run/intent/slice/result
  → PLAN=0 + 重启 → 同组重放：plan 轮全部 existing-agent/
  **flag_off**、正常成轮；knowledge-qa（product flag 未动）与
  unknown 均不受回滚影响 ✓

## 5. Full Regression

```text
Backend: 713 → 720 passed / 0 failed（+7 M3 slice 测试）
Web:     148 passed / 2 skipped / 0 failed
TS:      PASS
B4:      GREEN（17/17）
```

修复过程中发现并修正的两处测试基建问题（非业务缺陷）：B4 runner
BASE_OFF 未含 PLAN_SLICE（候选跑后 env 泄漏——已加入清理集）；
两个 B4/B6 断言按 M3 新现实更新（平凡注释消失；plan 域 slice_
decision 不再 None）。

## 6. Gray Observation（全绿后依授权执行；INSUFFICIENT LIVE SAMPLE——
脚本注入流量，独立实例 8106，live glm-5.3 + mock 治理知识）

| 场景 | ON 侧 | OFF 侧（回滚） |
|---|---|---|
| A 规划请求"帮我规划保险" | **plan fired**，planning agent 正确追问家庭信息（16.6s，WAITING_USER=合法规划行为） | existing-agent/flag_off，同形追问 |
| B 歧义"保险怎么买" | plan fired，COMPLETED（54.4s） | existing-agent/flag_off（46.9s） |
| C 无 case 修改"把保额调整到30万" | **不触发**（clarification_required）→legacy 澄清——**M1 live 实证** | 同（flag_off） |
| D 知识问答（隔离） | knowledge-qa fired（不受 plan flag 影响） | 同 ✓ |
| E 未知域（隔离） | legacy，sd=None | 同 ✓ |

零 slice_error；延迟=live 模型主导（8.6–54.4s），分类 0-16ms。

## 7. Architecture Impact

- One Runtime 保持：planning 行为单元=身份+守卫的挂载，无第二运行时/
  存储/注册表；路由表零改动（registry 条目早已声明）；执行脊柱/
  产物/评估/审批零触碰；grounding gate 零触碰。
- 权威链落位：insurance_plan/modify_existing_plan 现在可经 Router
  查表到 planning 行为单元（flag 门控）——**Router Authority 整体仍
  OFF**（M4 才裁决分段全量）。

## 8. Known Limitations

1. P4（active-case 修改等价）仍被 ADR-024 BLOCKED（解封后补 golden 案
   +基线）。
2. planning 叙事层无代码引用门（B6 已登记；契约 §6 禁令在位）。
3. 灰度样本=脚本注入（无真实用户流量）——INSUFFICIENT LIVE SAMPLE 维持。
4. chat 路径 GATE auto-approve（V0.1 债务，B6 登记）。

## 9. 下一步（事实性）

持续灰度（PLAN_SLICE=1 保持）积累样本 → M4 前置（ADR-025 §4：
全量权威分段 no-plan→full + demo 映射退役 + legacy 工具自选路径退役
+ M5 清理）需 Owner 授权；P4 等 ADR-024 数据政策定义。
