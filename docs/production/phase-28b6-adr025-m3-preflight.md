# Phase 28.B6 — ADR-025 Approval Record + M3 Planning Preflight 报告

Date: 2026-09-25 · 依据 phase-28b6-pre-audit.md（只读审计+调用链实证）。

## 1. Status

```text
PHASE STATUS: COMPLETE
```

## 2. ADR-025

```text
PROPOSED → APPROVED（2026-09-25，Phase 28.B6 Owner 批准记录）
```

- **approval scope**：治理框架（权威归属/阶段 M0..M5/开关/回滚/兼容/
  观测）+ 阶段准入方式——**各阶段仍须独立授权**，本批准≠任何阶段
  开工许可。
- **constraints**：Router Authority 保持 OFF 直至 M4；M3 另设 preflight
  门（本报告）+ 独立开工授权。
- **rollback requirement**：ADR-025 §6 回滚契约为一切切换硬前提
  （env+重启、无破坏性写、演练先行——M2 已实测）。
- 技术内容零改动（决策小节/替代方案/验证标准原样，测试钉死）；
  记录沿用 ADR Status 现有格式 + decision-freeze 追加条目——未新建
  第二套 governance 体系。

## 3. Architecture Audit（一致性审计）

```text
Intent Authority:      PASS（Intent Layer 唯一；prompt 意图段已降级；
                       LLM candidate 仅提案；demo 映射 demo-only）
Router Authority:      PASS（纯查表；decision_source 无 llm 值——schema
                       +测试双钉）
Registry Authority:    PASS（config 声明+启动 fail-closed；无 mutation
                       API；planning 条目身份就绪）
Agent Workflow Authority: PASS（planning 图归 planning agent；prompt 零
                       路由措辞——banned-token 扫描零命中+冻结哈希钉）
Execution Spine:       PASS（chat 与管线共用 orchestrator._execute_stage
                       唯一脊柱；无第二运行时）
```

禁项复核：无 LLM 直选 Agent / 无 agent 私联（生产路径）/ 前端不决
定生产 Agent（mapPromptToCase=demo 选 case；agent 模式后端分类）/
prompt 不决定分发 / demo 映射非生产权威。**Governance Drift: NONE**
（已知债务三项均显式登记：chat GATE auto-approve V0.1、planning 叙事
层无代码引用门、7 存储存量债——非新增）。

## 4. Planning Current State（完整清单，phase-28b6-pre-audit §2-3）

- **入口**：仅 legacy chat 路径（无切片；insurance_qa/product_qa 切片
  不涉 planning）。
- **Agent identity**：registry insurance-planning-agent（intents
  [insurance_plan, modify_existing_plan]、risk=high、output=
  insurance-report 契约）——身份就绪，运行时行为单元=M3 未建。
- **workflow**：8 阶段（insurance-analysis.yaml；AGENTS.md §4 冻结
  client-intake/requirement_analysis 上游）。
- **skills**：8 阶段各一 + knowledge-search；无隐藏 skill。
- **tools**：DIALOGUE 3 + STAGE 5 + QA 2（声明全集=可调用全集；stage
  工具经 orchestrator._execute_stage 走唯一脊柱；无 prompt 内嵌
  dispatch；无 frontend-only mapping）。
- **artifacts**：9 类型 contracts 契约（终产物 insurance-report）；
  eval 逐阶段 deterministic（业务 HG/结构/provenance——ADR-004/005）；
  失败→bounded repair→NEEDS_REVIEW 停轮。
- **events**：stage_*/tool_*/artifact_created/eval_*/run_*（=
  canonical EVENT_TYPES，双端契约测试在案）。

## 5. Prompt Freeze

```text
Planning prompt frozen: YES
  source: runtime/agent/prompts.py
  sha256: 193ed7da5865708ecd2dbe550d9630581a59c5299c02f8c1f4f4d1bcbaddd5bc
  （测试钉死：test_planning_prompt_frozen；变更=哈希更新+基线重采+review
   三位一体）
Router authority embedded in prompt: NO
  （banned-token 扫描零命中 + test_planning_prompt_has_no_router_authority）
  文档：docs/production/architecture/planning/PLANNING_PROMPT_FREEZE.md
```

## 6. Planning Baseline

golden corpus（tests/golden/router_cases.json，17 案）：**P 系列映射**
P1=GC-PL-G01（全链 9 产物）· P2=GC-PL-G02（缺信息 ask_user）·
P3=GC-PL-G03（歧义/防 plan→qa 漂移）· P4=**DEFERRED**（active-case 修改
被 ADR-024 数据政策 BLOCKED——解封后补采，已登记）· P5=GC-MD-G01
（无 case 修改→澄清）· P6=基线内产物 provenance 断言+叙事缺口登记 ·
P7=GC-PL-G04（no-hit 检索 fail-closed：insufficient_evidence 路径实证）·
P8=GC-PL-G05（推荐话术探针——钉住当前交付行为；叙事层代码门=已登记
缺口+M3 契约禁止）· P9=**基线 tripwire**（见下）· P10=prompt 冻结测试
+路由负向测试。

```text
golden cases: 17（B4 全 PASS / 0 RED——含 5 planning E1 案自等价）
planning baseline: 5/5 指纹采集并提交（tests/golden/planning-baseline.json：
  事件链哈希/artifact 哈希×9/eval verdict 集/risk signal 集）；
  tripwire 测试跨进程复核一致（test_planning_baseline_matches_committed）
E1 baseline status: READY（M3 候选须逐字节复现这些指纹——comparator/
  normalizer 零改动）
```

## 7. Rollback

```text
Planning flag OFF:                PASS（无 planning 切片存在=恒 legacy；
  测试证明假想 PLAN_SLICE=1/ROUTER_AUTHORITY=full env 均为惰性——权威
  不可经 env 副作用切换）
Candidate failure fallback:       PASS（模式已在 QA 切片实证：crash→
  legacy 回退+slice_error 标注，28.B4 测试常驻；M3 契约 §4 强制复用）
Router Authority OFF:             PASS（actual_execution=existing-agent
  实证）
```

## 8. Regression

```text
Backend: 713 passed / 0 failed  （before 703 + 10 preflight 新增）
Web:     148 passed / 2 skipped / 0 failed
TS:      PASS
B4:      GREEN（17/17 cases, 0 RED；报告已更新；
         tests/runtime/test_p28b4_gate.py 7/7）
```

QA/Product-QA 回归：C-1 16/16、C-2 15/15、校准 15/15 全绿（零既有
用例失败——无"与 M3 无关"式豁免）。

## 9. Scope

```text
Router Authority switched:  NO
Planning Slice enabled:     NO
M3 implementation:          NOT STARTED
Orchestrator changed:       NO（本阶段零 tracked 文件改动——git 复核）
Artifact contract changed:  NO
Grounding semantics changed: NO（gate/comparator/normalizer 零改动）
```

新增/修改面：ADR-025 Status（批准记录）· decision-freeze 追加 ·
planning/PLANNING_PROMPT_FREEZE.md + PLANNING_BOUNDARY_MATRIX.md ·
phase-28d-planning-slice-contract.md（契约 only）· router_cases.json
+3 案 · tests/golden/planning-baseline.json ·
test_p28b6_preflight.py（10 测试）· 审计+本报告。

## 10. Final Gate

```text
M3 READY FOR IMPLEMENTATION
```

条件逐项：ADR-025 approved ✓ · planning baseline established（5/5 指纹
+tripwire）✓ · prompt frozen（哈希钉死）✓ · E1 contract ready（九维
比较+复用 normalizer，基线在库）✓ · rollback verified（三态 PASS）✓ ·
regression green（713/0+148+2+tsc+B4 17/17）✓ · no governance blockers
（一致性审计全 PASS，drift NONE）✓。**仍需独立 M3 开工授权（NEXT
GATE），本阶段未跨。**

## 附：M3 实施约束速览（详见 phase-28d-planning-slice-contract.md）

flag `INSURANCE_AGENT_PLAN_SLICE` 默认 OFF · 候选异常→legacy 回退+
slice_error · E1 九维等价（基线哈希比对）· 禁：重分类意图/私路由/
编造事实/绕过证据门/隐藏运行时 · 失败矩阵全 fail-closed 到既有机制。
